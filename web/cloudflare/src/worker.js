// Worker de centinela.alinedlabs.co. Cloudflare sirve las páginas estáticas sin pasar por
// aquí: solo las rutas /api/* llegan a este código (runWorkerFirst en cloudflare.config.ts).
//
// POST /api/revisar con {"texto": "..."} revisa un mensaje con el revisor de Centinela y
// Claude Haiku 5.5: las mismas instrucciones y el mismo esquema que DetectorLLM en la
// librería (src/reviewer.js se genera desde Python). La clave de la API es un secreto de
// Cloudflare y nunca llega al navegador. El texto no se guarda ni se registra.
//
// Para apagarlo: REVISION_EN_VIVO = 'apagada' en cloudflare.config.ts y `cf deploy`.
import Anthropic from '@anthropic-ai/sdk';
import { ESQUEMA, INSTRUCCIONES, TRUCOS } from './reviewer.js';

const MODELO = 'claude-haiku-5-5';
const MAX_CARACTERES = 2000;
const MAX_BYTES = 16 * 1024;
const ORIGEN = 'https://centinela.alinedlabs.co';

const CABECERAS = {
  'Content-Type': 'application/json; charset=utf-8',
  'Cache-Control': 'no-store',
  'X-Content-Type-Options': 'nosniff',
  'Content-Security-Policy': "default-src 'none'; frame-ancestors 'none'",
  'Referrer-Policy': 'no-referrer',
};

const responder = (estado, datos, extra = {}) =>
  new Response(JSON.stringify(datos), { status: estado, headers: { ...CABECERAS, ...extra } });
const error = (estado, mensaje, extra) => responder(estado, { error: mensaje }, extra);

// Igual que centinela._marcas.envolver: el mensaje va entre marcas con un id al azar, y
// cualquier marca que traiga dentro se neutraliza.
function envolver(texto, marca) {
  const limpio = texto
    .replaceAll('<mensaje_cliente', '<mensaje-cliente')
    .replaceAll('</mensaje_cliente', '</mensaje-cliente');
  return `<mensaje_cliente id="${marca}">\n${limpio}\n</mensaje_cliente id="${marca}">`;
}

const marcaAlAzar = () =>
  [...crypto.getRandomValues(new Uint8Array(4))].map((b) => b.toString(16).padStart(2, '0')).join('');

// Igual que centinela.guardia._aviso.
function aviso(ordenes, engano, trucos) {
  const partes = [];
  if (ordenes) partes.push('Trae órdenes dirigidas al asistente de IA.');
  if (engano) partes.push('Parece un engaño dirigido a una persona.');
  if (trucos.length) partes.push(`Trucos que usa: ${trucos.map((t) => TRUCOS[t]).join('; ')}.`);
  return partes.length ? partes.join(' ') : 'Sin señales de manipulación.';
}

// Si el modelo se niega o no responde bien, decide una persona (falla cerrado).
const aRevision = (motivo, tokens) => ({
  decision: 'revisar',
  aviso: `${motivo} Por precaución, lo ve una persona.`,
  ordenes_para_ia: null,
  engano_a_personas: null,
  trucos: [],
  motivo: '',
  modelo: MODELO,
  tokens,
});

async function revisar(request, env) {
  if (request.method !== 'POST') return error(405, 'Usa POST.', { Allow: 'POST' });
  if (env.REVISION_EN_VIVO !== 'activa' || !env.ANTHROPIC_API_KEY) {
    return error(503, 'La revisión en vivo con Claude está apagada. La demostración en tu navegador sigue funcionando.');
  }
  if (request.headers.get('Origin') !== ORIGEN) return error(403, 'Solo se acepta desde el sitio de Centinela.');

  // Hasta 6 revisiones por minuto por visitante y 60 en total, para cuidar el saldo.
  const ip = request.headers.get('CF-Connecting-IP') || 'sin-ip';
  const porVisitante = await env.LIMITE_VISITANTE.limit({ key: ip });
  const total = porVisitante.success ? await env.LIMITE_TOTAL.limit({ key: 'total' }) : porVisitante;
  if (!total.success) {
    return error(429, 'Demasiadas revisiones seguidas. Espera un minuto y vuelve a intentarlo.', { 'Retry-After': '60' });
  }

  if (Number(request.headers.get('Content-Length') || 0) > MAX_BYTES) {
    return error(413, `El mensaje es muy largo: máximo ${MAX_CARACTERES} caracteres.`);
  }
  let texto;
  try {
    const cuerpo = await request.text();
    if (cuerpo.length > MAX_BYTES) return error(413, `El mensaje es muy largo: máximo ${MAX_CARACTERES} caracteres.`);
    texto = JSON.parse(cuerpo)?.texto;
  } catch {
    return error(400, 'Envía un JSON con el campo «texto».');
  }
  if (typeof texto !== 'string' || !texto.trim()) return error(400, 'Escribe o pega un mensaje.');
  texto = texto.trim();
  if (texto.length > MAX_CARACTERES) return error(413, `El mensaje es muy largo: máximo ${MAX_CARACTERES} caracteres.`);

  const cliente = new Anthropic({ apiKey: env.ANTHROPIC_API_KEY, maxRetries: 1, timeout: 25_000 });
  const marca = marcaAlAzar();
  let respuesta;
  try {
    respuesta = await cliente.messages.create({
      model: MODELO,
      max_tokens: 700,
      system: INSTRUCCIONES.replaceAll('{marker}', marca),
      messages: [{ role: 'user', content: envolver(texto, marca) }],
      output_config: { effort: 'low', format: { type: 'json_schema', schema: ESQUEMA } },
    });
  } catch (e) {
    if (e instanceof Anthropic.RateLimitError) return error(503, 'Claude está ocupado. Intenta de nuevo en un minuto.');
    return error(502, 'No se pudo consultar a Claude en este momento.');
  }

  const tokens = { entrada: respuesta.usage?.input_tokens ?? null, salida: respuesta.usage?.output_tokens ?? null };
  if (respuesta.stop_reason === 'refusal') return responder(200, aRevision('El modelo se negó a revisar el mensaje.', tokens));

  let datos = null;
  try {
    datos = JSON.parse(respuesta.content.find((b) => b.type === 'text')?.text ?? '');
  } catch {
    datos = null;
  }
  if (!datos || typeof datos.ordenes_para_ia !== 'boolean') {
    return responder(200, aRevision('El revisor no devolvió una respuesta válida.', tokens));
  }

  const ordenes = datos.ordenes_para_ia;
  const engano = datos.engano_a_personas === true;
  const trucos = [...new Set(Array.isArray(datos.trucos) ? datos.trucos : [])].filter(
    (t) => typeof t === 'string' && Object.hasOwn(TRUCOS, t),
  );
  return responder(200, {
    // Como en la librería, la decisión la toma el código con las dos respuestas del modelo.
    decision: ordenes || engano ? 'revisar' : 'permitir',
    aviso: aviso(ordenes, engano, trucos),
    ordenes_para_ia: ordenes,
    engano_a_personas: engano,
    trucos: trucos.map((t) => ({ id: t, descripcion: TRUCOS[t] })),
    motivo: typeof datos.motivo === 'string' ? datos.motivo.trim().slice(0, 400) : '',
    modelo: MODELO,
    tokens,
  });
}

export default {
  async fetch(request, env) {
    const { pathname } = new URL(request.url);
    if (pathname === '/api/revisar') return revisar(request, env);
    return error(404, 'No existe.');
  },
};

import { desarmar, crearTarjeta, resolver, EJEMPLOS } from './desarmar.js';
const casos = [];
const caso = (nombre, fn) => { let ok = false; try { ok = !!fn(); } catch { ok = false; } casos.push([nombre, ok]); };

for (const [k, v] of Object.entries(EJEMPLOS)) caso(`«${k}»: no queda http:// activo`, () => !/https?:\/\//i.test(crearTarjeta(v).textoDesarmado));
caso('Phishing: el teléfono queda oculto', () => { const t = crearTarjeta(EJEMPLOS.Phishing).textoDesarmado; return t.includes('[número oculto, termina en 99]') && !t.includes('0199'); });
caso('Mensaje normal: no cambia', () => desarmar(EJEMPLOS['Mensaje normal']).texto === EJEMPLOS['Mensaje normal']);
caso('«Gracias por su compra.Es un gusto.» no es dominio', () => { const r = desarmar('Gracias por su compra.Es un gusto.'); return r.enlaces.length === 0 && r.texto === 'Gracias por su compra.Es un gusto.'; });
caso('Dominio con «а» cirílica muestra xn--', () => { const r = desarmar('Entra a b\u0430nco.example.com hoy'); return r.texto.includes('xn--') && r.enlaces[0]?.nota.includes('se ve como'); });
caso('Fecha 2026-11-30 no se oculta', () => desarmar('Vence el 2026-11-30.').texto === 'Vence el 2026-11-30.');
caso('Liberar phishing sin segunda persona → espera_segunda_persona', () => resolver(crearTarjeta(EJEMPLOS.Phishing), 'es_legitimo', { etiqueta: 'soporte', revisor: 'Ana', segundoRevisor: ' ana ' }).estado === 'espera_segunda_persona');
caso('Liberar phishing con otra persona → liberado', () => resolver(crearTarjeta(EJEMPLOS.Phishing), 'es_legitimo', { etiqueta: 'soporte', revisor: 'Ana', segundoRevisor: 'Luis' }).estado === 'liberado');

const lista = document.getElementById('pruebas');
for (const [n, ok] of casos) { const li = document.createElement('li'); li.className = ok ? 'cn-prueba--ok' : 'cn-prueba--mal'; li.textContent = n; lista.append(li); }
const bien = casos.filter((c) => c[1]).length;
document.getElementById('resumen').textContent = `${bien} de ${casos.length} pruebas pasan`;
document.documentElement.dataset.resultado = bien === casos.length ? 'ok' : 'mal';

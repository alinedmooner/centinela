import { crearTarjeta, resolver, EJEMPLOS, ETIQUETAS } from './desarmar.js';

const el = (tag, clase, texto) => { const e = document.createElement(tag); if (clase) e.className = clase; if (texto != null) e.textContent = texto; return e; };

// Resalta [.], [@], hxxp(s) y números ocultos sin usar innerHTML.
export function pintarDesarmado(destino, texto) {
  destino.replaceChildren();
  const re = /hxxps?:\/\/|\[\.\]|\[@\]|\[número oculto, termina en \d{2}\]/g;
  let ultimo = 0;
  for (const m of texto.matchAll(re)) {
    if (m.index > ultimo) destino.append(document.createTextNode(texto.slice(ultimo, m.index)));
    destino.append(el('span', 'cn-desarmado', m[0]));
    ultimo = m.index + m[0].length;
  }
  if (ultimo < texto.length) destino.append(document.createTextNode(texto.slice(ultimo)));
}

function fila(dl, rotulo, contenido) {
  const d = el('div', 'cn-cuarentena__fila');
  d.append(el('dt', 'cn-etiqueta', rotulo));
  const dd = el('dd');
  if (typeof contenido === 'string') dd.textContent = contenido; else dd.append(contenido);
  d.append(dd); dl.append(d);
}

function dibujar(salida, tarjeta) {
  salida.replaceChildren();
  const marco = el('article', 'cn-cuarentena');
  const int = el('div', 'cn-cuarentena__interior');
  const cab = el('header', 'cn-cuarentena__encabezado cn-etiqueta');
  cab.append(el('span', null, 'REVISIÓN HUMANA · mensaje en cuarentena'), el('span', null, 'SOLO LECTURA'));

  const dl = el('dl', 'cn-cuarentena__filas');
  fila(dl, 'Aviso', tarjeta.aviso);
  fila(dl, 'Dice ser', tarjeta.diceSer.length ? tarjeta.diceSer.join(' · ') : 'No se presenta.');
  fila(dl, 'Pide', tarjeta.pide.length ? tarjeta.pide.join(' · ') : 'Nada que las reglas reconozcan.');
  fila(dl, 'Presiona con', tarjeta.presionaCon.length ? tarjeta.presionaCon.join(' · ') : 'Sin presión reconocida.');
  const chips = el('div', 'cn-cuarentena__chips');
  if (!tarjeta.enlaces.length) chips.textContent = 'Ninguno.';
  tarjeta.enlaces.forEach((e) => {
    const c = el('span', 'cn-chip cn-chip--desarmado');
    pintarDesarmado(c, e.desarmado);
    chips.append(c);
    if (e.tipo === 'enlace') chips.append(el('span', 'cn-etiqueta cn-sala__dominio', `lleva a ${e.dominio}`));
    if (e.nota) chips.append(el('span', 'cn-etiqueta cn-sala__dominio', e.nota));
  });
  fila(dl, 'Enlaces y correos (desactivados)', chips);

  const rem = el('div');
  rem.append(el('span', 'cn-remitente__rotulo cn-etiqueta', 'Texto del remitente (no confiable)'));
  const caja = el('div', 'cn-remitente');
  pintarDesarmado(caja, tarjeta.textoDesarmado);
  rem.append(caja);

  const dec = el('div', 'cn-decisiones');
  const b = (accion, texto, mod) => {
    const x = el('button', `cn-boton cn-decision ${mod || ''}`);
    x.type = 'button'; x.dataset.accion = accion; x.setAttribute('aria-pressed', 'false');
    x.append(el('span', null, texto)); return x;
  };
  const bf = b('es_fraude', 'Es fraude', 'cn-decision--fraude');
  const bl = b('es_legitimo', 'Es legítimo');
  if (tarjeta.requiereSegundaPersona) bl.append(el('span', 'cn-decision__nota', 'requiere una segunda persona'));
  const bn = b('no_estoy_seguro', 'No estoy seguro');
  dec.append(bf, bl, bn);
  const nota = el('p', 'cn-sala__nota-decision cn-etiqueta', 'Ninguna decisión hace lo que pide el mensaje.');

  const form = el('form', 'cn-sala__legitimo');
  form.hidden = true; form.noValidate = true;
  const id = 'et-' + Math.random().toString(36).slice(2, 7);
  const c1 = el('div', 'cn-campo');
  const l1 = el('label', 'cn-etiqueta', 'Etiqueta (obligatoria)'); l1.htmlFor = id;
  const sel = el('select', 'cn-campo__entrada'); sel.id = id; sel.required = true;
  sel.append(new Option('Elige una etiqueta…', ''));
  ETIQUETAS.forEach((e) => sel.append(new Option(e, e)));
  c1.append(l1, sel, el('p', 'cn-sala__pista cn-etiqueta', 'Etiquetas de un negocio de ejemplo que vende por WhatsApp. Cada negocio define las suyas.'));
  form.append(c1);
  let in1, in2;
  if (tarjeta.requiereSegundaPersona) {
    const mk = (r) => { const c = el('div', 'cn-campo'); const l = el('label', 'cn-etiqueta', r); const i = el('input', 'cn-campo__entrada'); i.id = id + r.length; l.htmlFor = i.id; i.autocomplete = 'off'; c.append(l, i); form.append(c); return i; };
    in1 = mk('Quien revisa'); in2 = mk('Segunda persona');
  }
  const conf = el('button', 'cn-boton cn-boton--primario', 'Confirmar etiqueta'); conf.type = 'submit';
  form.append(conf);

  const estado = el('div', 'cn-sala__estado');
  const mostrar = (r) => {
    estado.replaceChildren();
    const s = el('p', `cn-sello cn-sello--${r.estado}`, r.estado.replace(/_/g, ' ') + (r.etiqueta ? ` · ${r.etiqueta}` : ''));
    estado.append(s, el('p', null, r.mensaje));
  };

  dec.addEventListener('click', (e) => {
    const x = e.target.closest('[data-accion]'); if (!x) return;
    dec.querySelectorAll('[data-accion]').forEach((y) => y.setAttribute('aria-pressed', String(y === x)));
    if (x.dataset.accion === 'es_legitimo') { form.hidden = false; estado.replaceChildren(); sel.focus(); return; }
    form.hidden = true;
    mostrar(resolver(tarjeta, x.dataset.accion));
  });
  form.addEventListener('submit', (e) => {
    e.preventDefault();
    mostrar(resolver(tarjeta, 'es_legitimo', { etiqueta: sel.value, revisor: in1?.value, segundoRevisor: in2?.value }));
  });

  int.append(cab, dl, rem, dec, nota, form, estado);
  marco.append(int); salida.append(marco);
}

// Revisión en vivo: el revisor de Centinela con Claude, en el Worker (POST /api/revisar).
function pintarClaude(destino, d) {
  destino.replaceChildren();
  const revisa = d.decision === 'revisar';
  const caja = el('section', `cn-claude cn-claude--${revisa ? 'revisar' : 'permitir'}`);
  const cab = el('header', 'cn-claude__encabezado cn-etiqueta');
  cab.append(el('span', null, `En vivo · ${d.modelo || 'Claude'}`), el('span', 'cn-claude__decision', revisa ? 'Va a revisión humana' : 'Puede seguir'));
  const si = (v) => (v === true ? 'Sí' : v === false ? 'No' : 'Sin respuesta');
  const dl = el('dl', 'cn-cuarentena__filas');
  fila(dl, '¿Órdenes para la IA?', si(d.ordenes_para_ia));
  fila(dl, '¿Engaño a una persona?', si(d.engano_a_personas));
  fila(dl, 'Trucos', d.trucos && d.trucos.length ? d.trucos.map((t) => t.descripcion).join(' · ') : 'Ninguno.');
  if (d.motivo) fila(dl, 'Motivo', d.motivo);
  caja.append(cab, el('p', 'cn-claude__aviso', d.aviso || ''), dl, el('p', 'cn-claude__nota cn-etiqueta', 'Claude responde las dos preguntas; la decisión la toma el código.'));
  destino.append(caja);
}

async function revisarConClaude(texto, destino, boton) {
  destino.hidden = false;
  destino.replaceChildren(el('p', 'cn-sala__vacio', 'Consultando al revisor con Claude…'));
  boton.disabled = true;
  try {
    const r = await fetch('/api/revisar', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ texto }) });
    const datos = await r.json().catch(() => ({}));
    if (!r.ok || !datos.decision) {
      destino.replaceChildren(el('p', 'cn-claude__error', datos.error || `No se pudo revisar (error ${r.status}).`));
      return;
    }
    pintarClaude(destino, datos);
  } catch {
    destino.replaceChildren(el('p', 'cn-claude__error', 'No se pudo conectar con el revisor. Intenta de nuevo.'));
  } finally {
    boton.disabled = false;
  }
}

export function iniciar(raiz) {
  const area = raiz.querySelector('textarea');
  const salida = raiz.querySelector('[data-salida]');
  const chips = raiz.querySelector('[data-ejemplos]');
  const botonClaude = raiz.querySelector('[data-claude]');
  const salidaClaude = raiz.querySelector('[data-claude-salida]');
  const ocultarClaude = () => { if (salidaClaude) { salidaClaude.hidden = true; salidaClaude.replaceChildren(); } };
  Object.keys(EJEMPLOS).forEach((k) => {
    const c = el('button', 'cn-chip', k); c.type = 'button'; c.setAttribute('aria-pressed', 'false');
    c.addEventListener('click', () => {
      chips.querySelectorAll('.cn-chip').forEach((y) => y.setAttribute('aria-pressed', String(y === c)));
      area.value = EJEMPLOS[k]; revisar();
    });
    chips.append(c);
  });
  const revisar = () => {
    ocultarClaude();
    const v = area.value.trim();
    if (!v) { salida.replaceChildren(el('p', 'cn-sala__vacio', 'Pega un mensaje o elige un ejemplo.')); return null; }
    dibujar(salida, crearTarjeta(v));
    return v;
  };
  raiz.querySelector('form').addEventListener('submit', (e) => { e.preventDefault(); revisar(); });
  if (botonClaude && salidaClaude) {
    botonClaude.addEventListener('click', () => { const v = revisar(); if (v) revisarConClaude(v, salidaClaude, botonClaude); });
  }
}

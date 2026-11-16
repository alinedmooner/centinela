import { crearTarjeta, resolver, numeroOcultoRe, EJEMPLOS, ETIQUETAS } from './desarmar.js';
import { composeNotice, reviewWithClaude } from './live.js';
import { hasKey, pageLang, t } from '../i18n/index.js';

// Plain text of the dictionary, in the language of the page.
const T = (key, fields) => t(pageLang(), key, fields);

const el = (tag, clase, texto) => { const e = document.createElement(tag); if (clase) e.className = clase; if (texto != null) e.textContent = texto; return e; };

// The messages the room shows are Spanish. On a page in another language they are marked
// as Spanish, so that a screen reader reads them with the right voice.
const marcarEspanol = (nodo) => { if (pageLang() !== 'es') nodo.lang = 'es'; return nodo; };

// The CSS still names the stamps after the old Spanish states (cn-sello--bloqueado, ...).
const SELLO = {
  blocked: 'bloqueado',
  released: 'liberado',
  escalated: 'escalado',
  awaiting_second_person: 'espera_segunda_persona',
  missing_label: 'falta_etiqueta',
  invalid: 'invalido',
};

// Highlights [.], [@], hxxp(s) and hidden numbers without using innerHTML.
export function pintarDesarmado(destino, texto) {
  destino.replaceChildren();
  const re = new RegExp(`hxxps?:\\/\\/|\\[\\.\\]|\\[@\\]|${numeroOcultoRe(pageLang())}`, 'g');
  let ultimo = 0;
  for (const m of texto.matchAll(re)) {
    if (m.index > ultimo) destino.append(document.createTextNode(texto.slice(ultimo, m.index)));
    destino.append(el('span', 'cn-desarmado', m[0]));
    ultimo = m.index + m[0].length;
  }
  if (ultimo < texto.length) destino.append(document.createTextNode(texto.slice(ultimo)));
}

function fila(dl, rotulo, contenido, textoEnEspanol = false) {
  const d = el('div', 'cn-cuarentena__fila');
  d.append(el('dt', 'cn-etiqueta', rotulo));
  const dd = el('dd');
  if (textoEnEspanol) marcarEspanol(dd);
  if (typeof contenido === 'string') dd.textContent = contenido; else dd.append(contenido);
  d.append(dd); dl.append(d);
}

// The notice of the browser card: it has no model, so it only knows the rules' two findings.
function avisoDeTarjeta(tarjeta) {
  let aviso = tarjeta.ordenesIA ? T('js.notice.ai_instructions') : T('js.card.notice_none');
  if (tarjeta.presionaCon.length) {
    const nombres = tarjeta.presionaCon.map((id) => T(`js.pressure.${id}`)).join(', ');
    aviso += ' ' + T('js.notice.tricks', { tricks: nombres });
  }
  return aviso;
}

function dibujar(salida, tarjeta) {
  salida.replaceChildren();
  const marco = el('article', 'cn-cuarentena');
  const int = el('div', 'cn-cuarentena__interior');
  const cab = el('header', 'cn-cuarentena__encabezado cn-etiqueta');
  cab.append(el('span', null, T('js.card.title')), el('span', null, T('js.card.read_only')));

  const dl = el('dl', 'cn-cuarentena__filas');
  fila(dl, T('js.card.field.notice'), avisoDeTarjeta(tarjeta));
  fila(dl, T('js.card.field.claims'), tarjeta.diceSer.length ? tarjeta.diceSer.join(' · ') : T('js.card.none.claims'), tarjeta.diceSer.length > 0);
  fila(dl, T('js.card.field.asks'), tarjeta.pide.length ? tarjeta.pide.map((id) => T(`js.ask.${id}`)).join(' · ') : T('js.card.none.asks'));
  fila(dl, T('js.card.field.pressure'), tarjeta.presionaCon.length ? tarjeta.presionaCon.map((id) => T(`js.pressure.${id}`)).join(' · ') : T('js.card.none.pressure'));
  const chips = el('div', 'cn-cuarentena__chips');
  if (!tarjeta.enlaces.length) chips.textContent = T('js.card.none.links');
  tarjeta.enlaces.forEach((e) => {
    const c = el('span', 'cn-chip cn-chip--desarmado');
    pintarDesarmado(c, e.desarmado);
    chips.append(c);
    if (e.tipo === 'link') chips.append(el('span', 'cn-etiqueta cn-sala__dominio', T('js.card.leads_to', { domain: e.dominio })));
    if (e.nota) chips.append(el('span', 'cn-etiqueta cn-sala__dominio', e.nota));
  });
  fila(dl, T('js.card.field.links'), chips);

  const rem = el('div');
  rem.append(el('span', 'cn-remitente__rotulo cn-etiqueta', T('js.card.sender_text')));
  const caja = marcarEspanol(el('div', 'cn-remitente'));
  pintarDesarmado(caja, tarjeta.textoDesarmado);
  rem.append(caja);

  const dec = el('div', 'cn-decisiones');
  for (const accion of tarjeta.acciones) {
    const x = el('button', accion === 'is_fraud' ? 'cn-boton cn-decision cn-decision--fraude' : 'cn-boton cn-decision');
    x.type = 'button'; x.dataset.accion = accion; x.setAttribute('aria-pressed', 'false');
    x.append(el('span', null, T(`js.action.${accion}`)));
    if (accion === 'is_legitimate' && tarjeta.requiereSegundaPersona) x.append(el('span', 'cn-decision__nota', T('js.card.second_person')));
    dec.append(x);
  }
  const nota = el('p', 'cn-sala__nota-decision cn-etiqueta', T('js.card.decisions_note'));

  const form = el('form', 'cn-sala__legitimo');
  form.hidden = true; form.noValidate = true;
  const id = 'et-' + Math.random().toString(36).slice(2, 7);
  const c1 = el('div', 'cn-campo');
  const l1 = el('label', 'cn-etiqueta', T('js.card.label_field')); l1.htmlFor = id;
  const sel = el('select', 'cn-campo__entrada'); sel.id = id; sel.required = true;
  sel.append(new Option(T('js.card.choose_label'), ''));
  ETIQUETAS.forEach((e) => sel.append(new Option(T(`js.label.${e}`), e)));
  c1.append(l1, sel, el('p', 'cn-sala__pista cn-etiqueta', T('js.card.label_note')));
  form.append(c1);
  let in1, in2;
  if (tarjeta.requiereSegundaPersona) {
    const mk = (rotulo, sufijo) => {
      const c = el('div', 'cn-campo'); const l = el('label', 'cn-etiqueta', rotulo); const i = el('input', 'cn-campo__entrada');
      i.id = `${id}-${sufijo}`; l.htmlFor = i.id; i.autocomplete = 'off'; c.append(l, i); form.append(c); return i;
    };
    in1 = mk(T('js.card.reviewer'), 'a'); in2 = mk(T('js.card.second_reviewer'), 'b');
  }
  const conf = el('button', 'cn-boton cn-boton--primario', T('js.card.confirm')); conf.type = 'submit';
  form.append(conf);

  const estado = el('div', 'cn-sala__estado');
  const mostrar = (r) => {
    estado.replaceChildren();
    const s = el('p', `cn-sello cn-sello--${SELLO[r.estado]}`, T(`js.state.${r.estado}`) + (r.etiqueta ? ` · ${r.etiqueta}` : ''));
    estado.append(s, el('p', null, T(`js.resolution.${r.estado}`)));
  };

  dec.addEventListener('click', (e) => {
    const x = e.target.closest('[data-accion]'); if (!x) return;
    dec.querySelectorAll('[data-accion]').forEach((y) => y.setAttribute('aria-pressed', String(y === x)));
    if (x.dataset.accion === 'is_legitimate') { form.hidden = false; estado.replaceChildren(); sel.focus(); return; }
    form.hidden = true;
    mostrar(resolver(tarjeta, x.dataset.accion));
  });
  form.addEventListener('submit', (e) => {
    e.preventDefault();
    mostrar(resolver(tarjeta, 'is_legitimate', { etiqueta: sel.value, revisor: in1?.value, segundoRevisor: in2?.value }));
  });

  int.append(cab, dl, rem, dec, nota, form, estado);
  marco.append(int); salida.append(marco);
}

// Live review: Centinela's reviewer with Claude, in the Worker (POST /api/review). The button
// is only rendered while LIVE_REVIEW_ENABLED (src/config.js) is true.
function pintarClaude(destino, d) {
  destino.replaceChildren();
  const revisa = d.decision === 'review';
  // The CSS still names the two outcomes in Spanish (cn-claude--revisar, cn-claude--permitir).
  const caja = el('section', `cn-claude cn-claude--${revisa ? 'revisar' : 'permitir'}`);
  const cab = el('header', 'cn-claude__encabezado cn-etiqueta');
  cab.append(
    el('span', null, T('js.live.header', { model: d.model || 'Claude' })),
    el('span', 'cn-claude__decision', T(revisa ? 'js.live.decision.review' : 'js.live.decision.allow')),
  );
  const si = (v) => (v === true ? T('js.live.yes') : v === false ? T('js.live.no') : T('js.live.no_answer'));
  const trucos = (d.tricks ?? []).filter((id) => hasKey(pageLang(), `js.trick.${id}`));
  const dl = el('dl', 'cn-cuarentena__filas');
  fila(dl, T('js.live.q_ai'), si(d.ai_instructions));
  fila(dl, T('js.live.q_people'), si(d.people_deception));
  fila(dl, T('js.live.tricks'), trucos.length ? trucos.map((id) => T(`js.trick.${id}`)).join(' · ') : T('js.live.none'));
  if (d.reason) {
    // The model writes the reason in Spanish; it is shown as it comes, with a caption.
    const motivo = el('div');
    motivo.append(marcarEspanol(el('p', null, d.reason)), el('p', 'cn-etiqueta cn-sala__pista', T('js.live.reason_caption')));
    fila(dl, T('js.live.reason'), motivo);
  }
  caja.append(
    cab,
    el('p', 'cn-claude__aviso', composeNotice(d, pageLang())),
    dl,
    el('p', 'cn-claude__nota cn-etiqueta', T('js.live.note')),
  );
  destino.append(caja);
}

async function revisarConClaude(texto, destino, boton) {
  destino.hidden = false;
  destino.replaceChildren(el('p', 'cn-sala__vacio', T('js.live.consulting')));
  boton.disabled = true;
  try {
    const r = await reviewWithClaude(texto, pageLang());
    if (r.ok) pintarClaude(destino, r.review);
    else destino.replaceChildren(el('p', 'cn-claude__error', r.message));
  } catch {
    destino.replaceChildren(el('p', 'cn-claude__error', T('js.live.error.network')));
  } finally {
    boton.disabled = false;
  }
}

export function iniciar(raiz) {
  const area = raiz.querySelector('textarea');
  const salida = raiz.querySelector('[data-salida]');
  const chips = raiz.querySelector('[data-ejemplos]');
  const glosa = raiz.querySelector('[data-gloss]');
  const botonClaude = raiz.querySelector('[data-claude]');
  const salidaClaude = raiz.querySelector('[data-claude-salida]');
  const ocultarClaude = () => { if (salidaClaude) { salidaClaude.hidden = true; salidaClaude.replaceChildren(); } };
  // The English gloss of the chosen example; empty (and hidden) in Spanish and once the text is edited.
  const mostrarGlosa = (ejemplo) => {
    if (!glosa) return;
    const texto = ejemplo ? T(`js.example.${ejemplo}.gloss`) : '';
    glosa.textContent = texto;
    glosa.hidden = !texto;
  };
  Object.keys(EJEMPLOS).forEach((ejemplo) => {
    const c = el('button', 'cn-chip', T(`js.example.${ejemplo}.name`)); c.type = 'button'; c.setAttribute('aria-pressed', 'false');
    c.addEventListener('click', () => {
      chips.querySelectorAll('.cn-chip').forEach((y) => y.setAttribute('aria-pressed', String(y === c)));
      area.value = EJEMPLOS[ejemplo]; mostrarGlosa(ejemplo); revisar();
    });
    chips.append(c);
  });
  area.addEventListener('input', () => mostrarGlosa(null));
  const revisar = () => {
    ocultarClaude();
    const v = area.value.trim();
    if (!v) { salida.replaceChildren(el('p', 'cn-sala__vacio', T('js.room.empty'))); return null; }
    dibujar(salida, crearTarjeta(v, pageLang()));
    return v;
  };
  raiz.querySelector('form').addEventListener('submit', (e) => { e.preventDefault(); revisar(); });
  if (botonClaude && salidaClaude) {
    botonClaude.addEventListener('click', () => { const v = revisar(); if (v) revisarConClaude(v, salidaClaude, botonClaude); });
  }
}

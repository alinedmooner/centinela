import { desarmar, crearTarjeta, resolver, EJEMPLOS } from './desarmar.js';
import { pageLang, t } from '../i18n/index.js';

const lang = pageLang();
const T = (key, fields) => t(lang, key, fields);

const casos = [];
const caso = (nombre, fn) => { let ok = false; try { ok = !!fn(); } catch { ok = false; } casos.push([nombre, ok]); };

for (const [id, texto] of Object.entries(EJEMPLOS)) {
  caso(T('js.tests.no_active_link', { name: T(`js.example.${id}.name`) }), () => !/https?:\/\//i.test(crearTarjeta(texto, lang).textoDesarmado));
}
caso(T('js.tests.phone_hidden'), () => {
  const tx = crearTarjeta(EJEMPLOS.phishing, lang).textoDesarmado;
  return tx.includes(T('js.defang.hidden_number', { digits: '99' })) && !tx.includes('0199');
});
caso(T('js.tests.normal_unchanged'), () => desarmar(EJEMPLOS.normal, lang).texto === EJEMPLOS.normal);
caso(T('js.tests.not_a_domain'), () => { const r = desarmar('Gracias por su compra.Es un gusto.', lang); return r.enlaces.length === 0 && r.texto === 'Gracias por su compra.Es un gusto.'; });
caso(T('js.tests.cyrillic'), () => {
  const r = desarmar('Entra a bаnco.example.com hoy', lang);
  return r.texto.includes('xn--') && r.enlaces[0]?.nota === T('js.defang.looks_like', { domain: 'bаnco.example.com' });
});
caso(T('js.tests.date'), () => desarmar('Vence el 2026-11-30.', lang).texto === 'Vence el 2026-11-30.');
caso(T('js.tests.second_person_needed', { state: 'awaiting_second_person' }), () => resolver(crearTarjeta(EJEMPLOS.phishing, lang), 'is_legitimate', { etiqueta: 'soporte', revisor: 'Ana', segundoRevisor: ' ana ' }).estado === 'awaiting_second_person');
caso(T('js.tests.second_person_ok', { state: 'released' }), () => resolver(crearTarjeta(EJEMPLOS.phishing, lang), 'is_legitimate', { etiqueta: 'soporte', revisor: 'Ana', segundoRevisor: 'Luis' }).estado === 'released');

const lista = document.getElementById('pruebas');
for (const [n, ok] of casos) { const li = document.createElement('li'); li.className = ok ? 'cn-prueba--ok' : 'cn-prueba--mal'; li.textContent = n; lista.append(li); }
const bien = casos.filter((c) => c[1]).length;
document.getElementById('resumen').textContent = T('js.tests.summary', { passed: bien, total: casos.length });
document.documentElement.dataset.resultado = bien === casos.length ? 'ok' : 'mal';

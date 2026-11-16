import { pageLang, t } from '../i18n/index.js';

const hex = (s) => { const m = s.trim().match(/^#([0-9a-f]{6})$/i); return m ? [0, 2, 4].map((i) => parseInt(m[1].slice(i, i + 2), 16)) : null; };
const lum = ([r, g, b]) => { const c = [r, g, b].map((v) => { v /= 255; return v <= .03928 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4; }); return .2126 * c[0] + .7152 * c[1] + .0722 * c[2]; };
export const contraste = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + .05) / (y + .05); };
// The ratio with the decimal separator of the page's language: 12.34:1 or 12,34:1.
const fmt = (n) => n.toLocaleString(pageLang(), { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ':1';
const T = (key, fields) => t(pageLang(), key, fields);

export function iniciar(raiz = document) {
  const negro = hex('#050505'), papel = hex('#F6F4EE');
  raiz.querySelectorAll('[data-muestra]').forEach((li) => {
    const rgb = hex(li.dataset.valor); if (!rgb) return;
    li.querySelector('[data-negro]').textContent = T('js.contrast.black', { ratio: fmt(contraste(rgb, negro)) });
    li.querySelector('[data-papel]').textContent = T('js.contrast.paper', { ratio: fmt(contraste(rgb, papel)) });
  });
  const demo = raiz.querySelector('[data-demo-mov]'), btn = raiz.querySelector('[data-demo-btn]');
  if (demo && btn) btn.addEventListener('click', () => {
    const on = demo.classList.toggle('cn-demo-mov--activa');
    btn.setAttribute('aria-pressed', String(on)); btn.textContent = on ? T('js.demo.stop') : T('js.demo.play');
  });
  raiz.querySelectorAll('[data-copiar]').forEach((b) => b.addEventListener('click', async () => {
    try { await navigator.clipboard.writeText(document.getElementById(b.dataset.copiar).textContent); b.textContent = T('js.copy.done'); } catch { b.textContent = T('js.copy.manual'); }
    setTimeout(() => { b.textContent = T('js.copy.label'); }, 1800);
  }));
}
iniciar();

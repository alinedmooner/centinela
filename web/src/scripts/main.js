import { iniciar as iniciarHero } from './hero.js';
import { iniciar as iniciarSala } from './sala.js';
import { pageLang, t } from '../i18n/index.js';

const T = (key) => t(pageLang(), key);

const CLAVE = 'centinela:pausar-movimiento';
const leer = () => { try { return localStorage.getItem(CLAVE) === '1'; } catch { return false; } };
const guardar = (v) => { try { localStorage.setItem(CLAVE, v ? '1' : '0'); } catch { /* no storage available */ } };

export const movimientoReducido = () =>
  matchMedia('(prefers-reduced-motion: reduce)').matches || document.documentElement.classList.contains('cn-sin-movimiento');

function iniciarPausa(raiz) {
  const html = document.documentElement;
  const botones = raiz.querySelectorAll('[data-pausar]');
  const aplicar = (v) => {
    html.classList.toggle('cn-sin-movimiento', v);
    botones.forEach((b) => {
      b.setAttribute('aria-pressed', String(v));
      const texto = b.querySelector('.cn-nav__pausa-texto');
      if (texto) texto.textContent = v ? T('js.nav.resume') : T('js.nav.pause');
    });
    document.dispatchEvent(new CustomEvent('cn:movimiento', { detail: { pausado: v } }));
  };
  aplicar(leer());
  botones.forEach((b) => b.addEventListener('click', () => { const v = !html.classList.contains('cn-sin-movimiento'); guardar(v); aplicar(v); }));
}

function iniciarNav(raiz) {
  const nav = raiz.querySelector('.cn-nav');
  if (!nav) return;
  const alScroll = () => nav.classList.toggle('cn-nav--compacta', scrollY > 24);
  addEventListener('scroll', alScroll, { passive: true }); alScroll();
  const boton = nav.querySelector('.cn-nav__menu');
  const lista = nav.querySelector('.cn-nav__lista');
  if (boton && lista) {
    const cerrar = () => { boton.setAttribute('aria-expanded', 'false'); lista.classList.remove('cn-nav__lista--abierta'); };
    boton.addEventListener('click', () => {
      const abierto = boton.getAttribute('aria-expanded') === 'true';
      boton.setAttribute('aria-expanded', String(!abierto));
      lista.classList.toggle('cn-nav__lista--abierta', !abierto);
    });
    lista.addEventListener('click', (e) => { if (e.target.closest('a')) cerrar(); });
    addEventListener('keydown', (e) => { if (e.key === 'Escape') cerrar(); });
  }
  const enlaces = [...nav.querySelectorAll('.cn-nav__lista a[href^="#"]')];
  const io = new IntersectionObserver((es) => es.forEach((e) => {
    if (e.isIntersecting) enlaces.forEach((a) => a.setAttribute('aria-current', String(a.getAttribute('href') === '#' + e.target.id)));
  }), { rootMargin: '-45% 0px -50% 0px' });
  enlaces.forEach((a) => { const s = document.querySelector(a.getAttribute('href')); if (s) io.observe(s); });
}

function iniciarAparicion(raiz) {
  const els = raiz.querySelectorAll('.cn-aparece');
  if (!('IntersectionObserver' in window)) { els.forEach((e) => e.classList.add('cn-aparece--visible')); return; }
  const io = new IntersectionObserver((es) => es.forEach((e) => {
    if (e.isIntersecting) { e.target.classList.add('cn-aparece--visible'); io.unobserve(e.target); }
  }), { threshold: .12 });
  els.forEach((e) => io.observe(e));
}

function iniciarCopiar(raiz) {
  raiz.querySelectorAll('[data-copiar]').forEach((b) => b.addEventListener('click', async () => {
    const fuente = document.getElementById(b.dataset.copiar);
    const texto = fuente ? fuente.textContent : '';
    try { await navigator.clipboard.writeText(texto); b.textContent = T('js.copy.done'); }
    catch { b.textContent = T('js.copy.manual'); }
    setTimeout(() => { b.textContent = T('js.copy.label'); }, 1800);
  }));
}

export function iniciar(raiz = document) {
  iniciarPausa(raiz); iniciarNav(raiz); iniciarAparicion(raiz); iniciarCopiar(raiz);
  const hero = raiz.querySelector('[data-bandeja]'); if (hero) iniciarHero(hero);
  const sala = raiz.querySelector('[data-sala]'); if (sala) iniciarSala(sala);
}
iniciar();

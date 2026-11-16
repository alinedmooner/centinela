// URLs of the pages in each language. Only for Astro (it imports astro:i18n), unlike index.js.
//
// English lives at the root and Spanish under /es/ (see i18n in astro.config.mjs):
//   home    /          /es/
//   system  /sistema/  /es/sistema/
//   tests   /pruebas/  /es/pruebas/
import { getRelativeLocaleUrl } from 'astro:i18n';
import { DEFAULT_LANG, LANGS } from './index.js';

// A route is the page without its language: the path that follows the language prefix.
export const ROUTES = { home: '/', system: 'sistema/', tests: 'pruebas/' };

/** The path of ``route`` in ``lang``, for example pathFor('es', 'system') is /es/sistema/. */
export const pathFor = (lang, route) => getRelativeLocaleUrl(lang, ROUTES[route]);

/**
 * What getStaticPaths returns for a page that exists once per language: English with no
 * parameter (so it sits at the root) and every other language under its code.
 */
export const localePaths = () =>
  LANGS.map((lang) => ({ params: { lang: lang === DEFAULT_LANG ? undefined : lang }, props: { lang } }));

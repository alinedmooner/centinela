// The site's texts in two languages, and the helper that reads them.
//
// en.json and es.json have flat dotted keys and the same keys in both languages
// (tests/test_web_i18n.py checks it). A value is a string. Markup is allowed in the values
// the pages write with set:html; the values under "js." are plain text, because the scripts
// write them with textContent. A code snippet is a list of lines, joined with newlines.
// A missing key throws, so a page that asks for a text nobody wrote fails the build.
//
// No Astro and no DOM code here: the build, the browser scripts and the Node tests import it.
import en from './en.json' with { type: 'json' };
import es from './es.json' with { type: 'json' };

export const LANGS = ['en', 'es'];
export const DEFAULT_LANG = 'en';

const DICTIONARIES = { en, es };

/** Whether ``lang`` has a text for ``key``. The scripts use it for ids that come from a server. */
export function hasKey(lang, key) {
  return Object.hasOwn(DICTIONARIES[lang] ?? {}, key);
}

/**
 * The text for ``key`` in ``lang``, with ``{field}`` placeholders filled from ``fields``.
 * Without ``fields`` the text is returned as it is (code snippets contain braces).
 */
export function t(lang, key, fields) {
  const dictionary = DICTIONARIES[lang];
  if (!dictionary) throw new Error(`Unknown language "${lang}"; use one of ${LANGS.join(', ')}`);
  if (!Object.hasOwn(dictionary, key)) throw new Error(`Missing translation: "${key}" in "${lang}"`);
  const value = dictionary[key];
  const text = Array.isArray(value) ? value.join('\n') : value;
  if (!fields) return text;
  return text.replace(/\{(\w+)\}/g, (_, name) => {
    if (!Object.hasOwn(fields, name)) throw new Error(`Missing field "${name}" for "${key}" in "${lang}"`);
    return String(fields[name]);
  });
}

/** The language of the page the script runs in: its <html lang>. */
export function pageLang(root = globalThis.document?.documentElement) {
  return root?.lang === 'es' ? 'es' : DEFAULT_LANG;
}

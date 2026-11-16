// @ts-check
import { defineConfig } from 'astro/config';

// The browser scripts (src/scripts/*.js) only read the "js." texts of the dictionaries, but they
// import the whole files. This keeps the page copy out of the code that is sent to the browser:
// in the client build, en.json and es.json only keep the keys that start with "js.". The pages
// are rendered at build time and still see everything.
/** @type {import('vite').Plugin} */
const onlyScriptTexts = {
  name: 'centinela:script-texts-only',
  enforce: 'pre',
  transform(code, id) {
    if (this.environment?.name !== 'client') return null;
    if (!/[\\/]src[\\/]i18n[\\/](en|es)\.json$/.test(id.split('?')[0])) return null;
    const kept = Object.entries(JSON.parse(code)).filter(([key]) => key.startsWith('js.'));
    return { code: JSON.stringify(Object.fromEntries(kept)), map: null };
  },
};

// Static site: it needs no adapter.
export default defineConfig({
  site: 'https://centinela.alinedlabs.co',
  // English at the root and Spanish under /es/. The pages are src/pages/[...lang]/*.astro and
  // say which language they are in getStaticPaths; src/i18n/{en,es}.json hold the texts.
  i18n: {
    defaultLocale: 'en',
    locales: ['en', 'es'],
    routing: { prefixDefaultLocale: false },
  },
  build: {
    // All the CSS goes in files, with no inline <style>, so that the CSP can be strict.
    inlineStylesheets: 'never',
  },
  vite: {
    plugins: [onlyScriptTexts],
    build: {
      // The same with the scripts: never inline.
      assetsInlineLimit: 0,
    },
  },
});

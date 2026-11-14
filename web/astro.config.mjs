// @ts-check
import { defineConfig } from 'astro/config';

// Sitio estático: no necesita adaptador.
export default defineConfig({
  site: 'https://centinela.alinedlabs.co',
  build: {
    // Todo el CSS va en archivos, sin <style> en línea, para poder usar una CSP estricta.
    inlineStylesheets: 'never',
  },
  vite: {
    build: {
      // Lo mismo con los scripts: nunca en línea.
      assetsInlineLimit: 0,
    },
  },
});

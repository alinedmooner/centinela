// Worker de Cloudflare que sirve el sitio estático en centinela.alinedlabs.co.
import { defineConfig } from 'cf/config';

export default defineConfig({
  worker: {
    name: 'centinela-web',
    compatibilityDate: '2026-11-14',
    assets: {
      // /sistema y /sistema/ llevan a la misma página; lo que no existe muestra 404.html.
      htmlHandling: 'auto-trailing-slash',
      notFoundHandling: '404-page',
    },
    domains: ['centinela.alinedlabs.co'],
  },
});

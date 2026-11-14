// Worker de Cloudflare del sitio centinela.alinedlabs.co: las páginas estáticas y la
// revisión en vivo con Claude en /api/revisar (src/worker.js).
import { bindings, defineConfig } from 'cf/config';

export default defineConfig({
  worker: {
    name: 'centinela-web',
    compatibilityDate: '2026-11-14',
    entrypoint: './src/worker.js',
    env: {
      // Se sube con `cf deploy --secrets-file`; nunca va en el código ni en el navegador.
      ANTHROPIC_API_KEY: bindings.secret(),
      // 'activa' o 'apagada'. Después de la presentación: 'apagada' y `cf deploy`.
      REVISION_EN_VIVO: bindings.text('activa'),
      // Límites por ubicación de Cloudflare, para cuidar el saldo de la API.
      LIMITE_VISITANTE: bindings.rateLimit({ namespace: '4101', simple: { limit: 6, period: 60 } }),
      LIMITE_TOTAL: bindings.rateLimit({ namespace: '4102', simple: { limit: 60, period: 60 } }),
    },
    assets: {
      // /sistema y /sistema/ llevan a la misma página; lo que no existe muestra 404.html.
      htmlHandling: 'auto-trailing-slash',
      notFoundHandling: '404-page',
      // Solo la API pasa por el Worker; el resto lo sirve Cloudflare directo.
      runWorkerFirst: ['/api/*'],
    },
    domains: ['centinela.alinedlabs.co'],
  },
});

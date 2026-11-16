// Cloudflare Worker of the site centinela.alinedlabs.co: the static pages and the live review
// with Claude at /api/review (src/worker.js).
import { bindings, defineConfig } from 'cf/config';

export default defineConfig({
  worker: {
    name: 'centinela-web',
    compatibilityDate: '2026-11-14',
    entrypoint: './src/worker.js',
    env: {
      // Uploaded with `cf deploy --secrets-file`; it is never in the code or in the browser.
      ANTHROPIC_API_KEY: bindings.secret(),
      // 'on' or 'off'. Off since the end of the hackathon (2026-11-16): every review spends API
      // balance. To turn it back on: 'on' and `cf deploy --secrets-file`, and set
      // LIVE_REVIEW_ENABLED to true in web/src/config.js so that the page shows the button.
      LIVE_REVIEW: bindings.text('off'),
      // Limits for each Cloudflare location, to look after the API balance.
      LIMIT_VISITOR: bindings.rateLimit({ namespace: '4101', simple: { limit: 6, period: 60 } }),
      LIMIT_TOTAL: bindings.rateLimit({ namespace: '4102', simple: { limit: 60, period: 60 } }),
    },
    assets: {
      // /sistema and /sistema/ lead to the same page; what does not exist shows 404.html (one
      // page, in both languages).
      htmlHandling: 'auto-trailing-slash',
      notFoundHandling: '404-page',
      // Only the API goes through the Worker; Cloudflare serves the rest directly.
      runWorkerFirst: ['/api/*'],
    },
    domains: ['centinela.alinedlabs.co'],
  },
});

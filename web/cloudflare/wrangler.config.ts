// Ajustes de compilación para Cloudflare: el sitio es estático y ya está compilado
// en ../dist (lo genera `pnpm build` en web/). El CLI `cf` lo publica con Wrangler.
import { defineWranglerConfig } from 'wrangler/experimental-config';

export default defineWranglerConfig({
  assetsDirectory: '../dist',
});

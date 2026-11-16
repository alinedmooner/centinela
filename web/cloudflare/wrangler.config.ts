// Build settings for Cloudflare: the site is static and already built in ../dist (`pnpm build`
// in web/ generates it). The `cf` CLI publishes it with Wrangler.
import { defineWranglerConfig } from 'wrangler/experimental-config';

export default defineWranglerConfig({
  assetsDirectory: '../dist',
});

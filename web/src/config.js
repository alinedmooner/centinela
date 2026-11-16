// Build-time switches of the site.

// The "Review with Claude, live" button of the review room, and the note about it.
//
// The Worker (cloudflare/src/worker.js) answers POST /api/review only while its LIVE_REVIEW
// variable is 'on'. While this constant is false the button is not rendered, in either
// language, so nobody meets a button that does nothing. The code that talks to the Worker
// stays (src/scripts/live.js and sala.js): turning the review back on is changing this to
// true, setting LIVE_REVIEW to 'on' in cloudflare/cloudflare.config.ts and publishing.
export const LIVE_REVIEW_ENABLED = false;

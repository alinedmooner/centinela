// Client of the live review: POST /api/review on the Worker (cloudflare/src/worker.js).
//
// The Worker answers with ids and flags, never with display text:
//   200 {decision, ai_instructions, people_deception, tricks: [ids], reason, model, tokens,
//        fallback}                       (fallback: null, 'refusal' or 'invalid')
//   4xx/5xx {error: {code}}              (a code from SERVER_ERRORS)
// This file writes the notice and the error messages in the page's language, from the
// dictionaries (js.notice.*, js.trick.*, js.live.error.*).
import { hasKey, t } from '../i18n/index.js';

export const ENDPOINT = '/api/review';

// The error codes the Worker can answer with.
export const SERVER_ERRORS = [
  'off', 'origin', 'method', 'too_long', 'bad_request', 'empty', 'rate_limited', 'busy', 'upstream', 'not_found',
];

/**
 * The notice a person reads, composed like Python's Guard does it (centinela.guard._notice)
 * from the flags and the trick ids of the review. A review that fell back (the model refused
 * or answered badly) has its own notice: the code sent it to a person as a precaution.
 */
export function composeNotice(review, lang) {
  if (review.fallback) {
    const key = `js.notice.fallback.${review.fallback}`;
    return t(lang, hasKey(lang, key) ? key : 'js.notice.fallback.invalid');
  }
  const parts = [];
  if (review.ai_instructions) parts.push(t(lang, 'js.notice.ai_instructions'));
  if (review.people_deception) parts.push(t(lang, 'js.notice.deception'));
  const tricks = (review.tricks ?? []).filter((id) => hasKey(lang, `js.trick.${id}`));
  if (tricks.length) {
    const names = tricks.map((id) => t(lang, `js.trick.${id}`)).join('; ');
    parts.push(t(lang, 'js.notice.tricks', { tricks: names }));
  }
  return parts.length ? parts.join(' ') : t(lang, 'js.notice.none');
}

/** The message for an error code of the Worker; any other code gets the generic one. */
export function errorMessage(code, status, lang) {
  if (SERVER_ERRORS.includes(code)) return t(lang, `js.live.error.${code}`);
  return t(lang, 'js.live.error.generic', { status });
}

/**
 * Ask the Worker for a review. Resolves to {ok: true, review} or {ok: false, message},
 * with the message in ``lang``. It never rejects.
 */
export async function reviewWithClaude(text, lang, fetchFn = globalThis.fetch) {
  let response;
  try {
    response = await fetchFn(ENDPOINT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, lang }),
    });
  } catch {
    return { ok: false, message: t(lang, 'js.live.error.network') };
  }
  const data = await response.json().catch(() => null);
  if (!response.ok || !data || !data.decision) {
    return { ok: false, message: errorMessage(data?.error?.code, response.status, lang) };
  }
  return { ok: true, review: data };
}

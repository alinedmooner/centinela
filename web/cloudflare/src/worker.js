// Worker of centinela.alinedlabs.co. Cloudflare serves the static pages without going through
// here: only the /api/* routes reach this code (runWorkerFirst in cloudflare.config.ts).
//
// POST /api/review with {"text": "...", "lang": "en" | "es"} reviews a message with Centinela's
// reviewer and Claude Haiku 5.5: the same instructions and the same schema as LLMDetector in the
// library (src/reviewer.js is generated from Python and is Spanish on purpose: it is what the
// measurements were made with). The decision is made here, in code, from the model's two
// answers, as in the library. The Worker answers with ids and flags and no text for people: the
// page writes the notice in its language from its dictionary (src/i18n). `lang` is checked but
// does not change the review. The API key is a Cloudflare secret and never reaches the browser.
// The text is not stored or logged.
//
// 200 {decision: "review" | "allow", ai_instructions, people_deception, tricks: [ids], reason,
//      model, tokens: {input, output}, fallback: null | "refusal" | "invalid"}
//     A refusal or an invalid answer is "review" with both flags null and the fallback's
//     name: it fails closed, a person decides.
// Errors: the HTTP status and {"error": {"code": ...}}, where the code is one of
//     off 503, origin 403, method 405, too_long 413, bad_request 400, empty 400,
//     rate_limited 429, busy 503, upstream 502, not_found 404.
//
// To switch it off: LIVE_REVIEW = 'off' in cloudflare.config.ts and `cf deploy`.
import Anthropic from '@anthropic-ai/sdk';
import { ESQUEMA, INSTRUCCIONES, TRUCOS } from './reviewer.js';

const MODEL = 'claude-haiku-5-5';
const MAX_CHARS = 2000;
const MAX_BYTES = 16 * 1024;
const ORIGIN = 'https://centinela.alinedlabs.co';
const LANGS = ['en', 'es'];

const HEADERS = {
  'Content-Type': 'application/json; charset=utf-8',
  'Cache-Control': 'no-store',
  'X-Content-Type-Options': 'nosniff',
  'Content-Security-Policy': "default-src 'none'; frame-ancestors 'none'",
  'Referrer-Policy': 'no-referrer',
};

const respond = (status, data, extra = {}) =>
  new Response(JSON.stringify(data), { status, headers: { ...HEADERS, ...extra } });
const fail = (status, code, extra) => respond(status, { error: { code } }, extra);

// Like centinela._markers.wrap: the message goes between markers with a random id, and any
// marker it carries inside is neutralized.
function wrap(text, marker) {
  const clean = text
    .replaceAll('<mensaje_cliente', '<mensaje-cliente')
    .replaceAll('</mensaje_cliente', '</mensaje-cliente');
  return `<mensaje_cliente id="${marker}">\n${clean}\n</mensaje_cliente id="${marker}">`;
}

const randomMarker = () =>
  [...crypto.getRandomValues(new Uint8Array(4))].map((b) => b.toString(16).padStart(2, '0')).join('');

// If the model refuses or does not answer well, a person decides (it fails closed).
const toReview = (fallback, tokens) => ({
  decision: 'review',
  ai_instructions: null,
  people_deception: null,
  tricks: [],
  reason: '',
  model: MODEL,
  tokens,
  fallback,
});

async function review(request, env) {
  if (request.method !== 'POST') return fail(405, 'method', { Allow: 'POST' });
  if (env.LIVE_REVIEW !== 'on' || !env.ANTHROPIC_API_KEY) return fail(503, 'off');
  if (request.headers.get('Origin') !== ORIGIN) return fail(403, 'origin');

  // At most 6 reviews a minute for each visitor and 60 in total, to look after the balance.
  const ip = request.headers.get('CF-Connecting-IP') || 'no-ip';
  const perVisitor = await env.LIMIT_VISITOR.limit({ key: ip });
  const overall = perVisitor.success ? await env.LIMIT_TOTAL.limit({ key: 'total' }) : perVisitor;
  if (!overall.success) return fail(429, 'rate_limited', { 'Retry-After': '60' });

  if (Number(request.headers.get('Content-Length') || 0) > MAX_BYTES) return fail(413, 'too_long');
  let body;
  try {
    const raw = await request.text();
    if (raw.length > MAX_BYTES) return fail(413, 'too_long');
    body = JSON.parse(raw);
  } catch {
    return fail(400, 'bad_request');
  }
  if (body === null || typeof body !== 'object' || typeof body.text !== 'string') return fail(400, 'bad_request');
  if (body.lang !== undefined && !LANGS.includes(body.lang)) return fail(400, 'bad_request');
  const text = body.text.trim();
  if (!text) return fail(400, 'empty');
  if (text.length > MAX_CHARS) return fail(413, 'too_long');

  const client = new Anthropic({ apiKey: env.ANTHROPIC_API_KEY, maxRetries: 1, timeout: 25_000 });
  const marker = randomMarker();
  let response;
  try {
    response = await client.messages.create({
      model: MODEL,
      max_tokens: 700,
      system: INSTRUCCIONES.replaceAll('{marker}', marker),
      messages: [{ role: 'user', content: wrap(text, marker) }],
      output_config: { effort: 'low', format: { type: 'json_schema', schema: ESQUEMA } },
    });
  } catch (e) {
    if (e instanceof Anthropic.RateLimitError) return fail(503, 'busy');
    return fail(502, 'upstream');
  }

  const tokens = { input: response.usage?.input_tokens ?? null, output: response.usage?.output_tokens ?? null };
  if (response.stop_reason === 'refusal') return respond(200, toReview('refusal', tokens));

  // The keys of the model's JSON are Spanish: they are in the schema it answers with.
  let data = null;
  try {
    data = JSON.parse(response.content.find((b) => b.type === 'text')?.text ?? '');
  } catch {
    data = null;
  }
  if (!data || typeof data.ordenes_para_ia !== 'boolean') return respond(200, toReview('invalid', tokens));

  const aiInstructions = data.ordenes_para_ia;
  const peopleDeception = data.engano_a_personas === true;
  const tricks = [...new Set(Array.isArray(data.trucos) ? data.trucos : [])].filter(
    (t) => typeof t === 'string' && Object.hasOwn(TRUCOS, t),
  );
  return respond(200, {
    // As in the library, the decision is made by the code from the model's two answers.
    decision: aiInstructions || peopleDeception ? 'review' : 'allow',
    ai_instructions: aiInstructions,
    people_deception: peopleDeception,
    tricks,
    reason: typeof data.motivo === 'string' ? data.motivo.trim().slice(0, 400) : '',
    model: MODEL,
    tokens,
    fallback: null,
  });
}

export default {
  async fetch(request, env) {
    const { pathname } = new URL(request.url);
    if (pathname === '/api/review') return review(request, env);
    return fail(404, 'not_found');
  },
};

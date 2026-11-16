// Checks on the built site (dist/): run it after `pnpm build`.
//
// What it guards: every page says its language and its alternates; nothing inline that the CSP
// of public/_headers would block (scripts, <style>, style="", on*="" handlers); every #anchor
// leads somewhere; every link inside the site leads to a file; the English page keeps the old
// Spanish ids as aliases; the sitemap lists real, indexable pages.
import assert from 'node:assert/strict';
import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs';
import { join, relative, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

const DIST = fileURLToPath(new URL('../dist/', import.meta.url));
const SITE = 'https://centinela.alinedlabs.co';

const built = existsSync(DIST);
// Without a build there is nothing to check: one test says so, and the others are skipped.
const buildTest = (name, check) => test(name, { skip: built ? false : 'run `pnpm build` first' }, check);

const walk = (directory) => readdirSync(directory).flatMap((name) => {
  const path = join(directory, name);
  return statSync(path).isDirectory() ? walk(path) : [path];
});
const files = built ? walk(DIST).map((path) => relative(DIST, path).split(sep).join('/')) : [];
const pages = files.filter((file) => file.endsWith('.html')).sort();
const read = (file) => readFileSync(join(DIST, file), 'utf8');

// A small reader of tags: enough for the HTML Astro writes (attribute values have no ">").
function tags(html, name) {
  const found = [];
  for (const [, tag, rest] of html.matchAll(/<([a-zA-Z][\w:-]*)\b([^>]*)>/g)) {
    if (name && tag.toLowerCase() !== name) continue;
    const attributes = {};
    for (const [, key, quoted, single, bare] of rest.matchAll(/([^\s=/>"']+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'>]+)))?/g)) {
      attributes[key.toLowerCase()] = quoted ?? single ?? bare ?? '';
    }
    found.push({ tag: tag.toLowerCase(), attributes });
  }
  return found;
}

// What the page is for: its URL, its language and the route it belongs to ('/', '/sistema/' ...).
const urlOf = (file) => `/${file.replace(/(^|\/)index\.html$/, '$1')}`;
const langOf = (file) => (file.startsWith('es/') ? 'es' : 'en');
const routeOf = (file) => urlOf(file).replace(/^\/es(\/|$)/, '/');
// Pages that exist in both languages, and the one that exists once (every missing URL).
const ROUTE_PAGES = pages.filter((file) => file !== '404.html');
const NOINDEX = ['pruebas/index.html', 'es/pruebas/index.html', '404.html'];

test('the site is built (run `pnpm build` first)', () => {
  assert.ok(built, 'web/dist/ does not exist: run `pnpm build` first');
});

buildTest('the pages are the ones expected', () => {
  assert.deepEqual(pages, [
    '404.html', 'es/index.html', 'es/pruebas/index.html', 'es/sistema/index.html',
    'index.html', 'pruebas/index.html', 'sistema/index.html',
  ]);
  assert.ok(files.includes('404.html'), 'dist/404.html is what Cloudflare serves for a missing URL');
});

buildTest('every page says its language', () => {
  for (const file of pages) {
    const [html] = tags(read(file), 'html');
    assert.equal(html.attributes.lang, file === '404.html' ? 'en' : langOf(file), file);
  }
});

buildTest('every page of a route has its canonical link, hreflang alternates, and og:locale', () => {
  for (const file of ROUTE_PAGES) {
    const html = read(file);
    const links = tags(html, 'link');
    const alternates = Object.fromEntries(links.filter((l) => l.attributes.rel === 'alternate').map((l) => [l.attributes.hreflang, l.attributes.href]));
    const route = routeOf(file);
    const urlIn = (lang) => `${SITE}${lang === 'es' ? '/es' : ''}${route === '/' && lang === 'en' ? '/' : route === '/' ? '/' : route}`;
    assert.deepEqual(alternates, { en: urlIn('en'), es: urlIn('es'), 'x-default': urlIn('en') }, file);
    const canonical = links.find((l) => l.attributes.rel === 'canonical');
    assert.equal(canonical?.attributes.href, urlIn(langOf(file)), file);
    // Each alternate is a page of this build.
    for (const href of Object.values(alternates)) assert.ok(files.includes(`${href.slice(SITE.length)}index.html`.replace(/^\//, '')), `${file}: ${href}`);
    const locales = tags(html, 'meta').filter((m) => (m.attributes.property ?? '').startsWith('og:locale'));
    assert.deepEqual(locales.map((m) => [m.attributes.property, m.attributes.content]), [
      ['og:locale', langOf(file) === 'es' ? 'es_CO' : 'en_US'],
      ['og:locale:alternate', langOf(file) === 'es' ? 'en_US' : 'es_CO'],
    ], file);
  }
});

buildTest('the test page and the 404 are noindex, the others are not', () => {
  for (const file of pages) {
    const robots = tags(read(file), 'meta').find((m) => m.attributes.name === 'robots');
    assert.equal(robots?.attributes.content, NOINDEX.includes(file) ? 'noindex' : undefined, file);
  }
});

buildTest('nothing inline that the CSP blocks: scripts, <style>, style="", event handlers, javascript: links', () => {
  for (const file of pages) {
    const html = read(file);
    for (const { attributes } of tags(html, 'script')) {
      assert.ok(attributes.src || attributes.type === 'application/ld+json', `${file}: inline <script>`);
    }
    assert.equal(tags(html, 'style').length, 0, `${file}: <style> element`);
    for (const { tag, attributes } of tags(html)) {
      assert.ok(!('style' in attributes), `${file}: style="" on <${tag}>`);
      for (const name of Object.keys(attributes)) assert.ok(!/^on[a-z]+$/.test(name), `${file}: ${name}="" on <${tag}>`);
      for (const value of [attributes.href, attributes.src, attributes.action]) {
        assert.ok(!/^\s*javascript:/i.test(value ?? ''), `${file}: javascript: URL`);
      }
    }
  }
});

buildTest('only the site and Google Fonts are loaded from the pages (the CSP allows no more)', () => {
  for (const file of pages) {
    const html = read(file);
    for (const { tag, attributes } of tags(html)) {
      if (tag === 'link' && !['stylesheet', 'modulepreload', 'icon', 'preload'].includes(attributes.rel)) continue;
      const url = attributes.href ?? attributes.src;
      if (!url || tag === 'a' || url.startsWith('#')) continue; // links are not loads; <use href="#i-x"> is in the page
      const allowed = url.startsWith('/') || /^https:\/\/fonts\.(googleapis|gstatic)\.com\//.test(url);
      assert.ok(allowed, `${file}: <${tag}> loads ${url}`);
    }
  }
});

buildTest('every #anchor of a page leads to an id of that page, and ids are not repeated', () => {
  for (const file of pages) {
    const html = read(file);
    const ids = tags(html).map(({ attributes }) => attributes.id).filter(Boolean);
    assert.equal(new Set(ids).size, ids.length, `${file}: repeated ids ${ids.filter((id, n) => ids.indexOf(id) !== n)}`);
    for (const { tag, attributes } of tags(html)) {
      for (const value of [attributes.href]) {
        if (tag !== 'a' || !value?.startsWith('#') || value === '#') continue;
        assert.ok(ids.includes(decodeURIComponent(value.slice(1))), `${file}: ${value} leads nowhere`);
      }
      // aria-labelledby and the label of a field point at ids too.
      for (const value of [attributes['aria-labelledby'], attributes['aria-controls'], attributes.for]) {
        for (const id of (value ?? '').split(/\s+/).filter(Boolean)) assert.ok(ids.includes(id), `${file}: ${id} is not an id`);
      }
    }
  }
});

buildTest('every link inside the site leads to a file of the build', () => {
  for (const file of pages) {
    for (const { tag, attributes } of tags(read(file))) {
      const url = (tag === 'a' || tag === 'link') ? attributes.href : attributes.src;
      if (!url?.startsWith('/') || url.startsWith('//')) continue;
      const path = url.split(/[?#]/)[0];
      const target = path.endsWith('/') ? `${path.slice(1)}index.html` : path.slice(1);
      assert.ok(files.includes(target), `${file}: ${url} is not in dist/`);
    }
  }
});

buildTest('the page links to the other language, with lang and hreflang', () => {
  for (const file of ROUTE_PAGES.filter((f) => !f.includes('pruebas'))) {
    const other = langOf(file) === 'en' ? 'es' : 'en';
    const links = tags(read(file), 'a').filter((a) => a.attributes.hreflang === other);
    assert.ok(links.length >= 1, `${file}: no link to ${other}`);
    for (const { attributes } of links) {
      assert.equal(attributes.lang, other, file);
      const href = attributes.href;
      assert.ok(files.includes(`${href}index.html`.replace(/^\//, '')), `${file}: ${href}`);
      assert.equal(langOf(`${href}index.html`.replace(/^\//, '')), other);
    }
  }
});

// The sections of the landing page, by the dictionary key of their anchor (see src/i18n).
const SECTIONS = {
  home: ['home', 'inicio'], problem: ['problem', 'problema'], how: ['how-it-works', 'como-funciona'],
  room: ['room', 'sala'], results: ['results', 'resultados'], limits: ['limits', 'limites'],
  use: ['use', 'uso'], where: ['where', 'donde'], open: ['open', 'abierto'], team: ['team', 'equipo'],
};

buildTest('the English page has English ids and keeps the old Spanish ones as aliases; the Spanish page keeps its own', () => {
  const idsOf = (file) => new Set(tags(read(file)).map(({ attributes }) => attributes.id).filter(Boolean));
  const english = idsOf('index.html');
  const spanish = idsOf('es/index.html');
  for (const [name, [en, es]] of Object.entries(SECTIONS)) {
    assert.ok(english.has(en), `English page: #${en} (${name})`);
    assert.ok(english.has(es), `English page: the old #${es} still works (${name})`);
    assert.ok(spanish.has(es), `Spanish page: #${es} (${name})`);
    assert.ok(!spanish.has(en) || en === es, `Spanish page has no English id #${en}`);
  }
  // The nav links of each page go to the sections of that page, so aria-current can follow them.
  for (const [file, index] of [['index.html', 0], ['es/index.html', 1]]) {
    const hrefs = tags(read(file), 'a').map((a) => a.attributes.href).filter((h) => h?.startsWith('#'));
    for (const name of ['problem', 'how', 'room', 'results', 'limits', 'where', 'team']) {
      assert.ok(hrefs.includes(`#${SECTIONS[name][index]}`), `${file}: nav link to #${SECTIONS[name][index]}`);
    }
  }
});

buildTest('the live review is not offered while LIVE_REVIEW_ENABLED is false', () => {
  for (const file of ['index.html', 'es/index.html']) {
    const html = read(file);
    assert.ok(!html.includes('data-claude'), `${file}: the live review button or its output is on the page`);
  }
});

buildTest('the sitemap lists real, indexable pages with their alternates; robots.txt points to it', () => {
  const sitemap = read('sitemap.xml');
  const locs = [...sitemap.matchAll(/<loc>([^<]+)<\/loc>/g)].map((m) => m[1]);
  assert.deepEqual(locs, [`${SITE}/`, `${SITE}/es/`, `${SITE}/sistema/`, `${SITE}/es/sistema/`]);
  for (const loc of locs) {
    const file = `${loc.slice(SITE.length + 1)}index.html`;
    assert.ok(files.includes(file), `${loc} is not in dist/`);
    assert.ok(!NOINDEX.includes(file), `${loc} is noindex`);
  }
  // Each <url> lists the same three alternates as the page itself.
  for (const [, block] of sitemap.matchAll(/<url>([\s\S]*?)<\/url>/g)) {
    const loc = block.match(/<loc>([^<]+)<\/loc>/)[1];
    const alternates = Object.fromEntries([...block.matchAll(/<xhtml:link rel="alternate" hreflang="([^"]+)" href="([^"]+)"/g)].map((m) => [m[1], m[2]]));
    const file = `${loc.slice(SITE.length + 1)}index.html`;
    const page = Object.fromEntries(tags(read(file), 'link').filter((l) => l.attributes.rel === 'alternate').map((l) => [l.attributes.hreflang, l.attributes.href]));
    assert.deepEqual(alternates, page, loc);
  }
  assert.match(read('robots.txt'), /^Sitemap: https:\/\/centinela\.alinedlabs\.co\/sitemap\.xml$/m);
});

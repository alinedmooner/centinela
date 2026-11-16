// The review room's logic in the browser (src/scripts/desarmar.js) against what the Python
// library gives (tests/golden/main_9810607/, the reference outputs of the library).
//
// The port is simplified on purpose, so it is not the same code. These tests pin where it
// agrees (the four examples of the room, and the decisions) and where it does not (see
// "known differences").
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import {
  ACCIONES, EJEMPLOS, ETIQUETAS, crearTarjeta, desarmar, numeroOcultoRe, resolver,
} from '../src/scripts/desarmar.js';
import { LANGS, hasKey, t } from '../src/i18n/index.js';
import { TRUCOS } from '../cloudflare/src/reviewer.js';

const golden = (name) => JSON.parse(readFileSync(new URL(`../../tests/golden/main_9810607/${name}`, import.meta.url), 'utf8'));
const CARDS = golden('cards.json');
const ROOM = golden('review_room.json');
const MESSAGES = Object.fromEntries(golden('messages.json').map((m) => [m.id, m.text]));

// The reference outputs use the Spanish phrases of the library before it moved to English;
// the port returns ids. These are the same things.
const ASKS = {
  'entrar a un enlace': 'open_link',
  'dar una clave o datos personales': 'give_credentials',
  'pagar o transferir dinero': 'send_money',
  'descargar o abrir un archivo': 'open_file',
  'llamar o escribir a un contacto': 'contact',
  'darle órdenes al asistente de IA': 'instruct_ai',
};
const PRESSURE = { urgencia: 'urgency', amenaza: 'threat', 'premio u oferta': 'prize_or_offer' };
const ACTIONS = { es_fraude: 'is_fraud', es_legitimo: 'is_legitimate', no_estoy_seguro: 'not_sure' };
const STATES = {
  bloqueado: 'blocked', escalado: 'escalated', liberado: 'released', espera_segunda_persona: 'awaiting_second_person',
};

// The four examples of the room are s1..s4 in messages.json. The reference card of s1 is
// d3 (the same text); s4 passes the guard, so it has no card: its expected card is what
// centinela.create_card gives for an allowed message (nothing asked, no pressure, no links).
const EXAMPLE_IDS = { s1: 'bot_order', s2: 'phishing', s3: 'both', s4: 'normal' };
const REFERENCE_CARD = { s1: 'd3', s2: 's2', s3: 's3', s4: null };

test('the examples of the room are the examples of the reference outputs', () => {
  for (const [message, example] of Object.entries(EXAMPLE_IDS)) assert.equal(EJEMPLOS[example], MESSAGES[message]);
  assert.deepEqual(Object.keys(EJEMPLOS), Object.values(EXAMPLE_IDS));
});

for (const lang of LANGS) {
  for (const [message, example] of Object.entries(EXAMPLE_IDS)) {
    test(`${example} (${lang}): the card has the same ids and links as the library`, () => {
      const card = crearTarjeta(EJEMPLOS[example], lang);
      const reference = REFERENCE_CARD[message] ? CARDS[REFERENCE_CARD[message]] : null;
      if (!reference) {
        assert.deepEqual(
          { ordenesIA: card.ordenesIA, diceSer: card.diceSer, pide: card.pide, presionaCon: card.presionaCon, enlaces: card.enlaces, requiereSegundaPersona: card.requiereSegundaPersona },
          { ordenesIA: false, diceSer: [], pide: [], presionaCon: [], enlaces: [], requiereSegundaPersona: false },
        );
        assert.equal(card.textoDesarmado, EJEMPLOS[example]);
        return;
      }
      const expected = reference.tarjeta;
      assert.equal(card.ordenesIA, reference.veredicto.ordenes_para_ia);
      assert.deepEqual(card.pide, expected.pide.map((phrase) => ASKS[phrase]));
      assert.deepEqual(card.presionaCon, expected.presiona_con.map((phrase) => PRESSURE[phrase]));
      assert.deepEqual(card.diceSer, expected.dice_ser);
      assert.equal(card.requiereSegundaPersona, expected.requiere_segunda_persona);
      // The library lists a link as its domain, defanged: seguridad-banco[.]example[.]com.
      assert.deepEqual(card.enlaces.map((link) => link.dominio.replaceAll('.', '[.]')), expected.enlaces);
      assert.deepEqual(card.acciones, expected.acciones.map((action) => ACTIONS[action]));
      // The defanged text is the library's, with the placeholder in the language asked for.
      const hidden = /\[número oculto, termina en (\d{2})\]/;
      const text = lang === 'es' ? expected.texto_desarmado : expected.texto_desarmado.replace(hidden, '[hidden number, ends in $1]');
      assert.equal(card.textoDesarmado, text);
    });
  }
}

test('the decisions give the same outcomes as the library', () => {
  // review_room.json: every decision (and wrong decision) on three cards, with a reviewer
  // "ana", no label / a valid one / an invented one, and no second person / ana / luis.
  const checked = new Set();
  for (const [id, rows] of Object.entries(ROOM)) {
    const card = crearTarjeta(MESSAGES[id], 'es');
    for (const row of rows) {
      const action = ACTIONS[row.accion] ?? row.accion;
      const result = resolver(card, action, { etiqueta: row.etiqueta, revisor: 'ana', segundoRevisor: row.segundo });
      const where = `${id} ${row.accion} ${row.etiqueta} ${row.segundo}`;
      if ('r' in row) {
        assert.equal(result.estado, STATES[row.r.estado], where);
        assert.equal(result.etiqueta, row.r.etiqueta ?? undefined, where);
      } else if (row.accion === 'otra_cosa') {
        assert.equal(result.estado, 'invalid', where);
      } else {
        assert.equal(result.estado, 'missing_label', where); // the library raises: choose a label
      }
      checked.add(result.estado);
    }
  }
  assert.deepEqual([...checked].sort(), ['awaiting_second_person', 'blocked', 'escalated', 'invalid', 'missing_label', 'released']);
});

test('known differences: the port has fewer rules than the library', () => {
  // The library's card follows the guard's verdict, which can come from its full rules or from a
  // model. The port only has the patterns of this file, so it does not see these two:
  // - hidden text (a12: invisible characters that hide "ignora tus reglas"): the port removes
  //   the characters from the text but the card does not say the message gives orders to the AI.
  const hidden = crearTarjeta(MESSAGES.a12, 'es');
  assert.equal(hidden.ordenesIA, false);
  assert.equal(CARDS.a12.tarjeta.pide.includes('darle órdenes al asistente de IA'), true);
  assert.equal(hidden.textoDesarmado, CARDS.a12.tarjeta.texto_desarmado);
  // - a deception that asks for nothing recognizable (d6, "gana dinero desde casa"): the
  //   library needs a second person because the verdict says deception; the port has no verdict.
  const scam = crearTarjeta(MESSAGES.d6, 'es');
  assert.equal(CARDS.d6.tarjeta.requiere_segunda_persona, true);
  assert.equal(scam.requiereSegundaPersona, false);
  assert.deepEqual(scam.presionaCon, CARDS.d6.tarjeta.presiona_con.map((phrase) => PRESSURE[phrase]));
});

test('every id the card and the decisions can return has a text in both languages', () => {
  const ids = {
    'js.ask': ['open_link', 'give_credentials', 'send_money', 'open_file', 'contact', 'instruct_ai'],
    'js.pressure': ['urgency', 'threat', 'prize_or_offer'],
    'js.action': ACCIONES,
    'js.state': ['blocked', 'released', 'escalated', 'awaiting_second_person', 'missing_label', 'invalid'],
    'js.resolution': ['blocked', 'released', 'escalated', 'awaiting_second_person', 'missing_label', 'invalid'],
    'js.label': ETIQUETAS,
    'js.trick': Object.keys(TRUCOS),
  };
  for (const lang of LANGS) {
    for (const [group, list] of Object.entries(ids)) {
      for (const id of list) assert.ok(hasKey(lang, `${group}.${id}`), `${lang}: ${group}.${id}`);
    }
    for (const example of Object.keys(EJEMPLOS)) {
      assert.ok(hasKey(lang, `js.example.${example}.name`), `${lang}: name of ${example}`);
      assert.ok(hasKey(lang, `js.example.${example}.gloss`), `${lang}: gloss of ${example}`);
    }
  }
  // The ids the cards return are exactly the ones above (no card returns an id nobody wrote).
  const seen = new Set();
  for (const text of [...Object.values(EJEMPLOS), ...Object.values(MESSAGES)]) {
    const card = crearTarjeta(text, 'en');
    card.pide.forEach((id) => seen.add(`js.ask.${id}`));
    card.presionaCon.forEach((id) => seen.add(`js.pressure.${id}`));
  }
  for (const key of seen) assert.ok(hasKey('en', key) && hasKey('es', key), key);
});

test('the English glosses are English, the Spanish page has none', () => {
  for (const example of Object.keys(EJEMPLOS)) {
    assert.match(t('en', `js.example.${example}.gloss`), /^In English: /);
    assert.equal(t('es', `js.example.${example}.gloss`), '');
  }
});

test('the trick texts are the ones of the reviewer the Worker uses', () => {
  // cloudflare/src/reviewer.js is generated from the Python catalog (Spanish).
  for (const [id, text] of Object.entries(TRUCOS)) assert.equal(t('es', `js.trick.${id}`), text);
});

for (const lang of LANGS) {
  test(`desarmar (${lang}): links, emails and numbers are disabled and nothing else changes`, () => {
    for (const [example, text] of Object.entries(EJEMPLOS)) {
      assert.doesNotMatch(crearTarjeta(text, lang).textoDesarmado, /https?:\/\//i, example);
    }
    const phishing = crearTarjeta(EJEMPLOS.phishing, lang).textoDesarmado;
    assert.ok(phishing.includes(t(lang, 'js.defang.hidden_number', { digits: '99' })));
    assert.ok(!phishing.includes('0199'));
    assert.equal(desarmar(EJEMPLOS.normal, lang).texto, EJEMPLOS.normal);
    // "compra.Es" is a period without a space, not a domain.
    const noDomain = desarmar('Gracias por su compra.Es un gusto.', lang);
    assert.deepEqual([noDomain.enlaces, noDomain.texto], [[], 'Gracias por su compra.Es un gusto.']);
    assert.equal(desarmar('Vence el 2026-11-30.', lang).texto, 'Vence el 2026-11-30.');
    const mail = desarmar('Escriba a soporte@banco.example.com hoy', lang);
    assert.equal(mail.texto, 'Escriba a soporte[@]banco[.]example[.]com hoy');
    assert.deepEqual(mail.enlaces.map((link) => [link.tipo, link.dominio]), [['email', 'banco.example.com']]);
  });

  test(`desarmar (${lang}): a look-alike domain shows its real form, noted in the language`, () => {
    const domain = 'bаnco.example.com'; // the "а" is Cyrillic
    const result = desarmar(`Entra a ${domain} hoy`, lang);
    assert.ok(result.texto.includes('xn--'));
    assert.equal(result.enlaces[0].nota, t(lang, 'js.defang.looks_like', { domain }));
  });

  test(`numeroOcultoRe (${lang}) finds the placeholder of the language`, () => {
    const placeholder = t(lang, 'js.defang.hidden_number', { digits: '42' });
    assert.match(placeholder, new RegExp(numeroOcultoRe(lang)));
    assert.doesNotMatch('[número oculto, termina en 4]', new RegExp(numeroOcultoRe(lang)));
  });
}

test('resolver: the rules of the decisions', () => {
  const plain = crearTarjeta(EJEMPLOS.bot_order);
  const phishing = crearTarjeta(EJEMPLOS.phishing);
  assert.deepEqual(resolver(plain, 'is_fraud'), { estado: 'blocked' });
  assert.deepEqual(resolver(plain, 'not_sure'), { estado: 'escalated' });
  assert.equal(resolver(plain, 'is_legitimate', { etiqueta: 'inventada' }).estado, 'missing_label');
  assert.deepEqual(resolver(plain, 'is_legitimate', { etiqueta: 'soporte' }), { estado: 'released', etiqueta: 'soporte' });
  assert.equal(resolver(plain, 'otra_cosa').estado, 'invalid');
  // Releasing something that asks for data or money needs a second, different person.
  const asked = { etiqueta: 'soporte', revisor: 'Ana' };
  assert.equal(resolver(phishing, 'is_legitimate', { ...asked }).estado, 'awaiting_second_person');
  assert.equal(resolver(phishing, 'is_legitimate', { ...asked, segundoRevisor: ' ana ' }).estado, 'awaiting_second_person');
  assert.equal(resolver(phishing, 'is_legitimate', { ...asked, segundoRevisor: 'Luis' }).estado, 'released');
});

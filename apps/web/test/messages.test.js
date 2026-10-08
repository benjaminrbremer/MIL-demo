/**
 * The user-facing message per error code (REQ-017, REQ-107, D-012).
 * messages.js has no DOM code, so Node can import it as is.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readdir, readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { MESSAGES, messageFor } from '../client/js/messages.js';
import { WEB_DIR } from './helpers.js';

/** Every code in the error-code tables of docs/api-contract.md. */
async function contractCodes() {
  const contract = await readFile(join(WEB_DIR, '..', '..', 'docs', 'api-contract.md'), 'utf8');
  // Table rows start with the code in backticks: | `NO_TISSUE` | ...
  return [...contract.matchAll(/^\| `([A-Z_]+)` \|/gm)].map((match) => match[1]);
}

test('req_017: every error code in the API contract has a message', async () => {
  const codes = await contractCodes();

  assert.ok(codes.length >= 17, `found only ${codes.length} codes: is the table format the same?`);
  for (const code of codes) {
    assert.ok(MESSAGES[code], `no message for ${code}`);
  }
});

test('req_017: there are no messages for codes the contract does not define', async () => {
  const codes = new Set(await contractCodes());

  for (const code of Object.keys(MESSAGES)) {
    assert.ok(codes.has(code), `${code} is not in docs/api-contract.md`);
  }
});

test('req_017: messageFor gives the message for the code, with the code at the end', () => {
  const text = messageFor({ code: 'NO_TISSUE', message: 'device text' });

  assert.equal(text, `${MESSAGES.NO_TISSUE} (NO_TISSUE)`);
  assert.ok(!text.includes('device text'));
});

test('req_107: the offline codes tell the user what to check', () => {
  assert.match(messageFor({ code: 'DEVICE_OFFLINE' }), /Tailscale/);
  assert.match(messageFor({ code: 'WEB_SERVER_OFFLINE' }), /npm start/);
});

test("an unknown code falls back to the server's message", () => {
  assert.equal(messageFor({ code: 'NEW_CODE', message: 'Something new' }), 'Something new (NEW_CODE)');
});

test('a missing error still gives a sentence', () => {
  for (const error of [undefined, null, {}]) {
    assert.equal(messageFor(error), 'An unexpected error occurred (UNKNOWN)');
  }
});

test('req_017: browser code shows errors only through messageFor', async () => {
  // A device's own message is for logs; the UI says what to do (D-012, D-062).
  const dir = join(WEB_DIR, 'client', 'js');
  for (const name of await readdir(dir)) {
    if (name === 'messages.js') continue;
    const text = await readFile(join(dir, name), 'utf8');
    assert.doesNotMatch(text, /\berror\.message\b/, `${name} shows an error's raw message`);
  }
});

/**
 * The web server end to end: run server/index.js as `npm start` would,
 * against a fake inference service (REQ-107, REQ-109).
 */

import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import {
  HEALTH_BODY,
  TEST_TOKEN,
  freePort,
  runWebServerToExit,
  startFakeDevice,
  startWebServer,
} from './helpers.js';

let device;
let web;

before(async () => {
  device = await startFakeDevice();
  web = await startWebServer({ INFERENCE_URL: device.url, DEVICE_TOKEN: TEST_TOKEN });
});

after(async () => {
  web?.stop();
  await device?.close();
});

test('GET /api/health passes the device health through', async () => {
  const response = await fetch(`${web.url}/api/health`);

  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), HEALTH_BODY);
});

test('req_107: /api/health is 503 DEVICE_OFFLINE when the device is down', async () => {
  // Nothing listens on this port, so the connection is refused at once.
  const offline = await startWebServer({
    INFERENCE_URL: `http://127.0.0.1:${await freePort()}`,
    DEVICE_TOKEN: TEST_TOKEN,
  });
  try {
    const response = await fetch(`${offline.url}/api/health`);

    assert.equal(response.status, 503);
    const body = await response.json();
    assert.equal(body.error.code, 'DEVICE_OFFLINE');
    assert.equal(typeof body.error.message, 'string');
  } finally {
    offline.stop();
  }
});

test('req_108: the browser never sees the device token', async () => {
  const response = await fetch(`${web.url}/api/health`);
  const text = await response.text();

  assert.ok(!text.includes(TEST_TOKEN));
  for (const [name, value] of response.headers) {
    assert.ok(!value.includes(TEST_TOKEN), `token in response header ${name}`);
  }
});

test('unknown /api paths get a contract-shaped 404', async () => {
  const response = await fetch(`${web.url}/api/nope`);

  assert.equal(response.status, 404);
  assert.deepEqual(await response.json(), {
    error: { code: 'NOT_FOUND', message: 'Not found' },
  });
});

test('req_109: the page carries the research notice in plain HTML', async () => {
  // In the HTML itself, not added by JavaScript, so it shows even if
  // every script fails.
  const response = await fetch(`${web.url}/`);

  assert.equal(response.status, 200);
  assert.match(response.headers.get('content-type'), /text\/html/);
  assert.match(await response.text(), /Research demo - not for clinical use/);
});

for (const missing of ['INFERENCE_URL', 'DEVICE_TOKEN']) {
  test(`startup fails fast without ${missing}`, async () => {
    const env = { INFERENCE_URL: 'http://127.0.0.1:1', DEVICE_TOKEN: TEST_TOKEN };
    delete env[missing];

    const { code, output } = await runWebServerToExit(env);

    assert.notEqual(code, 0);
    assert.match(output, new RegExp(`Missing required setting ${missing}`));
  });
}

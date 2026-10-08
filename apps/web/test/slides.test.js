/**
 * The slide list and the Deep Zoom proxy end to end (REQ-101, REQ-102,
 * REQ-107): the real server/index.js against a fake inference service.
 */

import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import {
  DZI_XML,
  NOT_READY_ID,
  READY_ID,
  SLIDES_BODY,
  TEST_TOKEN,
  TILE_BYTES,
  TILE_CACHE_CONTROL,
  freePort,
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

const tileUrl = (id, level = 8) => `${web.url}/api/slides/${id}_files/${level}/0_0.jpeg`;

test('req_101: GET /api/slides passes the device list through', async () => {
  const response = await fetch(`${web.url}/api/slides`);

  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), SLIDES_BODY);
  assert.equal(device.requests.at(-1).url, '/v1/slides');
});

test('req_102: the .dzi descriptor is proxied as XML', async () => {
  const response = await fetch(`${web.url}/api/slides/${READY_ID}.dzi`);

  assert.equal(response.status, 200);
  assert.match(response.headers.get('content-type'), /^application\/xml/);
  assert.equal(await response.text(), DZI_XML);
  assert.equal(device.requests.at(-1).url, `/v1/slides/${READY_ID}.dzi`);
});

test('req_102: tiles are proxied byte for byte with their cache header', async () => {
  const response = await fetch(tileUrl(READY_ID));

  assert.equal(response.status, 200);
  assert.equal(response.headers.get('content-type'), 'image/jpeg');
  assert.equal(response.headers.get('cache-control'), TILE_CACHE_CONTROL);
  assert.deepEqual(Buffer.from(await response.arrayBuffer()), TILE_BYTES);
});

test('req_108: device headers other than type and cache never reach the browser', async () => {
  const response = await fetch(tileUrl(READY_ID));

  assert.equal(response.headers.get('x-device-internal'), null);
  for (const [name, value] of response.headers) {
    assert.ok(!value.includes(TEST_TOKEN), `token in response header ${name}`);
  }
});

test('a slide that is not ready gets the device 409 for descriptor and tiles', async () => {
  for (const url of [`${web.url}/api/slides/${NOT_READY_ID}.dzi`, tileUrl(NOT_READY_ID)]) {
    const response = await fetch(url);

    assert.equal(response.status, 409);
    assert.equal((await response.json()).error.code, 'SLIDE_NOT_READY');
  }
});

test('a device error without the contract shape keeps its status (D-057)', async () => {
  const response = await fetch(tileUrl(READY_ID, 99));

  assert.equal(response.status, 500);
  assert.equal((await response.json()).error.code, 'INTERNAL_ERROR');
});

test('malformed slide IDs and tile paths are 404 and never reach the device', async () => {
  const before = device.requests.length;
  const urls = [
    `${web.url}/api/slides/not-a-uuid.dzi`,
    `${web.url}/api/slides/${NOT_READY_ID.toUpperCase()}.dzi`, // IDs are lowercase hex
    `${web.url}/api/slides/${'z'.repeat(8)}-2222-4333-8444-555555555555.dzi`,
    `${web.url}/api/slides/${'-'.repeat(36)}_files/8/0_0.jpeg`,
    `${web.url}/api/slides/${READY_ID}_files/x/0_0.jpeg`,
    `${web.url}/api/slides/${READY_ID}_files/8/0_0.png`,
    `${web.url}/api/slides/${READY_ID}_files/8/..%2F..%2Fhealth`,
  ];

  for (const url of urls) {
    const response = await fetch(url);
    assert.equal(response.status, 404, url);
    assert.equal((await response.json()).error.code, 'NOT_FOUND', url);
  }
  assert.equal(device.requests.length, before);
});

test('req_107: /api/slides and tiles are 503 DEVICE_OFFLINE when the device is down', async () => {
  const offline = await startWebServer({
    INFERENCE_URL: `http://127.0.0.1:${await freePort()}`,
    DEVICE_TOKEN: TEST_TOKEN,
  });
  try {
    for (const path of ['/api/slides', `/api/slides/${READY_ID}.dzi`]) {
      const response = await fetch(`${offline.url}${path}`);

      assert.equal(response.status, 503, path);
      assert.equal((await response.json()).error.code, 'DEVICE_OFFLINE', path);
    }
  } finally {
    offline.stop();
  }
});

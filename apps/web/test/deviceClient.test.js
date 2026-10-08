/**
 * deviceClient.js against a fake inference service (REQ-107, REQ-108).
 *
 * config.js reads the environment once, when it is first imported. So the
 * fake device starts and the environment is set BEFORE deviceClient.js is
 * imported (a dynamic import, below). Node runs each test file in its own
 * process, so this doesn't affect other test files.
 */

import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import {
  DZI_XML,
  HEALTH_BODY,
  NOT_READY_ID,
  READY_ID,
  TEST_TOKEN,
  TILE_BYTES,
  TILE_CACHE_CONTROL,
  TILE_PATH,
  startFakeDevice,
} from './helpers.js';

const device = await startFakeDevice();
process.env.INFERENCE_URL = `${device.url}/`; // trailing slash: config strips it
process.env.DEVICE_TOKEN = TEST_TOKEN;
after(() => device.close());

const { deviceGet, deviceGetRaw, DeviceError } = await import('../server/deviceClient.js');

/** Await a promise that should reject with a DeviceError; return the error. */
async function deviceErrorFrom(promise) {
  try {
    await promise;
  } catch (err) {
    assert.ok(err instanceof DeviceError, `expected DeviceError, got ${err?.name}`);
    return err;
  }
  assert.fail('expected the call to fail');
}

test('req_108: calls /v1 on the device with the token header', async () => {
  const body = await deviceGet('/health');

  assert.deepEqual(body, HEALTH_BODY);
  const last = device.requests.at(-1);
  assert.equal(last.url, '/v1/health'); // no "//" from the trailing slash
  assert.equal(last.headers['x-device-token'], TEST_TOKEN);
});

test('device errors pass through with their status, code, and message', async () => {
  const err = await deviceErrorFrom(deviceGet('/missing'));

  assert.equal(err.status, 404);
  assert.equal(err.code, 'NOT_FOUND');
  assert.equal(err.message, 'Slide not found');
});

test('an error body without the contract shape becomes INTERNAL_ERROR', async () => {
  const err = await deviceErrorFrom(deviceGet('/no-shape'));

  assert.equal(err.status, 500);
  assert.equal(err.code, 'INTERNAL_ERROR');
});

test('a successful non-JSON answer is BAD_GATEWAY (502)', async () => {
  const err = await deviceErrorFrom(deviceGet('/not-json'));

  assert.equal(err.status, 502);
  assert.equal(err.code, 'BAD_GATEWAY');
});

test('req_107: a device that never answers is DEVICE_OFFLINE after the timeout', async () => {
  // Takes about 5 s: the real timeout, not a shortened one.
  const started = Date.now();
  const err = await deviceErrorFrom(deviceGet('/hang'));

  assert.equal(err.status, 503);
  assert.equal(err.code, 'DEVICE_OFFLINE');
  const elapsed = Date.now() - started;
  assert.ok(elapsed >= 4500 && elapsed < 8000, `took ${elapsed} ms`);
});

test('req_102: deviceGetRaw returns the bytes, content type, and cache header', async () => {
  const raw = await deviceGetRaw(TILE_PATH);

  assert.equal(raw.contentType, 'image/jpeg');
  assert.equal(raw.cacheControl, TILE_CACHE_CONTROL);
  assert.ok(Buffer.isBuffer(raw.body));
  assert.deepEqual(raw.body, TILE_BYTES); // byte for byte, not decoded as text
  assert.equal(device.requests.at(-1).headers['x-device-token'], TEST_TOKEN);
});

test('deviceGetRaw returns text bodies too, with no cache header', async () => {
  const raw = await deviceGetRaw(`/slides/${READY_ID}.dzi`);

  assert.equal(raw.contentType, 'application/xml');
  assert.equal(raw.cacheControl, null);
  assert.equal(raw.body.toString('utf8'), DZI_XML);
});

test('deviceGetRaw passes contract errors through', async () => {
  const err = await deviceErrorFrom(deviceGetRaw(`/slides/${NOT_READY_ID}.dzi`));

  assert.equal(err.status, 409);
  assert.equal(err.code, 'SLIDE_NOT_READY');
  assert.equal(err.message, 'Slide is not ready');
});

test('a failed answer that is not JSON keeps its status as INTERNAL_ERROR (D-057)', async () => {
  // deviceGet and deviceGetRaw share this path (errorFrom).
  for (const call of [deviceGet, deviceGetRaw]) {
    const err = await deviceErrorFrom(call(`/slides/${READY_ID}_files/99/0_0.jpeg`));

    assert.equal(err.status, 500);
    assert.equal(err.code, 'INTERNAL_ERROR');
  }
});

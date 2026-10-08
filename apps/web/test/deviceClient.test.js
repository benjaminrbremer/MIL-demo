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
import { HEALTH_BODY, TEST_TOKEN, startFakeDevice } from './helpers.js';

const device = await startFakeDevice();
process.env.INFERENCE_URL = `${device.url}/`; // trailing slash: config strips it
process.env.DEVICE_TOKEN = TEST_TOKEN;
after(() => device.close());

const { deviceGet, DeviceError } = await import('../server/deviceClient.js');

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

test('a non-JSON answer is BAD_GATEWAY (502)', async () => {
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

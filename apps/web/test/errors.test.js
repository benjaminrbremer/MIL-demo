/**
 * sendError: every error reaches the browser in the contract shape
 * {"error": {"code", "message"}}, and our own bugs never leak details.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { TEST_TOKEN } from './helpers.js';

// errors.js imports deviceClient.js, which imports config.js: set the
// required settings first (never contacted in this file).
process.env.INFERENCE_URL = 'http://127.0.0.1:1';
process.env.DEVICE_TOKEN = TEST_TOKEN;
const { sendError } = await import('../server/errors.js');
const { DeviceError } = await import('../server/deviceClient.js');

/** A stand-in for Express's `res` that records what was sent. */
function fakeResponse() {
  const res = {
    statusCode: undefined,
    body: undefined,
    status(code) {
      res.statusCode = code;
      return res; // Express's status() returns res, so .json() can chain
    },
    json(body) {
      res.body = body;
      return res;
    },
  };
  return res;
}

test('a DeviceError keeps its status, code, and message', () => {
  const res = fakeResponse();

  sendError(res, new DeviceError(409, 'SLIDE_NOT_READY', 'Slide is not ready'));

  assert.equal(res.statusCode, 409);
  assert.deepEqual(res.body, { error: { code: 'SLIDE_NOT_READY', message: 'Slide is not ready' } });
});

test('any other error is a 500 INTERNAL_ERROR with a fixed message', (t) => {
  const logged = t.mock.method(console, 'error', () => {});
  const res = fakeResponse();

  sendError(res, new TypeError('secret detail /Users/someone/file.txt'));

  assert.equal(res.statusCode, 500);
  assert.deepEqual(res.body, { error: { code: 'INTERNAL_ERROR', message: 'Internal server error' } });
  // The log names the error type only, not its message.
  assert.equal(logged.mock.callCount(), 1);
  const line = logged.mock.calls[0].arguments.join(' ');
  assert.match(line, /TypeError/);
  assert.doesNotMatch(line, /secret detail/);
});

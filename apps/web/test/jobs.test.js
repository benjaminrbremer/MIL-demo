/**
 * Job routes, the SSE progress relay and the heatmap proxy end to end
 * (REQ-103, REQ-104, REQ-106, REQ-107, REQ-108): the real server/index.js
 * against a fake device whose progress stream the tests control.
 */

import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import {
  READY_ID,
  TEST_TOKEN,
  freePort,
  readSse,
  sseEvent,
  sseEventNames,
  startFakeDevice,
  startWebServer,
  waitFor,
} from './helpers.js';

const JOB_ID = 'aaaaaaaa-1111-4222-8333-444444444444';
const LONG_JOB_ID = 'bbbbbbbb-1111-4222-8333-444444444444';
const UNKNOWN_JOB_ID = 'cccccccc-1111-4222-8333-444444444444';
const BUSY_SLIDE_ID = 'dddddddd-1111-4222-8333-444444444444';
const RUNNING_JOB_ID = 'eeeeeeee-1111-4222-8333-444444444444';

/** Not a real PNG: bytes a text decoder would mangle (the PNG signature, then non-UTF-8). */
const HEATMAP_BYTES = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0xff, 0xfe, 0x00]);
const HEATMAP_CACHE_CONTROL = 'private, max-age=3600';

/** A job object shaped like the contract's. */
function jobObject(id, slideId, status, extra = {}) {
  return {
    id, slide_id: slideId, status, stage: null, progress: { done: null, total: null },
    error: null, created_at: '2026-10-08T05:00:00Z', started_at: null, finished_at: null,
    models: [], timings_s: {}, result: null, ...extra,
  };
}

const QUEUED = jobObject(JOB_ID, READY_ID, 'queued');
const COMPLETED = jobObject(JOB_ID, READY_ID, 'completed', { finished_at: '2026-10-08T05:00:07Z' });
const PROGRESS = { status: 'running', stage: 'extracting_features', progress: { done: 64, total: 2281 } };

// The fake device holds the first stream open until the test calls release().
let releaseStream = () => {};

function handleJobs(req, res, entry) {
  const json = (status, body) => {
    res.writeHead(status, { 'content-type': 'application/json' });
    res.end(JSON.stringify(body));
  };
  const url = new URL(req.url, 'http://device');

  if (req.method === 'POST' && url.pathname === '/v1/jobs') {
    const { slide_id: slideId } = JSON.parse(entry.body || '{}');
    if (slideId === BUSY_SLIDE_ID) {
      json(409, { error: { code: 'JOB_ALREADY_ACTIVE', message: 'Slide already has a queued or running job' } });
    } else {
      json(202, jobObject(JOB_ID, slideId, 'queued'));
    }
    return true;
  }
  if (req.method !== 'GET') return false;

  if (url.pathname === '/v1/jobs') {
    json(200, [COMPLETED]);
    return true;
  }
  if (url.pathname === `/v1/jobs/${JOB_ID}`) {
    json(200, COMPLETED);
    return true;
  }
  if (url.pathname === `/v1/jobs/${JOB_ID}/events`) {
    res.writeHead(200, { 'content-type': 'text/event-stream', 'cache-control': 'no-cache' });
    res.write(sseEvent('snapshot', QUEUED));
    releaseStream = () => {
      res.write(sseEvent('progress', PROGRESS));
      res.write(sseEvent('completed', COMPLETED));
      res.end();
    };
    return true;
  }
  if (url.pathname === `/v1/jobs/${LONG_JOB_ID}/events`) {
    // Longer than the web server's 5 s device timeout.
    res.writeHead(200, { 'content-type': 'text/event-stream' });
    res.write(sseEvent('snapshot', QUEUED));
    const timer = setTimeout(() => {
      res.write(sseEvent('completed', COMPLETED));
      res.end();
    }, 6000);
    res.on('close', () => clearTimeout(timer));
    return true;
  }
  if (url.pathname === `/v1/jobs/${JOB_ID}/heatmap.png`) {
    res.writeHead(200, {
      'content-type': 'image/png',
      'cache-control': HEATMAP_CACHE_CONTROL,
      'x-device-internal': 'must-not-be-forwarded',
    });
    res.end(HEATMAP_BYTES);
    return true;
  }
  if (url.pathname === `/v1/jobs/${RUNNING_JOB_ID}/heatmap.png`) {
    json(409, { error: { code: 'JOB_NOT_COMPLETED', message: 'Job is not completed' } });
    return true;
  }
  if (url.pathname.startsWith(`/v1/jobs/${UNKNOWN_JOB_ID}/`)) {
    json(404, { error: { code: 'NOT_FOUND', message: 'Job not found' } });
    return true;
  }
  return false;
}

let device;
let web;

before(async () => {
  device = await startFakeDevice({ handle: handleJobs });
  web = await startWebServer({ INFERENCE_URL: device.url, DEVICE_TOKEN: TEST_TOKEN });
});

after(async () => {
  web?.stop();
  await device?.close();
});

const post = (body, contentType = 'application/json') =>
  fetch(`${web.url}/api/jobs`, {
    method: 'POST',
    headers: { 'content-type': contentType },
    body: typeof body === 'string' ? body : JSON.stringify(body),
  });

// ---- POST /api/jobs (REQ-103) ----

test('req_103: POST /api/jobs queues a job: 202, forwarding only slide_id as JSON', async () => {
  const response = await post({ slide_id: READY_ID, extra: 'dropped', priority: 99 });

  assert.equal(response.status, 202);
  assert.deepEqual(await response.json(), QUEUED);
  const sent = device.requests.at(-1);
  assert.equal(sent.method, 'POST');
  assert.equal(sent.url, '/v1/jobs');
  // Both headers survive: the token and the body's content type.
  assert.equal(sent.headers['x-device-token'], TEST_TOKEN);
  assert.match(sent.headers['content-type'], /^application\/json/);
  assert.deepEqual(JSON.parse(sent.body), { slide_id: READY_ID });
});

test('req_103: the device 409 JOB_ALREADY_ACTIVE passes through', async () => {
  const response = await post({ slide_id: BUSY_SLIDE_ID });

  assert.equal(response.status, 409);
  assert.equal((await response.json()).error.code, 'JOB_ALREADY_ACTIVE');
});

test('POST /api/jobs without a valid slide_id is 422 and never reaches the device', async () => {
  const before = device.requests.length;
  for (const body of [{}, { slide_id: 'nope' }, { slide_id: 42 }, { slide_id: READY_ID.toUpperCase() + 'X' }]) {
    const response = await post(body);

    assert.equal(response.status, 422, JSON.stringify(body));
    assert.equal((await response.json()).error.code, 'VALIDATION_ERROR');
  }
  // A body that isn't JSON at all leaves req.body empty: also 422.
  const text = await post('slide_id=x', 'text/plain');
  assert.equal(text.status, 422);
  assert.equal(device.requests.length, before);
});

test('POST /api/jobs with malformed JSON is a contract-shaped 400', async () => {
  const response = await post('{"slide_id": ');

  assert.equal(response.status, 400);
  assert.match(response.headers.get('content-type'), /application\/json/);
  assert.equal((await response.json()).error.code, 'BAD_REQUEST');
});

// ---- GET /api/jobs, /api/jobs/:id (REQ-104 recovery reads these) ----

test('req_104: GET /api/jobs?slide_id= forwards the filter; no filter lists all', async () => {
  const filtered = await fetch(`${web.url}/api/jobs?slide_id=${READY_ID}`);
  assert.equal(filtered.status, 200);
  assert.deepEqual(await filtered.json(), [COMPLETED]);
  assert.equal(device.requests.at(-1).url, `/v1/jobs?slide_id=${READY_ID}`);

  const all = await fetch(`${web.url}/api/jobs`);
  assert.equal(all.status, 200);
  assert.equal(device.requests.at(-1).url, '/v1/jobs');
});

test('GET /api/jobs with a malformed slide_id is 422 and never reaches the device', async () => {
  const before = device.requests.length;
  for (const value of ['nope', `${READY_ID}%26status%3Dx`]) {
    const response = await fetch(`${web.url}/api/jobs?slide_id=${value}`);
    assert.equal(response.status, 422, value);
  }
  assert.equal(device.requests.length, before);
});

test('GET /api/jobs/:id passes the job through; a malformed ID is 404 locally', async () => {
  const ok = await fetch(`${web.url}/api/jobs/${JOB_ID}`);
  assert.equal(ok.status, 200);
  assert.deepEqual(await ok.json(), COMPLETED);

  const before = device.requests.length;
  const bad = await fetch(`${web.url}/api/jobs/not-a-job`);
  assert.equal(bad.status, 404);
  assert.equal((await bad.json()).error.code, 'NOT_FOUND');
  assert.equal(device.requests.length, before);
});

// ---- SSE relay (REQ-104) ----

test('req_104: events are relayed as they arrive, not buffered until the end', async () => {
  const response = await fetch(`${web.url}/api/jobs/${JOB_ID}/events`);
  assert.equal(response.status, 200);
  assert.match(response.headers.get('content-type'), /^text\/event-stream/);
  assert.equal(response.headers.get('cache-control'), 'no-cache');
  const reader = response.body.getReader();

  // The device has sent only the snapshot and is holding the stream open.
  const first = await readSse(reader, (text) => text.includes('\n\n'));
  assert.equal(first.ended, false);
  assert.deepEqual(sseEventNames(first.text), ['snapshot']);
  const relayed = device.requests.at(-1);
  assert.equal(relayed.url, `/v1/jobs/${JOB_ID}/events`);
  assert.equal(relayed.headers['x-device-token'], TEST_TOKEN);

  releaseStream();
  const rest = await readSse(reader);
  assert.equal(rest.ended, true); // the relay ends when the device ends
  assert.deepEqual(sseEventNames(first.text + rest.text), ['snapshot', 'progress', 'completed']);
  assert.ok(!(first.text + rest.text).includes(TEST_TOKEN));
});

test('req_104: closing the browser stream closes the device stream', async () => {
  const controller = new AbortController();
  const response = await fetch(`${web.url}/api/jobs/${JOB_ID}/events`, { signal: controller.signal });
  await readSse(response.body.getReader(), (text) => text.includes('\n\n'));
  const upstream = device.requests.at(-1);
  assert.equal(upstream.closed, false);

  controller.abort(); // the browser tab goes away

  await waitFor(() => upstream.closed);
});

test('req_104: a stream that outlives the 5 s device timeout is not cut off', async () => {
  // About 6 s: the device sends `completed` after 6 s.
  const response = await fetch(`${web.url}/api/jobs/${LONG_JOB_ID}/events`);
  const { text, ended } = await readSse(response.body.getReader());

  assert.equal(ended, true);
  assert.deepEqual(sseEventNames(text), ['snapshot', 'completed']);
});

test('an unknown job stream is a JSON 404 before any stream starts', async () => {
  const response = await fetch(`${web.url}/api/jobs/${UNKNOWN_JOB_ID}/events`);

  assert.equal(response.status, 404);
  assert.match(response.headers.get('content-type'), /application\/json/);
  assert.equal((await response.json()).error.code, 'NOT_FOUND');
});

test('a malformed job ID on the stream route is 404 and never reaches the device', async () => {
  const before = device.requests.length;
  const response = await fetch(`${web.url}/api/jobs/not-a-job/events`);

  assert.equal(response.status, 404);
  assert.equal(device.requests.length, before);
});

// ---- Heatmap proxy (REQ-106) ----

test('req_106: the heatmap PNG is proxied byte for byte with its cache header', async () => {
  const response = await fetch(`${web.url}/api/jobs/${JOB_ID}/heatmap.png`);

  assert.equal(response.status, 200);
  assert.equal(response.headers.get('content-type'), 'image/png');
  assert.equal(response.headers.get('cache-control'), HEATMAP_CACHE_CONTROL);
  assert.deepEqual(Buffer.from(await response.arrayBuffer()), HEATMAP_BYTES);
  const sent = device.requests.at(-1);
  assert.equal(sent.url, `/v1/jobs/${JOB_ID}/heatmap.png`);
  assert.equal(sent.headers['x-device-token'], TEST_TOKEN);
});

test('req_108: the heatmap response carries no other device headers', async () => {
  const response = await fetch(`${web.url}/api/jobs/${JOB_ID}/heatmap.png`);

  assert.equal(response.headers.get('x-device-internal'), null);
  for (const [name, value] of response.headers) {
    assert.ok(!value.includes(TEST_TOKEN), `token in response header ${name}`);
  }
});

test('req_106: heatmap errors pass through: 409 JOB_NOT_COMPLETED and 404 NOT_FOUND', async () => {
  const running = await fetch(`${web.url}/api/jobs/${RUNNING_JOB_ID}/heatmap.png`);
  assert.equal(running.status, 409);
  assert.equal((await running.json()).error.code, 'JOB_NOT_COMPLETED');

  const unknown = await fetch(`${web.url}/api/jobs/${UNKNOWN_JOB_ID}/heatmap.png`);
  assert.equal(unknown.status, 404);
  assert.equal((await unknown.json()).error.code, 'NOT_FOUND');
});

test('a malformed job ID on the heatmap route is 404 and never reaches the device', async () => {
  const before = device.requests.length;
  for (const id of ['not-a-job', JOB_ID.toUpperCase(), '..%2F..%2Fhealth']) {
    const response = await fetch(`${web.url}/api/jobs/${id}/heatmap.png`);

    assert.equal(response.status, 404, id);
    assert.equal((await response.json()).error.code, 'NOT_FOUND', id);
  }
  assert.equal(device.requests.length, before);
});

test('req_107: job routes are 503 DEVICE_OFFLINE when the device is down', async () => {
  const offline = await startWebServer({
    INFERENCE_URL: `http://127.0.0.1:${await freePort()}`,
    DEVICE_TOKEN: TEST_TOKEN,
  });
  try {
    const requests = [
      fetch(`${offline.url}/api/jobs`, {
        method: 'POST', headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ slide_id: READY_ID }),
      }),
      fetch(`${offline.url}/api/jobs?slide_id=${READY_ID}`),
      fetch(`${offline.url}/api/jobs/${JOB_ID}/events`),
      fetch(`${offline.url}/api/jobs/${JOB_ID}/heatmap.png`),
    ];
    for (const response of await Promise.all(requests)) {
      assert.equal(response.status, 503, response.url);
      assert.equal((await response.json()).error.code, 'DEVICE_OFFLINE');
    }
  } finally {
    offline.stop();
  }
});

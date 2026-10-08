/**
 * Test helpers: a fake inference service and a way to run the real web server.
 *
 * The web server reads its settings once, when config.js is imported, and
 * server/index.js starts listening as soon as it runs. So the route tests
 * start it as a separate Node process with test settings, exactly as
 * `npm start` would, and talk to it over HTTP.
 */

import { createServer } from 'node:http';
import { spawn } from 'node:child_process';
import { join } from 'node:path';

export const TEST_TOKEN = 'test-token-0123456789';
export const WEB_DIR = join(import.meta.dirname, '..');

/** A health body shaped like the contract's GET /v1/health. */
export const HEALTH_BODY = {
  status: 'ok',
  service_version: '0.1.0',
  api_version: 'v1',
  gpu: { available: true, name: 'Fake GPU' },
  models: [
    { role: 'encoder', name: 'fake/encoder', version: 'aaaa1111', sha256: 'a'.repeat(64) },
    { role: 'mil', name: 'fake/mil', version: 'bbbb2222', sha256: 'b'.repeat(64) },
  ],
  queue: { running: 0, queued: 0 },
};

export const READY_ID = '11111111-2222-4333-8444-555555555555';
export const NOT_READY_ID = '66666666-7777-4888-9999-aaaaaaaaaaaa';

/** A slide list shaped like the contract's GET /v1/slides. */
export const SLIDES_BODY = [
  {
    id: READY_ID, status: 'ready', width: 4000, height: 3000, level_count: 3,
    mpp_x: 0.25, mpp_y: 0.25, detected_at: '2026-10-07T14:03:11Z',
    registered_at: '2026-10-07T14:03:19Z', error: null,
  },
  {
    id: NOT_READY_ID, status: 'arriving', width: null, height: null, level_count: null,
    mpp_x: null, mpp_y: null, detected_at: '2026-10-07T14:05:00Z',
    registered_at: null, error: null,
  },
];

export const DZI_XML =
  '<Image TileSize="254" Overlap="1" Format="jpeg" xmlns="http://schemas.microsoft.com/deepzoom/2008">' +
  '<Size Width="4000" Height="3000" /></Image>';
/** Not a real image: bytes a text decoder would mangle, to prove they pass through untouched. */
export const TILE_BYTES = Buffer.from([0xff, 0xd8, 0xff, 0xe0, 0x00, 0x80, 0xfe, 0x01, 0xff, 0xd9]);
export const TILE_CACHE_CONTROL = 'private, max-age=3600';
export const TILE_PATH = `/slides/${READY_ID}_files/8/0_0.jpeg`;

/**
 * Start a fake inference service on a free port.
 * Routes (all under /v1):
 *   /health        200 health JSON, but 401 if the token is wrong
 *   /not-json      200 with an HTML body
 *   /missing       404 in the contract error shape
 *   /no-shape      500 with a JSON body that isn't the error shape
 *   /hang          never answers (for the timeout)
 *   /slides                            200 SLIDES_BODY
 *   /slides/<READY_ID>.dzi             200 application/xml DZI_XML
 *   /slides/<READY_ID>_files/8/0_0.jpeg  200 image/jpeg TILE_BYTES, with
 *                                      Cache-Control and a header that must
 *                                      not reach the browser
 *   /slides/<READY_ID>_files/99/0_0.jpeg 500 with a plain-text body
 *   /slides/<NOT_READY_ID>...          409 SLIDE_NOT_READY
 * A test can add its own routes with `handle(req, res, entry)`: it runs
 * after the token check and returns true when it answered the request.
 * Each recorded request has method, url, headers, body (text), and
 * `closed`, which turns true when the client hangs up.
 * @param {{handle?: (req: import('node:http').IncomingMessage,
 *                    res: import('node:http').ServerResponse,
 *                    entry: object) => boolean}} [options]
 * @returns {Promise<{url: string, requests: Array<object>, close: () => Promise<void>}>}
 */
export async function startFakeDevice({ handle } = {}) {
  const requests = [];
  const server = createServer(async (req, res) => {
    let body = '';
    for await (const chunk of req) body += chunk;
    const entry = { method: req.method, url: req.url, headers: req.headers, body, closed: false };
    res.on('close', () => (entry.closed = true));
    requests.push(entry);
    const json = (status, body) => {
      res.writeHead(status, { 'content-type': 'application/json' });
      res.end(JSON.stringify(body));
    };
    if (req.headers['x-device-token'] !== TEST_TOKEN) {
      json(401, { error: { code: 'UNAUTHORIZED', message: 'Missing or invalid device token' } });
      return;
    }
    if (handle?.(req, res, entry)) return;
    switch (req.url) {
      case '/v1/health':
        json(200, HEALTH_BODY);
        break;
      case '/v1/not-json':
        res.writeHead(200, { 'content-type': 'text/html' });
        res.end('<html>not the device</html>');
        break;
      case '/v1/missing':
        json(404, { error: { code: 'NOT_FOUND', message: 'Slide not found' } });
        break;
      case '/v1/no-shape':
        json(500, { detail: 'something else' });
        break;
      case '/v1/hang':
        break; // never respond
      case '/v1/slides':
        json(200, SLIDES_BODY);
        break;
      case `/v1/slides/${READY_ID}.dzi`:
        res.writeHead(200, { 'content-type': 'application/xml' });
        res.end(DZI_XML);
        break;
      case `/v1${TILE_PATH}`:
        res.writeHead(200, {
          'content-type': 'image/jpeg',
          'cache-control': TILE_CACHE_CONTROL,
          'x-device-internal': 'must-not-be-forwarded',
        });
        res.end(TILE_BYTES);
        break;
      case `/v1/slides/${READY_ID}_files/99/0_0.jpeg`:
        res.writeHead(500, { 'content-type': 'text/plain' });
        res.end('Internal Server Error');
        break;
      case `/v1/slides/${NOT_READY_ID}.dzi`:
      case `/v1/slides/${NOT_READY_ID}_files/8/0_0.jpeg`:
        json(409, { error: { code: 'SLIDE_NOT_READY', message: 'Slide is not ready' } });
        break;
      default:
        json(404, { error: { code: 'NOT_FOUND', message: 'Not found' } });
    }
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  return {
    url: `http://127.0.0.1:${server.address().port}`,
    requests,
    close: () => {
      server.closeAllConnections(); // includes the hanging /hang request
      return new Promise((resolve) => server.close(resolve));
    },
  };
}

/** A port nothing is listening on (taken from the OS, then released). */
export async function freePort() {
  const server = createServer();
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  const { port } = server.address();
  await new Promise((resolve) => server.close(resolve));
  return port;
}

/**
 * Run server/index.js with the given settings and wait until it is listening.
 * Only the variables passed here are set (plus PATH), so nothing leaks in
 * from the developer's shell or .env.
 * @param {Record<string, string>} env
 * @returns {Promise<{url: string, stop: () => void}>}
 */
export async function startWebServer(env) {
  const port = await freePort();
  const child = spawn(process.execPath, ['server/index.js'], {
    cwd: WEB_DIR,
    env: { PATH: process.env.PATH, PORT: String(port), ...env },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  await new Promise((resolve, reject) => {
    let output = '';
    const onData = (chunk) => {
      output += chunk;
      if (output.includes('Web app on')) resolve();
    };
    child.stdout.on('data', onData);
    child.stderr.on('data', onData);
    child.on('exit', (code) => reject(new Error(`web server exited (${code}): ${output}`)));
  });
  return { url: `http://127.0.0.1:${port}`, stop: () => child.kill() };
}

/**
 * Run server/index.js and wait for it to exit (for startup failures).
 * @param {Record<string, string>} env
 * @returns {Promise<{code: number | null, output: string}>}
 */
export function runWebServerToExit(env) {
  const child = spawn(process.execPath, ['server/index.js'], {
    cwd: WEB_DIR,
    env: { PATH: process.env.PATH, ...env },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  let output = '';
  child.stdout.on('data', (chunk) => (output += chunk));
  child.stderr.on('data', (chunk) => (output += chunk));
  const timer = setTimeout(() => child.kill(), 5000); // in case it starts after all
  return new Promise((resolve) => {
    child.on('exit', (code) => {
      clearTimeout(timer);
      resolve({ code, output });
    });
  });
}

/** Wait until `condition()` is true; fail after `timeoutMs`. */
export async function waitFor(condition, timeoutMs = 3000) {
  const deadline = Date.now() + timeoutMs;
  while (!condition()) {
    if (Date.now() > deadline) throw new Error('condition not met in time');
    await new Promise((resolve) => setTimeout(resolve, 20));
  }
}

/** One Server-Sent Event in the wire format: `event: <name>` and `data: <json>`. */
export function sseEvent(name, data) {
  return `event: ${name}\ndata: ${JSON.stringify(data)}\n\n`;
}

/**
 * Read an SSE response body as text until `until(textSoFar)` is true or the
 * stream ends. Returns the text and whether the stream had ended.
 * @param {ReadableStreamDefaultReader<Uint8Array>} reader
 * @param {(text: string) => boolean} [until]
 */
export async function readSse(reader, until = () => false) {
  const decoder = new TextDecoder();
  let text = '';
  while (!until(text)) {
    const { value, done } = await reader.read();
    if (done) return { text, ended: true };
    text += decoder.decode(value, { stream: true });
  }
  return { text, ended: false };
}

/** Event names in an SSE text, in order (comments like `: ping` are skipped). */
export function sseEventNames(text) {
  return [...text.matchAll(/^event: (\S+)$/gm)].map((match) => match[1]);
}

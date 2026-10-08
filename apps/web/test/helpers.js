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

/**
 * Start a fake inference service on a free port.
 * Routes (all under /v1):
 *   /health        200 health JSON, but 401 if the token is wrong
 *   /not-json      200 with an HTML body
 *   /missing       404 in the contract error shape
 *   /no-shape      500 with a JSON body that isn't the error shape
 *   /hang          never answers (for the timeout)
 * @returns {Promise<{url: string, requests: Array<{url: string, headers: object}>, close: () => Promise<void>}>}
 */
export async function startFakeDevice() {
  const requests = [];
  const server = createServer((req, res) => {
    requests.push({ url: req.url, headers: req.headers });
    const json = (status, body) => {
      res.writeHead(status, { 'content-type': 'application/json' });
      res.end(JSON.stringify(body));
    };
    if (req.headers['x-device-token'] !== TEST_TOKEN) {
      json(401, { error: { code: 'UNAUTHORIZED', message: 'Missing or invalid device token' } });
      return;
    }
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

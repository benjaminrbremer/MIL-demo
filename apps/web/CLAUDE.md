# CLAUDE.md - web app

## Role
Runs on the Mac. Express server that serves the browser client and mediates
every request to the inference service. Holds no job or slide state of its
own; the device is the source of truth.

## Commands
- Install: `npm install`
- Run: `npm start` (reads `.env`; see `.env.example`)
- Node version pinned in `.nvmrc`
- Tests: `npm test` (Node's built-in `node:test`; starts the real server
  against a fake device, no `.env` needed; about 7 s because two tests
  wait out real timeouts)

## Suggested layout
```
server/
  index.js          Express app, static files, route mounting
  config.js         env: INFERENCE_URL, DEVICE_TOKEN, PORT
  deviceClient.js   the ONLY module that calls the inference service;
                    adds X-Device-Token; maps connection failures to
                    DEVICE_OFFLINE
  errors.js         sendError, sendNotFound, and the final Express error
                    handler (invalid JSON -> 400 BAD_REQUEST)
  ids.js            isUuid: slide and job IDs are checked before any
                    device URL is built
  raw.js            sendRaw: device bytes to the browser with only
                    Content-Type and Cache-Control (D-058)
  routes/           health.js (/api/health); slides.js (/api/slides,
                    .dzi and tile proxy, D-058); jobs.js (/api/jobs,
                    the SSE relay, D-060, and the heatmap proxy, D-063)
client/
  index.html
  css/
  js/               ES modules: main.js, api.js, slideList.js,
                    viewer.js (slide and heatmap overlay), progress.js,
                    results.js; describe.js and messages.js have no DOM
                    code, so tests import them directly (D-062)
  (OpenSeadragon: served from node_modules at /vendor/openseadragon/,
   loaded as a classic script before main.js; D-059)
test/
  helpers.js        fake inference service; runs server/index.js
  *.test.js         the tests; REQ IDs in test names (e.g. req_107)
```

## Rules
- Plain JavaScript, ES modules, no framework, no bundler, no TypeScript.
- Browser code calls only `/api/...` on the Node server. It never builds
  inference-service URLs.
- Use JSDoc types on functions that cross the API boundary.
- Insert untrusted text into the DOM with `textContent`, never `innerHTML`.
- Prefer built-ins (global `fetch`, streams) over new dependencies.
  OpenSeadragon is installed from npm so its version is pinned.
- Slide list: poll `/api/slides` every few seconds. Job progress: SSE.
- On browser refresh, recover by fetching the latest job for the selected
  slide and reconnecting to its event stream.
- Always show the "Research demo - not for clinical use" notice and the
  model versions reported by `/api/health`.

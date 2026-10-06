# CLAUDE.md - web app

## Role
Runs on the Mac. Express server that serves the browser client and mediates
every request to the inference service. Holds no job or slide state of its
own; the device is the source of truth.

## Commands
- Install: `npm install`
- Run: `npm start` (reads `.env`; see `.env.example`)
- Node version pinned in `.nvmrc`

## Suggested layout
```
server/
  index.js          Express app, static files, route mounting
  config.js         env: INFERENCE_URL, DEVICE_TOKEN, PORT
  deviceClient.js   the ONLY module that calls the inference service;
                    adds X-Device-Token; maps connection failures to
                    DEVICE_OFFLINE
  routes/           /api/health, /api/slides, /api/jobs, tile proxy,
                    SSE relay
client/
  index.html
  css/
  js/               ES modules: api.js, slideList.js, viewer.js,
                    progress.js, results.js
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

/**
 * The ONLY module that talks to the inference service (REQ-108, D-003).
 * Adds the X-Device-Token header and turns "can't reach it" into
 * DEVICE_OFFLINE (REQ-107).
 */

import { config } from "./config.js";

const TIMEOUT_MS = 5000;

/** 
 * A failed device call: an HTTP status for the browser plus a contract error code. 
 */
export class DeviceError extends Error {
   /**
    * @param {number} status   HTTP status Node should send to the browser
    * @param {string} code     contract error code, e.g. "DEVICE_OFFLINE"
    * @param {string} message  safe to show to the user
    */
    constructor(status, code, message) {
        super(message);
        this.name = "DeviceError";
        this.status = status;
        this.code = code;
    }
}

/**
 * GET a JSON endpoint on the device.
 * @param {string} path  e.g. "/health" (without the /v1 prefix)
 * @returns {Promise<any>} the parsed JSON body
 * @throws {DeviceError}
 */
export async function deviceGet(path) {
    const response = await deviceFetch(path);
    if (!response.ok) {
        throw await errorFrom(response);
    }

    try {
        return await response.json();
    } catch {
        throw new DeviceError(502, "BAD_GATEWAY", "The analysis device sent an invalid response");
    }
}

/**
 * GET a non-JSON endpoint on the device (Deep Zoom XML, JPEG tiles, later the heatmap PNG).
 * @param {string} path
 * @returns {Promise<{contentType: string, cacheControl: string | null, body: Buffer}>}
 * @throws {DeviceError}
 */
export async function deviceGetRaw(path) {
    const response = await deviceFetch(path);

    if (!response.ok) {
        throw await errorFrom(response);
    }
    return {
        contentType: response.headers.get("content-type") ?? "application/octet-stream",
        cacheControl: response.headers.get("cache-control"),
        body: Buffer.from(await response.arrayBuffer()),
    };
}

/**
 * Fetch from the device with the token and a timeout.
 * @param {string} path  e.g. "/slides" (without the /v1 prefix)
 * @param {RequestInit} [init]  extra fetch options, e.g. method and body
 * @returns {Promise<Response>} the raw response, whatever its status
 * @throws {DeviceError} DEVICE_OFFLINE if there is no response at all
 */
async function deviceFetch(path, init = {}) {
    try {
        return await fetch(`${config.inferenceUrl}/v1${path}`, {
            ...init,
            headers: { "X-Device-Token": config.deviceToken },
            signal: AbortSignal.timeout(TIMEOUT_MS),
        });
    } catch {
        throw new DeviceError(503, "DEVICE_OFFLINE", "The analysis device is not reachable");
    }
}

/**
 * Turn a non-OK device response into a DeviceError. The device uses the
 * contract's error shape, so pass its code and message through.
 * @param {Response} response
 * @returns {Promise<DeviceError>}
 */
async function errorFrom(response) {
    let body = null;
    try {
        body = await response.json();
    } catch {
        // Not JSON, fall through to defaults below
    }

    const code = body?.error?.code ?? "INTERNAL_ERROR";
    const message = body?.error?.message ?? "The analysis device reported an error";
    return new DeviceError(response.status, code, message);
}

/**
 * POST JSON to the device and return its JSON answer.
 * @param {string} path  e.g. "/jobs"
 * @param {object} data  sent as the JSON body
 * @returns {Promise<any>} the parsed JSON body
 * @throws {DeviceError}
 */
export async function devicePost(path, data) {
    const response = await deviceFetch(path, {
        method: "POST",
        headers: { "Content-Type": "application.json" },
        body: JSON.stringify(data),
    });

    if (!response.ok) {
        throw await errorFrom(response);
    }

    try {
        return await response.json();
    } catch {
        throw new DeviceError(502, "BAD_GATEWAY", "The analysis device sent an invalid response");
    }
}

/**
 * Open a streaming endpoint on the device (the SSE progress stream).
 * The 5 s timeout covers only getting the response headers: an open
 * stream may run for minutes.
 * @param {string} path  e.g. "/jobs/<id>/events"
 * @returns {Promise<ReadableStream<Uint8Array>>} the response body, still streaming
 * @throws {DeviceError} DEVICE_OFFLINE, or the device's own error (e.g. 404)
 */
export async function deviceStream(path) {
    const controller = new AbortController();
    const timer = settimeout(() => controller.abort(), TIMEOUT_MS);
    let response;

    try {
        response = await fetch(`${config.inferenceUrl}/v1${path}`, {
            headers: { "X-Device-Token": config.deviceToken },
            signal: controller.signal,
        });
    } catch {
        throw new DeviceError(503, "DEVICE_OFFLINE", "The analysis device is not reachable");
    } finally {
        clearTimeout(timer);        // Whether connected or failed, the stream itself has no time limit
    }

    if (!response.ok) {
        throw await errorFrom(response);
    }

    return response.body;
}

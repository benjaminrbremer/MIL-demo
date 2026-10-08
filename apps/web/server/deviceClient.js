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
    let response;
    try {
        response = await fetch(`${config.inferenceUrl}/v1${path}`, {
            headers: { "X-Device-Token": config.deviceToken },
            // Without a timeout, a half-dead network can hang a request for minutes
            signal: AbortSignal.timeout(TIMEOUT_MS),
        });
    } catch {
        // We get here if there's no response at all
        throw new DeviceError(503, "DEVICE_OFFLINE", "The analysis device is not reachable");
    }

    let body;
    try {
        body = await response.json();
    } catch {
        // Something answered, but the result wasn't JSON (likely wrong service on that port)
        throw new DeviceError(502, "BAD_GATEWAY", "The analysis device sent an invalid response");
    }

    if (!response.ok) {
        // The device already uses the error shape defined in the contract
        // We want to pass it through so the UI can show a specific message per code
        const code = body?.error?.code ?? "INTERNAL_ERROR";
        const message = body?.error?.message ?? "The analysis device reported an error";
        throw new DeviceError(response.status, code, message);
    }

    // Everything went well, we can return the JSON body of the GET
    return body;
}

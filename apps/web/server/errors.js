// server/errors.js

import { DeviceError } from "./deviceClient.js";

/** 
 * Send any error to the browser in the contract shape, never leaking internals. 
 */
export function sendError(res, err) {
    if (err instanceof DeviceError) {
        res.status(err.status).json({ error: { code: err.code, message: err.message } });
        return;
    }
    // Unhandled error case indicates bug in our code. Make sure to log it
    console.error(`Unhandled ${err?.name ?? "error"} in web server`);
    res.status(500).json({ error: { code: "INTERNAL_SERVER", message: "Internal server error" } });
}

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
    res.status(500).json({ error: { code: "INTERNAL_ERROR", message: "Internal server error" } });
}

/**
 * Contract-shaped 404.
 * @param {import('express').Response} res
 */
export function sendNotFound(res) {
    res.status(404).json({ error: { code: "NOT_FOUND", message: "Not found" } });
}

/**
 * Express error handler, registered last in index.js. Express recognises it by
 * its four parameters, so `next` must stay even though it's unused.
 * Without it, a malformed JSON body gets Express's HTML error page.
 */
export function handleErrors(err, req, res, next) {
    if (err?.type === "entity.parse.failed") {
        res.status(400).json({ error: { code: "BAD_REQUEST", message: "Request body is not valid JSON" } });
        return;
    }
    sendError(res, err);
}

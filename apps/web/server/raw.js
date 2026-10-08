// server/raw.js
// Send bytes from deviceGetRaw to the browser with only allowlisted headers (D-058)

/**
 * Send device bytes to the browser with only the headers we allow.
 * @param {import('express').Response} res
 * @param {{contentType: string, cacheControl: string | null, body: Buffer}} raw
 */
export function sendRaw(res, raw) {
    res.type(raw.contentType);
    if (raw.cacheControl) {
        res.set("Cache-Control", raw.cacheControl);
    }
    res.send(raw.body);
}

/**
 * Every call from the browser goes through here, and only to /api/... (REQ-108).
 * Never throws: returns {ok, status, body} so callers handle errors explicitly.
 * @param {string} path  e.g. "/api/health"
 * @returns {Promise<{ok: boolean, status: number, body: any}>}
 */
export async function getJson(path) {
    // Only using one try here because this is browser-side:
    // a failure in either call means the user couldn't get a response
    try {
        const response = await fetch(path);
        const body = await response.json();
        return { ok: response.ok, status: response.status, body };
    } catch {
        // The Node server itself is down or non-JSON was received
        return {
            ok: false,
            status: 0,
            body: { error: { code: "WEB_SERVER_OFFLINE", message: "The web server is not reachable" } },
        };
    }
}

/**
 * POST JSON to the web server. Never throws, like getJson.
 * @param {string} path  e.g. "/api/jobs"
 * @param {object} data  sent as the JSON body
 * @returns {Promise<{ok: boolean, status: number, body: any}>}
 */
export async function postJson(path, data) {
    try {
        const response = await fetch(path, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(data),
        });
        const body = await response.json();
        return { ok: response.ok, status: response.status, body };
    } catch {
        return {
            ok: false,
            status: 0,
            body: { error: {code: "WEB_SERVER_OFFLINE", message: "The web server is not reachable" } },
        };
    }
}

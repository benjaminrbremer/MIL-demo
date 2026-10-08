/**
 * A user-facing message for every error code in docs/api-contract.md (REQ-017, D-012).
 * Pure (no DOM), so test/messages.test.js can import it and check that no
 * code in the contract is missing.
 */

export const MESSAGES = {
    // Reaching the device
    DEVICE_OFFLINE: "The analysis device is not reachable. Check that the inference service is running on the desktop and that Tailscale is connected.",
    BAD_GATEWAY: "Something answered at the device address, but it isn't the analysis service. Check INFERENCE_URL in the web server's .env.",
    WEB_SERVER_OFFLINE: "The web server is not reachable. Check that npm start is still running on this Mac, then reload.",
    UNAUTHORIZED: "The analysis device rejected the web server's token. Check that DEVICE_TOKEN is the same on both machines.",

    // Job failures
    SLIDE_UNREADABLE: "The slide file can't be read. It may have been moved or deleted, or it isn't a supported slide format.",
    NO_TISSUE: "Too little tissue was found to analyse this slide (fewer than 16 patches). Check that the scan isn't blank.",
    NO_RESOLUTION: "The slide file doesn't record its pixel size, so it can't be cut into 128 µm patches. Export it again with resolution metadata.",
    INTERRUPTED: "The analysis device restarted while this job was queued or running. Start the analysis again.",
    INFERENCE_FAILED: "The analysis failed unexpectedly. Try again; if it fails again, check the device log.",

    // Requests the device refused
    SLIDE_NOT_READY: "This slide isn't ready yet. Wait until its status is Ready.",
    JOB_ALREADY_ACTIVE: "This slide is already being analysed.",
    JOB_NOT_COMPLETED: "The heatmap is only available once the analysis has completed.",
    NOT_FOUND: "That slide or job no longer exists on the analysis device.",
    VALIDATION_ERROR: "The request had a missing or invalid slide or job ID. Reload the page.",
    BAD_REQUEST: "The server couldn't understand the request. Reload the page.",
    METHOD_NOT_ALLOWED: "The analysis device doesn't support this request. The web app and device versions may not match.",
    INTERNAL_ERROR: "Something went wrong on the server. Try again; if it keeps happening, check the server logs.",
};

/**
 * One sentence for the user, with the code at the end for support.
 * Unknown codes fall back to the server's own (client-safe) message.
 * @param {{code?: string, message?: string} | null | undefined} error
 * @returns {string}
 */
export function messageFor(error) {
    const code = error?.code ?? "UNKNOWN"
    const text = MESSAGE[code] ?? error?.message ?? "An unexpected error occurred";
    return `${text} (${code})`;
}

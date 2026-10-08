// server/ids.js
// Slide and job IDs are lowercase UUIDs (Python's str(uuid4()))
// Anything else is rejected before it reaches a device URL (D-058)

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

/**
 * @param {unknown} value  e.g. a route parameter or a field from a JSON body
 * @returns {boolean}
 */
export function isUuid(value) {
    return typeof value === "string" && UUID.test(value);
}

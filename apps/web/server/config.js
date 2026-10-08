/**
 * Settings from the environment (loaded from .env by `node --env-file`).
 * Missing required values stop the server at startup, not at the first request.
 */

function required(name) {
    const value = process.env[name];
    if (!value) {
        throw new Error(`Missing required setting ${name} (see .env.example)`);
    }
    return value;
}

export const config = {
    // Strip a trailing slash so the full inference URL + path never has "//"
    inferenceUrl: required('INFERENCE_URL').replace(/\/$/, ''),
    deviceToken: required('DEVICE_TOKEN'),
    port: Number(process.env.PORT ?? 3000),
};

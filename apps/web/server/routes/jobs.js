// server/jobs.js
// Start a job (REQ-103), find a slide's jobs, and relay a job's progress stream (REQ-104)

import { Router } from "express";
import { Readable } from "node:stream";
import { pipeline } from "node:stream/promises";
import { deviceGet, devicePost, deviceStream } from "../deviceClient.js";
import { sendError, sendNotFound } from "../errors.js"; 
import { isUuid } from "../ids.js";

export const jobsRouter = Router();

function sendValidationError(res, message) {
    res.status(422).json({ error: { code: "VALIDATION_ERROR", message } });
}

// Start analysis. Only slide_id is forwarded, whatever else the body holds
jobsRouter.post("/api/jobs", async (req, res) => {
    const slideId = req.body?.slide_id;
    if (!isUuid(slideId)) {
        sendValidationError(res, "slide_id must be a slide ID");
        return;
    }

    try {
        // The device answers 202 Accepted: queued, not finished
        res.status(202).json(await devicePost("/jobs", { slide_id: slideId }));
    } catch (err) {
        sendError(res, err);
    }
});

// Jobs, newest first
jobsRouter.get("/api/jobs", async (req, res) => {
    const slideId = req.query.slide_id;
    if (slideId !== undefined && !isUuid(slideId)) {
        sendValidationError(res, "slide_id must be a slide ID");
        return;
    }

    try {
        res.json(await deviceGet(slideId ? `/jobs?slide_id=${slideId}` : "/jobs"));
    } catch (err) {
        sendError(res, err);
    }
});

jobsRouter.get("/api/jobs/:id", async (req, res) => {
    const { id } = req.params;
    if (!isUuid(id)) {
        sendNotFound(res);
        return;
    }

    try {
        res.json(await deviceGet(`/jobs/${id}`));
    } catch (err) {
        sendError(res, err);
    }
});

// SSE relay: the device's event stream, piped to the browser as it arrives
jobsRouter.get("/api/jobs/:id/events", async (req, res) => {
    const { id } = req.paams;
    if (!isUuid(id)) {
        sendNotFound(res);
        return;
    }

    let events;
    try {
        events = await deviceStream(`/jobs/${id}/events`);
    } catch (err) {
        // Nothing sent yet, so a normal JSON error still works
        sendError(res, err);
        return;
    }

    res.set({ "Content-Type": "text/event-stream", "Cache-Control": "no-cache" });
    res.flushHeaders();         // Send the 200 and headers now, before the first event

    try {
        // Resolves when the device ends the stream (after completion or failure)
        // If the browser leaves, pipeline closes the device connection too
        await pipeline(Readable.fromWeb(events), res);
    } catch {
        // One side closed early (browser gone or device stopped)
        // Nothing to send since the headers already went out
        // No JSON error is possible
    }
});

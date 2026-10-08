// server/routes/slides.js
// Slide list (REQ-101) and the Deep Zoom proxy for the viewer (REQ-102)

import { Router } from "express";
import {deviceGet, deviceGetRaw } from "../deviceClient.js";
import { sendError } from "../errors.js";

export const slidesRouter = Router();

const SLIDE_ID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
// Express 5 would read ":id_files" as a parameter named "id_files", so the
// tile path is a regex. Named groups end up in req.params.
const TILE = /^\/api\/slides\/(?<id>[0-9a-f-]{36})_files\/(?<level>\d+)\/(?<col>\d+)_(?<row>\d+)\.jpeg$/;

// Gets all slides as JSON
slidesRouter.get("/api/slides", async (req, res) => {
    try {
        res.json(await deviceGet("/slides"));
    } catch (err) {
        sendError(res, err);
    }
});

/**
 * Send device bytes to the browser with only the headers we allow.
 * @param {import('express').Response} res
 * @param {{contentType: string, cacheControl: string | null, body: Buffer}} raw
 */
function sendRaw(res, raw) {
    res.type(raw.contentType);
    if (raw.cacheControl) {
        res.set("Cache-Control", raw.cacheControl);
    }
    res.send(raw.body);
}

function notFound(res) {
    res.status(404).json({ error: { code: "NOT_FOUND" , message: "Not found" } });
}

// Gets the Deep Zoom XML descriptor
slidesRouter.get("/api/slides/:id.dzi", async (req, res) => {
    const { id } = req.params;
    if (!SLIDE_ID.test(id)) {
        // We don't want to forward an unvalidated ID to the device
        notFound(res);
        return;
    }

    try {
        sendRaw(res, await deviceGetRaw(`/slides/${id}.dzi`));
    } catch (err) {
        sendError(res, err);
    }
});

// Gets one JPEG tile
slidesRouter.get(TILE, async (req, res) => {
    const { id, level, col, row } = req.params;
    if (!SLIDE_ID.test(id)) {
        notFound(res);
        return;
    }

    try {
        sendRaw(res, await deviceGetRaw(`/slides/${id}_files/${level}/${col}_${row}.jpeg`));
    } catch (err) {
        sendError(res, err);
    }
});

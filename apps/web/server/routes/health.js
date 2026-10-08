// server/routes/health.js

import { Router } from "express";
import { deviceGet } from "../deviceClient.js";
import { sendError } from "../errors.js";

export const healthRouter = Router();

healthRouter.get("/api/health", async (req, res) => {
    try {
        res.json(await deviceGet("/health"));
    } catch (err) {
        sendError(res, err);
    }
});

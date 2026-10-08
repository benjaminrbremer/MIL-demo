import express from "express";
import { join } from "node:path";
import { config } from "./config.js";
import { healthRouter } from "./routes/health.js";
import { slidesRouter } from "./routes/slides.js";
import { jobsRouter } from "./routes/jobs.js";
import { handleErrors, sendNotFound } from "./errors.js";

const app = express();

// Parse JSON request bodies into req.body. Only runs for requests that say
// Content-Type: application/json; for anything else req.body stays undefined.
app.use(express.json());

// Serve client/ as static files: GET / returns client/index.html
// import.meta.dirname = the folder this file is in (server/)
app.use(express.static(join(import.meta.dirname, "..", "client")));

// OpenSeadragon's browser files, straight from node_modules, so the version
// is the one pinned in package-lock.json
app.use(
    "/vendor/openseadragon",
    express.static(join(import.meta.dirname, "..", "node_modules", "openseadragon", "build", "openseadragon")),
);

app.use(healthRouter);
app.use(slidesRouter);
app.use(jobsRouter);

// Unknown /api paths: contract-shaped 404, not Express's HTML page
app.use("/api", (req, res) => sendNotFound(res));

// Errors from any other route or middleware above. This muse be last
app.use(handleErrors);

// Listen on localhost only: the browser runs on this machine
app.listen(config.port, "127.0.0.1", () => {
    console.log(`Web app on http://127.0.0.1:${config.port}`);
});

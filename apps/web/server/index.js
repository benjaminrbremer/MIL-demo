import express from "express";
import { join } from "node:path";
import { config } from "./config.js";
import { healthRouter } from "./routes/health.js";
import { slidesRouter } from "./routes/slides.js";

const app = express();

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

// Unknown /api paths: contract-shaped 404, not Express's HTML page
app.use("/api", (req, res) => {
    res.status(404).json({ error: { code: "NOT_FOUND", message: "Not found" } });
});

// Listen on localhost only: the browser runs on this machine
app.listen(config.port, "127.0.0.1", () => {
    console.log(`Web app on http://127.0.0.1:${config.port}`);
});

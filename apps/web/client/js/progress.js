/**
 * The analysis panel for the selected slide (REQ-103, REQ-104).
 * The device is the source of truth: on every selection (and so after a
 * page reload) we ask it for the slide's newest job, then follow that job's
 * event stream while it is queued or running.
 */

import { getJson, postJson } from "./api.js";

const RETRY_MS = 3000;

// The order the pipeline runs its stages in (docs/api-contract.md, job object)
const STAGES = ["segmenting", "patching", "extracting_features", "aggregating", "rendering"];
const STAGE_TEXT = {
    segmenting: "Finding tissue",
    patching: "Cutting the tissue into patches",
    extracting_features: "Extracting patch features",
    aggregating: "Scoring the slide",
    rendering: "Rendering heatmap and quality metrics",
};

const startButton = document.querySelector("#start-analysis");
const statusLine = document.querySelector("#job-status");
const bar = document.querySelector("#job-progress");
const detail = document.querySelector("#job-detail");

let slideId = null;         // The selected slide
let job = null;             // The newest job we know of for it, or null if none
let source = null;          // The open EventSource, or null
let loading = false;        // Waiting for the slide's jobs or for a POST

/** 
 * @param {object|null} j  a job object 
 */
function isActive(j) {
    return j !== null && (j.status === "queued" || j.status === "running");
}

function renderProgress() {
    const { done, total } = job.progress;
    bar.hidden = false;
    if (done !== null && total) {
        bar.max = total;
        bar.value = done;
        detail.textContent = `${done.toLocaleString()} of ${total.toLocaleString()} patches`;
    } else {
        // No count for this stage: an indeterminate bar (the animated one)
        bar.removeAttribute("value");
        detail.textContent = "";
    }
}

/** 
 * Draw the panel from slideId, job and loading. 
 */
function render() {
    startButton.disabled = slideId === null || loading || isActive(job);
    bar.hidden = true;
    detail.textContent = "";

    if (slideId === null) {
        statusLine.textContent = "Select a ready slide to analyze it.";
    } else if (loading) {
        statusLine.textContent = "Loading...";
    } else if (job === null) {
        statusLine.textContent = "This slide hasn't been analyzed yet.";
    } else if (job.status === "queued") {
        statusLine.textContent = "Queued: waiting for the GPU.";
        renderProgress();
    } else if (job.status === "running") {
        const step = STAGES.indexOf(job.stage) + 1;
        statusLine.textContent = step > 0 
            ? `Step ${step} of ${STAGES.length}: ${STAGE_TEXT[job.stage]}` 
            : "Starting...";
        renderProgress();
    } else if (job.status === "completed") {
        statusLine.textContent = "Analysis complete."       // Results panel added in a future effort
    } else {
        statusLine.textContent = `Analysis failed: ${job.error.message} (${job.error.code})`;
    }
}

function stopFollowing() {
    source?.close();
    source = null;
}

/**
 * Follow a job's progress stream until it completes or fails.
 * @param {string} jobId
 */
function follow(jobId) {
    stopFollowing();
    const followedSlide = slideId;
    const es = new EventSource(`/api/jobs/${jobId}/events`);
    source = es;

    // Named events need addEventListener: onmessage only sees unnamed ones
    es.addEventListener("snapshot", (event) => {
        job = JSON.parse(event.data);
        render();
    });
    es.addEventListener("progress", (event) => {
        // A progress event has only status, stage, and progress
        job = { ...job, ...JSON.parse(event.data) };
        render();
    });
    for (const name of ["completed", "failed"]) {
        es.addEventListener(name, (event) => {
            job = JSON.parse(event.data);
            stopFollowing();    // Otherwise EventSource reconnects when the device closes the stream
            render();
        });
    }
    es.addEventListener("error", () => {
        if (es.readyState === EventSource.CONNECTING) {
            // The browser is already reconnecting; the next snapshot catches up
            statusLine.textContent = "Connection lost. Reconnecting...";
            return;
        }
        // CLOSED: Node answered with an error instead of a stream 
        // This indicates device is offline, or the job is gone
        // Ask again in a few seconds
        stopFollowing();
        statusLine.textContent = "Can't reach the analysis device. Retrying...";
        setTimeout(() => {
            if (slideId === followedSlide) showJobFor(followedSlide);
        }, RETRY_MS);
    });
}

/**
 * Show the newest job for a slide, and follow it if it's still running.
 * Called on every selection, including the one restored after a reload.
 * @param {string} id  a ready slide's ID
 */
export async function showJobFor(id) {
    stopFollowing();
    slideId = id;
    job = null;
    loading = true;
    render();

    const { ok, body } = await getJson(`/api/jobs?slide_id=${id}`);
    if (slideId !== id) return;         // The user picked another slide while we waited
    loading = false;
    if (!ok) {
        render();
        statusLine.textContent = `Can't load this slide's analysis: ${body.error.message}`;
        return;
    }
    job = body[0] ?? null;      // Newest first (contract)
    render();
    if (isActive(job)) {
        follow(job.id);
    }
}

startButton.addEventListener("click", async () => {
    const id = slideId;
    loading = true;         // disables the button: no double submit
    render();

    const { ok, body } = await postJson("/api/jobs", { slide_id: id });
    if (slideId !== id) return;
    loading = false;
    if (ok) {
        job = body;         // status "queued"
        render();
        follow(job.id);
    } else if (body.error.code === "JOB_ALREADY_ACTIVE") {
        // Started elsewhere (another tab): follow that job instead
        showJobFor(id);
    } else {
        render();
        statusLine.textContent = `Can't start analysis: ${body.error.message}`;
    }
});

render();

/**
 * The slide list: polls /api/slides and renders one button per slide (REQ-101).
 * Only ready slides can be selected; the selection survives every refresh.
 */

import { getJson } from "./api.js";
import { messageFor } from "./messages.js";

const POLL_MS = 3000;

const list = document.querySelector("#slide-list");
const status = document.querySelector("#slide-list-status");

/** 
 * The slide ID saved in the URL (#slide=<id>), or null. 
 */
function slideFromUrl() {
    return new URLSearchParams(location.hash.slice(1)).get("slide");
}

let selectedId = slideFromUrl();    // Restored after a reload (REQ-104)
let restored = false;               // has the restored selection been checked yet?
let lastJson = null;                // The last list we rendered, as a string
let onSelect = () => {};

const STATUS_TEXT = {
    arriving: "Arriving...",
    registering: "Registering...",
    ready: "Ready",
    unreadable: "Unreadable",
};

/**
 * One list item for one slide.
 * @param {{id: string, status: string, width: number|null, height: number|null,
 *          detected_at: string, error: {code: string, message: string}|null}} slide
 * @returns {HTMLLIElement}
 */
function renderSlide(slide) {
    const item = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.slideId = slide.id;
    button.disabled = slide.status !== "ready";
    if (slide.id === selectedId) {
        button.setAttribute("aria-current", "true");
    }

    // No filename exists in the API (REQ-006), so the ID is the label
    const name = document.createElement("span");
    name.textContent = `Slide ${slide.id.slice(0, 8)}`;

    const state = document.createElement("span");
    state.className = `status status-${slide.status}`;
    state.textContent = `  - ${STATUS_TEXT[slide.status] ?? slide.status}`;

    const details = document.createElement("div");
    details.className = "muted";
    const parts = [`detected ${new Date(slide.detected_at).toLocaleString()}`];
    if (slide.width && slide.height) {
        parts.unshift(`${slide.width.toLocaleString()} x ${slide.height.toLocaleString()} px`);
    }
    if (slide.error) {
        parts.push(messageFor(slide.error));
    }
    details.textContent = parts.join("  -  ");

    button.append(name, state, details);
    item.append(button);
    return item;
}

/** 
 * @param {Array<object>} slides 
 */
function render(slides) {
    if (slides.length === 0) {
        list.replaceChildren();
        status.textContent = "No slides on the device yet. Copy one into the acquisition folder.";
        return;
    }
    status.textContent = "";
    list.replaceChildren(...slides.map(renderSlide));
}

async function refresh() {
    const { ok, body } = await getJson("/api/slides");
    if (!ok) {
        // Keep showing the last list; the health banner explains the outage.
        status.textContent = lastJson 
            ? `Can't refresh the list (${body.error.code}). Showing the last known slides.` 
            : `Can't load slides: ${messageFor(body.error)}`;
        return;
    }

    const json = JSON.stringify(body);
    if (json === lastJson) {
        return;     // Nothing changed, so don't touch anything
    }

    // If JSON changed, re-render body and update lastJson
    lastJson = json;
    const restoring = !restored;
    if (restoring) {
        restored = true;
        // Only reopen it if it's still a ready slide on the device
        const slide = body.find((s) => s.id === selectedId);
        if (slide?.status !== "ready") selectedId = null;
    }
    render(body);
    if (restoring && selectedId) onSelect(selectedId);
}

async function pollLoop() {
    await refresh();
    // Schedule the next one only after this one finishes
    // setInterval() could send another request before the first returns on a slow network
    // This could lead to out-of-order responses, giving a state response race
    // setTimeout is safe
    setTimeout(pollLoop, POLL_MS)
}

list.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-slide-id]");
    if (!button || button.disabled) return;
    selectedId = button.dataset.slideId;

    // replaceState, not location.hash = ...: no back-button entry per clock
    history.replaceState(null, "", `#slide=${selectedId}`);

    // Re-render from the last data to move the highlight when something new is selected
    render(JSON.parse(lastJson));
    onSelect(selectedId);
});

/**
 * Start polling.
 * @param {{onSelect: (slideId: string) => void}} options  called when the user picks a ready slide
 */
export function startSlideList(options) {
    onSelect = options.onSelect;
    pollLoop();
}

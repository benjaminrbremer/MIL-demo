/**
 * The slide viewer (REQ-102). Wraps OpenSeadragon, loaded as a classic
 * script that defines the global `OpenSeadragon`.
 */

const container = document.querySelector("#viewer");
const message = document.querySelector("#viewer-message");

let viewer = null;          // Created on first use
let heatmap = null;         // The overlay TiledImage, once it has loaded
let heatmapJobId = null;    // The job whose heatmap is shown or loading
let heatmapRequest = 0;     // Bumped on every add and clear: older callbacks see a mismatch
let heatmapVisible = true;  // The checkbox
let heatmapOpacity = 0.5;   // The slider, 0 to 1

function getViewer() {
    if (viewer) return viewer;
    viewer = OpenSeadragon({
        element: container,
        prefixUrl: "/vendor/openseadragon/images/",  // button icons
        showNavigator: true,                        // the small overview map
        maxZoomPixelRatio: 2,                       // don't zoom far past full resolution
    });

    // addHandler() is OpenSeadragon's equivalent of addEventListener()
    viewer.addHandler("open", () => {
        message.textContent = "";
    });
    viewer.addHandler("open-failed", () => {
        // The .dzi request failed: slide not ready, file removed (D-029), or device offline
        container.hidden = true;
        message.textContent = "This slide could not be opened. It may no longer be readable.";
    });
    return viewer;
}

/**
 * Show a slide. OpenSeadragon fetches the .dzi, then the tiles it needs.
 * Safe from stale responses because open() cancels previous request if new one is made before 
 * previous is filled.
 * No fetch needed here because OpenSeadragon makes its own requests
 * @param {string} slideId
 */
export function showSlide(slideId) {
    clearHeatmap();     // open() empties the world; this also cancels a heatmap still loading
    container.hidden = false;
    message.textContent = "Loading...";
    // Relative /api URL: the browser never learns the device address (REQ-108)
    getViewer().open(`/api/slides/${slideId}.dzi`);
}

function applyOpacity() {
    heatmap?.setOpacity(heatmapVisible ? heatmapOpacity : 0);
}

/** 
 * Remove the overlay, and make any heatmap still loading discard itself. 
 */
export function clearHeatmap() {
    heatmapRequest += 1;
    if (heatmap) {
        viewer.world.removeItem(heatmap);
    }
    heatmap = null;
    heatmapJobId = null;
}

/**
 * Lay a completed job's attention heatmap over the current slide.
 * @param {string} jobId
 * @param {{onError: () => void}} options  called if the PNG can't be loaded
 */
export function showHeatmap(jobId, options) {
    if (heatmapJobId === jobId) return;     // Already shown or on its way
    clearHeatmap();
    heatmapJobId = jobId;
    const request = heatmapRequest;

    getViewer().addSimpleImage({
        // Relative /api URL, like the slide (REQ-108)
        url: `/api/jobs/${jobId}/heatmap.png`,
        // The PNG covers exactly the slide's level-0 rectangle (D-053), and the 
        // slide is 1 viewport unit wide, so this lines them up
        x: 0,
        y: 0,
        width: 1,
        opacity: heatmapVisible ? heatmapOpacity : 0,
        success: (event) => {
            if (request !== heatmapRequest) {
                // The user moved on while it loaded: OpenSeadragon has just
                // added it to whatever slide is open now, so take it out again
                viewer.world.removeItem(event.item);
                return;
            }
            heatmap = event.item;
            applyOpacity();         // Controls may have changed while image was loading
        },
        error: () => {
            if (request !== heatmapRequest) return;
            heatmapJobId = null;
            options.onError();
        },
    });
}

/** 
 * @param {boolean} visible 
 */
export function setHeatmapVisible(visible) {
    heatmapVisible = visible;
    applyOpacity();
}

/** 
 * @param {number} opacity  0 (invisible) to 1 (opaque) 
 */
export function setHeatmapOpacity(opacity) {
    heatmapOpacity = opacity;
    applyOpacity();
}

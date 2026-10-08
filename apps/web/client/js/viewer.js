/**
 * The slide viewer (REQ-102). Wraps OpenSeadragon, loaded as a classic
 * script that defines the global `OpenSeadragon`.
 */

const container = document.querySelector("#viewer");
const message = document.querySelector("#viewer-message");

let viewer = null;      // Created on first use

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
    container.hidden = false;
    message.textContent = "Loading...";
    // Relative /api URL: the browser never learns the device address (REQ-108)
    getViewer().open(`/api/slides/${slideId}.dzi`);
}

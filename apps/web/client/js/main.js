import { getJson } from './api.js';
import { startSlideList } from './slideList.js';
import { showSlide } from './viewer.js';
import { showJobFor, startProgress } from "./progress.js";
import { showResult } from "./results.js";
import { messageFor } from "./messages.js";

// Note how these line up with the divs in index.HTML
const banner = document.querySelector("#offline-banner");
const modelList = document.querySelector("#model-list");

function showBanner(text) {
    banner.textContent = text;
    banner.hidden = false;
}

function renderModels(models) {
    modelList.replaceChildren();
    for (const model of models) {
        const item = document.createElement("li");
        item.textContent = `${model.role}: ${model.name} @ ${model.version}`;
        modelList.append(item);
    }
}

async function checkHealth() {
    const { ok, body } = await getJson("/api/health");

    if (!ok) {
        showBanner(messageFor(body.error));
        return;
    }
    banner.hidden = true;
    renderModels(body.models);
}

checkHealth();
startSlideList({ 
    onSelect: (slideId) => {
        showSlide(slideId);
        showJobFor(slideId);
    },
});
startProgress({ onResult: showResult });

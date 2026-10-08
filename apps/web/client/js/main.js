import { getJson } from "./api.js";

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
        showBanner(
            body.error.code === "DEVICE_OFFLINE" 
            ? "Analysis device offline. Check that the inference service is running." 
            : `Error: ${body.error.message}`);
            return;
    }
    banner.hidden = true;
    renderModels(body.models);
}

checkHealth();

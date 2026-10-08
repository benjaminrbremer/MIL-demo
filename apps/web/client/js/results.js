/**
 * The results panel for a completed job (REQ-105) and its heatmap
 * controls (REQ-106). Decisions live in describe.js; this file only draws.
 */

import { describeResult } from "./describe.js";
import { clearHeatmap, setHeatmapOpacity, setHeatmapVisible, showHeatmap } from "./viewer.js";

const panel = document.querySelector(".results-panel");
const prediction = document.querySelector("#result-prediction");
const probabilityList = document.querySelector("#result-probabilities");
const warningBox = document.querySelector("#result-warnings");
const resultMessage = document.querySelector("#result-message");
const metricList = document.querySelector("#result-metrics");
const modelList = document.querySelector("#result-models");
const controls = document.querySelector("#heatmap-controls");
const visibleBox = document.querySelector("#heatmap-visible");
const opacitySlider = document.querySelector("#heatmap-opacity");
const heatmapMessage = document.querySelector("#heatmap-message");

/** 
 * @param {string} text 
 */
function warning(text) {
    const box = document.createElement("p");
    box.className = "warning";
    box.setAttribute("role", "alert");      // announced as soon as it appears
    box.textContent = text;
    return box;
}

/** 
 * @param {Array<[string, string]>} pairs 
 */
function renderMetrics(pairs) {
    metricList.replaceChildren(...pairs.flatMap(([label, value]) => {
        const dt = document.createElement("dt");
        dt.textContent = label;
        const dd = document.createElement("dd");
        dd.textContent = value;
        return [dt, dd];
    }));
}

/** 
 * @param {object} job  a completed job 
 */
function renderModels(job) {
    modelList.replaceChildren(...job.models.map((model) => {
        const item = document.createElement("li");
        item.textContent = `${model.role}: ${model.name} @ ${model.version}`;
        return item;
    }));
    const seconds = Object.values(job.timings_s).reduce((sum, s) => sum + s, 0);
    const total = document.createElement("li");
    total.textContent = `Analysis time: ${seconds.toFixed(1)} s`;
    modelList.append(total);
}

/**
 * Show a completed job's result, or hide the panel (null).
 * @param {object|null} job
 */
export function showResult(job) {
    if (job === null) {
        panel.hidden = true;
        clearHeatmap();
        return;
    }
    panel.hidden = false;
    heatmapMessage.textContent = "";

    if (job.result === null) {
        // Completed by the early stub pipeline: there's nothing to show (D-036)
        prediction.textContent = "No result recorded for this job";
        probabilityList.replaceChildren();
        warningBox.replaceChildren();
        resultMessage.textContent = "Run the analysis again to get a result.";
        renderMetrics([]);
        controls.disabled = true;
        clearHeatmap();
        return;
    }

    const view = describeResult(job.result);
    prediction.textContent = `Model prediction: ${view.prediction}`;
    probabilityList.replaceChildren(...view.probabilities.map(({ label, value }) => {
        const item = document.createElement("li");
        item.textContent = `${label}: ${value}`;
        return item;
    }));
    warningBox.replaceChildren(...view.warnings.map(warning));
    resultMessage.textContent = view.checksMissing ? "Uncertainty and quality checks weren't run for this job (it finished before that feature existed). Run it again to get them." : "";
    renderMetrics(view.metrics);
    renderModels(job);

    controls.disabled = false;
    showHeatmap(job.id, {
        onError: () => {
            controls.disabled = true;
            heatmapMessage.textContent = view.checksMissing ? "This job has no heatmap (it finished before the feature existed)." : "The heatmap couldn't be loaded. Select the slide again to retry.";
        },
    });
}

visibleBox.addEventListener("change", () => setHeatmapVisible(visibleBox.checked));
// "input" fires continuously while dragging: "change" only on release
opacitySlider.addEventListener("input", () => setHeatmapOpacity(opacitySlider.value / 100));

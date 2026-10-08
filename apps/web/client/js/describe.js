/**
 * Turn a completed job's result into plain display data (REQ-105).
 * Pure (no DOM), so test/describe.test.js can check the decisions.
 */

// Class names come from the model config (docs/spike-findings.md)
const CLASS_TEXT = {
    "metastasis":  "Metastasis",
    "no-metastasis": "No metastasis",
};

/** 
 * @param {number} p  a fraction, e.g. 0.912 → "91.2%" 
 */
export function percent(p) {
    return `${(p * 100).toFixed(1)}%`;
}

/** 
 * @param {string} name  a class name from the model 
 */
function classText(name) {
    return CLASS_TEXT[name] ?? name;    // an unknown class will still show by its raw name
}

/**
 * @param {object} result  job.result from the contract (not null)
 * @returns {{
 *   prediction: string,
 *   probabilities: Array<{label: string, value: string}>,
 *   warnings: string[],
 *   metrics: Array<[string, string]>,
 *   checksMissing: boolean,
 * }}
 */
export function describeResult(result) {
    const probabilities = Object.entries(result.probabilities)
        .sort(([, a], [, b]) => b - a)      // Highest first
        .map(([name, p]) => ({ label: classText(name), value: percent(p) }));
    
    const warnings = [];
    if (result.uncertain === true) {
        const p = result.probabilities[result.predicted_class];
        const [low, high] = result.uncertainty.band;
        warnings.push(
            `Uncertain result: the model gave ${percent(p)}, inside the uncertainty band ` + 
            `(${percent(low)} to ${percent(high)}). Treat this prediction as inconclusive.`,
        );
    }

    const quality = result.quality;
    if (quality?.segmentation_suspect) {
        warnings.push(
            `Check the segmentation tissue was found on ${percent(quality.tissue_fraction)} of the slide, ` + 
            "so background may have been analyzed as tissue. Look at the heatmap before relying on this result.",
        );
    }

    const metrics = quality === null ? [] : [
        ["Tussue area", `${quality.tissue_area_mm2.toFixed(1)} mm^2`],
        ["Tissue fraction", percent(quality.tissue_fraction)],
        ["Patches analyzed", quality.patch_count.toLocaleString()],
        ["Blur", quality.blur_fraction === null ? "Not measured in this version" : percent(quality.blur_fraction)],
    ];

    return {
        prediction: classText(result.predicted_class),
        probabilities,
        warnings,
        metrics,
        // Jobs completed before recent update have no uncertainty or quality checks
        checksMissing: result.uncertain === null,
    };
}

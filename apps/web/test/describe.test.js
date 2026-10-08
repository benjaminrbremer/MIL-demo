/**
 * describeResult (REQ-105): what the results panel shows for a completed
 * job's result. describe.js has no DOM code, so Node can import it as is.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { describeResult, percent } from '../client/js/describe.js';

/** A result shaped like the contract's, from a real test_065 run. */
function resultObject(overrides = {}) {
  return {
    probabilities: { 'no-metastasis': 0.0638, metastasis: 0.9362 },
    predicted_class: 'metastasis',
    uncertain: false,
    uncertainty_band: [0.3, 0.7],
    quality: {
      tissue_area_mm2: 21.06,
      tissue_fraction: 0.0983,
      patch_count: 1294,
      blur_fraction: null,
      segmentation_suspect: false,
    },
    ...overrides,
  };
}

const values = (metrics) => metrics.map(([, value]) => value);

test('percent shows a fraction with one decimal place', () => {
  assert.equal(percent(0.912), '91.2%');
  assert.equal(percent(0.3), '30.0%');
  assert.equal(percent(1), '100.0%');
});

test('req_105: a confident result shows the prediction, probabilities and metrics, with no warnings', () => {
  const view = describeResult(resultObject());

  assert.equal(view.prediction, 'Metastasis');
  // Highest first, whatever order the device sent them in.
  assert.deepEqual(view.probabilities, [
    { label: 'Metastasis', value: '93.6%' },
    { label: 'No metastasis', value: '6.4%' },
  ]);
  assert.deepEqual(view.warnings, []);
  assert.equal(view.checksMissing, false);
  assert.deepEqual(values(view.metrics), ['21.1 mm^2', '9.8%', (1294).toLocaleString(), 'Not measured in this version']);
});

test('req_105: an uncertain result warns, giving the probability and the band', () => {
  const view = describeResult(resultObject({
    probabilities: { 'no-metastasis': 0.45, metastasis: 0.55 },
    uncertain: true,
  }));

  assert.equal(view.prediction, 'Metastasis'); // still shown, but with the warning
  assert.equal(view.warnings.length, 1);
  assert.match(view.warnings[0], /^Uncertain result/);
  assert.match(view.warnings[0], /55\.0%/);
  assert.match(view.warnings[0], /30\.0% to 70\.0%/);
});

test('req_105: the uncertainty warning follows the device flag, not the client', () => {
  // The device decides (REQ-012, bounds included); the browser never
  // recomputes it, so a 0.55 the device calls certain gets no warning.
  const view = describeResult(resultObject({
    probabilities: { 'no-metastasis': 0.45, metastasis: 0.55 },
    uncertain: false,
  }));

  assert.deepEqual(view.warnings, []);
});

test('req_105: a segmentation-suspect result warns with the tissue fraction', () => {
  const view = describeResult(resultObject({
    quality: { ...resultObject().quality, tissue_fraction: 0.72, segmentation_suspect: true },
  }));

  assert.equal(view.warnings.length, 1);
  assert.match(view.warnings[0], /segmentation/i);
  assert.match(view.warnings[0], /72\.0%/);
});

test('req_105: an uncertain and suspect result shows both warnings', () => {
  const view = describeResult(resultObject({
    uncertain: true,
    quality: { ...resultObject().quality, tissue_fraction: 0.65, segmentation_suspect: true },
  }));

  assert.equal(view.warnings.length, 2);
});

test('req_105: a measured blur fraction is shown as a percentage', () => {
  const view = describeResult(resultObject({
    quality: { ...resultObject().quality, blur_fraction: 0.125 },
  }));

  assert.equal(values(view.metrics)[3], '12.5%');
});

test('req_105: a job from before item 7 has no checks: no warnings, no metrics, flagged as missing', () => {
  const view = describeResult(resultObject({ uncertain: null, uncertainty_band: null, quality: null }));

  assert.equal(view.prediction, 'Metastasis');
  assert.deepEqual(view.warnings, []);
  assert.deepEqual(view.metrics, []);
  assert.equal(view.checksMissing, true);
});

test('an unknown class name is shown as the model gives it', () => {
  const view = describeResult(resultObject({
    probabilities: { 'no-metastasis': 0.2, 'isolated-cells': 0.8 },
    predicted_class: 'isolated-cells',
  }));

  assert.equal(view.prediction, 'isolated-cells');
  assert.equal(view.probabilities[0].label, 'isolated-cells');
});

#!/usr/bin/env node
/*
 * smoke_test.js - catch runtime errors in the dashboard that a parse check misses.
 *
 *   node smoke_test.js            # test house_power_dashboard.html
 *   node smoke_test.js some.html  # test a specific file
 *
 * Why this exists: a `new Function(script)` parse check only proves the syntax is
 * valid. It says nothing about whether a card actually renders. A structural edit
 * once deleted the line `let selectedMonthlyIdx = null, monthlyAccuracyAnimate = true;`
 * and the Monthly Bill Estimate chart silently drew nothing for a day - it threw
 * "monthlyAccuracyAnimate is not defined" at run time while still parsing fine.
 *
 * This stubs every element id found in the HTML, then actually CALLS every
 * top-level function and reports which ones throw. Run it after any structural
 * edit, before publishing.
 *
 * Exit code 0 = clean, 1 = something threw.
 */
const fs = require('fs');
const path = require('path');

const target = process.argv[2] || path.join(__dirname, 'house_power_dashboard.html');
const html = fs.readFileSync(target, 'utf8');

const m = html.match(/<script>([\s\S]*)<\/script>/);
if (!m) { console.error('no <script> block found in ' + target); process.exit(1); }
const script = m[1].replace(/\/\/ ---------- INIT ----------[\s\S]*$/, '');

// stub every id the page references, so nothing is missing for the wrong reason
const ids = [...new Set([...html.matchAll(/id="([\w-]+)"/g)].map(x => x[1]))];
const reg = {};
ids.forEach(i => reg[i] = {
  id: i, innerHTML: '', innerText: '', value: '', min: '0', max: '100',
  checked: false, disabled: false, style: {},
  options: { length: 0 },              // <select>.options - updateSim reads this
  appendChild() {}, insertBefore() {}, remove() {}, setAttribute() {},
  addEventListener() {}, querySelector: () => null,
});

global.document = {
  getElementById: id => reg[id] || null,
  createElement: () => ({ style: {}, innerHTML: '', appendChild() {}, setAttribute() {} }),
  querySelectorAll: () => [],
};
global.localStorage = {
  _d: {}, getItem(k) { return this._d[k] ?? null; },
  setItem(k, v) { this._d[k] = v; }, removeItem(k) { delete this._d[k]; },
};
global.window = global;
global.alert = () => {};
global.fetch = () => new Promise(() => {});   // never resolves - not testing network here

// Functions that need a real user gesture, real network, or arguments.
// These are exercised by hand, not here.
const SKIP = new Set([
  'loadCurrentWeather', 'toggleNote', 'togglePerfNote', 'showTab', 'setTemp',
  'shiftRecent', 'selectRecentDay', 'selectMonthlyAccuracy', 'applyOutagePreset',
  'addCustomBattery', 'addCustomAppliance', 'removeCustomBattery', 'removeCustomAppliance',
  'setChecked', 'setStation', 'appendApplianceOption', 'makeBatteryRowEl',
  'makeApplianceRowEl', 'makeEgoDirectRowEl', 'egoBatteryOptionsHtml', 'stationOptionsHtml',
  'fmtDateNice', 'actualElecCost', 'electricDaily', 'gasDaily', 'getElectricConfidence',
  'getGasConfidence', 'loadCustomList', 'saveCustomList', 'allBatteries', 'allAppliances',
]);

const names = [...script.matchAll(/^function (\w+)\(/gm)].map(x => x[1]);

eval(script + `
;(function(){
  const skip = new Set(${JSON.stringify([...SKIP])});
  const names = ${JSON.stringify(names)};
  const bad = [];
  let ok = 0, skipped = 0;
  names.forEach(n => {
    if (skip.has(n)) { skipped++; return; }
    try { eval(n + '()'); ok++; }
    catch (e) { bad.push([n, e.message]); }
  });
  console.log('file    : ' + ${JSON.stringify(path.basename(target))});
  console.log('called  : ' + ok + ' ok, ' + bad.length + ' failed (' + skipped + ' skipped by design)');
  if (bad.length) {
    console.log('\\nFAILURES:');
    bad.forEach(([n, msg]) => console.log('  ! ' + n + '() -> ' + msg));
    process.exitCode = 1;
  } else {
    console.log('all render functions executed cleanly');
  }
})();
`);

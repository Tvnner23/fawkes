"use strict";
// Execute the exact Python companion expressions against a bounded DOM model.
// The real-design DOM and Matrix return are separately exercised in a browser.
const fs = require("fs");
const vm = require("vm");
const assert = require("assert");
const input = JSON.parse(fs.readFileSync(0, "utf8"));
const kind = input.case;
const shell = {dataset: {page: "4", projectionState: kind === "not_live" ? "stale" : "live"}};
const page = {hidden: true};
let clicks = 0;
const attributes = {"data-page-target": "0"};
const control = {
  textContent: kind === "legacy" ? "Summary" : kind === "translated" ? "Résumé" :
    "01 / BRIEFING Summary What happened. What comes next.",
  disabled: kind === "disabled",
  getAttribute(name) {
    if (name === "aria-disabled" && kind === "aria_disabled") return "true";
    return attributes[name] || null;
  },
  click() {
    clicks++;
    if (kind === "navigation_noop") return;
    shell.dataset.page = "0";
    page.hidden = kind === "hidden_page";
    attributes["aria-current"] = kind === "wrong_aria" ? "false" : "page";
  }
};
const controls = ["missing_control", "restore_missing"].includes(kind) ? [] :
  ["duplicate_control", "restore_duplicate"].includes(kind) ? [control, control] : [control];
const pages = kind === "missing_page" ? [] : kind === "duplicate_page" ? [page, page] : [page];
const document = {
  readyState: "complete", activeElement: "reply-composer", scrollTop: 173,
  querySelectorAll(selector) {
    if (selector === '#dev-console button[data-page-target="0"]') return controls;
    if (selector === '#dev-console .console-page[data-page="0"]') return pages;
    throw Error("Unexpected selector " + selector);
  },
  querySelector(selector) {
    if (selector === "#preview-context" || selector === "#connection-state") return null;
    if (selector === 'meta[name="fawkes-console-context"]')
      return {content: kind === "wrong_context" ? "ACCEPTED:another" : input.context};
    if (selector === "#dev-console") return shell;
    if (selector === '[data-page-target="0"]') return controls[0] || null;
    if (selector === '#dev-console .console-page[data-page="0"]') return pages[0] || null;
    throw Error("Unexpected selector " + selector);
  }
};
const context = vm.createContext({
  document, window: {},
  location: {origin: ["wrong_origin", "restore_wrong_origin"].includes(kind) ?
    "https://not-the-pi.invalid" : "http://127.0.0.1:8791",
    pathname: kind === "wrong_path" ? "/other" : "/dev-console"}
});
const result = {old_text_found: /^summary$/i.test(control.textContent.trim())};
if (kind.startsWith("restore")) {
  result.restored = vm.runInContext(input.expressions.RESTORE_CONTROLS, context);
} else {
  result.startup = vm.runInContext(input.expressions.SUMMARY, context);
  result.controls_before_matrix = vm.runInContext(input.expressions.CONTROLS_READY, context);
  context.window.__fawkesMatrix = {};
  result.controls_after_matrix = vm.runInContext(input.expressions.CONTROLS_READY, context);
}
Object.assign(result, {page: shell.dataset.page, clicks, focus: document.activeElement,
  scroll: document.scrollTop, config: context.window.__fawkesMatrixConfig || null});
assert(clicks <= 1, "At most the selected startup button may be clicked");
console.log(JSON.stringify(result));

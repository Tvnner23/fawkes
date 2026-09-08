(function (root, factory) {
  "use strict";
  const api = factory(root);
  if (typeof module === "object" && module.exports) module.exports = api;
  root.FawkesDevConsole = api;
})(typeof globalThis === "object" ? globalThis : this, function (root) {
  "use strict";

  const ENDPOINTS = Object.freeze({
    projection: "/api/development/dev-console"
  });
  const PROJECTION_SCHEMA = "fawkes.dev_console.read_only.v1";
  const PAGE_TITLES = Object.freeze([
    "Activity Summary",
    "Campaign Status",
    "Repository View",
    "Architecture View"
  ]);
  const ATTENTION_ID = /^attention-[a-f0-9]{64}$/;
  const HEX_DIGEST = /^[a-f0-9]{64}$/;
  const SAFE_ID = /^[A-Za-z0-9][A-Za-z0-9._:/-]*$/;
  const TERMINAL_CAMPAIGN_STATES = new Set([
    "succeeded", "failed_safe", "cancelled", "denied", "expired"
  ]);

  function isObject(value) {
    return value !== null && typeof value === "object" && !Array.isArray(value);
  }

  function safeText(value, maximum) {
    const limit = Number.isInteger(maximum) ? maximum : 240;
    if (typeof value !== "string" && typeof value !== "number" && typeof value !== "boolean") return "";
    return String(value)
      .replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/g, "")
      .trim()
      .slice(0, limit);
  }

  function safeIdentifier(value, maximum) {
    const text = safeText(value, maximum || 180);
    return SAFE_ID.test(text) ? text : "";
  }

  function safeDigest(value) {
    const text = safeText(value, 64).toLowerCase();
    return HEX_DIGEST.test(text) ? text : "";
  }

  function finiteInteger(value, fallback) {
    const number = Number(value);
    return Number.isSafeInteger(number) && number >= 0 ? number : fallback;
  }

  function parseIdleSeconds(value, fallback) {
    const fallbackValue = Number.isFinite(Number(fallback)) ? Number(fallback) : 60;
    const parsed = value === null || value === undefined || value === "" ? NaN : Number(value);
    const selected = Number.isFinite(parsed) ? Math.round(parsed) : Math.round(fallbackValue);
    return Math.max(15, Math.min(600, selected));
  }

  function classifyProjectionState(options) {
    const value = options || {};
    if (value.mode === "sample") return "sample";
    if (value.previousSuccess && (!value.currentSuccess || value.malformed || value.buildMismatch || value.disconnected)) {
      return "stale";
    }
    if (value.disconnected) return "disconnected";
    if (value.malformed) return "unavailable";
    if (!value.currentSuccess) return "unavailable";
    if (value.buildMismatch) return "stale";
    const now = Number.isFinite(value.nowMs) ? value.nowMs : Date.now();
    const observed = Number.isFinite(value.observedAtMs) ? value.observedAtMs : now;
    const threshold = Number.isFinite(value.staleAfterMs) ? Math.max(1, value.staleAfterMs) : 30000;
    return now - observed > threshold ? "stale" : "live";
  }

  function isHorizontalSwipe(startX, startY, endX, endY, options) {
    const value = options || {};
    if (value.codeScroll) return false;
    const threshold = Number.isFinite(value.threshold) ? value.threshold : 54;
    const ratio = Number.isFinite(value.ratio) ? value.ratio : 1.5;
    const dx = Number(endX) - Number(startX);
    const dy = Number(endY) - Number(startY);
    if (![dx, dy].every(Number.isFinite)) return false;
    return Math.abs(dx) >= threshold && Math.abs(dx) > Math.abs(dy) * ratio;
  }

  function safeAttentionHref(rawUrl, attentionId, baseUrl) {
    if (!ATTENTION_ID.test(String(attentionId || "")) || typeof rawUrl !== "string"
        || rawUrl.length > 2048 || !/^https?:\/\//.test(rawUrl)) return "";
    try {
      const base = new URL(baseUrl || "http://localhost/");
      const parsed = new URL(rawUrl, base);
      if (!/^https?:$/.test(parsed.protocol) || parsed.username || parsed.password || parsed.hash) return "";
      if (parsed.origin !== base.origin) return "";
      if (parsed.pathname !== "/") return "";
      const keys = Array.from(parsed.searchParams.keys());
      if (keys.length !== 3 || new Set(keys).size !== 3) return "";
      if (parsed.searchParams.get("view") !== "developer"
          || parsed.searchParams.get("section") !== "attention") return "";
      const values = parsed.searchParams.getAll("attention");
      if (values.length !== 1 || values[0] !== attentionId) return "";
      return rawUrl;
    } catch (_error) {
      return "";
    }
  }

  function normalizeWorker(value) {
    if (!isObject(value)) return null;
    const worker = {};
    for (const key of ["worker_id", "role", "functional_role", "target", "transport_binding", "execution_mode_required"]) {
      const text = safeIdentifier(value[key], 160);
      if (text) worker[key] = text;
    }
    return Object.keys(worker).length ? worker : null;
  }

  function normalizeReference(value) {
    if (!isObject(value)) return null;
    const reference = {
      reference_type: safeIdentifier(value.reference_type || value.type, 100),
      reference_id: safeIdentifier(value.reference_id || value.id, 180),
      record_sha256: safeDigest(value.record_sha256 || value.sha256)
    };
    if (!reference.reference_type || !reference.reference_id) return null;
    if (!reference.record_sha256) delete reference.record_sha256;
    return reference;
  }

  function normalizeEventSummary(value) {
    if (!isObject(value)) return null;
    const summary = {};
    for (const key of ["status", "task_scope_id", "return_report_id", "review_report_id", "verification_status", "transport_result_reference"]) {
      const text = safeIdentifier(value[key], 180);
      if (text) summary[key] = text;
    }
    for (const [source, target] of [
      ["acceptance_condition_ids_satisfied", "accepted_condition_count"],
      ["violated_acceptance_condition_ids", "violated_condition_count"],
      ["defects", "defect_count"],
      ["validation_evidence", "validation_evidence_count"]
    ]) {
      if (Array.isArray(value[source])) summary[target] = value[source].length;
    }
    if (typeof value.failure === "string") summary.failure = safeText(value.failure, 160);
    if (isObject(value.failure)) {
      summary.failure = safeIdentifier(value.failure.code || value.failure.category || value.failure.stage, 160);
    }
    return Object.keys(summary).length ? summary : null;
  }

  function normalizeActivity(value) {
    if (!isObject(value)) return null;
    const eventId = safeIdentifier(value.event_id, 180);
    const kind = safeIdentifier(value.kind, 140);
    const createdAt = safeText(value.created_at, 80);
    if (!eventId || !kind || !createdAt || !Number.isFinite(Date.parse(createdAt))) return null;
    const event = {event_id: eventId, kind, created_at: createdAt};
    const worker = normalizeWorker(value.worker);
    const summary = normalizeEventSummary(value.summary);
    if (worker) event.worker = worker;
    if (summary) event.summary = summary;
    const iteration = finiteInteger(isObject(value.detail) ? value.detail.iteration : undefined, null);
    if (iteration !== null) event.iteration = iteration;
    return event;
  }

  function normalizeNeedsTanner(value, options) {
    if (!isObject(value)) return null;
    const attentionId = safeIdentifier(value.attention_id, 90);
    const result = {
      attention_id: ATTENTION_ID.test(attentionId) ? attentionId : "",
      reason: safeText(value.plain_reason || value.reason, 240),
      decision_needed: safeText(value.decision_needed, 180),
      expires_at: safeText(value.expires_at, 80)
    };
    result.detail_url = safeAttentionHref(value.detail_url, result.attention_id,
      options && options.baseUrl);
    if (!result.attention_id && !result.reason && !result.decision_needed) return null;
    return result;
  }

  function normalizeCampaignProjection(value, options) {
    if (!isObject(value)) return null;
    const campaignId = safeIdentifier(value.campaign_id, 180);
    const status = safeIdentifier(value.status, 100);
    if (!campaignId || !status) return null;
    const result = {
      campaign_id: campaignId,
      objective: safeText(value.objective, 360) || "Objective unavailable",
      status,
      current_stage: safeIdentifier(value.current_stage, 120) || status,
      iteration: finiteInteger(value.iteration, 0),
      maximum_iterations: finiteInteger(value.maximum_iterations, 0),
      cancelled: value.cancelled === true,
      terminal: TERMINAL_CAMPAIGN_STATES.has(status),
      creates_authority: false
    };
    result.builder = normalizeWorker(value.builder);
    result.reviewer = normalizeWorker(value.reviewer);
    result.needs_tanner = normalizeNeedsTanner(value.needs_tanner, options);
    result.recovery_references = Array.isArray(value.recovery_references)
      ? value.recovery_references.map(normalizeReference).filter(Boolean).slice(0, 32) : [];
    result.activity = Array.isArray(value.activity)
      ? value.activity.map(normalizeActivity).filter(Boolean).slice(-80) : [];
    return result;
  }

  function normalizeCampaignResponse(payload, options) {
    if (!Array.isArray(payload)) return {valid: false, campaigns: []};
    let valid = true;
    const campaigns = [];
    for (const entry of payload.slice(0, 80)) {
      const projection = normalizeCampaignProjection(entry, options);
      if (!projection) valid = false;
      else campaigns.push(projection);
    }
    return {valid, campaigns};
  }

  function normalizeAttentionEvent(value, options) {
    if (!isObject(value)) return null;
    const attentionId = safeIdentifier(value.attention_id, 90);
    const campaignId = safeIdentifier(value.campaign_id, 180);
    const state = safeIdentifier(value.state, 100);
    if (!ATTENTION_ID.test(attentionId) || !campaignId || !state) return null;
    const expiresAt = safeText(value.expires_at, 80);
    const expiresMs = Date.parse(expiresAt);
    const nowMs = options && Number.isFinite(options.nowMs) ? options.nowMs : Date.now();
    const href = safeAttentionHref(value.detail_url, attentionId, options && options.baseUrl);
    const pending = state === "needs_tanner" || state === "pending" || state === "awaiting_decision";
    const consumerState = safeIdentifier(value.consumer_state, 80);
    const invocationId = safeIdentifier(value.invocation_id, 180);
    const consumerAvailable = consumerState === "live" || consumerState === "durably_resumable";
    const actionable = value.actionable === true && consumerAvailable && Boolean(invocationId)
      && pending && href
      && Number.isFinite(expiresMs) && expiresMs > nowMs;
    return {
      attention_id: attentionId,
      campaign_id: campaignId,
      invocation_id: invocationId,
      state,
      blocked_action: safeText(value.blocked_action || value.requested_action, 240),
      why_required: safeText(value.why_required || value.reason, 240),
      expires_at: Number.isFinite(expiresMs) ? expiresAt : "",
      consumer_state: consumerState || "unavailable",
      actionable: Boolean(actionable),
      detail_url: actionable ? href : "",
      creates_authority: false
    };
  }

  function normalizeAttentionResponse(payload, options) {
    if (!Array.isArray(payload)) return {valid: false, attention: []};
    let valid = true;
    const attention = [];
    for (const raw of payload.slice(0, 40)) {
      const event = normalizeAttentionEvent(raw, options);
      if (!event) valid = false;
      else attention.push(event);
    }
    return {valid, attention};
  }

  function normalizeRuntimeResponse(payload) {
    if (!Array.isArray(payload)) return {valid: false, components: []};
    const components = [];
    let valid = true;
    const ordered = payload.slice(0, 80).sort((left, right) =>
      String(isObject(left) ? left.name : "").localeCompare(String(isObject(right) ? right.name : "")));
    for (const raw of ordered) {
      const safeName = safeIdentifier(isObject(raw) ? raw.name : "", 100);
      const state = safeIdentifier(isObject(raw) ? raw.state : "", 80);
      if (!safeName || !state) {
        valid = false;
        continue;
      }
      components.push({name: safeName, state, creates_authority: false});
    }
    return {valid, components};
  }

  function normalizeStatusResponse(payload) {
    if (!isObject(payload)) return {valid: false, build: null};
    const releaseId = safeIdentifier(payload.release_id, 180);
    const mode = safeIdentifier(payload.mode, 80);
    if (!releaseId || !mode) return {valid: false, build: null};
    return {valid: true, build: {
      release_id: releaseId,
      mode,
      manifest_sha256: safeDigest(payload.manifest_sha256),
      creates_authority: false
    }};
  }

  function normalizePayloads(payload, options) {
    const values = payload || {};
    const opts = options || {};
    const schemaValid = values.schema_version === PROJECTION_SCHEMA;
    const authorityClosed = values.creates_authority === false
      && values.creates_continuing_authority === false;
    const observedAt = safeText(values.observed_at, 80);
    const observedAtMs = Date.parse(observedAt);
    const observationValid = Boolean(observedAt) && Number.isFinite(observedAtMs);
    const status = normalizeStatusResponse(values.build);
    const campaigns = normalizeCampaignResponse(values.campaigns, opts);
    const attention = normalizeAttentionResponse(values.attention, opts);
    const runtime = normalizeRuntimeResponse(values.components);
    const expected = safeIdentifier(opts.expectedBuildId, 180);
    const buildMismatch = Boolean(expected && expected !== "__FAWKES_BUILD_ID__"
      && status.build && status.build.release_id !== expected);
    const malformed = !(schemaValid && authorityClosed && observationValid
      && status.valid && campaigns.valid && attention.valid && runtime.valid);
    return {
      ok: !malformed && !buildMismatch,
      malformed,
      buildMismatch,
      build: status.build,
      observed_at: observationValid ? observedAt : "",
      observed_at_ms: observationValid ? observedAtMs : null,
      campaigns: campaigns.campaigns,
      attention: attention.attention,
      components: runtime.components,
      creates_authority: false,
      creates_continuing_authority: false
    };
  }

  class ConsoleNavigation {
    constructor(options) {
      const value = options || {};
      this.pageCount = Math.max(1, finiteInteger(value.pageCount, 4));
      this.idleSeconds = parseIdleSeconds(value.idleSeconds, 60);
      this.onChange = typeof value.onChange === "function" ? value.onChange : function () {};
      this.scheduler = value.scheduler || {setTimeout: root.setTimeout.bind(root), clearTimeout: root.clearTimeout.bind(root)};
      this.page = 0;
      this.timer = null;
      this.activity();
    }

    go(index, reason) {
      const selected = Number(index);
      if (!Number.isInteger(selected)) return this.page;
      const normalized = Math.max(0, Math.min(this.pageCount - 1, selected));
      const changed = normalized !== this.page;
      this.page = normalized;
      if (reason !== "idle") this.activity();
      if (changed || reason === "initial" || reason === "idle") this.onChange(this.page, reason || "navigation");
      return this.page;
    }

    next() { return this.go(this.page + 1, "next"); }
    previous() { return this.go(this.page - 1, "previous"); }

    activity() {
      if (this.timer !== null) this.scheduler.clearTimeout(this.timer);
      this.timer = this.scheduler.setTimeout(() => {
        this.timer = null;
        this.go(0, "idle");
      }, this.idleSeconds * 1000);
    }

    swipe(startX, startY, endX, endY, options) {
      if (!isHorizontalSwipe(startX, startY, endX, endY, options)) return this.page;
      return Number(endX) < Number(startX) ? this.next() : this.previous();
    }

    destroy() {
      if (this.timer !== null) this.scheduler.clearTimeout(this.timer);
      this.timer = null;
    }
  }

  function element(documentRef, tag, className, text) {
    const node = documentRef.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = safeText(text, 1000);
    return node;
  }

  function detailList(documentRef, entries) {
    const list = element(documentRef, "ul");
    for (const entry of entries) {
      const item = element(documentRef, "li");
      const label = element(documentRef, "strong", "", entry[0] + ": ");
      const value = documentRef.createTextNode(safeText(entry[1], 600) || "Unavailable");
      item.append(label, value);
      list.appendChild(item);
    }
    return list;
  }

  function createCard(documentRef, heading, copy, details, className, stableKey) {
    const card = element(documentRef, "details", "console-card" + (className ? " " + className : ""));
    if (stableKey) card.dataset.consoleKey = safeText(stableKey, 240);
    const summary = element(documentRef, "summary");
    summary.appendChild(element(documentRef, "span", "summary-heading", "• " + heading));
    summary.appendChild(element(documentRef, "p", "summary-copy", copy));
    const body = element(documentRef, "div", "detail");
    body.appendChild(detailList(documentRef, details));
    card.append(summary, body);
    return card;
  }

  function workerLabel(worker) {
    if (!worker) return "Unavailable";
    return worker.worker_id || worker.role || worker.functional_role || "Available identity (not displayed)";
  }

  function activityExplanation(event) {
    const labels = {
      provider_action_reserved: "A bounded provider action was reserved by the canonical campaign.",
      builder_return_retained: "The canonical campaign retained a Worker return record.",
      independent_review_retained: "The canonical campaign retained an independent review record.",
      reviewed_application_completed: "The canonical application owner recorded its terminal result.",
      reviewed_git_completed: "The canonical Git owner recorded its terminal result.",
      rider_cancelled_campaign: "Tanner cancelled the campaign through the canonical owner.",
      provider_completion_ambiguous: "Provider completion was ambiguous; the campaign stopped fail-safe."
    };
    return labels[event.kind] || "The canonical campaign recorded this body-free transition.";
  }

  function renderAttention(documentRef, target, attention) {
    target.replaceChildren();
    const event = attention.find((item) => item.actionable) || attention[0];
    if (!event) return;
    const card = element(documentRef, "section", "attention-card" + (event.actionable ? "" : " unavailable"));
    card.appendChild(element(documentRef, "p", "eyebrow", "TANNER ATTENTION · CANONICAL PAGE"));
    card.appendChild(element(documentRef, "h3", "", event.actionable ? "A decision is pending" : "Attention is not actionable"));
    card.appendChild(element(documentRef, "p", "", event.why_required || event.blocked_action || "No body-free reason is available."));
    card.appendChild(element(documentRef, "p", "meta", "Campaign " + event.campaign_id + (event.expires_at ? " · expires " + event.expires_at : "")));
    if (event.actionable && event.detail_url) {
      const link = element(documentRef, "a", "attention-link", "Open canonical Attention page");
      link.href = event.detail_url;
      link.rel = "noopener";
      link.dataset.attentionId = event.attention_id;
      card.appendChild(link);
    } else {
      card.appendChild(element(documentRef, "p", "warning", "No decision link is offered from stale, expired, or invalid data."));
    }
    target.appendChild(card);
  }

  function renderActivity(documentRef, target, campaigns) {
    target.replaceChildren();
    const events = [];
    for (const campaign of campaigns) {
      for (const event of campaign.activity) events.push({campaign, event});
    }
    events.sort((left, right) => Date.parse(right.event.created_at) - Date.parse(left.event.created_at));
    if (!events.length) {
      target.appendChild(element(documentRef, "p", "empty", "No body-free campaign activity is currently projected."));
      return;
    }
    for (const item of events.slice(0, 60)) {
      const summary = item.event.summary || {};
      const details = [
        ["Campaign", item.campaign.campaign_id],
        ["Recorded", item.event.created_at],
        ["Canonical event", item.event.kind],
        ["Worker / Reviewer", workerLabel(item.event.worker)],
        ["Report reference", summary.return_report_id || summary.review_report_id || "Unavailable"],
        ["Code / diff explanation", "Unavailable in this body-free projection; source and diff bodies are never fetched by this console."]
      ];
      const card = createCard(documentRef, item.event.kind.replace(/_/g, " "),
        activityExplanation(item.event), details, "",
        "activity:" + item.campaign.campaign_id + ":" + item.event.event_id);
      card.dataset.eventId = item.event.event_id;
      const link = element(documentRef, "a", "evidence-link", "View campaign binding");
      link.href = "#campaign-heading";
      link.dataset.pageLink = "1";
      card.querySelector(".detail").appendChild(link);
      target.appendChild(card);
    }
  }

  function renderCampaigns(documentRef, target, campaigns) {
    target.replaceChildren();
    if (!campaigns.length) {
      target.appendChild(element(documentRef, "p", "empty", "No canonical campaign projection is available."));
      return;
    }
    for (const campaign of campaigns) {
      const details = [
        ["Campaign identity", campaign.campaign_id],
        ["Stage", campaign.current_stage],
        ["Iteration", campaign.iteration + " / " + campaign.maximum_iterations],
        ["Worker", workerLabel(campaign.builder)],
        ["Reviewer", workerLabel(campaign.reviewer)],
        ["Provider reservations / remaining limits", "Unavailable in the current body-free projection"]
      ];
      if (campaign.needs_tanner) details.push(["Needs Tanner", campaign.needs_tanner.reason || campaign.needs_tanner.decision_needed]);
      target.appendChild(createCard(documentRef, campaign.status.replace(/_/g, " "), campaign.objective, details,
        campaign.terminal ? "terminal" : "", "campaign:" + campaign.campaign_id));
    }
  }

  function projectionTruthLabel(state) {
    if (state === "live") return "CURRENT AUTHENTICATED PROJECTION";
    if (state === "sample") return "SAMPLE FIXTURE · NOT CURRENT";
    if (state === "stale") return "STALE LAST-VERIFIED PROJECTION";
    if (state === "disconnected") return "DISCONNECTED · NO CURRENT PROJECTION";
    return "UNAVAILABLE · NO CURRENT PROJECTION";
  }

  function renderRepository(documentRef, target, projection, state) {
    target.replaceChildren();
    const build = projection.build;
    target.appendChild(createCard(documentRef, "Authenticated build binding",
      build && state === "live"
        ? "The authenticated compact projection identifies this current development build."
        : "This view is not current and cannot establish repository state.", [
        ["Projection status", projectionTruthLabel(state)],
        ["Build", build ? build.release_id : "Unavailable"],
        ["Mode", build ? build.mode : "Unavailable"],
        ["Branch / HEAD", "Unavailable: not exposed by the existing canonical read-only projection"],
        ["Source and diff bodies", "Not loaded"]
      ], "", "repository:build"));
    for (const campaign of projection.campaigns) {
      const references = campaign.recovery_references.length
        ? campaign.recovery_references.map((item) => item.reference_type + ":" + item.reference_id).join(", ")
        : "Unavailable";
      target.appendChild(createCard(documentRef, campaign.campaign_id,
        state === "live"
          ? "Current body-free repository binding from the canonical campaign projection."
          : "Non-current body-free campaign information retained only for display.", [
          ["Projection status", projectionTruthLabel(state)],
          ["Status", campaign.status],
          ["Recovery references", references],
          ["Reviewed file list", "Unavailable in this projection"],
          ["Repository browsing", "Restricted to identities already projected by the authorized development workspace"]
        ], "", "repository:" + campaign.campaign_id));
    }
  }

  function renderArchitecture(documentRef, target, components, state) {
    target.replaceChildren();
    const contracts = [
      ["LangGraph runner", "Graph position, bounded scheduling, checkpoints, and presentation only."],
      ["Canonical campaign", "Owns provider reservations, budgets, review routing, cancellation, and terminal state."],
      ["Independent Reviewer + Attention", "Reviewer evidence remains advisory until canonical validation; protected decisions stay on the existing Attention page."],
      ["Reviewed application", "Owns exact one-shot application and retained terminal evidence."],
      ["Git transaction", "Owns drift validation, protected ref advancement, and observation-only reconciliation."]
    ];
    for (const contract of contracts) {
      target.appendChild(createCard(documentRef, contract[0], contract[1], [
        ["Classification", "REFERENCE · explanatory map · not authority"],
        ["Runtime projection", projectionTruthLabel(state)]
      ], "", "architecture:contract:" + contract[0]));
    }
    if (!components.length) {
      target.appendChild(element(documentRef, "p", "empty", "Live component status is unavailable."));
    } else {
      for (const component of components) {
        target.appendChild(createCard(documentRef, component.name,
          state === "live" ? "Current authenticated component projection" : "Non-current component projection", [
          ["Projection status", projectionTruthLabel(state)],
          ["Projected state", component.state],
          ["Authority", "None created by this view"]
        ], "", "architecture:component:" + component.name));
      }
    }
  }

  async function fetchJson(fetchImpl, path, timeoutMs) {
    const controller = typeof root.AbortController === "function" ? new root.AbortController() : null;
    const timer = controller ? root.setTimeout(() => controller.abort(), timeoutMs) : null;
    try {
      const response = await fetchImpl(path, {
        method: "GET",
        credentials: "same-origin",
        headers: {Accept: "application/json"},
        signal: controller ? controller.signal : undefined
      });
      if (!response || !response.ok) {
        const error = new Error("read-only projection request failed");
        error.kind = response && (response.status === 401 || response.status === 403) ? "authentication" : "http";
        error.status = response ? response.status : 0;
        throw error;
      }
      return await response.json();
    } finally {
      if (timer !== null) root.clearTimeout(timer);
    }
  }

  function boot(options) {
    const value = options || {};
    const documentRef = value.document || root.document;
    if (!documentRef) return null;
    const shell = documentRef.getElementById("dev-console");
    if (!shell) return null;
    const fetchImpl = value.fetch || (typeof root.fetch === "function" ? root.fetch.bind(root) : null);
    const pages = Array.from(documentRef.querySelectorAll(".console-page"));
    const indicators = Array.from(documentRef.querySelectorAll("[data-page-target]"));
    const title = documentRef.getElementById("page-title");
    const connection = documentRef.getElementById("connection-state");
    const updated = documentRef.getElementById("last-updated");
    const activityFeed = documentRef.getElementById("activity-feed");
    const attentionSlot = documentRef.getElementById("attention-slot");
    const campaignList = documentRef.getElementById("campaign-list");
    const repository = documentRef.getElementById("repository-content");
    const architecture = documentRef.getElementById("architecture-content");
    const buildMeta = documentRef.querySelector('meta[name="fawkes-build-id"]');
    const expectedBuildId = buildMeta ? buildMeta.content : "";
    const urlIdle = value.idleSeconds !== undefined ? value.idleSeconds
      : (root.location ? new URL(root.location.href).searchParams.get("idle") : null);
    const idleSeconds = parseIdleSeconds(urlIdle, shell.dataset.idleSeconds || 60);
    let selectedCard = null;
    let pointerStart = null;
    let lastGood = null;
    let lastSuccessMs = null;
    let stopped = false;
    let pollTimer = null;
    let staleTimer = null;
    let expiryTimer = null;
    let refreshSequence = 0;
    let latestAppliedSequence = 0;
    const clock = typeof value.now === "function" ? value.now : Date.now;
    const projectionScheduler = value.projectionScheduler || {
      setTimeout: root.setTimeout.bind(root), clearTimeout: root.clearTimeout.bind(root)
    };

    const refreshTargets = [activityFeed, campaignList, repository, architecture];

    function cardsIn(target) {
      return target && typeof target.querySelectorAll === "function"
        ? Array.from(target.querySelectorAll("details.console-card")) : [];
    }

    function cardKey(card) {
      return card && card.dataset ? card.dataset.consoleKey || "" : "";
    }

    function captureRefreshState() {
      const focused = documentRef.activeElement && documentRef.activeElement.closest
        ? documentRef.activeElement.closest("details.console-card") : null;
      return {
        scrollTops: refreshTargets.map((target) => Number(target.scrollTop) || 0),
        openKeys: new Set(refreshTargets.flatMap(cardsIn).filter((card) => card.open)
          .map(cardKey).filter(Boolean)),
        selectedKey: cardKey(selectedCard),
        focusedKey: cardKey(focused)
      };
    }

    function restoreRefreshState(retained) {
      const cards = refreshTargets.flatMap(cardsIn);
      const byKey = new Map(cards.map((card) => [cardKey(card), card]).filter(([key]) => Boolean(key)));
      for (const key of retained.openKeys) {
        const card = byKey.get(key);
        if (card) card.open = true;
      }
      selectedCard = byKey.get(retained.selectedKey) || null;
      if (selectedCard) selectedCard.classList.add("selected");
      refreshTargets.forEach((target, index) => { target.scrollTop = retained.scrollTops[index] || 0; });
      const focused = byKey.get(retained.focusedKey);
      const summary = focused && focused.querySelector && focused.querySelector("summary");
      if (summary && typeof summary.focus === "function") summary.focus({preventScroll: true});
    }

    function isAttachedCard(card) {
      let current = card;
      while (current) {
        if (current === shell) return true;
        current = current.parentNode;
      }
      return false;
    }

    function showPage(page) {
      pages.forEach((item, index) => { item.hidden = index !== page; });
      indicators.forEach((item, index) => {
        if (index === page) item.setAttribute("aria-current", "page");
        else item.removeAttribute("aria-current");
      });
      title.textContent = PAGE_TITLES[page] || "Developer Console";
    }

    const navigation = new ConsoleNavigation({
      pageCount: pages.length || 4,
      idleSeconds,
      scheduler: value.scheduler,
      onChange: showPage
    });
    showPage(0);

    function setState(state, observedAt) {
      connection.className = "state " + state;
      connection.textContent = state.toUpperCase();
      shell.dataset.projectionState = state;
      updated.textContent = observedAt
        ? ((state === "stale" ? "Last verified " : "Updated ") + new Date(observedAt).toLocaleString())
        : "No current projection";
    }

    function visibleAttentionAt(projection, state, nowMs) {
      return (projection.attention || []).map((item) => {
        const expiresMs = Date.parse(item.expires_at);
        const actionable = state === "live" && item.actionable === true
          && Number.isFinite(expiresMs) && expiresMs > nowMs;
        return actionable ? item : {...item, actionable: false, detail_url: ""};
      });
    }

    function render(projection, state, observedAt, nowMs) {
      const retained = captureRefreshState();
      setState(state, observedAt);
      documentRef.getElementById("summary-intro").textContent = state === "live"
        ? "Authenticated, body-free canonical activity. Select a heading for available detail."
        : state === "sample"
          ? "Sample fixture data — never current canonical state."
          : "Projection is " + state + "; it must not be treated as current authority.";
      const visibleAttention = visibleAttentionAt(projection, state,
        Number.isFinite(nowMs) ? nowMs : clock());
      renderAttention(documentRef, attentionSlot, visibleAttention);
      renderActivity(documentRef, activityFeed, projection.campaigns || []);
      renderCampaigns(documentRef, campaignList, projection.campaigns || []);
      renderRepository(documentRef, repository, projection, state);
      renderArchitecture(documentRef, architecture, projection.components || [], state);
      restoreRefreshState(retained);
    }

    function clearProjectionTimers() {
      if (staleTimer !== null) projectionScheduler.clearTimeout(staleTimer);
      if (expiryTimer !== null) projectionScheduler.clearTimeout(expiryTimer);
      staleTimer = null;
      expiryTimer = null;
    }

    function scheduleProjectionInvalidation(projection, observedAtMs) {
      clearProjectionTimers();
      const currentMs = clock();
      staleTimer = projectionScheduler.setTimeout(() => {
        staleTimer = null;
        if (!stopped && lastGood === projection) render(lastGood, "stale", lastSuccessMs, clock());
      }, Math.max(0, observedAtMs + 30001 - currentMs));
      const expiries = (projection.attention || [])
        .filter((item) => item.actionable)
        .map((item) => Date.parse(item.expires_at))
        .filter((item) => Number.isFinite(item) && item > currentMs);
      if (expiries.length) {
        const firstExpiry = Math.min(...expiries);
        expiryTimer = projectionScheduler.setTimeout(() => {
          expiryTimer = null;
          if (stopped || lastGood !== projection) return;
          const sampled = clock();
          if (sampled < firstExpiry) {
            scheduleProjectionInvalidation(projection, observedAtMs);
            return;
          }
          const currentState = classifyProjectionState({
            currentSuccess: true, previousSuccess: true,
            nowMs: sampled, observedAtMs, staleAfterMs: 30000
          });
          render(lastGood, currentState, lastSuccessMs, sampled);
          scheduleProjectionInvalidation(projection, observedAtMs);
        }, Math.max(0, firstExpiry - currentMs));
      }
    }

    async function refresh() {
      if (stopped) return;
      const sequence = ++refreshSequence;
      if (value.samplePayload) {
        const sampledAt = clock();
        const sample = normalizePayloads(value.samplePayload, {
          baseUrl: value.baseUrl || (root.location && root.location.href), expectedBuildId: "", nowMs: sampledAt
        });
        if (sequence !== refreshSequence || stopped) return;
        latestAppliedSequence = sequence;
        clearProjectionTimers();
        render(sample, "sample", sample.observed_at_ms || sampledAt, sampledAt);
        return;
      }
      if (!fetchImpl) {
        setState(lastGood ? "stale" : "disconnected", lastSuccessMs);
        return;
      }
      try {
        const raw = await fetchJson(fetchImpl, ENDPOINTS.projection, 15000);
        const now = clock();
        if (sequence !== refreshSequence || sequence < latestAppliedSequence || stopped) return;
        const projection = normalizePayloads(raw, {
          baseUrl: value.baseUrl || (root.location && root.location.href), expectedBuildId, nowMs: now
        });
        const state = classifyProjectionState({
          currentSuccess: true,
          previousSuccess: Boolean(lastGood),
          malformed: projection.malformed,
          buildMismatch: projection.buildMismatch,
          nowMs: now,
          observedAtMs: projection.observed_at_ms
        });
        latestAppliedSequence = sequence;
        if (projection.ok) {
          lastGood = projection;
          lastSuccessMs = projection.observed_at_ms;
          scheduleProjectionInvalidation(projection, lastSuccessMs);
        }
        render(projection.ok || !lastGood ? projection : lastGood, state,
          projection.ok ? projection.observed_at_ms : lastSuccessMs, now);
      } catch (error) {
        if (sequence !== refreshSequence || sequence < latestAppliedSequence || stopped) return;
        latestAppliedSequence = sequence;
        const disconnected = !error || error.kind === "authentication" || !error.kind || error.name === "AbortError";
        const state = classifyProjectionState({
          currentSuccess: false, previousSuccess: Boolean(lastGood), disconnected
        });
        if (lastGood) render(lastGood, state, lastSuccessMs, clock());
        else {
          setState(state, null);
          documentRef.getElementById("summary-intro").textContent = "Authenticated read-only projections are unavailable.";
        }
      }
    }

    documentRef.getElementById("previous-page").addEventListener("click", () => navigation.previous());
    documentRef.getElementById("next-page").addEventListener("click", () => navigation.next());
    indicators.forEach((item) => item.addEventListener("click", () => navigation.go(Number(item.dataset.pageTarget), "indicator")));
    shell.addEventListener("click", (event) => {
      navigation.activity();
      const pageLink = event.target.closest && event.target.closest("[data-page-link]");
      if (pageLink) navigation.go(Number(pageLink.dataset.pageLink), "detail-link");
      const card = event.target.closest && event.target.closest("details.console-card");
      if (selectedCard && selectedCard !== card) selectedCard.classList.remove("selected");
      selectedCard = card || selectedCard;
      if (selectedCard) selectedCard.classList.add("selected");
    });
    shell.addEventListener("wheel", () => navigation.activity(), {passive: true});
    shell.addEventListener("auxclick", (event) => {
      navigation.activity();
      if (event.button !== 1) return;
      event.preventDefault();
      const visible = pages[navigation.page];
      const card = isAttachedCard(selectedCard) && !selectedCard.closest("[hidden]")
        ? selectedCard : visible && visible.querySelector("details.console-card");
      if (card) {
        card.open = !card.open;
        card.classList.add("selected");
        selectedCard = card;
      }
    });
    shell.addEventListener("keydown", (event) => {
      navigation.activity();
      if (event.target.closest && event.target.closest(".code-scroll")) return;
      if (event.key === "ArrowLeft") { event.preventDefault(); navigation.previous(); }
      if (event.key === "ArrowRight") { event.preventDefault(); navigation.next(); }
    });
    const stack = documentRef.getElementById("page-stack");
    stack.addEventListener("pointerdown", (event) => {
      pointerStart = {x: event.clientX, y: event.clientY,
        codeScroll: Boolean(event.target.closest && event.target.closest(".code-scroll"))};
      navigation.activity();
    });
    stack.addEventListener("pointerup", (event) => {
      if (!pointerStart) return;
      navigation.swipe(pointerStart.x, pointerStart.y, event.clientX, event.clientY,
        {codeScroll: pointerStart.codeScroll});
      pointerStart = null;
    });
    stack.addEventListener("pointercancel", () => { pointerStart = null; });

    refresh();
    pollTimer = value.pollIntervalMs === 0 || !root.setInterval
      ? null : root.setInterval(refresh, Number.isFinite(value.pollIntervalMs) ? value.pollIntervalMs : 10000);
    return {
      navigation,
      refresh,
      stop: function () {
        stopped = true;
        navigation.destroy();
        if (pollTimer !== null && root.clearInterval) root.clearInterval(pollTimer);
        clearProjectionTimers();
      }
    };
  }

  const api = Object.freeze({
    ENDPOINTS,
    PROJECTION_SCHEMA,
    PAGE_TITLES,
    parseIdleSeconds,
    classifyProjectionState,
    isHorizontalSwipe,
    safeAttentionHref,
    normalizeCampaignProjection,
    normalizeCampaignResponse,
    normalizeAttentionResponse,
    normalizeRuntimeResponse,
    normalizeStatusResponse,
    normalizePayloads,
    ConsoleNavigation,
    boot,
    startConsole: boot
  });

  if (root.document && root.document.readyState === "loading") {
    root.document.addEventListener("DOMContentLoaded", function () { boot(); }, {once: true});
  } else if (root.document) {
    boot();
  }
  return api;
});

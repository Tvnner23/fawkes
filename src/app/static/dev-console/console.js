(function (root, factory) {
  "use strict";
  const api = factory(root);
  if (typeof module === "object" && module.exports) module.exports = api;
  root.FawkesDevConsole = api;
})(typeof globalThis === "object" ? globalThis : this, function (root) {
  "use strict";

  const ENDPOINTS = Object.freeze({
    projection: "/api/development/dev-console",
    updates: "/api/development/console-updates",
    csrf: "/api/session/console-csrf"
  });
  const PROJECTION_SCHEMA = "fawkes.dev_console.read_only.v1";
  const PAGE_TITLES = Object.freeze([
    "Activity Summary",
    "Campaign Status",
    "Repository View",
    "Architecture View",
    "Worker conversation"
  ]);
  const ATTENTION_ID = /^attention-[a-f0-9]{64}$/;
  const HEX_DIGEST = /^[a-f0-9]{64}$/;
  const GIT_MODE = /^[0-7]{6}$/;
  const GIT_OID = /^[a-f0-9]{40,64}$/;
  const SAFE_ID = /^[A-Za-z0-9][A-Za-z0-9._:/-]*$/;
  const TERMINAL_CAMPAIGN_STATES = new Set([
    "succeeded", "failed_safe", "cancelled", "denied", "expired"
  ]);
  const CONNECTION_LABELS = Object.freeze({
    live: "◉ Live",
    sample: "SAMPLE DATA",
    stale: "◷ Stale",
    disconnected: "⊘ Disconnected",
    unavailable: "◌ Worker unknown"
  });

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

  function safeGitOid(value) {
    const text = safeText(value, 64).toLowerCase();
    return GIT_OID.test(text) ? text : "";
  }

  function safeMultilineText(value, maximum) {
    if (typeof value !== "string") return "";
    return value.replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/g, "")
      .slice(0, maximum || 2048);
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

  function previewContextLabel(build, candidateContext) {
    const context = safeIdentifier(candidateContext, 100);
    if (context.startsWith("UNREVIEWED:")) {
      return "UNREVIEWED · " + context.slice(-12);
    }
    if (!build) return "CONTEXT UNKNOWN";
    if (build.mode === "development_checkout") return "DEVELOPMENT PREVIEW";
    if (build.mode === "approved_release") return "APPROVED RELEASE";
    return "CONTEXT UNKNOWN";
  }

  function isOpenCampaignRecord(campaign) {
    return Boolean(campaign && !campaign.terminal
      && campaign.status !== "historical_contract_unavailable"
      && campaign.status !== "integrity_unavailable");
  }

  function campaignObservation(campaigns, projectionState, nowMs = Date.now()) {
    if (projectionState === "sample") return {kind: "sample", label: "SAMPLE CAMPAIGN DATA"};
    if (projectionState !== "live") return {kind: "unknown", label: "EXECUTION UNKNOWN"};
    const values = Array.isArray(campaigns) ? campaigns : [];
    if (!values.length) return {kind: "unavailable", label: "EXECUTION UNAVAILABLE"};
    for (const campaign of values) {
      for (const clock of roleClocks(campaign, projectionState, nowMs)) {
        if (clock.label === "Executing") return {kind: "executing", label: clock.role.toUpperCase() + " EXECUTING"};
        if (clock.label.includes("clock paused")) return {kind: "waiting", label: clock.role.toUpperCase() + " WAITING FOR TANNER"};
      }
    }
    if (values.some(isOpenCampaignRecord)) {
      return {kind: "unknown", label: "EXECUTION NOT OBSERVED"};
    }
    return {kind: "inactive", label: "NO OPEN CAMPAIGN RECORD"};
  }

  function attentionObservation(attention, projectionState) {
    if (projectionState === "sample") return {kind: "sample", label: "SAMPLE ATTENTION"};
    if (projectionState !== "live") return {kind: "unknown", label: "ATTENTION UNKNOWN"};
    const values = Array.isArray(attention) ? attention : [];
    if (values.some((item) => item.actionable)) {
      return {kind: "actionable", label: "ACTION REQUIRED"};
    }
    return {kind: "inactive", label: "NO ACTIONABLE REQUEST"};
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
      objective: safeText(value.objective, 500) || campaignId,
      created_at: safeText(value.created_at, 80),
      status,
      current_stage: safeIdentifier(value.current_stage, 120) || status,
      iteration: finiteInteger(value.iteration, 0),
      maximum_iterations: finiteInteger(value.maximum_iterations, 0),
      satisfied_condition_count: finiteInteger(value.satisfied_condition_count, null),
      cancelled: value.cancelled === true,
      terminal: TERMINAL_CAMPAIGN_STATES.has(status),
      creates_authority: false
    };
    result.builder = normalizeWorker(value.builder);
    result.reporting = normalizeConsoleReporting(value.console_reporting);
    result.reviewer = normalizeWorker(value.reviewer);
    result.needs_tanner = normalizeNeedsTanner(value.needs_tanner, options);
    result.recovery_references = Array.isArray(value.recovery_references)
      ? value.recovery_references.map(normalizeReference).filter(Boolean).slice(0, 32) : [];
    result.activity = Array.isArray(value.activity)
      ? value.activity.map(normalizeActivity).filter(Boolean).slice(-80) : [];
    result.managed = Array.isArray(value.managed_worker_activity) ? value.managed_worker_activity.slice(0,8).map(item=>({
      invocation_id:safeIdentifier(item.invocation_id,180), worker_id:safeIdentifier(item.worker_id,180),
      updated_at:safeText(item.updated_at,80),
      verified_at:safeText(item.verified_at,80), role:safeIdentifier(item.role||'worker',30),
      state:['running','waiting','completed','failed','disconnected'].includes(item.state)?item.state:'unknown',
      events:Array.isArray(item.events)?item.events.slice(-64).map(event=>({event_id:safeIdentifier(event.event_id,180),
        created_at:safeText(event.created_at,80),kind:safeIdentifier(event.kind,80),
        state:safeIdentifier(event.state,80),public_message:safeText(event.public_message,2000)})):[]
    })) : [];
    const observations = isObject(value.operational_learning_observations)
      ? value.operational_learning_observations : {};
    result.observations = {};
    for (const field of ["builder_invocations", "logical_reviews",
      "review_transport_attempts", "reviewer_process_invocations", "correction_count",
      "reviewer_defect_count", "source_section_count"]) {
      const count = finiteInteger(observations[field], null);
      if (count !== null) result.observations[field] = count;
    }
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

  function normalizeRepositoryResponse(payload) {
    if (!isObject(payload) || payload.creates_authority !== false
        || payload.creates_continuing_authority !== false) {
      return {valid: false, repository: null};
    }
    const branch = safeIdentifier(payload.branch, 180);
    const head = safeGitOid(payload.head);
    const comparisonBase = payload.comparison_base === "root"
      ? "root" : safeGitOid(payload.comparison_base);
    const selectionBasis = safeIdentifier(payload.selection_basis, 80);
    const counts = isObject(payload.status_summary) ? payload.status_summary : null;
    if (!branch || !head || !comparisonBase
        || selectionBasis !== "head_commit_paths" || !counts) {
      return {valid: false, repository: null};
    }
    const statusSummary = {};
    for (const field of ["dirty_paths", "tracked_changes", "untracked_paths",
      "staged_paths", "deleted_paths"]) {
      const count = finiteInteger(counts[field], null);
      if (count === null) return {valid: false, repository: null};
      statusSummary[field] = count;
    }
    if (!Array.isArray(payload.files) || payload.files.length > 32) {
      return {valid: false, repository: null};
    }
    const files = [];
    for (const raw of payload.files) {
      if (!isObject(raw)) return {valid: false, repository: null};
      const path = safeText(raw.path, 500);
      const parts = path.split("/");
      const file = {
        path,
        mode: safeText(raw.mode, 6),
        object_type: safeIdentifier(raw.object_type, 32),
        object_id: safeGitOid(raw.object_id),
        head_change: safeIdentifier(raw.head_change, 8),
        worktree_state: safeIdentifier(raw.worktree_state, 32),
        revision: safeGitOid(raw.revision),
        review_status: safeIdentifier(raw.review_status, 64),
        diff_excerpt: safeMultilineText(raw.diff_excerpt, 2048)
      };
      if (!path || path.startsWith("/") || parts.some((part) => !part || part === "." || part === "..")
          || !GIT_MODE.test(file.mode) || file.object_type !== "blob"
          || !file.object_id || !file.revision || file.revision !== head
          || !file.head_change || !file.worktree_state || !file.review_status) {
        return {valid: false, repository: null};
      }
      files.push(file);
    }
    return {valid: true, repository: {
      branch,
      head,
      comparison_base: comparisonBase,
      selection_basis: selectionBasis,
      status_summary: statusSummary,
      files,
      creates_authority: false,
      creates_continuing_authority: false
    }};
  }

  function lifecycleTime(value) {
    const match = typeof value === "string" && value.match(
      /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d{1,6})?(Z|[+-]\d{2}:\d{2})$/);
    if (!match || +match[2] < 1 || +match[2] > 12 || +match[3] < 1
        || +match[3] > new Date(Date.UTC(+match[1], +match[2], 0)).getUTCDate()
        || +match[4] > 23 || +match[5] > 59 || +match[6] > 59) return NaN;
    return Date.parse(value);
  }

  function normalizeConsoleReporting(value) {
    if (!isObject(value) || value.creates_authority !== false) return null;
    return {observed_at: safeText(value.observed_at, 80),
      turns: (Array.isArray(value.turns) ? value.turns : []).slice(0,32).map(item=>({
        role:safeIdentifier(item.role,20),turn_id:safeIdentifier(item.turn_id,180),
        thread_id:safeIdentifier(item.thread_id,180),
        invocation_id:safeIdentifier(item.invocation_id,180),
        started_at:safeText(item.started_at,80),ended_at:safeText(item.ended_at,80),
        observed_at:safeText(item.observed_at,80),state:safeIdentifier(item.state,32),
        active_verified:item.active_verified===true,
        duration_incomplete:item.duration_incomplete===true,
        active_seconds:Number.isSafeInteger(item.active_seconds)&&item.active_seconds>=0?item.active_seconds:null,
        waiting_seconds:Number.isSafeInteger(item.waiting_seconds)&&item.waiting_seconds>=0?item.waiting_seconds:null})),
      timing_history_incomplete:value.timing_history_incomplete===true,
      timing_incomplete_roles:Array.isArray(value.timing_incomplete_roles) && value.timing_incomplete_roles.length<=2
        && value.timing_incomplete_roles.every(role=>role==="worker"||role==="reviewer")
        ? value.timing_incomplete_roles.filter(role=>role==="worker"||role==="reviewer")
        : value.timing_history_incomplete===true ? ["worker","reviewer"] : [],
      record_sha256: safeIdentifier(value.record_sha256, 64),
      intervals: (Array.isArray(value.intervals) ? value.intervals : []).slice(0, 24).map((item) => ({
        stage: safeIdentifier(item.stage, 40), attempt: finiteInteger(item.attempt, 0),
        started_at: safeText(item.started_at, 80), ended_at: safeText(item.ended_at, 80),
        state: safeIdentifier(item.state, 80), active_verified: item.active_verified === true,
        timing_basis: safeIdentifier(item.timing_basis, 80),
        active_time_excludes_attention: item.active_time_excludes_attention === true,
        duration_seconds: Number.isSafeInteger(item.duration_seconds) && item.duration_seconds >= 0
          ? item.duration_seconds : null,
        source_references: (Array.isArray(item.source_references) ? item.source_references : [])
          .slice(0, 8).map((source) => safeText(source, 200))
      }))};
  }

  function formatDuration(seconds) {
    if (!Number.isSafeInteger(seconds) || seconds < 0) return "—";
    const pad = (number) => String(number).padStart(2, "0");
    return (seconds >= 3600 ? pad(Math.floor(seconds / 3600)) + ":" : "")
      + pad(Math.floor(seconds / 60) % 60) + ":" + pad(seconds % 60);
  }

  function intervalSeconds(interval, reporting, state, nowMs) {
    const start = lifecycleTime(interval.started_at), end = lifecycleTime(interval.ended_at);
    const observed = lifecycleTime(reporting.observed_at);
    if (!Number.isFinite(start) || !Number.isFinite(observed) || start > observed
        || observed > nowMs || !interval.source_references.length) return null;
    if (interval.active_time_excludes_attention) {
      const base=interval.duration_seconds;
      const finish=interval.ended_at?end:observed;
      if(!Number.isSafeInteger(base)||base<0||!Number.isFinite(finish)||finish<start||finish>observed
        ||base>Math.floor((finish-start)/1000))return null;
      return base+(!interval.ended_at&&interval.active_verified&&state==='live'&&nowMs-observed<=30000
        ?Math.floor((nowMs-observed)/1000):0);
    }
    if (interval.ended_at) {
      const seconds = Math.floor((end - start) / 1000);
      return Number.isFinite(end) && end >= start && end <= observed && interval.duration_seconds === seconds
        ? seconds : null;
    }
    if (!interval.active_verified || interval.duration_seconds === null) return null;
    const base = Math.floor((observed - start) / 1000);
    if (interval.duration_seconds !== base) return null;
    if (state === "live" && nowMs - observed <= 30000) {
      interval.last_displayed_seconds = Math.floor((nowMs - start) / 1000);
    }
    return interval.last_displayed_seconds === undefined ? base : interval.last_displayed_seconds;
  }

  function updateStageTimers(graph, campaign, state, nowMs) {
    if (!graph || !campaign) return;
    const reporting = campaign.reporting;
    for (const node of graph.querySelectorAll("[data-stage-timer]")) {
      const intervals = (reporting && reporting.intervals || []).filter((item) => item.stage === node.dataset.stageTimer);
      const latest = intervals[intervals.length - 1];
      node.textContent = latest ? formatDuration(intervalSeconds(latest, reporting, state, nowMs)) : "—";
      node.title = latest && latest.timing_basis === "historical_invocation_envelope"
        ? "Historical invocation elapsed time; not native active execution time." : "Recorded stage timing";
      const observed = reporting ? lifecycleTime(reporting.observed_at) : NaN;
      if (latest && latest.active_verified) {
        const live = state === "live" && Number.isFinite(observed) && nowMs >= observed && nowMs - observed <= 30000;
        const step = node.parentNode;
        step.classList.toggle("current", live);
        step.classList.toggle("waiting", !live);
        const label = step.querySelector(".graph-node-state");
        if (label) label.textContent = live ? "current" : "last known";
      }
    }
  }

  function nativeTurnLabel(turn, state, nowMs) {
    const observed = turn && lifecycleTime(turn.observed_at);
    const fresh = state === "live" && Number.isFinite(observed)
      && nowMs >= observed && nowMs - observed <= 30000;
    return !turn ? "Not observed"
      : turn.ended_at ? "Waiting · last turn " + turn.state + (turn.duration_incomplete ? " · timing unavailable" : "")
        : !fresh ? "Last known · current execution unknown"
          : turn.state === "waiting" ? "Waiting for Tanner · clock paused"
            : turn.active_verified ? "Executing" : "Execution unknown";
  }

  function roleClocks(campaign, state, nowMs) {
    const turns = campaign && campaign.reporting && campaign.reporting.turns || [];
    return ["worker", "reviewer"].map(role => {
      const own = turns.filter(turn => turn.role === role);
      const last = own[own.length - 1];
      const values = own.map(turn => {
        if (turn.active_seconds === null) return null;
        const verified = lifecycleTime(turn.observed_at);
        const live = state === "live" && turn.active_verified && Number.isFinite(verified)
          && nowMs >= verified && nowMs - verified <= 30000;
        return turn.active_seconds + (live ? Math.floor((nowMs - verified) / 1000) : 0);
      });
      const reporting = campaign && campaign.reporting;
      const incomplete = reporting && reporting.timing_history_incomplete
        && (!Array.isArray(reporting.timing_incomplete_roles)
          || reporting.timing_incomplete_roles.some(value=>value!=="worker"&&value!=="reviewer")
          || reporting.timing_incomplete_roles.includes(role));
      return {role, last, seconds: values.length ? values[values.length - 1] : null,
        total: values.length && !incomplete && values.every(value => value !== null)
          ? values.reduce((a,b) => a+b, 0) : null,
        label: nativeTurnLabel(last, state, nowMs)};
    });
  }

  function renderRoleClocks(documentRef, target, campaign, state, nowMs) {
    if (!target) return;
    const identity = JSON.stringify([campaign && campaign.campaign_id, campaign && campaign.reporting && campaign.reporting.turns,
      campaign && campaign.reporting && campaign.reporting.timing_history_incomplete]);
    if (target.clockIdentity === identity) {
      roleClocks(campaign, state, nowMs).forEach((clock, index) => {
        const card = target.children[index];
        if (!card) return;
        card.querySelector('.role-clock-value').textContent = formatDuration(clock.seconds);
        card.querySelector('.role-clock-state').textContent = clock.label;
        card.querySelector('.role-clock-total').textContent = "Cumulative active " + formatDuration(clock.total);
      });
      return;
    }
    target.clockIdentity = identity;
    const open = Array.from(target.querySelectorAll("details")).map(item => item.open);
    target.replaceChildren();
    for (const clock of roleClocks(campaign, state, nowMs)) {
      const card = element(documentRef, "section", "role-clock");
      card.append(element(documentRef, "strong", "", clock.role === "worker" ? "Worker" : "Reviewer"),
        element(documentRef, "div", "role-clock-value", formatDuration(clock.seconds)),
        element(documentRef, "p", "meta role-clock-state", clock.label),
        element(documentRef, "p", "meta role-clock-total", "Cumulative active " + formatDuration(clock.total)));
      if (clock.last) card.appendChild(element(documentRef, "p", "meta",
        "Turn " + clock.last.turn_id + " · wait " + formatDuration(clock.last.waiting_seconds)));
      const history = element(documentRef, "details", "");
      history.open = Boolean(open[clock.role === "worker" ? 0 : 1]);
      history.appendChild(element(documentRef, "summary", "", "Retained turns"));
      for (const turn of campaign && campaign.reporting && campaign.reporting.turns || []) {
        if (turn.role === clock.role) history.appendChild(element(documentRef, "p", "meta",
          `${turn.turn_id} · ${turn.started_at} · active ${formatDuration(turn.active_seconds)} · waiting ${formatDuration(turn.waiting_seconds)} · ${turn.state}`));
      }
      card.appendChild(history); target.appendChild(card);
    }
  }

  function normalizeJobsResponse(payload) {
    if (!Array.isArray(payload) || payload.length > 32) return {valid: false, jobs: []};
    const jobs = [];
    for (const raw of payload) {
      if (!isObject(raw) || raw.creates_authority !== false) return {valid: false, jobs: []};
      const job = {
        job_id: safeIdentifier(raw.job_id, 180), objective: safeText(raw.objective, 500),
        created_at: safeText(raw.created_at,80), is_current_objective:raw.is_current_objective===true,
        state: safeIdentifier(raw.state, 32), recorded_status: safeIdentifier(raw.recorded_status, 100),
        current_step: safeText(raw.current_step, 180), last_activity_at: safeText(raw.last_activity_at, 80),
        accomplished: safeText(raw.accomplished, 1800), gained: safeText(raw.gained, 1200),
        historical_next: safeText(raw.return_recap && raw.return_recap.next, 950),
        result_report: safeIdentifier(raw.return_recap && raw.return_recap.report_id, 180),
        public_result: safeText(raw.public_result, 500),
        parent_campaign_id: safeIdentifier(raw.parent_campaign_id, 180),
        source_record_sha256: safeIdentifier(raw.source_record_sha256, 64),
        next: safeText(raw.next, 500), worker: normalizeWorker(raw.worker),
        successful: raw.successful, historical: raw.historical, creates_authority: false
      };
      if (!job.job_id || !job.objective || !["working", "waiting", "done", "failed", "closed", "unknown", "needs_you"].includes(job.state)
          || !job.recorded_status || typeof job.successful !== "boolean"
          || typeof job.historical !== "boolean"
          || (job.last_activity_at && !Number.isFinite(Date.parse(job.last_activity_at)))) {
        return {valid: false, jobs: []};
      }
      jobs.push(job);
    }
    return {valid: true, jobs};
  }

  function normalizeRoadmapResponse(payload) {
    if (!isObject(payload) || payload.creates_authority !== false
        || payload.creates_continuing_authority !== false
        || payload.schema_version !== "fawkes.console.roadmap.v1"
        || !Array.isArray(payload.phases) || !Array.isArray(payload.tracks)) {
      return {valid: false, roadmap: null};
    }
    const normalizeItem = (raw, kind) => {
      if (!isObject(raw)) return null;
      const item = {id: safeIdentifier(raw.id, 100), kind, name: safeText(raw.name, 240),
        summary: safeText(raw.summary, 600), maturity: safeIdentifier(raw.maturity, 40),
        source: safeText(raw.source, 500), source_status: safeIdentifier(raw.source_status, 60),
        source_sha256: safeDigest(raw.source_sha256), source_revision: safeGitOid(raw.source_revision),
        source_bytes: finiteInteger(raw.source_bytes, null),
        source_excerpt: typeof raw.source_excerpt === "string" && raw.source_excerpt.length <= 16384
          ? raw.source_excerpt : "",
        group: safeText(raw.group, 160), mapped_component: safeIdentifier(raw.mapped_component, 80),
        runtime_state: safeIdentifier(raw.runtime_state, 40),
        prerequisites: Array.isArray(raw.prerequisites)
          ? raw.prerequisites.map((item) => safeIdentifier(item, 100)).filter(Boolean).slice(0, 40) : []};
      if (!item.id || !item.name || !item.summary || !item.maturity || !item.source
          || !item.source_status || !item.source_sha256 || !item.source_revision
          || item.source_bytes === null || item.source_bytes < 1
          || !item.group || item.summary.split(/\s+/).length < 5) return null;
      if (kind === "phase") item.number = finiteInteger(raw.number, null);
      return item;
    };
    const phases = payload.phases.map((raw) => normalizeItem(raw, "phase"));
    const tracks = payload.tracks.map((raw) => normalizeItem(raw, "track"));
    const expected = Array.from({length: 40}, (_, number) => "phase-" + number);
    if (phases.some((item) => !item || item.number === null) || tracks.some((item) => !item)
        || phases.map((item) => item.id).join("|") !== expected.join("|")
        || !Array.isArray(payload.expected_phase_ids)
        || payload.expected_phase_ids.join("|") !== expected.join("|")
        || payload.coverage_complete !== true) return {valid: false, roadmap: null};
    const allIds = new Set([...phases, ...tracks].map((item) => item.id));
    if (allIds.size !== phases.length + tracks.length
        || phases.some((item, index) => item.number !== index)
        || tracks.some((item) => !item.id.startsWith("track-"))
        || [...phases, ...tracks].some((item) => item.prerequisites.some((id) => !allIds.has(id) || id === item.id))) {
      return {valid: false, roadmap: null};
    }
    const sourceSha = safeDigest(payload.source_sha256);
    const sourceRevision = safeGitOid(payload.source_revision);
    if (!sourceSha || !sourceRevision) return {valid: false, roadmap: null};
    return {valid: true, roadmap: {phases, tracks, source_path: safeText(payload.source_path, 500),
      source_sha256: sourceSha, source_revision: sourceRevision, coverage_complete: true,
      creates_authority: false, creates_continuing_authority: false}};
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
    const repository = normalizeRepositoryResponse(values.repository);
    const jobs = normalizeJobsResponse(values.jobs);
    const roadmap = normalizeRoadmapResponse(values.roadmap);
    const expected = safeIdentifier(opts.expectedBuildId, 180);
    const buildMismatch = Boolean(expected && expected !== "__FAWKES_BUILD_ID__"
      && status.build && status.build.release_id !== expected);
    const malformed = !(schemaValid && authorityClosed && observationValid
      && status.valid && campaigns.valid && attention.valid && runtime.valid
      && repository.valid && jobs.valid && roadmap.valid);
    return {
      ok: !malformed && !buildMismatch,
      malformed,
      buildMismatch,
      build: status.build,
      observed_at: observationValid ? observedAt : "",
      observed_at_ms: observationValid ? observedAtMs : null,
      campaigns: campaigns.campaigns,
      current_campaign_id:safeIdentifier(values.current_campaign_id,180),
      attention: attention.attention,
      components: runtime.components,
      repository: repository.repository,
      jobs: jobs.jobs,
      roadmap: roadmap.roadmap,
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

  function svgElement(documentRef, tag, attributes, text) {
    const node = typeof documentRef.createElementNS === "function"
      ? documentRef.createElementNS("http://www.w3.org/2000/svg", tag)
      : documentRef.createElement(tag);
    for (const [name, value] of Object.entries(attributes || {})) {
      node.setAttribute(name, String(value));
    }
    if (text !== undefined) node.textContent = safeText(text, 240);
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
      provider_action_reserved: "Fawkes set aside the bounded allowance for one provider action.",
      builder_return_retained: "Fawkes saved the Worker result.",
      independent_review_retained: "Fawkes saved an independent review.",
      reviewed_application_completed: "The reviewed changes finished applying.",
      reviewed_git_completed: "The reviewed local Git update finished.",
      rider_cancelled_campaign: "Tanner ended the campaign.",
      provider_completion_ambiguous: "The provider result was uncertain, so Fawkes stopped safely."
    };
    return labels[event.kind] || "Fawkes recorded this campaign step without including private bodies.";
  }

  function activityHeading(kind) {
    const labels = {
      provider_action_reserved: "Provider work reserved",
      builder_return_retained: "Worker result saved",
      independent_review_retained: "Independent review recorded",
      reviewed_application_completed: "Reviewed changes applied",
      reviewed_git_completed: "Local Git update completed",
      rider_cancelled_campaign: "Campaign ended by Tanner",
      provider_completion_ambiguous: "Provider result uncertain"
    };
    return labels[kind] || safeText(kind, 140).replace(/_/g, " ");
  }

  function campaignStatusLabel(status) {
    const labels = {
      ready: "Ready",
      awaiting_independent_review: "Waiting for independent review",
      review_accepted_application_pending: "Accepted changes waiting to apply",
      reviewed_application_completed: "Reviewed changes applied",
      succeeded: "Completed",
      failed_safe: "Stopped safely",
      cancelled: "Cancelled",
      tanner_escalation: "Needs Tanner",
      historical_contract_unavailable: "Historical record",
      integrity_unavailable: "Record unavailable"
    };
    return labels[status] || safeText(status, 100).replace(/_/g, " ");
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

  function renderJobs(documentRef, target, jobs, projectionState) {
    target.replaceChildren();
    // Canonical objective order is shared with Campaign and saved updates.
    const values = Array.isArray(jobs) ? jobs.slice() : [];
    if (!values.length) {
      target.appendChild(element(documentRef, "p", "empty",
        "No job records are available to this preview. This does not mean Fawkes has no history or that every job is idle."));
      return;
    }
    for (const job of values) {
      const card = element(documentRef, "article", "job-card " + job.state
        + (job.state === "done" && !job.successful ? " unsuccessful" : ""));
      card.dataset.consoleKey = "job:" + job.job_id;
      card.appendChild(element(documentRef,"p","eyebrow",job.is_current_objective?'CURRENT OBJECTIVE':'RETAINED JOB HISTORY'));
      const heading = element(documentRef, "div", "job-title-row");
      heading.append(element(documentRef, "span", "job-state",
        (projectionState === "live" || projectionState === "sample" ? "" : "Last known ")
          + (job.state === "done" && !job.successful ? "done · unsuccessful" : job.state.replace("_", " "))),
        element(documentRef, "span", "meta", workerLabel(job.worker)));
      card.append(heading, element(documentRef, "h3", "job-objective", job.objective),
        element(documentRef, "p", "job-step", (job.state === "needs_you" ? "Needs Tanner · " : "Current step · ")
          + (job.current_step || "Unknown")),
        element(documentRef, "p", "job-time", "Last activity · " + (job.last_activity_at || "Unknown")));
      if (job.accomplished || job.next || job.public_result) {
        const recap = element(documentRef, "div", "job-recap");
        const short = (text) => text.length > 260 ? text.slice(0, 260) + " … (full recap in Details)" : text;
        recap.append(element(documentRef, "p", "", "Accomplished · " + short(job.accomplished || "Recorded outcome retained.")),
          element(documentRef, "p", "", "Gained · " + short(job.gained || "No deployed gain is claimed by this record.")),
          element(documentRef, "p", "", "Next · " + (job.next || "Unknown")));
        if (job.public_result) recap.appendChild(element(documentRef, "p", "", "Public Worker result · " + job.public_result));
        card.appendChild(recap);
      }
      if (job.state === "needs_you") {
        card.appendChild(element(documentRef, "p", "warning", "Supported action · "
          + (job.next || "Open the exact canonical Attention request shown above.")));
      }
      const details = element(documentRef, "details", "metadata-details console-card");
      details.dataset.consoleKey = "job:" + job.job_id + ":details";
      details.append(element(documentRef, "summary", "", "Details"), detailList(documentRef, [
        ["Job identity", job.job_id], ["Recorded campaign status", job.recorded_status],
        ["Parent job", job.parent_campaign_id || "Not recorded; no parent completion inferred"],
        ["Source record digest", job.source_record_sha256 || "Unavailable"],
        ["Complete accomplishment", job.accomplished], ["Complete gain", job.gained],
        ["Worker return", job.result_report || "No typed return available"],
        ["Historical next at Worker return (not a current instruction)", job.historical_next || "Not recorded"],
        ["Observation", projectionTruthLabel(projectionState)],
        ["Scope", "Fawkes-managed jobs only; a separately opened standalone CLI is not attached"]
      ]));
      card.appendChild(details);
      const link = element(documentRef, "a", "evidence-link", "Open campaign evidence");
      link.href = "#campaign-heading";
      link.dataset.pageLink = "1";
      link.dataset.campaignId = job.job_id;
      card.appendChild(link);
      target.appendChild(card);
    }
  }

  function campaignGraphModel(campaign) {
    const stages = [
      {id: "created", label: "Created", state: "completed", recorded: true},
      {id: "worker", label: "Worker", state: "unknown", recorded: false},
      {id: "review", label: "Review", state: "unknown", recorded: false},
      {id: "application", label: "Apply", state: "unknown", recorded: false},
      {id: "git", label: "Git", state: "unknown", recorded: false},
      {id: "terminal", label: "Outcome", state: "unknown", recorded: false}
    ];
    const byId = new Map(stages.map((stage) => [stage.id, stage]));
    const kinds = new Set((campaign.activity || []).map((event) => event.kind));
    if (kinds.has("provider_action_reserved") || kinds.has("builder_return_retained")) {
      byId.get("worker").state = kinds.has("builder_return_retained") ? "completed" : "waiting";
      byId.get("worker").recorded = true;
    }
    if (kinds.has("builder_failed_safe")) {
      byId.get("worker").state = "failed";
      byId.get("worker").recorded = true;
    }
    if (kinds.has("independent_review_retained")) {
      byId.get("review").state = "completed";
      byId.get("review").recorded = true;
    }
    if (kinds.has("reviewed_application_completed")) {
      byId.get("application").state = "completed";
      byId.get("application").recorded = true;
    }
    if (kinds.has("reviewed_git_completed")) {
      byId.get("git").state = "completed";
      byId.get("git").recorded = true;
    }
    const currentByStatus = {
      ready: "worker",
      awaiting_independent_review: "review",
      review_accepted_application_pending: "application",
      reviewed_application_completed: "git"
    };
    const current = currentByStatus[campaign.status];
    if (current && byId.get(current).state !== "completed") {
      byId.get(current).state = "waiting";
      byId.get(current).recorded = true;
    }
    if (campaign.status === "succeeded") {
      byId.get("terminal").state = "completed";
      byId.get("terminal").recorded = true;
    } else if (campaign.terminal) {
      byId.get("terminal").state = campaign.status === "failed_safe"
        ? "failed" : "blocked";
      byId.get("terminal").recorded = true;
    } else if (campaign.needs_tanner) {
      const unresolved = stages.find((stage) => stage.state === "current"
        || stage.state === "waiting" || stage.state === "unknown");
      if (unresolved) unresolved.state = "waiting";
    }
    for (const stage of stages) {
      const intervals = (campaign.reporting && campaign.reporting.intervals || [])
        .filter((item) => item.stage === stage.id);
      stage.intervals = intervals;
      if (intervals.length) {
        const latest = intervals[intervals.length - 1];
        stage.recorded = true;
        stage.state = latest.active_verified ? "current"
          : ["completed", "pass", "pass_with_caveats", "committed", "applied_verified_after_review", "succeeded"].includes(latest.state)
            ? "completed" : /fail|exception/.test(latest.state) ? "failed"
              : ["cancelled", "denied", "expired"].includes(latest.state) ? "blocked" : "waiting";
      }
    }
    const edges = stages.slice(0, -1).map((stage, index) => ({
      from: stage.id,
      to: stages[index + 1].id,
      established: stage.recorded && stages[index + 1].recorded
    }));
    const correctionCount = finiteInteger((campaign.observations || {}).correction_count, 0);
    return {
      stages,
      edges,
      correction_loop: correctionCount > 0 && byId.get("review").recorded
        ? {from: "review", to: "worker", count: correctionCount} : null
    };
  }

  function campaignGraphStages(campaign) {
    return campaignGraphModel(campaign).stages;
  }

  function selectCampaign(campaigns, selectedId) {
    const values = Array.isArray(campaigns) ? campaigns : [];
    return values.find((campaign) => campaign.campaign_id === selectedId)
      || values[0] || null;
  }

  function factWidget(documentRef, label, value) {
    const widget = element(documentRef, "div", "fact-widget");
    widget.append(element(documentRef, "span", "", label),
      element(documentRef, "strong", "", value));
    return widget;
  }

  function renderCampaignDashboard(documentRef, elements, campaigns, selectedId, selectedStageId, observationState = "live", nowMs = Date.now()) {
    const campaign = selectCampaign(campaigns, selectedId);
    elements.selector.replaceChildren();
    for (const candidate of campaigns) {
      const option = element(documentRef, "option", "",
        (candidate.terminal ? "History · " : "Open record · ")
          + campaignStatusLabel(candidate.status) + " · " + candidate.campaign_id.slice(-12));
      option.value = candidate.campaign_id;
      option.selected = Boolean(campaign && campaign.campaign_id === candidate.campaign_id);
      elements.selector.appendChild(option);
    }
    elements.empty.hidden = Boolean(campaign);
    elements.dashboard.hidden = !campaign;
    if (!campaign) {
      elements.history.textContent = "NO ACTIVE CAMPAIGN";
      elements.empty.textContent = "No campaign records are available to this preview. This is not an all-history or idle claim.";
      return {campaign_id: "", stage_id: ""};
    }
    elements.history.textContent = campaign.terminal
      ? "HISTORICAL RECORD" : "OPEN RECORD · " + campaignObservation([campaign], observationState, nowMs).label;
    elements.widgets.replaceChildren(
      factWidget(documentRef, "Recorded outcome", campaignStatusLabel(campaign.status)),
      factWidget(documentRef, "Recorded stage", campaignStatusLabel(campaign.current_stage)),
      factWidget(documentRef, "Iteration limit", campaign.iteration + " / " + campaign.maximum_iterations),
      factWidget(documentRef, "Provider turns", campaign.observations.builder_invocations === undefined
        ? "Not projected" : String(campaign.observations.builder_invocations))
    );
    const model = campaignGraphModel(campaign);
    const stages = model.stages;
    const selectedStage = stages.find((stage) => stage.id === selectedStageId)
      || stages.find((stage) => ["current", "waiting", "blocked", "failed"].includes(stage.state))
      || stages[0];
    elements.graph.replaceChildren();
    const definitions = svgElement(documentRef, "defs");
    const marker = svgElement(documentRef, "marker", {
      id: "campaign-arrow", viewBox: "0 0 10 10", refX: "8", refY: "5",
      markerWidth: "6", markerHeight: "6", orient: "auto-start-reverse"
    });
    marker.appendChild(svgElement(documentRef, "path", {d: "M 0 0 L 10 5 L 0 10 z"}));
    definitions.appendChild(marker);
    elements.graph.appendChild(definitions);
    const positions = new Map(stages.map((stage, index) => [stage.id, {
      x: 8 + (index * 108), y: 84
    }]));
    for (const edge of model.edges) {
      const start = positions.get(edge.from);
      const end = positions.get(edge.to);
      elements.graph.appendChild(svgElement(documentRef, "path", {
        d: `M${start.x + 88} ${start.y + 29} H${end.x}`,
        class: "graph-edge reference-edge", "marker-end": "url(#campaign-arrow)"
      }));
      if (edge.established) {
        elements.graph.appendChild(svgElement(documentRef, "path", {
          d: `M${start.x + 88} ${start.y + 29} H${end.x}`,
          class: "graph-edge established-edge", "marker-end": "url(#campaign-arrow)"
        }));
      }
    }
    if (model.correction_loop) {
      const review = positions.get("review");
      const worker = positions.get("worker");
      elements.graph.appendChild(svgElement(documentRef, "path", {
        d: `M${review.x + 44} ${review.y} C${review.x + 44} 20 ${worker.x + 44} 20 ${worker.x + 44} ${worker.y}`,
        class: "graph-edge correction-edge", "marker-end": "url(#campaign-arrow)"
      }));
      elements.graph.appendChild(svgElement(documentRef, "text", {
        x: (review.x + worker.x + 88) / 2, y: 18, class: "graph-edge-label"
      }, `Recorded correction loop ×${model.correction_loop.count}`));
    }
    for (const stage of stages) {
      const position = positions.get(stage.id);
      const node = svgElement(documentRef, "g", {
        class: "graph-step " + stage.state + (stage.id === selectedStage.id ? " selected" : ""),
        transform: `translate(${position.x} ${position.y})`, tabindex: "0", role: "button",
        "aria-label": `${stage.label}: ${stage.state}`
      });
      node.dataset.campaignStage = stage.id;
      node.append(svgElement(documentRef, "rect", {width: "88", height: "58", rx: "9"}),
        svgElement(documentRef, "text", {x: "44", y: "24", class: "graph-node-title"}, stage.label),
        svgElement(documentRef, "text", {x: "44", y: "43", class: "graph-node-state"}, stage.state));
      const timer = svgElement(documentRef, "text", {x: "44", y: "77", class: "stage-timer"}, "—");
      timer.dataset.stageTimer = stage.id;
      node.appendChild(timer);
      elements.graph.appendChild(node);
    }
    elements.detail.replaceChildren(
      element(documentRef, "p", "eyebrow", "SELECTED STEP"),
      element(documentRef, "h3", "", selectedStage.label),
      detailList(documentRef, [
        ["Recorded step state", selectedStage.state],
        ["Evidence", selectedStage.recorded ? "Supported by this campaign record" : "Reference workflow only"],
        ["Campaign identity", campaign.campaign_id],
        ["Recorded status", campaign.status],
        ["Worker", workerLabel(campaign.builder)],
        ["Reviewer", workerLabel(campaign.reviewer)],
        ["Satisfied acceptance conditions", campaign.satisfied_condition_count === null
          ? "Not projected" : String(campaign.satisfied_condition_count)],
        ["Budget remaining", "Not projected; no percentage is inferred"]
      ])
    );
    const attempts = (campaign.reporting && campaign.reporting.intervals || []).filter((item) =>
      item.stage === selectedStage.id || (selectedStage.id === "review" && item.stage === "review_queue"));
    for (const attempt of attempts) {
      elements.detail.appendChild(element(documentRef, "p", "stage-attempt",
        `Attempt ${attempt.attempt} · ${attempt.stage.replace("_", " ")} · ${attempt.state} · `
        + (attempt.timing_basis === "historical_invocation_envelope" ? "Historical invocation elapsed (not native active time) · " : "")
        + formatDuration(intervalSeconds(attempt, campaign.reporting, "stale", Date.now()))
        + ` · ${attempt.started_at || "Unknown start"} → ${attempt.ended_at || "No recorded close"}`
        + ` · Source: ${attempt.source_references.join(", ")}`));
    }
    if (campaign.reporting) elements.detail.appendChild(element(documentRef, "p", "meta",
      "Source record: " + (campaign.reporting.record_sha256 || "Unavailable")
      + ". Review queue ends at dispatch preparation; a reservation does not prove Reviewer launch."));
    updateStageTimers(elements.graph, campaign, "stale", Date.now());
    return {campaign_id: campaign.campaign_id, stage_id: selectedStage.id};
  }

  function projectionTruthLabel(state) {
    if (state === "live") return "CONNECTED · CURRENT READ-ONLY DATA";
    if (state === "sample") return "SAMPLE FIXTURE · NOT CURRENT";
    if (state === "stale") return "STALE LAST-VERIFIED PROJECTION";
    if (state === "disconnected") return "DISCONNECTED · NO CURRENT PROJECTION";
    return "UNAVAILABLE · NO CURRENT PROJECTION";
  }

  function renderRepositoryDashboard(documentRef, elements, repository, state, selectedPath, detailOpen) {
    const retainedTreeScroll = Number(elements.tree.scrollTop) || 0;
    elements.widgets.replaceChildren();
    elements.tree.replaceChildren();
    elements.metadata.replaceChildren();
    if (!repository) {
      elements.browser.hidden = true;
      elements.detailView.hidden = true;
      elements.empty.hidden = false;
      elements.empty.textContent = "The bounded repository projection is unavailable.";
      return {path: "", detail_open: false};
    }
    elements.empty.hidden = true;
    const summary = repository.status_summary;
    elements.widgets.replaceChildren(
      factWidget(documentRef, "Branch", repository.branch),
      factWidget(documentRef, "HEAD revision", repository.head.slice(0, 12)),
      factWidget(documentRef, "HEAD files shown", String(repository.files.length)),
      factWidget(documentRef, "Working-tree paths", String(summary.dirty_paths)),
      factWidget(documentRef, "Staged", String(summary.staged_paths))
    );
    const selected = repository.files.find((file) => file.path === selectedPath)
      || repository.files[0] || null;
    let priorGroup = "";
    for (const file of repository.files) {
      const group = file.path.includes("/") ? file.path.split("/")[0] : "root";
      if (group !== priorGroup) {
        elements.tree.appendChild(element(documentRef, "p", "tree-group", group));
        priorGroup = group;
      }
      const button = element(documentRef, "button", "tree-file"
        + (selected && selected.path === file.path ? " selected" : ""), file.path);
      button.type = "button";
      button.dataset.repositoryPath = file.path;
      button.appendChild(element(documentRef, "span", "badge", file.head_change));
      elements.tree.appendChild(button);
    }
    elements.tree.scrollTop = retainedTreeScroll;
    if (!selected) {
      elements.browser.hidden = false;
      elements.detailView.hidden = true;
      elements.empty.hidden = repository.files.length !== 0;
      if (!repository.files.length) elements.empty.textContent =
        "No files are included in the bounded HEAD revision selection.";
      return {path: "", detail_open: false};
    }
    elements.browser.hidden = Boolean(detailOpen);
    elements.detailView.hidden = !detailOpen;
    elements.comparison.textContent = repository.comparison_base === "root"
      ? "ROOT COMMIT → HEAD " + repository.head.slice(0, 12)
      : repository.comparison_base.slice(0, 12) + " → HEAD " + repository.head.slice(0, 12);
    elements.heading.textContent = selected.path;
    elements.summary.textContent = "Committed " + selected.head_change
      + " in this HEAD revision · working tree: " + selected.worktree_state;
    const facts = detailList(documentRef, [
      ["Projection status", projectionTruthLabel(state)],
      ["Exact revision", selected.revision],
      ["Blob", selected.object_id],
      ["Mode", selected.mode],
      ["HEAD change", selected.head_change],
      ["Working-tree state", selected.worktree_state],
      ["Review status", selected.review_status]
    ]);
    elements.metadata.appendChild(facts);
    elements.diff.textContent = selected.diff_excerpt || "No bounded diff excerpt is available.";
    return {path: selected.path, detail_open: Boolean(detailOpen)};
  }

  const ARCHITECTURE_COMPONENTS = Object.freeze({
    identity: {title: "Phoenix identity", maturity: "Built",
      owner: "Defines identity, continuity, privacy, and authority boundaries.",
      relationships: "Constrains every record owner and protected transition.",
      evidence: "docs/phoenix/FOUNDATION.md", observation: "unavailable"},
    archive: {title: "Archive and evidence", maturity: "Built",
      owner: "Retains body-free provenance, receipts, and durable operational evidence.",
      relationships: "Supports Memory, development review, and later reconciliation.",
      evidence: "docs/phoenix/APP_ARCHITECTURE.md", observation: "unavailable"},
    memory: {title: "Memory", maturity: "Built",
      owner: "Maintains governed continuity records without granting execution authority.",
      relationships: "Consumes bounded evidence and supports the Library.",
      evidence: "docs/phoenix/CANONICAL_ROADMAP.md", observation: "unavailable"},
    library: {title: "Library", maturity: "Built",
      owner: "Provides retained knowledge through governed retrieval paths.",
      relationships: "Draws from Memory and serves permitted clients.",
      evidence: "docs/phoenix/APP_ARCHITECTURE.md", observation: "unavailable"},
    clients: {title: "Clients and console", maturity: "Built",
      owner: "Presents authenticated projections and routes exact Attention links.",
      relationships: "Requests work from canonical services; it does not own their authority.",
      evidence: "src/app/server.py", observation: "app_server",
      observedName: "Canonical app server (not this localhost candidate preview)"},
    development: {title: "Development campaign", maturity: "In progress",
      owner: "Owns stepwise campaign state, reservations, review, application, and Git sequencing.",
      relationships: "Coordinates Workers and uses Native Attention for protected actions.",
      evidence: "src/runtime/codex_development_campaign.py", observation: "development_coordinator",
      observedName: "Canonical development coordinator"},
    attention: {title: "Native Attention", maturity: "Built",
      owner: "Records Tanner's exact, expiring, single-use protected-action decision.",
      relationships: "Guards protected development actions without transferring authority to this console.",
      evidence: "src/runtime/development_attention.py", observation: "app_server",
      observedName: "Attention projection on the canonical app server"},
    workers: {title: "Workers and Reviewers", maturity: "In progress",
      owner: "Perform bounded candidate work and independent evidence review.",
      relationships: "Return evidence to the campaign; they cannot directly apply or commit.",
      evidence: "docs/phoenix/CANONICAL_ROADMAP.md", observation: "reviewer_launcher",
      observedName: "Reviewer launcher"},
    application_git: {title: "Application and Git", maturity: "Built",
      owner: "Applies accepted postimages once and advances the exact reviewed commit.",
      relationships: "Consumes campaign-owned eligibility; restart reconciliation is observation-only.",
      evidence: "src/runtime/git_commit_transaction.py", observation: "unavailable"},
    embodiment: {title: "Physical embodiment", maturity: "Planned",
      owner: "Progressive portable-console and later physical-body direction.",
      relationships: "Informed by the development system; no movement or sensing is implemented here.",
      evidence: "docs/phoenix/ROADMAP_AMENDMENT_2026_09_08_EXECUTION.md", observation: "unavailable"}
  });

  function architectureObservation(components, nodeId, state) {
    const contract = ARCHITECTURE_COMPONENTS[nodeId];
    if (!contract || state !== "live") return "unknown";
    if (contract.observation === "unavailable") return "unavailable";
    const observed = components.find((item) => item.name === contract.observation);
    if (!observed || observed.state === "unobserved_configured") return "unavailable";
    return observed.state;
  }

  function renderArchitectureDashboard(documentRef, map, detail, components, state, selectedId) {
    const selected = ARCHITECTURE_COMPONENTS[selectedId] ? selectedId : "development";
    for (const button of Array.from(map.querySelectorAll("[data-architecture-node]"))) {
      const nodeId = button.dataset.architectureNode;
      const observation = architectureObservation(components, nodeId, state);
      button.classList.toggle("selected", nodeId === selected);
      button.classList.remove("observed", "unavailable");
      button.classList.add(observation === "unknown" || observation === "unavailable"
        ? "unavailable" : "observed");
      button.title = "Observed state: " + observation;
    }
    const contract = ARCHITECTURE_COMPONENTS[selected];
    const observation = architectureObservation(components, selected, state);
    detail.replaceChildren(
      element(documentRef, "p", "eyebrow", "REFERENCE SYSTEM COMPONENT"),
      element(documentRef, "h3", "", contract.title),
      detailList(documentRef, [
        ["Implementation maturity", contract.maturity],
        ["Purpose", contract.owner],
        ["Relationships", contract.relationships],
        ["Observed service / instance", contract.observedName || "No runtime source projected"],
        ["Observed runtime state", observation],
        ["Observation freshness", projectionTruthLabel(state)],
        ["Evidence", contract.evidence],
        ["Interpretation", "Reference maturity is not runtime health; connection freshness proves neither"]
      ])
    );
    return selected;
  }

  // Relations are retained from Current's source diagram, never phase numbering.
  const COMBINED_RELATIONS = Object.freeze([
    ["identity", "archive", "evidence"], ["archive", "memory", "learns"],
    ["memory", "library", "supports"], ["clients", "identity", "identity"],
    ["clients", "development", "requests"], ["development", "attention", "guards"],
    ["development", "workers", "coordinates"], ["workers", "application_git", "returns"],
    ["attention", "application_git", "permits"], ["development", "embodiment", "informs"],
    ["memory", "embodiment", "continuity"]
  ]);

  // Authored topical associations to the exact phase headings, NOT implementation
  // ownership or prerequisites. A renamed source heading visibly becomes unmapped.
  const COMBINED_PHASE_TOPICS = Object.freeze([
    ["Ownership, integrity", "identity"], ["Durable Library", "library"],
    ["canonical processing ledger", "archive"], ["export staging importer", "archive"],
    ["historical and federated search", "library"], ["Historical corpus validation", "library"],
    ["Retrieval Flight Recorder", "library"], ["Unified Retrieval Planner", "library"],
    ["cross-conversation continuity", "memory"], ["Context Composer", "memory"],
    ["Improvement Workshop", "development"], ["temporal knowledge", "memory"],
    ["Claim Ledger", "memory"], ["historical absorption", "memory"],
    ["Decision and Outcome", "memory"], ["Relationship Memory", "memory"],
    ["Personality development", "identity"], ["Development Orchestrator", "development"],
    ["budget and model router", "workers"], ["video understanding", "library"],
    ["Environmental Perception", "embodiment"], ["Temporal awareness", "development"],
    ["Persistent self-created workflows", "development"], ["Proactive intelligence", "development"],
    ["Safe simulation", "development"], ["Credential Authority", "attention"],
    ["Physical Safety", "embodiment"], ["tool and action framework", "attention"],
    ["Embodiment and Evolving", "embodiment"], ["Cross-Device Presence", "clients"],
    ["Reading and Guided Learning", "library"], ["Realtime voice", "clients"],
    ["event-sound experience", "clients"], ["environmental adapters", "embodiment"],
    ["Portable Phoenix Continuity", "identity"], ["multi-Phoenix management", "identity"],
    ["Household Identity", "identity"], ["Peer-Phoenix testimony", "memory"],
    ["Phoenix-to-Phoenix communication", "clients"], ["Full Phoenix ecosystem", "identity"]
  ]);

  function combinedModel(roadmap) {
    const nodes = [{id: "combined-root", name: "Fawkes system", kind: "root",
      summary: "Explore shared components and source-bound capabilities. Grouping is not a dependency."}];
    const edges = [], groups = [];
    for (const [id, component] of Object.entries(ARCHITECTURE_COMPONENTS)) {
      const node = {id, name: component.title, summary: component.owner, kind: "component",
        maturity: component.maturity, source: component.evidence, children: []};
      nodes.push(node); groups.push(node);
      // The real architecture connects the shared foundations. Avoid ten
      // redundant root spokes obscuring those documented relationships.
      if (id === "identity") edges.push({from: "combined-root", to: id, kind: "grouping", label: "contains"});
    }
    const flows = [
      ["console-surface", "Pi / PC console", "clients", "Lets Tanner inspect the same authenticated campaign state from supported console browsers.", "src/app/static/dev-console/console.js"],
      ["pc-console-service", "PC console service", "clients", "Serves authenticated observations and durable updates while the required PC remains awake.", "src/app/server.py"],
      ["pi-companion", "Pi companion", "embodiment", "Opens Summary through the bridge and manages Matrix; remote device health requires separate evidence.", "docs/console-observation-contract.md"],
      ["managed-worker", "Managed Worker", "workers", "Executes the bound task and waits for exact native decisions; a standalone CLI is separate.", "src/runtime/codex_development_campaign.py"],
      ["managed-reviewer", "Independent Reviewer", "workers", "Examines exact candidate material read-only and returns a separately validated independent disposition.", "src/runtime/wsl_codex_reviewer.py"],
      ["pc-saved-update", "Saved PC update", "clients", "Retains one dated report for retrieval and copying on the device where that browser is open.", "src/app/server.py"]
    ];
    for (const [id,name,parent,summary,source] of flows) {
      nodes.push({id,name,parent,summary,source,kind:"operation",maturity:"Existing implementation"});
      groups.find(group=>group.id===parent).children.push(id);
      edges.push({from:parent,to:id,kind:"association",label:"implemented flow participant",source});
    }
    for (const [from,to,label,source] of [
      ["console-surface","pc-console-service","authenticated state / update request","src/app/server.py"],
      ["pi-companion","console-surface","opens Summary through retained bridge","docs/console-observation-contract.md"],
      ["pc-console-service","attention","exact authenticated decision","src/app/server.py"],
      ["attention","managed-worker","one-action response to waiting operation","src/runtime/codex_app_server.py"],
      ["managed-worker","development","task return / progress","src/runtime/codex_development_campaign.py"],
      ["development","managed-reviewer","bound read-only review request","src/runtime/wsl_codex_reviewer.py"],
      ["managed-reviewer","development","independent return, not deployment","src/runtime/wsl_codex_reviewer.py"],
      ["pc-console-service","pc-saved-update","durable snapshot / exact download","src/app/server.py"]
    ]) edges.push({from,to,label,source,kind:"flow"});
    const unmapped = new Map();
    for (const item of [...(roadmap && roadmap.phases || []), ...(roadmap && roadmap.tracks || [])]) {
      const topic = item.kind === "phase" && COMBINED_PHASE_TOPICS[item.number];
      const component = topic && item.name.includes(topic[0]) ? topic[1] : item.mapped_component;
      let group = groups.find((node) => node.id === component);
      if (!group) {
        const key = item.group;
        if (!unmapped.has(key)) {
          const node = {id: "unmapped-" + item.id, name: "Unmapped · " + key, kind: "group",
            summary: "No component association is documented in this inventory. This is a discovery group, not a prerequisite.", children: []};
          unmapped.set(key, node); groups.push(node); nodes.push(node);
          edges.push({from: "combined-root", to: node.id, kind: "grouping", label: "unmapped inventory"});
        }
        group = unmapped.get(key);
      }
      group.children.push(item.id);
      nodes.push({...item, parent: group.id,
        association_basis: topic && component === topic[1]
          ? "Authored topic association from the retained Phase " + item.number + " heading: " + item.name
          : "Existing source inventory association; not a runtime owner or prerequisite."});
      edges.push({from: group.id, to: item.id,
        kind: group.kind === "component" ? "association" : "grouping",
        label: group.kind === "component" ? "associated capability" : "unmapped member",
        source: item.source, source_sha256: item.source_sha256});
      for (const prerequisite of item.prerequisites || []) {
        edges.push({from: prerequisite, to: item.id, kind: "prerequisite", label: "documented prerequisite",
          source: item.source, source_sha256: item.source_sha256});
      }
    }
    for (const [from, to, label] of COMBINED_RELATIONS) edges.push({from, to, label, kind: "architecture",
      source: "src/app/static/dev-console/index.html#architecture-map"});
    for (const group of groups) {
      if (group.kind === "component" && group.children.some(id => {
        const child = nodes.find(node => node.id === id);
        return child && child.kind !== "operation" && child.maturity !== "implemented";
      })) group.maturity = group.maturity === "Built" ? "Foundation built; expansions planned" : group.maturity;
    }
    return {nodes, edges, groups};
  }

  function combinedLayout(model, expanded) {
    // Same foundation placement as Current, not a second tall inventory list.
    const anchors = {identity: [20, 34, 140], archive: [205, 34, 140],
      memory: [390, 34, 130], library: [535, 34, 105], clients: [20, 134, 140],
      development: [205, 134, 140], attention: [390, 110, 130], workers: [535, 134, 105],
      application_git: [390, 260, 130], embodiment: [205, 292, 140]};
    const positions = new Map([["combined-root", {x: 20, y: 292, width: 140, height: 64}]]);
    let y = 420, unmappedCount = 0;
    for (const group of model.groups) {
      const anchor = anchors[group.id];
      positions.set(group.id, anchor ? {x: anchor[0], y: anchor[1], width: anchor[2], height: 64}
        : unmappedCount === 0 ? {x: 535, y: 292, width: 105, height: 64}
          : {x: 20, y, width: 260, height: 90});
      if (!anchor && unmappedCount++ > 0) y += 120;
    }
    // Compact two-dimensional capability islands, not a long vertical strip.
    // Reserve the first island for Current's foundations. Each visible entity
    // still has one identity and one non-overlapping box in this same SVG.
    const open = model.groups.filter(group => expanded.has(group.id) && group.children.length);
    const columns = Math.min(3, Math.ceil(Math.sqrt(open.length + 1)));
    let rowY = 0, rowHeight = Math.max(400, y - 20);
    open.forEach((group, slot) => {
      const column = (slot + 1) % columns;
      if (column === 0) {rowY += rowHeight + 40; rowHeight = 0;}
      group.children.forEach((id, index) => positions.set(id, {
        x: column * 700 + 20 + (index % 3) * 216,
        y: rowY + 20 + Math.floor(index / 3) * 120, width: 196, height: 94}));
      rowHeight = Math.max(rowHeight, Math.ceil(group.children.length / 3) * 120 + 20);
    });
    return {positions, width: Math.max(660, ...Array.from(positions.values(), p => p.x + p.width + 20)),
      height: Math.max(400, ...Array.from(positions.values(), p => p.y + p.height + 20))};
  }

  function combinedState() {
    return {expanded: new Set(), selected: "identity", x: 0, y: 0, zoom: 1, suppressClick: false,
      minimumZoom: 0.15, initialized: false};
  }

  function transformCombined(graph, state) {
    const layer = graph && graph.querySelector("[data-combined-layer]");
    if (layer) layer.setAttribute("transform", `translate(${state.x} ${state.y}) scale(${state.zoom})`);
  }

  function combinedControl(state, action, layout) {
    if (layout) state.minimumZoom = Math.min(0.15, Math.min(660 / layout.width, 400 / layout.height) / 2);
    if (action === "fit" && layout) {
      state.zoom = Math.min(1, 660 / layout.width, 400 / layout.height);
      state.x = (660 - layout.width * state.zoom) / 2; state.y = (400 - layout.height * state.zoom) / 2;
    } else if (action === "reset") {
      state.zoom = 1; state.x = 0; state.y = 0;
    } else if (action === "in" || action === "out") {
      const old = state.zoom;
      state.zoom = Math.max(state.minimumZoom, Math.min(3, old * (action === "in" ? 1.25 : 0.8)));
      state.x = 330 - (330 - state.x) * state.zoom / old;
      state.y = 200 - (200 - state.y) * state.zoom / old;
    } else {
      state.x += action === "left" ? 70 : action === "right" ? -70 : 0;
      state.y += action === "up" ? 70 : action === "down" ? -70 : 0;
    }
  }

  function focusCombined(model, state, id) {
    const node = model.nodes.find((item) => item.id === id);
    if (!node) return;
    state.selected = id;
    if (node.parent) state.expanded.add(node.parent);
    const position = combinedLayout(model, state.expanded).positions.get(id);
    state.zoom = Math.max(0.85, state.zoom);
    state.x = 330 - (position.x + position.width / 2) * state.zoom;
    state.y = 170 - (position.y + position.height / 2) * state.zoom;
  }

  function combinedOperationStatus(id, projection, state, nowMs = Date.now()) {
    const live = state === "live";
    const campaign = selectCampaign(projection && projection.campaigns,
      projection && projection.current_campaign_id);
    const identity = campaign ? campaign.campaign_id : "No current campaign";
    if (["managed-worker","managed-reviewer"].includes(id)) {
      const role = id === "managed-worker" ? "worker" : "reviewer";
      const observations = (campaign && campaign.managed || [])
        .filter(item => (item.role || "worker") === role).sort((a,b)=>Date.parse(b.updated_at)-Date.parse(a.updated_at));
      const current = observations[0];
      if (!current) return {short:"Not attached",detail:identity+" · No managed "+role+" observation. A standalone CLI is not attached."};
      const known = current.state === "completed" || current.state === "failed";
      const fresh = live && Number.isFinite(Date.parse(current.verified_at))
        && nowMs-Date.parse(current.verified_at)>=0 && nowMs-Date.parse(current.verified_at)<=30000;
      // Process reachability is not execution. Use the same native-state
      // interpretation as role clocks, scoped to this role and invocation.
      const turns = (campaign.reporting && campaign.reporting.turns || [])
        .filter(turn => turn.role === role && turn.invocation_id === current.invocation_id);
      const turn = turns[turns.length - 1];
      const native = nativeTurnLabel(turn, fresh ? "live" : "disconnected", nowMs);
      const label = known ? "Last " + current.state : !fresh ? "Unknown / last known"
        : !turn ? "No native turn"
          : native.startsWith("Waiting") ? "Waiting"
            : native === "Executing" ? "Executing" : "Execution unknown";
      return {short:label,detail:`${identity} · ${current.invocation_id} · ${label}. Native turn ${turn ? turn.thread_id + "/" + turn.turn_id : "not observed"}: ${native}. Last activity ${current.updated_at||'unknown'}; last verified ${current.verified_at||'unavailable'}. A retained record is not a live process.`};
    }
    if (id === "pi-companion") return {short:"Remote unknown",detail:"This PC observation does not verify Pi reachability. The retained accepted rollout and Tanner's physical checks are historical evidence, not a live device heartbeat."};
    if (id === "pc-console-service") return {short:live?"Reachable":"Not current",detail:"Authenticated PC service synchronization: "+(live?"successful":"not current")+". This does not establish Worker execution or Pi health."};
    if (id === "console-surface") return {short:live?"Synchronized":"Last known",detail:identity+" · "+(live?"Browser received current authenticated observations.":"Retained observations only; current task state is unknown.")};
    if (id === "pc-saved-update") return {short:live?"Service reachable":"Not current",detail:"Send update saves an exact snapshot, then requests Windows clipboard delivery. Only a matching Windows read-back acknowledgement confirms copying; service reachability alone does not."};
    return {short:"Unknown",detail:"No independent runtime observation for this item."};
  }

  function renderCombined(documentRef, elements, roadmap, state, components, projectionState) {
    if (!elements.combinedMap) return null;
    const model = combinedModel(roadmap), layout = combinedLayout(model, state.expanded);
    const graph = elements.combinedMap;
    state.minimumZoom = Math.min(0.15, Math.min(660 / layout.width, 400 / layout.height) / 2);
    if (!state.initialized) {combinedControl(state, "fit", layout); state.initialized = true;}
    const operational = node => combinedOperationStatus(node.id,elements.projection,projectionState);
    const renderKey = JSON.stringify([model, Array.from(state.expanded), state.selected,
      model.nodes.filter(node=>node.kind==="operation").map(operational)]);
    if (graph.dataset.combinedRenderKey !== renderKey && !state.gesturing) {
    graph.dataset.combinedRenderKey = renderKey;
    graph.replaceChildren();
    const defs = svgElement(documentRef, "defs");
    const marker = svgElement(documentRef, "marker", {id: "combined-arrow", viewBox: "0 0 10 10",
      refX: "9", refY: "5", markerWidth: "6", markerHeight: "6", orient: "auto"});
    marker.appendChild(svgElement(documentRef, "path", {d: "M0 0 L10 5 L0 10z", fill: "#87a5b9"}));
    defs.appendChild(marker); graph.appendChild(defs);
    const layer = svgElement(documentRef, "g", {"data-combined-layer": "true"});
    graph.appendChild(layer);
    model.edges.forEach((edge, index) => {
      const from = layout.positions.get(edge.from), to = layout.positions.get(edge.to);
      if (!from || !to) return; // Hidden endpoints remain discoverable in details.
      const sx = from.x + from.width, sy = from.y + from.height / 2, ex = to.x, ey = to.y + to.height / 2;
      const currentPaths = ["M160 66 H205", "M345 66 H390", "M520 66 H535",
        "M90 134 V98", "M160 166 H205", "M345 166 L390 142",
        "M345 182 C410 220 470 220 535 182", "M600 198 L500 260",
        "M455 174 V260", "M275 198 V292", "M455 98 L325 292"];
      const relation = COMBINED_RELATIONS.findIndex(item => item[0] === edge.from && item[1] === edge.to);
      const lane = 8 + (index % 3) * 4;
      const route = edge.kind === "architecture" && relation >= 0 ? currentPaths[relation]
        : edge.from === "combined-root" ? `M${from.x} ${sy} H${lane} V${ey} H${ex}`
        : `M${from.x + from.width / 2} ${from.y + from.height} V${from.y + from.height + 12} H${lane} V${ey} H${ex}`;
      const path = svgElement(documentRef, "path", {
        d: route,
        class: "combined-edge " + edge.kind, "aria-label": `${edge.from} → ${edge.to}: ${edge.label}`,
        ...(["architecture","prerequisite","flow"].includes(edge.kind) ? {"marker-end": "url(#combined-arrow)"} : {})});
      path.appendChild(svgElement(documentRef, "title", {}, `${edge.kind}: ${edge.label}`));
      layer.appendChild(path);
      if ((edge.from === state.selected || edge.to === state.selected)
          && ["architecture", "prerequisite", "flow"].includes(edge.kind)) {
        layer.appendChild(svgElement(documentRef, "text", {x: ex - 10, y: ey - 9,
          class: "combined-edge-label"}, edge.label));
      }
    });
    for (const node of model.nodes) {
      const position = layout.positions.get(node.id);
      if (!position) continue;
      const group = node.children && node.children.length > 0;
      const button = svgElement(documentRef, "g", {class: "combined-node "
        + (node.maturity || "unknown").toLowerCase().replace(/ /g, "-")
        + (position.height === 64 ? " foundation" : "")
        + (state.selected === node.id ? " selected" : ""), role: "button", tabindex: "0",
        transform: `translate(${position.x} ${position.y})`,
        "aria-label": node.name + (group ? `, ${node.children.length} capabilities; activate to expand or collapse` : ""),
        ...(group ? {"aria-expanded": String(state.expanded.has(node.id))} : {})});
      button.dataset.combinedId = node.id;
      button.appendChild(svgElement(documentRef, "rect", {width: position.width, height: position.height}));
      const compactName = {archive: "Archive & evidence", development: "Development",
        clients: "Clients & console", workers: "Workers", application_git: "Application & Git",
        embodiment: "Physical embodiment"}[node.id] || (node.kind === "group" ? "Not mapped yet" : node.name);
      const words = compactName.split(/\s+/), lines = [""];
      for (const word of words) {
        if ((lines[lines.length - 1] + word).length > Math.floor(position.width / (position.height === 64 ? 6.5 : 8))) lines.push("");
        lines[lines.length - 1] += (lines[lines.length - 1] ? " " : "") + word;
      }
      lines.slice(0, 2).forEach((line, index) => button.appendChild(svgElement(documentRef, "text",
        {x: position.width / 2, y: (position.height === 64 ? 18 : 23) + index * (position.height === 64 ? 15 : 19)}, line + (index === 1 && lines.length > 2 ? "…" : ""))));
      button.appendChild(svgElement(documentRef, "text", {x: position.width / 2, y: position.height - 12, class: "combined-status"},
        (group ? (state.expanded.has(node.id) ? "− " : "+ ") + node.children.length + " · " : "")
        + (node.kind === "operation" ? operational(node).short : String(node.maturity).startsWith("Foundation built") ? "Partial" : node.maturity === "In progress" ? "In progress" : node.maturity || (node.kind === "group" ? "Unknown" : "Overview"))
        + (node.source_status === "proposed" ? " · proposed" : "")));
      layer.appendChild(button);
    }
    }
    transformCombined(graph, state);
    if (elements.combinedCoverage) elements.combinedCoverage.textContent = roadmap
      ? `${Object.keys(ARCHITECTURE_COMPONENTS).length} components · ${roadmap.phases.length} phases · ${roadmap.tracks.length} tracks. Tap a foundation to reveal its capabilities.`
      : "Roadmap unavailable; component reference only. Coverage is unknown.";
    if (elements.combinedSelect) {
      const optionsKey = JSON.stringify(model.nodes.map(node => [node.id, node.name]));
      if (elements.combinedSelect.dataset.optionsKey !== optionsKey) {
      elements.combinedSelect.dataset.optionsKey = optionsKey;
      elements.combinedSelect.replaceChildren();
      for (const node of model.nodes) {
        const option = element(documentRef, "option", "", node.id + " · " + node.name);
        option.value = node.id; option.selected = node.id === state.selected;
        elements.combinedSelect.appendChild(option);
      }
      }
      elements.combinedSelect.value = state.selected;
    }
    const selected = model.nodes.find((node) => node.id === state.selected) || model.nodes[0];
    // Preserve source-excerpt reading state when an ordinary refresh repeats selection.
    const key = JSON.stringify([selected, projectionState, components, operational(selected)]);
    if (elements.detail.dataset.combinedDetailKey !== key) {
      elements.detail.dataset.combinedDetailKey = key;
      elements.detail.replaceChildren(element(documentRef, "h3", "", selected.name),
        element(documentRef, "p", "", selected.summary), detailList(documentRef, [
          ["Phase / track / component", selected.id], ["Maturity", selected.maturity || "Grouping only"],
          ["Planning status", selected.source_status || "Component reference"],
          ["Runtime", selected.kind === "operation" ? operational(selected).detail : selected.kind === "component" ? architectureObservation(components || [], selected.id, projectionState) : "unknown"],
          ["Source", selected.source || "Existing console inventory grouping"],
          ["Source revision", selected.source_revision || "Not projected"],
          ["Source digest", selected.source_sha256 || "Not projected"],
          ["Source bytes", String(selected.source_bytes || "Not projected")],
          ["Association basis", selected.association_basis || "Current architecture reference"],
          ["Relations", model.edges.filter((edge) => edge.from === selected.id || edge.to === selected.id)
            .map((edge) => `${edge.from} → ${edge.to}: ${edge.kind} · ${edge.label}`).join("; ")],
          ["Observation", projectionTruthLabel(projectionState)]
        ]));
      if (selected.source_excerpt) {
        const details = element(documentRef, "details", "roadmap-source-details");
        details.append(element(documentRef, "summary", "", "Read retained source excerpts"),
          element(documentRef, "pre", "detail-summary", selected.source_excerpt));
        elements.detail.appendChild(details);
      }
    }
    return {model, layout};
  }

  function bindCombinedGestures(graph, state, onActivity) {
    if (!graph) return;
    const pointers = new Map();
    let previous = null, travel = 0;
    const measure = () => {
      const points = Array.from(pointers.values());
      return {x: points.reduce((sum, p) => sum + p.x, 0) / points.length,
        y: points.reduce((sum, p) => sum + p.y, 0) / points.length,
        distance: points.length === 2 ? Math.hypot(points[0].x - points[1].x, points[0].y - points[1].y) : 0};
    };
    graph.addEventListener("pointerdown", (event) => {
      if (event.button !== undefined && event.button !== 0) return;
      if (pointers.size >= 2) {state.suppressClick = true; return;}
      if (!pointers.size) {state.suppressClick = false; travel = 0;}
      pointers.set(event.pointerId, {x: event.clientX, y: event.clientY});
      state.gesturing = true;
      previous = measure();
      if (pointers.size > 1) state.suppressClick = true;
      // Capture the original node so stationary taps still select that node.
      if (event.target.setPointerCapture) event.target.setPointerCapture(event.pointerId);
      onActivity();
    });
    graph.addEventListener("pointermove", (event) => {
      if (!pointers.has(event.pointerId)) return;
      pointers.set(event.pointerId, {x: event.clientX, y: event.clientY});
      const next = measure(), rect = graph.getBoundingClientRect();
      // SVG may be letterboxed by the responsive height cap. Pinch around
      // the actual drawing coordinates, not the outer element's left edge.
      const width = rect.width || 660, height = rect.height || width * 400 / 660;
      const scale = Math.min(width / 660, height / 400), ratio = 1 / scale;
      const left = rect.left + (width - 660 * scale) / 2;
      const top = rect.top + (height - 400 * scale) / 2;
      const dx = next.x - previous.x, dy = next.y - previous.y;
      travel += Math.hypot(dx, dy);
      if (travel > 8) state.suppressClick = true;
      if (state.suppressClick) {
        if (previous.distance && next.distance) {
          const old = state.zoom;
          state.zoom = Math.max(state.minimumZoom, Math.min(3, old * next.distance / previous.distance));
          const cx = (previous.x - left) * ratio, cy = (previous.y - top) * ratio;
          state.x = cx - (cx - state.x) * state.zoom / old;
          state.y = cy - (cy - state.y) * state.zoom / old;
        }
        state.x += dx * ratio; state.y += dy * ratio;
        transformCombined(graph, state); event.preventDefault(); onActivity();
      }
      previous = next;
    });
    const end = (event) => {
      pointers.delete(event.pointerId);
      state.gesturing = pointers.size > 0;
      if (event.type === "pointercancel") state.suppressClick = true;
      previous = pointers.size ? measure() : null;
    };
    graph.addEventListener("pointerup", end); graph.addEventListener("pointercancel", end);
    graph.addEventListener("lostpointercapture", end);
  }

  function renderRoadmapInventory(documentRef, elements, roadmap, options) {
    const value = options || {};
    const mode = ["current", "roadmap", "combined"].includes(value.mode) ? value.mode : "current";
    const heading = documentRef.getElementById("architecture-heading");
    if (heading) heading.hidden = mode === "combined";
    elements.overview.hidden = mode !== "current";
    elements.inventory.hidden = mode !== "roadmap";
    if (elements.combined) elements.combined.hidden = mode !== "combined";
    for (const button of elements.modes) {
      button.setAttribute("aria-pressed", String(button.dataset.architectureMode === mode));
    }
    if (mode === "combined") {
      renderCombined(documentRef, elements, roadmap, value.combinedState || elements.combinedState || combinedState(),
        value.components || elements.components || [], value.projectionState || elements.projectionState || "unavailable");
      return {mode, selected_id: value.selectedId || ""};
    }
    delete elements.detail.dataset.combinedDetailKey;
    if (!roadmap || mode === "current") return {mode, selected_id: value.selectedId || ""};
    const openGroups = new Set(Array.from(elements.groups.querySelectorAll("details.roadmap-group"))
      .filter((group) => group.open).map((group) => group.dataset.roadmapGroup));
    const filter = safeText(value.filter, 80).toLowerCase();
    const items = [...roadmap.phases, ...roadmap.tracks];
    const visible = items.filter((item) => !filter
      || (item.name + " " + item.summary + " " + item.id).toLowerCase().includes(filter));
    const grouped = new Map();
    for (const item of visible) {
      if (!grouped.has(item.group)) grouped.set(item.group, []);
      grouped.get(item.group).push(item);
    }
    elements.coverage.textContent = roadmap.coverage_complete
      ? `40 canonical phases plus ${roadmap.tracks.length} sourced tracks · source ${roadmap.source_revision.slice(0, 12)}`
      : "Coverage mismatch — the roadmap source and displayed inventory differ.";
    elements.groups.replaceChildren();
    for (const [name, groupItems] of grouped) {
      const group = element(documentRef, "details", "roadmap-group");
      group.dataset.roadmapGroup = name;
      group.open = openGroups.has(name) || (!openGroups.size && grouped.size === 1);
      group.appendChild(element(documentRef, "summary", "", `${name} · ${groupItems.length}`));
      const body = element(documentRef, "div", "roadmap-items");
      for (const item of groupItems) {
        const button = element(documentRef, "button", "roadmap-item"
          + (item.id === value.selectedId ? " selected" : ""));
        button.type = "button";
        button.dataset.roadmapId = item.id;
        button.append(element(documentRef, "strong", "", item.kind === "phase"
          ? `Phase ${item.number} · ${item.name}` : item.name),
          element(documentRef, "span", "", item.summary),
          element(documentRef, "span", "roadmap-item-status",
            `${item.maturity} · ${item.source_status}`));
        body.appendChild(button);
      }
      group.appendChild(body);
      elements.groups.appendChild(group);
    }
    let selected = items.find((item) => item.id === value.selectedId)
      || visible[0] || items[0] || null;
    if (selected) {
      const partial = selected.maturity === "partial"
        ? "Foundation implemented; substantial expansions remain planned." : selected.maturity;
      elements.detail.replaceChildren(
        element(documentRef, "p", "eyebrow", selected.kind === "phase" ? "ROADMAP CAPABILITY" : "RECORDED TRACK"),
        element(documentRef, "h3", "", selected.name),
        element(documentRef, "p", "detail-summary", selected.summary),
        detailList(documentRef, [
          ["What exists / remains", partial],
          ["Milestone", selected.kind === "phase" ? `Phase ${selected.number}` : "Cross-cutting track"],
          ["Documented prerequisites", selected.prerequisites.length
            ? selected.prerequisites.join(", ") : "Not mapped yet"],
          ["Associated component", selected.mapped_component || "Not mapped yet"],
          ["Planning status", selected.source_status],
          ["Runtime observation", "Unknown — planned inventory is not a running-service claim"],
          ["Source", selected.source],
          ["Source revision", selected.source_revision],
          ["Source digest", selected.source_sha256],
          ["Source bytes", String(selected.source_bytes)]
        ])
      );
      if (selected.source_excerpt) {
        const sourceDetails = element(documentRef, "details", "roadmap-source-details");
        sourceDetails.append(element(documentRef, "summary", "", "Read retained source excerpts"),
          element(documentRef, "pre", "detail-summary", selected.source_excerpt));
        elements.detail.append(sourceDetails);
      }
    }
    return {mode, selected_id: selected ? selected.id : ""};
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

  function windowsClipboardMessage(update) {
    const id = safeIdentifier(update && update.snapshot_id, 90);
    const receipt = update && update.windows_clipboard;
    const bound = receipt && receipt.snapshot_id === id;
    const status = bound ? receipt.status : "unknown";
    if (status === "copied" && receipt.content_sha256 === update.content_sha256
        && receipt.code === "verified_windows_readback" && Number.isFinite(Date.parse(receipt.copied_at))) {
      return `Copied to Windows clipboard · ${safeText(receipt.copied_at, 80)} · ${id}. Press Ctrl+V on your PC.`;
    }
    if (status === "pending") return `Update saved · ${id} · Windows clipboard delivery pending; not confirmed yet.`;
    if (status === "superseded") return `Update saved · ${id} · A newer/current update takes priority; this one was not copied again.`;
    if (status === "not_requested") return `Saved update · ${id} · No Windows clipboard write was requested for this historical snapshot.`;
    if (status === "failed" || status === "unavailable") return `Update saved · ${id} · Windows clipboard unavailable or failed. The saved update is still retrievable.`;
    return `Update saved · ${id} · Windows clipboard delivery unconfirmed. Copy/download remains available; no automatic replay.`;
  }

  async function postJson(fetchImpl, path, body, options) {
    const value = options || {};
    const response = await fetchImpl(path, {method: "POST", credentials: "same-origin",
      headers: {Accept: "application/json", "Content-Type": "application/json",
        ...(value.csrf ? {"X-Fawkes-CSRF-Token": value.csrf} : {})},
      body: JSON.stringify(body || {})});
    const payload = await response.json();
    if (!response.ok) {
      const error = new Error(safeText(payload && payload.error && payload.error.message, 500)
        || "console update request failed");
      error.status = response.status;
      throw error;
    }
    return payload;
  }

  function managedFeedObservation(projection, projectionState, nowMs) {
    if (projectionState === "sample") return {state: "sample", label: "SAMPLE Worker"};
    if (projectionState === "disconnected") return {state: "disconnected", label: "⊘ Disconnected"};
    if (projectionState !== "live") return {state: "stale", label: "◷ Stale"};
    const selected = selectCampaign(projection && projection.campaigns, projection && projection.current_campaign_id);
    const managed = (selected && selected.managed || []).slice();
    if (!managed.length) return {state: "unavailable", label: "◌ Worker not attached"};
    managed.sort((left, right) => Date.parse(right.updated_at || 0) - Date.parse(left.updated_at || 0));
    const latest = managed[0];
    if (latest.state === "disconnected") return {state: "disconnected", label: "⊘ Disconnected", updated_at: latest.updated_at};
    if (["completed", "failed"].includes(latest.state)) {
      return {state: "unavailable", label: "◌ Worker not attached", updated_at: latest.updated_at};
    }
    const age = Number(nowMs) - Date.parse(latest.verified_at || '');
    if (!Number.isFinite(age) || age < 0 || age > 30_000) {
      return {state: "stale", label: "◷ Stale", updated_at: latest.updated_at};
    }
    return {state: "live", label: "◉ Live", updated_at: latest.updated_at};
  }

  function attachContentScrolling(documentRef, environment) {
    const host=environment||root;
    let gesture=null, suppressUntil=0, previousSelect=null;
    const now=()=>Date.now();
    function within(target) {
      return target&&target.closest&&target.closest('#dev-console, #native-permission');
    }
    function scrollers(target) {
      const items=[];
      for(let node=target;node&&node!==documentRef.body;node=node.parentElement) {
        if(node.nodeType===1&&/(auto|scroll)/.test(host.getComputedStyle(node).overflowY)
          &&node.scrollHeight>node.clientHeight+1)items.push(node);
      }
      return items;
    }
    function restore() {
      if(previousSelect){previousSelect.node.style.userSelect=previousSelect.value;previousSelect=null;}
    }
    function down(event) {
      if(event.isPrimary===false)return;
      restore();gesture=null;suppressUntil=0;
      if(event.button!==0||!within(event.target))return;
      // Combined owns its bounded canvas pan, including the existing Pi mouse mapping.
      if(event.target.closest('.combined-map'))return;
      const selection=host.getSelection&&host.getSelection();
      const editable=event.target.closest('input, textarea, select, [contenteditable="true"]');
      gesture={id:event.pointerId,x:event.clientX,y:event.clientY,lastY:event.clientY,
        start:now(),moved:false,dragging:false,scrollers:scrollers(event.target),
        mouseFallback:event.pointerType==='mouse'&&host.__fawkesMatrixConfig
          &&host.__fawkesMatrixConfig.emulatedPointerScroll===true&&!editable
          &&(!selection||selection.isCollapsed),target:event.target};
    }
    function move(event) {
      if(!gesture||event.pointerId!==gesture.id)return;
      const dx=event.clientX-gesture.x,dy=event.clientY-gesture.y;
      if(Math.hypot(dx,dy)>=12)gesture.moved=true;
      // Native touch is never prevented or translated. The existing Pi compositor
      // maps its Goodix touchscreen to a mouse; only the companion opts it in.
      if(!gesture.mouseFallback)return;
      if(!gesture.dragging) {
        // Hold before dragging retains ordinary text selection; controls/inputs
        // keep taps. No mouse fallback is enabled in the PC console by default.
        if(now()-gesture.start>450){
          gesture.mouseFallback=false;return;
        }
        if(!gesture.moved||!gesture.scrollers.length)return;
        // Sub-threshold jitter has not established a direction yet.
        if(Math.abs(dx)>Math.abs(dy)){gesture.mouseFallback=false;return;}
        gesture.dragging=true;
        const node=gesture.scrollers[0];previousSelect={node,value:node.style.userSelect};node.style.userSelect='none';
        const selection=host.getSelection&&host.getSelection();
        if(selection&&selection.removeAllRanges)selection.removeAllRanges();
      }
      let remaining=gesture.lastY-event.clientY;gesture.lastY=event.clientY;
      for(const node of gesture.scrollers) {
        const before=node.scrollTop;
        node.scrollTop=Math.max(0,Math.min(node.scrollHeight-node.clientHeight,before+remaining));
        remaining-=node.scrollTop-before;
        if(Math.abs(remaining)<1)break;
      }
      if(event.cancelable)event.preventDefault();
      event.stopPropagation();
    }
    function end(event) {
      if(!gesture||event.pointerId!==gesture.id)return;
      const moved=gesture.moved||Math.hypot(event.clientX-gesture.x,event.clientY-gesture.y)>=12;
      if(moved||event.type==='pointercancel')suppressUntil=now()+800;
      if(gesture.dragging){if(event.cancelable)event.preventDefault();event.stopPropagation();}
      restore();gesture=null;
    }
    function click(event) {
      // A trailing drag click is blocked even when it lands on Idle or a newly
      // rendered decision. A new real pointerdown or keyboard click is distinct.
      if(event.detail!==0&&now()<suppressUntil){event.preventDefault();event.stopImmediatePropagation();}
    }
    const listeners={pointerdown:down,pointermove:move,pointerup:end,pointercancel:end,click};
    for(const [kind,fn] of Object.entries(listeners))documentRef.addEventListener(kind,fn,{capture:true,passive:false});
    return ()=>{restore();for(const [kind,fn] of Object.entries(listeners))documentRef.removeEventListener(kind,fn,true);};
  }

  function boot(options) {
    const value = options || {};
    const documentRef = value.document || root.document;
    if (!documentRef) return null;
    const shell = documentRef.getElementById("dev-console");
    if (!shell) return null;
    const stopContentScrolling=attachContentScrolling(documentRef);
    const fetchImpl = value.fetch || (typeof root.fetch === "function" ? root.fetch.bind(root) : null);
    const pages = Array.from(documentRef.querySelectorAll(".console-page"));
    const indicators = Array.from(documentRef.querySelectorAll("[data-page-target]"));
    const title = documentRef.getElementById("page-title");
    const connection = documentRef.getElementById("connection-state");
    const lastSync = documentRef.getElementById("last-sync");
    const bridgeState = documentRef.getElementById("bridge-state");
    const previewContext = documentRef.getElementById("preview-context");
    const campaignState = documentRef.getElementById("campaign-state");
    const attentionState = documentRef.getElementById("attention-state");
    const updated = documentRef.getElementById("last-updated");
    const activityFeed = documentRef.getElementById("activity-feed");
    const attentionSlot = documentRef.getElementById("attention-slot");
    const saveUpdate = documentRef.getElementById("save-console-update");
    const updateResult = documentRef.getElementById("update-result");
    const preparedUpdates = documentRef.getElementById("prepared-updates");
    const campaignElements = {
      selector: documentRef.getElementById("campaign-selector"),
      history: documentRef.getElementById("campaign-history-state"),
      empty: documentRef.getElementById("campaign-empty"),
      dashboard: documentRef.getElementById("campaign-dashboard"),
      widgets: documentRef.getElementById("campaign-widgets"),
      graph: documentRef.getElementById("campaign-graph"),
      detail: documentRef.getElementById("campaign-detail")
    };
    const repositoryElements = {
      widgets: documentRef.getElementById("repository-widgets"),
      browser: documentRef.getElementById("repository-browser"),
      tree: documentRef.getElementById("repository-tree"),
      detailView: documentRef.getElementById("repository-detail-view"),
      back: documentRef.getElementById("repository-back"),
      comparison: documentRef.getElementById("repository-comparison"),
      heading: documentRef.getElementById("repository-file-heading"),
      summary: documentRef.getElementById("repository-file-summary"),
      metadata: documentRef.getElementById("repository-metadata"),
      diff: documentRef.getElementById("repository-diff"),
      empty: documentRef.getElementById("repository-empty")
    };
    const architectureMap = documentRef.getElementById("architecture-map");
    const architectureDetail = documentRef.getElementById("architecture-detail");
    const architectureElements = {
      map: architectureMap, detail: architectureDetail,
      combined: documentRef.getElementById("combined-view"),
      combinedMap: documentRef.getElementById("combined-map"),
      combinedCoverage: documentRef.getElementById("combined-coverage"),
      combinedSelect: documentRef.getElementById("combined-select"),
      combinedState: combinedState(),
      overview: documentRef.getElementById("architecture-overview"),
      inventory: documentRef.getElementById("roadmap-inventory"),
      groups: documentRef.getElementById("roadmap-groups"),
      coverage: documentRef.getElementById("roadmap-coverage"),
      filter: documentRef.getElementById("roadmap-filter"),
      modes: Array.from(documentRef.querySelectorAll("[data-architecture-mode]"))
    };
    const buildMeta = documentRef.querySelector('meta[name="fawkes-build-id"]');
    const contextMeta = documentRef.querySelector('meta[name="fawkes-console-context"]');
    const expectedBuildId = buildMeta ? buildMeta.content : "";
    const candidateContext = contextMeta ? contextMeta.content : "";
    const urlIdle = value.idleSeconds !== undefined ? value.idleSeconds
      : (root.location ? new URL(root.location.href).searchParams.get("idle") : null);
    const idleSeconds = parseIdleSeconds(urlIdle, shell.dataset.idleSeconds || 60);
    let selectedCard = null;
    let pointerStart = null;
    let lastGood = null;
    let lastSuccessMs = null;
    let displayedProjection = null;
    let stopped = false;
    let pollTimer = null;
    let staleTimer = null;
    let expiryTimer = null;
    let refreshSequence = 0;
    let latestAppliedSequence = 0;
    let selectedCampaignId = "";
    let selectedCampaignStageId = "";
    let selectedRepositoryPath = "";
    let repositoryDetailOpen = false;
    let selectedArchitectureId = "development";
    let architectureMode = "current";
    let selectedRoadmapId = "";
    let roadmapFilter = "";
    let pendingUpdateKey = "";
    let preparedUpdatePending = false;
    let pendingUpdateCampaign = null;
    let explicitCampaignSelection = false;
    let localStore;
    try {
      localStore = value.storage || root.localStorage;
      const retained = JSON.parse(localStore.getItem("fawkes-console-update-retry-v1") || "null");
      if (retained && typeof retained.key === "string") {
        pendingUpdateKey = retained.key; pendingUpdateCampaign = retained.campaign_id || null;
      }
    } catch (_unavailable) { /* Saving remains available without local browser storage. */ }
    const clock = typeof value.now === "function" ? value.now : Date.now;
    const projectionScheduler = value.projectionScheduler || {
      setTimeout: root.setTimeout.bind(root), clearTimeout: root.clearTimeout.bind(root)
    };

    const refreshTargets = [activityFeed];
    const discoveredScrollTargets = Array.from(documentRef.querySelectorAll(".page-scroll"));
    const scrollTargets = discoveredScrollTargets.length ? discoveredScrollTargets : refreshTargets;

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
        scrollTops: scrollTargets.map((target) => Number(target.scrollTop) || 0),
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
      scrollTargets.forEach((target, index) => { target.scrollTop = retained.scrollTops[index] || 0; });
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
      // A held gesture belongs to its uninterrupted page visit, not merely a
      // page number that could be left and revisited before pointer release.
      pointerStart = null;
      shell.dataset.page = String(page);
      // Compact menus reflow the header while open, rather than covering a
      // pending request. A page transition closes them, including arrow/swipe.
      for (const id of ["page-menu", "connection-details"]) {
        const menu = documentRef.getElementById(id);
        if (menu) menu.open = false;
      }
      pages.forEach((item, index) => { item.hidden = index !== page; });
      shell.dataset.workerScreen = String(page === 4);
      // Reuse the same five-page menu and its listeners on Worker. Moving the
      // owner preserves page identity without a second set of navigation IDs.
      const pageMenu = documentRef.getElementById("page-menu");
      const menuSlot = documentRef.getElementById(page === 4 ? "worker-menu-slot" : "console-menu-slot");
      if (pageMenu && menuSlot && pageMenu.parentNode !== menuSlot) menuSlot.appendChild(pageMenu);
      // Move the ONE existing companion-bound Idle button; do not clone its
      // handler, create a second Matrix owner, or synthesize an Idle click.
      const idle = documentRef.getElementById("console-idle");
      const idleSlot = documentRef.getElementById(page === 4 ? "worker-idle-slot" : "console-idle-slot");
      if (idle && idleSlot && idle.parentNode !== idleSlot) idleSlot.appendChild(idle);
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

    function setState(state, observedAt, projection) {
      const feed = managedFeedObservation(projection, state, clock());
      connection.className = "state " + feed.state;
      connection.textContent = feed.label;
      lastSync.textContent = observedAt ? "Last sync " + new Date(observedAt).toLocaleTimeString()
        : "No verified sync";
      bridgeState.textContent = observedAt && state === "live"
        ? "PC SERVICE REACHABLE" : "PC SERVICE NOT CURRENT";
      previewContext.textContent = previewContextLabel(projection && projection.build, candidateContext);
      const observedCampaign = campaignObservation((projection && projection.campaigns || [])
        .filter(item => item.campaign_id === projection.current_campaign_id), state, clock());
      campaignState.textContent = observedCampaign.label;
      campaignState.dataset.campaignObservation = observedCampaign.kind;
      const observedAttention = attentionObservation(projection && projection.attention, state);
      attentionState.textContent = observedAttention.label;
      attentionState.dataset.attentionObservation = observedAttention.kind;
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
      displayedProjection = projection;
      setState(state, observedAt, projection);
      documentRef.getElementById("summary-intro").textContent = state === "live"
        ? "At-a-glance status from available managed-job records. Detailed Worker playback remains in canonical evidence, not this screen."
        : state === "sample"
          ? "Sample fixture data — never current canonical state."
          : "Projection is " + state + "; it must not be treated as current authority.";
      const visibleAttention = visibleAttentionAt(projection, state,
        Number.isFinite(nowMs) ? nowMs : clock());
      renderAttention(documentRef, attentionSlot, visibleAttention);
      renderJobs(documentRef, activityFeed, projection.jobs || [], state);
      if (!explicitCampaignSelection || !(projection.campaigns || []).some(c => c.campaign_id === selectedCampaignId)) {
        selectedCampaignId = projection.current_campaign_id || "";
        explicitCampaignSelection = false;
      }
      const selectionLabel = documentRef.getElementById("summary-selection");
      if (selectionLabel) selectionLabel.textContent = "Current objective · " + (projection.current_campaign_id || "No campaign recorded");
      const campaignSelection = renderCampaignDashboard(documentRef, campaignElements,
        projection.campaigns || [], selectedCampaignId, selectedCampaignStageId, state, clock());
      selectedCampaignId = campaignSelection.campaign_id;
      selectedCampaignStageId = campaignSelection.stage_id;
      updateStageTimers(campaignElements.graph, selectCampaign(projection.campaigns, selectedCampaignId), state, clock());
      renderRoleClocks(documentRef, documentRef.getElementById("campaign-role-clocks"),
        selectCampaign(projection.campaigns, selectedCampaignId), state, clock());
      const repositorySelection = renderRepositoryDashboard(documentRef, repositoryElements,
        projection.repository, state, selectedRepositoryPath, repositoryDetailOpen);
      selectedRepositoryPath = repositorySelection.path;
      repositoryDetailOpen = repositorySelection.detail_open;
      architectureElements.components = projection.components || [];
      architectureElements.projection = projection;
      architectureElements.projectionState = state;
      if (architectureMode === "current") selectedArchitectureId = renderArchitectureDashboard(documentRef, architectureMap,
        architectureDetail, projection.components || [], state, selectedArchitectureId);
      const roadmapSelection = renderRoadmapInventory(documentRef, architectureElements,
        projection.roadmap, {mode: architectureMode, selectedId: selectedRoadmapId,
          filter: roadmapFilter});
      architectureMode = roadmapSelection.mode;
      selectedRoadmapId = roadmapSelection.selected_id;
      restoreRefreshState(retained);
    }

    function renderPreparedUpdates(payload) {
      preparedUpdates.replaceChildren();
      const updates = payload && Array.isArray(payload.updates) ? payload.updates : [];
      preparedUpdatePending = updates.some(update => update.windows_clipboard && update.windows_clipboard.status === "pending");
      if (!updates.length) {
        preparedUpdates.appendChild(element(documentRef, "p", "meta",
          "No durable update has been prepared yet."));
        return;
      }
      for (const update of updates) {
        const snapshotId = safeIdentifier(update.snapshot_id, 90);
        if (!/^console-update-[a-f0-9]{64}$/.test(snapshotId)) continue;
        const card = element(documentRef, "article", "prepared-update");
        card.appendChild(element(documentRef, "p", "", `${update.created_at || "Unknown time"} · ${snapshotId}`));
        card.appendChild(element(documentRef, "p", "meta", windowsClipboardMessage(update)));
        const actions = element(documentRef, "div", "prepared-update-actions");
        const copy = element(documentRef, "button", "", "Copy completed + working on");
        copy.type = "button"; copy.dataset.copyUpdateId = snapshotId;
        const download = element(documentRef, "a", "", "Download .txt");
        download.href = `${ENDPOINTS.updates}/${snapshotId}.txt`;
        download.download = `${snapshotId}.txt`;
        actions.append(copy, download);
        card.appendChild(actions);
        preparedUpdates.appendChild(card);
      }
    }

    async function refreshPreparedUpdates() {
      if (!fetchImpl || value.samplePayload) return;
      try {
        renderPreparedUpdates(await fetchJson(fetchImpl, ENDPOINTS.updates, 10000));
      } catch (_error) {
        if (!preparedUpdates.children.length) preparedUpdates.appendChild(element(documentRef,
          "p", "warning", "Prepared updates are unavailable; any previous durable snapshot was not overwritten."));
      }
    }

    async function savePreparedUpdate() {
      if (!fetchImpl) return;
      saveUpdate.disabled = true;
      updateResult.textContent = "Saving the current update and sending it to Windows clipboard…";
      try {
        const csrf = await postJson(fetchImpl, ENDPOINTS.csrf, {});
        if (!pendingUpdateKey) {
          const suffix = root.crypto && typeof root.crypto.randomUUID === "function"
            ? root.crypto.randomUUID() : `${clock()}-${Math.random().toString(16).slice(2)}`;
          pendingUpdateKey = "console-browser-" + suffix;
          pendingUpdateCampaign = displayedProjection && displayedProjection.current_campaign_id || null;
          try { localStore.setItem("fawkes-console-update-retry-v1", JSON.stringify({
            key: pendingUpdateKey, campaign_id: pendingUpdateCampaign})); } catch (_unavailable) {}
        }
        const update = await postJson(fetchImpl, ENDPOINTS.updates,
          {idempotency_key: pendingUpdateKey, ...(pendingUpdateCampaign ? {campaign_id: pendingUpdateCampaign} : {})}, {csrf: csrf.csrf_token});
        updateResult.textContent = windowsClipboardMessage(update);
        pendingUpdateKey = "";
        pendingUpdateCampaign = null;
        try {localStore.removeItem("fawkes-console-update-retry-v1");} catch (_unavailable) {}
        await refreshPreparedUpdates();
      } catch (error) {
        updateResult.textContent = "Windows delivery not confirmed · " + safeText(error && error.message, 300)
          + " · A snapshot may already be saved. Retry checks the same request; previous updates remain available.";
      } finally {
        saveUpdate.disabled = false;
      }
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
        setState(lastGood ? "stale" : "disconnected", lastSuccessMs, lastGood);
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
        if (root.dispatchEvent && typeof root.CustomEvent === 'function') {
          root.dispatchEvent(new root.CustomEvent(projection.ok && state === 'live'
            ? 'fawkes:console-observation' : 'fawkes:console-disconnected', {detail:raw}));
        }
      } catch (error) {
        if (root.dispatchEvent && typeof root.CustomEvent === 'function') root.dispatchEvent(new root.CustomEvent('fawkes:console-disconnected'));
        if (sequence !== refreshSequence || sequence < latestAppliedSequence || stopped) return;
        latestAppliedSequence = sequence;
        const disconnected = !error || error.kind === "authentication" || !error.kind || error.name === "AbortError";
        const state = classifyProjectionState({
          currentSuccess: false, previousSuccess: Boolean(lastGood), disconnected
        });
        if (lastGood) render(lastGood, state, lastSuccessMs, clock());
        else {
          setState(state, null, null);
          documentRef.getElementById("summary-intro").textContent = "Authenticated read-only projections are unavailable.";
        }
      }
    }

    documentRef.getElementById("previous-page").addEventListener("click", () => navigation.previous());
    documentRef.getElementById("next-page").addEventListener("click", () => navigation.next());
    indicators.forEach((item) => item.addEventListener("click", () => {
      // Choosing the already-current page also dismisses the native menu;
      // navigation correctly emits no page-change event for that selection.
      for (const id of ["page-menu", "connection-details"]) {
        const menu = documentRef.getElementById(id);
        if (menu) menu.open = false;
      }
      navigation.go(Number(item.dataset.pageTarget), "indicator");
    }));
    campaignElements.selector.addEventListener("change", () => {
      explicitCampaignSelection = true;
      selectedCampaignId = safeIdentifier(campaignElements.selector.value, 180);
      selectedCampaignStageId = "";
      if (displayedProjection) {
        const selected = renderCampaignDashboard(documentRef, campaignElements,
          displayedProjection.campaigns || [], selectedCampaignId, selectedCampaignStageId);
        selectedCampaignId = selected.campaign_id;
        selectedCampaignStageId = selected.stage_id;
      }
      navigation.activity();
    });
    campaignElements.graph.addEventListener("click", (event) => {
      const selected = event.target.closest && event.target.closest("[data-campaign-stage]");
      if (!selected || !displayedProjection) return;
      selectedCampaignStageId = safeIdentifier(selected.dataset.campaignStage, 40);
      const result = renderCampaignDashboard(documentRef, campaignElements,
        displayedProjection.campaigns || [], selectedCampaignId, selectedCampaignStageId);
      selectedCampaignId = result.campaign_id;
      selectedCampaignStageId = result.stage_id;
      navigation.activity();
    });
    campaignElements.graph.addEventListener("keydown", (event) => {
      if (!['Enter', ' '].includes(event.key)) return;
      const selected = event.target.closest && event.target.closest("[data-campaign-stage]");
      if (!selected) return;
      event.preventDefault();
      campaignElements.graph.emit ? campaignElements.graph.emit("click", {target: selected})
        : selected.dispatchEvent(new MouseEvent("click", {bubbles: true}));
    });
    repositoryElements.tree.addEventListener("click", (event) => {
      const selected = event.target.closest && event.target.closest("[data-repository-path]");
      if (!selected || !displayedProjection) return;
      selectedRepositoryPath = safeText(selected.dataset.repositoryPath, 500);
      repositoryDetailOpen = true;
      const result = renderRepositoryDashboard(documentRef, repositoryElements,
        displayedProjection.repository, shell.dataset.projectionState || "unavailable",
        selectedRepositoryPath, repositoryDetailOpen);
      selectedRepositoryPath = result.path;
      repositoryDetailOpen = result.detail_open;
      navigation.activity();
    });
    repositoryElements.back.addEventListener("click", () => {
      if (!displayedProjection) return;
      repositoryDetailOpen = false;
      const result = renderRepositoryDashboard(documentRef, repositoryElements,
        displayedProjection.repository, shell.dataset.projectionState || "unavailable",
        selectedRepositoryPath, repositoryDetailOpen);
      selectedRepositoryPath = result.path;
      repositoryDetailOpen = result.detail_open;
      navigation.activity();
    });
    architectureElements.modes.forEach((button) => button.addEventListener("click", () => {
      architectureMode = safeIdentifier(button.dataset.architectureMode, 20) || "current";
      if (displayedProjection) {
        const result = renderRoadmapInventory(documentRef, architectureElements,
          displayedProjection.roadmap, {mode: architectureMode, selectedId: selectedRoadmapId,
            filter: roadmapFilter});
        architectureMode = result.mode; selectedRoadmapId = result.selected_id;
        if (architectureMode === "current") renderArchitectureDashboard(documentRef, architectureMap,
          architectureDetail, displayedProjection.components || [], shell.dataset.projectionState, selectedArchitectureId);
      }
      navigation.activity();
    }));
    architectureElements.filter.addEventListener("input", () => {
      roadmapFilter = safeText(architectureElements.filter.value, 80);
      if (displayedProjection) {
        const result = renderRoadmapInventory(documentRef, architectureElements,
          displayedProjection.roadmap, {mode: architectureMode, selectedId: selectedRoadmapId,
            filter: roadmapFilter});
        selectedRoadmapId = result.selected_id;
      }
      navigation.activity();
    });
    architectureElements.groups.addEventListener("click", (event) => {
      const selected = event.target.closest && event.target.closest("[data-roadmap-id]");
      if (!selected || !displayedProjection) return;
      selectedRoadmapId = safeIdentifier(selected.dataset.roadmapId, 100);
      const result = renderRoadmapInventory(documentRef, architectureElements,
        displayedProjection.roadmap, {mode: architectureMode, selectedId: selectedRoadmapId,
          filter: roadmapFilter});
      selectedRoadmapId = result.selected_id;
      navigation.activity();
    });
    architectureMap.addEventListener("click", (event) => {
      const selected = event.target.closest && event.target.closest("[data-architecture-node]");
      if (!selected) return;
      selectedArchitectureId = safeIdentifier(selected.dataset.architectureNode, 40);
      selectedArchitectureId = renderArchitectureDashboard(documentRef, architectureMap,
        architectureDetail, displayedProjection ? displayedProjection.components : [],
        shell.dataset.projectionState || "unavailable", selectedArchitectureId);
      navigation.activity();
    });
    architectureMap.addEventListener("keydown", (event) => {
      if (!['Enter', ' '].includes(event.key)) return;
      const selected = event.target.closest && event.target.closest("[data-architecture-node]");
      if (!selected) return;
      event.preventDefault();
      selectedArchitectureId = safeIdentifier(selected.dataset.architectureNode, 40);
      selectedArchitectureId = renderArchitectureDashboard(documentRef, architectureMap,
        architectureDetail, displayedProjection ? displayedProjection.components : [],
        shell.dataset.projectionState || "unavailable", selectedArchitectureId);
      navigation.activity();
    });
    documentRef.getElementById("architecture-reset").addEventListener("click", () => {
      if (architectureMode === "combined") {
        const model = combinedModel(displayedProjection && displayedProjection.roadmap);
        combinedControl(architectureElements.combinedState, "fit", combinedLayout(model, architectureElements.combinedState.expanded));
        transformCombined(architectureElements.combinedMap, architectureElements.combinedState);
        navigation.activity();
        return;
      }
      selectedArchitectureId = "development";
      selectedRoadmapId = "";
      roadmapFilter = "";
      architectureElements.filter.value = "";
      renderArchitectureDashboard(documentRef, architectureMap, architectureDetail,
        displayedProjection ? displayedProjection.components : [], shell.dataset.projectionState || "unavailable",
        selectedArchitectureId);
      if (displayedProjection) {
        const result = renderRoadmapInventory(documentRef, architectureElements,
          displayedProjection.roadmap, {mode: architectureMode, selectedId: "", filter: ""});
        selectedRoadmapId = result.selected_id;
      }
      navigation.activity();
    });
    function drawCombined() {
      if (displayedProjection) renderCombined(documentRef, architectureElements, displayedProjection.roadmap,
        architectureElements.combinedState, displayedProjection.components || [], shell.dataset.projectionState);
    }
    bindCombinedGestures(architectureElements.combinedMap, architectureElements.combinedState, () => navigation.activity());
    if (architectureElements.combinedMap) {
      const activate = (event) => {
        if (architectureElements.combinedState.suppressClick) {event.preventDefault(); return;}
        const node = event.target.closest && event.target.closest("[data-combined-id]");
        if (!node || !displayedProjection) return;
        const state = architectureElements.combinedState;
        state.selected = node.dataset.combinedId;
        const selected = combinedModel(displayedProjection.roadmap).groups.find((group) => group.id === state.selected);
        if (selected) state.expanded.has(selected.id) ? state.expanded.delete(selected.id) : state.expanded.add(selected.id);
        // Keep the chosen group and its first capabilities in view, rather
        // than expanding silently below the visible overview.
        if (selected && state.expanded.has(selected.id) && selected.children.length) {
          const position = combinedLayout(combinedModel(displayedProjection.roadmap), state.expanded).positions.get(selected.children[0]);
          state.zoom = 1; state.x = 20 - position.x; state.y = 28 - position.y;
        }
        drawCombined(); navigation.activity();
      };
      architectureElements.combinedMap.addEventListener("click", activate);
      architectureElements.combinedMap.addEventListener("keydown", (event) => {
        if (["Enter", " "].includes(event.key)) {
          event.preventDefault(); architectureElements.combinedState.suppressClick = false; activate(event);
        } else {
          const action = {ArrowLeft: "left", ArrowRight: "right", ArrowUp: "up", ArrowDown: "down", "+": "in", "-": "out", "0": "reset"}[event.key];
          if (action) {event.preventDefault(); combinedControl(architectureElements.combinedState, action);
            transformCombined(architectureElements.combinedMap, architectureElements.combinedState); navigation.activity();}
        }
      });
      documentRef.getElementById("combined-controls").addEventListener("click", (event) => {
        const button = event.target.closest && event.target.closest("[data-combined-control]");
        if (!button) return;
        const state = architectureElements.combinedState;
        const model = combinedModel(displayedProjection && displayedProjection.roadmap);
        const action = button.dataset.combinedControl;
        if (action === "overview") state.expanded.clear();
        combinedControl(state, action === "overview" ? "fit" : action, combinedLayout(model, state.expanded));
        if (action === "overview") drawCombined();
        transformCombined(architectureElements.combinedMap, architectureElements.combinedState); navigation.activity();
      });
      architectureElements.combinedSelect.addEventListener("change", () => {
        if (!displayedProjection) return;
        focusCombined(combinedModel(displayedProjection.roadmap), architectureElements.combinedState,
          architectureElements.combinedSelect.value);
        drawCombined(); navigation.activity();
      });
    }
    if (saveUpdate) saveUpdate.addEventListener("click", () => { navigation.activity(); savePreparedUpdate(); });
    const workerEntry = documentRef.getElementById("reply-to-worker");
    if (workerEntry) workerEntry.addEventListener("click", () => {
      const target = indicators.find(item => item.dataset.pageTarget === "4");
      if (target) target.click();
    });
    preparedUpdates.addEventListener("click", async (event) => {
      const button = event.target.closest && event.target.closest("[data-copy-update-id]");
      if (!button || !fetchImpl) return;
      navigation.activity();
      const snapshotId = safeIdentifier(button.dataset.copyUpdateId, 90);
      try {
        const update = await fetchJson(fetchImpl, `${ENDPOINTS.updates}/${snapshotId}`, 10000);
        const content = typeof update.content === "string" ? update.content : "";
        if (!content) throw new Error("The saved update content is unavailable.");
        const clipboard = value.clipboard || (root.navigator && root.navigator.clipboard);
        if (!clipboard || typeof clipboard.writeText !== "function") throw new Error("Clipboard access is unavailable.");
        await clipboard.writeText(content);
        updateResult.textContent = `Copied to this device's clipboard · ${snapshotId}. Pi copying does not fill Windows' clipboard.`;
      } catch (error) {
        updateResult.textContent = "Copy unavailable; use Download .txt or the selectable text below.";
        try {
          const update = await fetchJson(fetchImpl, `${ENDPOINTS.updates}/${snapshotId}`, 10000);
          const fallback = element(documentRef, "pre", "code-scroll selectable-update",
            safeMultilineText(update.content, 96000));
          button.closest(".prepared-update").appendChild(fallback);
        } catch (_ignored) { /* Download remains the exact server-owned fallback. */ }
      }
    });
    shell.addEventListener("click", (event) => {
      navigation.activity();
      const pageLink = event.target.closest && event.target.closest("[data-page-link]");
      if (pageLink) {
        if (pageLink.dataset.campaignId && displayedProjection) {
          selectedCampaignId = pageLink.dataset.campaignId; explicitCampaignSelection = true;
          selectedCampaignStageId = "";
          render(displayedProjection, shell.dataset.projectionState, lastSuccessMs, clock());
        }
        navigation.go(Number(pageLink.dataset.pageLink), "detail-link");
      }
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
      if (event.target.closest && event.target.closest(
        ".code-scroll, input, textarea, select, button, [contenteditable]:not([contenteditable='false']), .gesture-surface")) return;
      if (event.key === "ArrowLeft") { event.preventDefault(); navigation.previous(); }
      if (event.key === "ArrowRight") { event.preventDefault(); navigation.next(); }
    });
    const stack = documentRef.getElementById("page-stack");
    stack.addEventListener("pointerdown", (event) => {
      pointerStart = {x: event.clientX, y: event.clientY, page: navigation.page,
        codeScroll: Boolean(event.target.closest
          && event.target.closest(".code-scroll, .gesture-surface, input, textarea, select, [contenteditable]:not([contenteditable='false'])"))};
      navigation.activity();
    });
    stack.addEventListener("pointerup", (event) => {
      if (!pointerStart) return;
      // Worker is a typing/reading surface: Back is the explicit exit.
      // Also discard a gesture carried across an explicit page transition.
      if (navigation.page !== 4 && pointerStart.page === navigation.page) {
        navigation.swipe(pointerStart.x, pointerStart.y, event.clientX, event.clientY,
          {codeScroll: pointerStart.codeScroll});
      }
      pointerStart = null;
    });
    stack.addEventListener("pointercancel", () => { pointerStart = null; });

    refresh();
    if (value.disableUpdateRefresh !== true) refreshPreparedUpdates();
    pollTimer = value.pollIntervalMs === 0 || !root.setInterval
      ? null : root.setInterval(() => {
        refresh();
        // A reload during native delivery observes the eventual receipt; it
        // never executes another write or keeps an expired attempt pending.
        if (preparedUpdatePending) refreshPreparedUpdates();
      }, Number.isFinite(value.pollIntervalMs) ? value.pollIntervalMs : 10000);
    const timingTimer = root.setInterval ? root.setInterval(() => {
      if (displayedProjection) updateStageTimers(campaignElements.graph,
        selectCampaign(displayedProjection.campaigns, selectedCampaignId), shell.dataset.projectionState, clock());
      if (displayedProjection) renderRoleClocks(documentRef, documentRef.getElementById("campaign-role-clocks"),
        selectCampaign(displayedProjection.campaigns, selectedCampaignId), shell.dataset.projectionState, clock());
    }, 1000) : null;
    return {
      navigation,
      refresh,
      refreshPreparedUpdates,
      stop: function () {
        stopped = true;
        navigation.destroy();
        stopContentScrolling();
        if (pollTimer !== null && root.clearInterval) root.clearInterval(pollTimer);
        if (timingTimer !== null && root.clearInterval) root.clearInterval(timingTimer);
        clearProjectionTimers();
      }
    };
  }

  const api = Object.freeze({
    windowsClipboardMessage,
    ENDPOINTS,
    PROJECTION_SCHEMA,
    PAGE_TITLES,
    parseIdleSeconds,
    classifyProjectionState,
    previewContextLabel,
    campaignObservation,
    activityHeading,
    campaignStatusLabel,
    isHorizontalSwipe,
    safeAttentionHref,
    normalizeCampaignProjection,
    normalizeCampaignResponse,
    normalizeAttentionResponse,
    normalizeRuntimeResponse,
    normalizeStatusResponse,
    normalizeRepositoryResponse,
    normalizeJobsResponse,
    normalizeRoadmapResponse,
    normalizePayloads,
    campaignGraphStages,
    campaignGraphModel,
    selectCampaign,
    architectureObservation,
    managedFeedObservation,
    renderRoadmapInventory,
    normalizeConsoleReporting, lifecycleTime, formatDuration, intervalSeconds, updateStageTimers, roleClocks,
    combinedModel, combinedLayout, combinedState, combinedControl, focusCombined, renderCombined, bindCombinedGestures, combinedOperationStatus,
    renderJobs, renderCampaignDashboard,
    ConsoleNavigation,
    attachContentScrolling,
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

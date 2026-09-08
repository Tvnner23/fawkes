(function (root, factory) {
  "use strict";
  const api = factory(root);
  if (typeof module === "object" && module.exports) module.exports = api;
  root.FawkesWorkerConversation = api;
  if (root.document) api.boot(root.document);
})(typeof globalThis === "object" ? globalThis : this, function (root) {
  "use strict";
  const URL = "/api/development/worker";
  const THREAD = /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/;
  const HEX = /^[a-f0-9]{64}$/;
  function message(value) {
    if (!value || typeof value.text !== "string" || typeof value.message_id !== "string"
      || typeof value.turn_id !== "string" || !HEX.test(value.content_sha256)
      || !["worker", "user"].includes(value.role)) throw new Error("Malformed public Worker message");
    return value;
  }
  function projection(value) {
    if (!value || value.schema_version !== "fawkes.worker_conversation.v1" || !THREAD.test(value.thread_id)
      || !Array.isArray(value.messages) || !["active", "idle", "notLoaded", "systemError"].includes(value.state)
      || typeof value.can_reply !== "boolean" || !Number.isFinite(Date.parse(value.verified_at))) {
      throw new Error("Worker identity or state is unavailable");
    }
    value.messages.forEach(message);
    if (value.latest_final) {
      message(value.latest_final);
      if (value.latest_final.phase !== "final_answer" || value.latest_final.role !== "worker") throw new Error("Not a final Worker message");
    }
    return value;
  }
  function copyStatus(update, expected) {
    const binding = update && update.worker_message;
    if (!binding || binding.thread_id !== expected.thread_id || binding.message_id !== expected.message_id
      || binding.content_sha256 !== expected.content_sha256 || update.content_sha256 !== expected.content_sha256) {
      throw new Error("Windows snapshot does not match this final message");
    }
    const receipt = update.windows_clipboard || {};
    if (receipt.status === "copied" && receipt.code === "verified_windows_readback"
      && receipt.snapshot_id === update.snapshot_id && receipt.content_sha256 === update.content_sha256) {
      return "Copied verbatim to Windows · " + update.snapshot_id + " · " + receipt.copied_at + ". Press Ctrl+V on your PC.";
    }
    return "Windows copy " + (receipt.status || "not confirmed") + ". Snapshot " + update.snapshot_id + " is retained; this is not a confirmed clipboard write.";
  }
  function insertKey(text, start, end, key) {
    if (key === "Backspace") {
      const before = Array.from(text.slice(0, start));
      if (start === end && before.length) start -= before[before.length - 1].length;
      key = "";
    }
    const inserted = key === "Space" ? " " : key === "Enter" ? "\n" : key;
    return {text: text.slice(0, start) + inserted + text.slice(end), position: start + inserted.length};
  }
  function boot(doc) {
    const page = doc.getElementById("worker-page");
    if (!page || !root.fetch) return null;
    const byId = id => doc.getElementById(id);
    const input = byId("worker-reply"), send = byId("worker-send-reply"), copy = byId("worker-send-update");
    const state = byId("worker-session-state"), replyResult = byId("worker-reply-result"), copyResult = byId("worker-copy-result");
    let current = null, busy = false, olderCursor = null, pendingReply = null, pendingCopy = null, shift = false;
    let lastSuccess = 0, currentHistory = "", readingOlder = false;
    let refreshing = false, reconciling = false;
    let storageHealthy = true;
    function retain() {
      try {
        const body = JSON.stringify({draft: input.value, pendingReply, pendingCopy});
        const storage = root.localStorage;
        storage.setItem("fawkes-worker-page-v1", body);
        if (storage.getItem("fawkes-worker-page-v1") !== body) throw new Error("Local identity read-back differs");
        storageHealthy = true; return true;
      } catch (_) {
        storageHealthy = false;
        replyResult.textContent = "Local reply identity could not be saved. Nothing new will be sent until storage works; your text remains here.";
        return false;
      }
    }
    try {
      const saved = JSON.parse(root.localStorage.getItem("fawkes-worker-page-v1") || "{}");
      if (typeof saved.draft === "string") input.value = saved.draft;
      if (saved.pendingReply && THREAD.test(saved.pendingReply.reply_id)) pendingReply = saved.pendingReply;
      if (saved.pendingCopy && typeof saved.pendingCopy.idempotency_key === "string") pendingCopy = saved.pendingCopy;
    } catch (_) { storageHealthy = false; replyResult.textContent = "Local reply storage is unavailable. Sending is disabled; your existing server snapshots are retained."; }
    async function request(path, data) {
      const controller = new AbortController(), timer = root.setTimeout(() => controller.abort(), 25000);
      try {
        const options = {credentials: "same-origin", cache: "no-store", signal: controller.signal};
        if (data !== undefined) {
          const csrf = await root.fetch("/api/session/console-csrf", {method: "POST", credentials: "same-origin",
            headers: {"Content-Type": "application/json"}, body: "{}", signal: controller.signal});
          if (!csrf.ok) throw new Error("Sign-in is required");
          options.method = "POST"; options.headers = {"Content-Type": "application/json", "X-Fawkes-CSRF-Token": (await csrf.json()).csrf_token};
          options.body = JSON.stringify(data);
        }
        const response = await root.fetch(path, options), body = await response.json();
        if (!response.ok) throw new Error(body.error && body.error.message || "Worker connection unavailable");
        return body;
      } finally { root.clearTimeout(timer); }
    }
    function controls() {
      const fresh = current && Date.now() - lastSuccess < 15000;
      if (current && lastSuccess > 0) {
        state.dataset.connection = !fresh ? "stale" : current.state;
        state.textContent = !fresh ? "Stale · retained text is last known; connection verification overdue"
          : current.state === "notLoaded" ? "History only · Worker not attached"
          : current.state === "systemError" ? "Worker error"
          : "Connected · " + (current.state === "active" ? "Turn active" : "Waiting for input");
      }
      copy.disabled = busy || !fresh || !current.latest_final || !storageHealthy;
      send.disabled = busy || !fresh || !current.can_reply || !input.value.trim() || !storageHealthy;
    }
    function history(messages, append) {
      const container = byId("worker-conversation-history");
      if (!append) container.replaceChildren();
      if (!messages.length) {
        const empty = doc.createElement("p");
        empty.textContent = "No public messages are available on this conversation page. Saved history is retained; tool and reasoning records are not displayed.";
        container.appendChild(empty);
      }
      for (const item of messages) {
        const article = doc.createElement("article"); article.className = "worker-history-message";
        article.dataset.messageId = item.message_id;
        const label = doc.createElement("p"); label.className = "meta";
        article.dataset.role = item.role;
        label.textContent = (item.role === "worker" ? "WORKER" : "TANNER") + (item.phase === "final_answer" ? " // FINAL" : item.role === "worker" && item.phase === null ? " // PHASE UNKNOWN" : "") + " · " + item.turn_id;
        const body = doc.createElement("pre"); body.className = "worker-message"; body.textContent = item.text;
        article.append(label, body); container.appendChild(article);
      }
    }
    function receipt(value) {
      if (!pendingReply || value.reply_id !== pendingReply.reply_id || value.thread_id !== pendingReply.thread_id
        || value.text !== pendingReply.text) throw new Error("Reply receipt identity differs");
      if (value.status === "received" && value.turn_id && value.message_id) {
        replyResult.textContent = "Received by this Worker · " + value.reply_id + " · " + value.turn_id;
        if (input.value === pendingReply.text) input.value = "";
        pendingReply = null;
      } else if (value.status === "queued") {
        replyResult.textContent = "Queued for this Worker · " + value.reply_id + ". Waiting for its received-message evidence.";
      } else {
        replyResult.textContent = "Reply " + (value.status || "unconfirmed") + " · " + value.reply_id + ". Retrying this same request does not create a new reply.";
      }
      retain();
    }
    async function refresh() {
      if (page.hidden || refreshing) return;
      refreshing = true;
      try {
        const value = projection(await request(URL));
        if (current && value.thread_id !== current.thread_id) throw new Error("Worker session changed; do not send to an unverified replacement");
        current = value; lastSuccess = Date.now();
        byId("worker-session-identity").textContent = "Session " + value.thread_id + " · Verified " + value.verified_at;
        const final = value.latest_final;
        if (final) {
          if (byId("worker-final-message").textContent !== final.text) byId("worker-final-message").textContent = final.text;
          byId("worker-final-identity").textContent = "Final message " + final.message_id + " · Turn " + final.turn_id;
        } else {
          byId("worker-final-message").textContent = "No exact final message was available in the bounded lookup. Browse the retained conversation; no summary has been substituted.";
          byId("worker-final-identity").textContent = "Latest final message unavailable";
        }
        const signature = JSON.stringify(value.messages.map(m => [m.message_id, m.content_sha256]));
        if (!readingOlder && signature !== currentHistory) { history(value.messages, false); currentHistory = signature; olderCursor = value.next_cursor; }
        byId("worker-older").disabled = !olderCursor;
      } catch (error) {
        lastSuccess = 0; state.dataset.connection = "disconnected";
        state.textContent = "Disconnected · retained text is last known";
        replyResult.textContent = error.message + (pendingReply ? " · Reply identity retained; no automatic resend." : "");
      } finally { refreshing = false; controls(); }
      // Receipt latency must not hold the projection or clipboard controls.
      // Only one observation is in flight; POSTs retain their own serialization.
      reconcileReply();
    }
    async function reconcileReply() {
      if (!pendingReply || reconciling || busy) return;
      const expected = pendingReply;
      reconciling = true;
      try {
        const value = await request(URL + "/replies/" + expected.reply_id);
        if (pendingReply === expected) receipt(value);
      } catch (error) {
        if (pendingReply === expected) replyResult.textContent = "Reply receipt unavailable · " + error.message
          + ". Original reply identity retained. Send the same text to safely retry/check that identity.";
      } finally { reconciling = false; controls(); }
    }
    byId("worker-older").addEventListener("click", async () => {
      if (!olderCursor || busy) return; busy = true; controls();
      try { const value = projection(await request(URL + "?cursor=" + encodeURIComponent(olderCursor)));
        if (!current || value.thread_id !== current.thread_id) throw new Error("History belongs to a different Worker");
        history(value.messages, false); readingOlder = true; olderCursor = value.next_cursor; byId("worker-older").disabled = !olderCursor;
      } catch (error) { replyResult.textContent = error.message; } finally { busy = false; controls(); }
    });
    byId("worker-newest").addEventListener("click", () => { readingOlder = false; currentHistory = ""; refresh(); });
    copy.addEventListener("click", async () => {
      if (copy.disabled || !current.latest_final) return;
      const expected = {thread_id: current.thread_id, message_id: current.latest_final.message_id, content_sha256: current.latest_final.content_sha256};
      if (!pendingCopy || pendingCopy.message_id !== expected.message_id || pendingCopy.content_sha256 !== expected.content_sha256) {
        pendingCopy = {...expected, idempotency_key: "worker-final-" + root.crypto.randomUUID()};
      }
      if (!retain()) { copyResult.textContent = "Windows copy not attempted: the request identity could not be saved locally."; controls(); return; }
      busy = true; controls(); copyResult.textContent = "Sending the exact final message to Windows…";
      try {
        const update = await request(URL + "/clipboard", pendingCopy);
        copyResult.textContent = copyStatus(update, expected);
        if (update.windows_clipboard && update.windows_clipboard.status === "copied") { pendingCopy = null; retain(); }
      } catch (error) { copyResult.textContent = "Windows copy not confirmed · " + error.message + " · Saved snapshots remain available; request identity retained."; }
      finally { busy = false; controls(); }
    });
    byId("worker-reply-form").addEventListener("submit", async event => {
      event.preventDefault(); if (send.disabled) return;
      if (input.value.includes("\0") || new TextEncoder().encode(input.value).length > 16000) {
        replyResult.textContent = "Reply must be at most 16000 UTF-8 bytes without NUL. Edit the text; no reply identity or submission was created."; return;
      }
      if (pendingReply && (pendingReply.text !== input.value || pendingReply.thread_id !== current.thread_id)) {
        replyResult.textContent = "The earlier reply is still unresolved. Keep its original text to check/retry the same identity; do not create a duplicate."; return;
      }
      if (!pendingReply) pendingReply = {thread_id: current.thread_id, reply_id: root.crypto.randomUUID(), text: input.value};
      if (!retain()) { controls(); return; }
      busy = true; controls(); replyResult.textContent = "Sending this reply to the exact Worker session…";
      try { receipt(await request(URL + "/replies", pendingReply)); }
      catch (error) { replyResult.textContent = "Reply not confirmed · " + error.message + " · Same request identity retained."; }
      finally { busy = false; controls(); }
    });
    input.addEventListener("input", () => { retain(); controls(); });
    const keyboard = byId("worker-keyboard");
    function keys() {
      keyboard.replaceChildren();
      const rows = ["1234567890", "qwertyuiop", "asdfghjkl", "zxcvbnm.,/", ["Shift", "Space", "Enter", "Backspace"]];
      for (const row of rows) {
        const group = doc.createElement("div"); group.className = "worker-keyboard-row";
        for (let key of row) {
          if (shift && key.length === 1) key = key.toUpperCase();
          const button = doc.createElement("button"); button.type = "button"; button.textContent = key;
          button.dataset.key = key;
          if (key === "Space") button.className = "worker-space";
          button.addEventListener("pointerdown", event => { if (event.isPrimary) event.preventDefault(); });
          button.addEventListener("click", () => {
            if (key === "Shift") { shift = !shift; keys(); return; }
            const next = insertKey(input.value, input.selectionStart, input.selectionEnd, key);
            if (new TextEncoder().encode(next.text).length > 16000) { replyResult.textContent = "Reply reaches its 16000-byte limit."; return; }
            input.value = next.text; input.focus({preventScroll: true}); input.setSelectionRange(next.position, next.position);
            retain(); controls();
          }); group.appendChild(button);
        } keyboard.appendChild(group);
      }
    }
    keys(); byId("worker-keyboard-toggle").addEventListener("click", () => {
      keyboard.hidden = !keyboard.hidden;
      byId("worker-keyboard-toggle").setAttribute("aria-expanded", String(!keyboard.hidden));
    });
    const observer = new MutationObserver(() => { if (!page.hidden) refresh(); });
    observer.observe(page, {attributes: true, attributeFilter: ["hidden"]});
    const timer = root.setInterval(() => { controls(); refresh(); }, 5000);
    refresh();
    return {refresh, stop() { observer.disconnect(); root.clearInterval(timer); }};
  }
  return {projection, message, copyStatus, insertKey, boot};
});

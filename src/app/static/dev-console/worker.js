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
    for (const key of ["completed_turn_ids", "known_turn_ids", "active_turn_ids", "page_item_ids"]) {
      if (value[key] !== undefined && (!Array.isArray(value[key]) || value[key].some(id=>typeof id!=="string" || !id)
          || new Set(value[key]).size !== value[key].length)) throw new Error("Malformed Worker history identities");
    }
    if (value.next_cursor != null && (typeof value.next_cursor !== "string" || !value.next_cursor || value.next_cursor.length>4096)) throw new Error("Malformed Worker history cursor");
    if (value.next_turn_cursor != null && (typeof value.next_turn_cursor !== "string" || !value.next_turn_cursor || value.next_turn_cursor.length>4096)) throw new Error("Malformed Worker turn evidence cursor");
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
  // Both inputs are in the owner's descending order. A refreshed head is
  // prepended; a cursor page is appended. Identity, not prose or timestamps,
  // removes overlap. Content updates replace the SAME item, not a new message.
  function mergeMessages(existing, page, older) {
    const ordered = older ? existing.concat(page) : page.concat(existing);
    const latest = new Map(existing.map(m => [m.message_id,m]));
    page.forEach(m => {message(m); latest.set(m.message_id,m);});
    const seen = new Set();
    return ordered.filter(m => !seen.has(m.message_id) && seen.add(m.message_id)).map(m => latest.get(m.message_id));
  }
  function pageIds(value) { return value.page_item_ids || value.messages.map(m=>m.message_id); }
  // Join by the underlying item frontier, including body-free non-public IDs.
  // Never jump the frontier just because a refreshed head is newer. A gap is
  // walked through the owner's opaque cursors before merging into the history.
  function advanceHead(cache, value, cursorPage=false) {
    const ids=pageIds(value), page=value.messages;
    if (cursorPage) {
      if (!cache.gap) throw new Error("Unexpected history continuation");
      const gap=cache.gap;
      gap.messages=mergeMessages(gap.messages,page,true);
      if (ids.includes(cache.anchor)) {
        cache.messages=mergeMessages(cache.messages,gap.messages,false);
        cache.anchor=gap.newAnchor;cache.gap=null;return cache;
      }
      if (!value.next_cursor || gap.seen.has(value.next_cursor)) throw new Error("History continuity is unavailable; retained messages were not replaced");
      gap.seen.add(value.next_cursor);gap.cursor=value.next_cursor;return cache;
    }
    if (cache.gap) return cache;
    if (!cache.anchor || ids.includes(cache.anchor)) {
      cache.messages=mergeMessages(cache.messages,page,false);
      cache.anchor=ids[0] || cache.anchor;return cache;
    }
    if (!ids.length || !value.next_cursor) throw new Error("History continuity is unavailable; retained messages were not replaced");
    cache.gap={messages:page.slice(),cursor:value.next_cursor,newAnchor:ids[0],seen:new Set([value.next_cursor])};
    return cache;
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
    let retainedMessages = [], completedTurns = new Set(), historyCursorInitialized = false;
    let knownTurns = new Set(), completionTargets = new Set(), completionSeen = new Set(), completionCursor = null;
    const headCache={messages:[],anchor:null,gap:null};
    function learnTurns(value) {
      for (const id of value.known_turn_ids || value.completed_turn_ids || []) knownTurns.add(id);
      for (const id of value.completed_turn_ids || []) {completedTurns.add(id);knownTurns.add(id);}
      if (value.latest_final) {completedTurns.add(value.latest_final.turn_id);knownTurns.add(value.latest_final.turn_id);}
    }
    function missingCompletion() {
      const active=new Set(current && current.active_turn_ids || []);
      return retainedMessages.concat(headCache.messages).filter(m=>m.role==="worker"&&m.phase==="commentary"&&!knownTurns.has(m.turn_id)&&!active.has(m.turn_id)).map(m=>m.turn_id);
    }
    const reading = byId("worker-reading"), progress = byId("worker-progress"), newActivity = byId("worker-new-activity");
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
      const nearEnd = reading ? reading.scrollHeight - reading.clientHeight - reading.scrollTop < 50 : false;
      const offset = reading ? reading.scrollTop : 0;
      const open = new Set(Array.from(container.querySelectorAll ? container.querySelectorAll("details[open]") : []).map(e=>e.dataset.bundleId));
      const anchor = reading && Array.from(container.children).find(e => e.getBoundingClientRect && e.getBoundingClientRect().bottom >= reading.getBoundingClientRect().top);
      const anchorId = anchor && anchor.dataset.messageId;
      const anchorOffset = anchor && anchor.getBoundingClientRect().top - reading.getBoundingClientRect().top;
      retainedMessages = mergeMessages(retainedMessages,messages,append);
      container.replaceChildren();
      if (!retainedMessages.length) {
        const empty = doc.createElement("p");
        empty.textContent = "No public messages are available on this conversation page. Saved history is retained; tool and reasoning records are not displayed.";
        container.appendChild(empty);
      }
      let bundle = null;
      for (const item of retainedMessages.slice().reverse()) {
        const article = doc.createElement("article"); article.className = "worker-history-message";
        article.dataset.messageId = item.message_id;
        const label = doc.createElement("p"); label.className = "meta";
        article.dataset.role = item.role;
        article.dataset.phase = item.phase || "unknown";
        label.textContent = (item.role === "worker" ? "WORKER" : "TANNER") + (item.phase === "final_answer" ? " // FINAL" : item.role === "worker" && item.phase === null ? " // PHASE UNKNOWN" : "") + " · " + item.turn_id;
        const body = doc.createElement("pre"); body.className = "worker-message"; body.textContent = item.text;
        article.append(label, body);
        if (item.role === "worker" && item.phase === "commentary" && completedTurns.has(item.turn_id)) {
          if (!bundle || bundle.dataset.bundleId !== item.turn_id) {
            bundle = doc.createElement("details"); bundle.className="worker-progress-bundle";
            bundle.dataset.bundleId=item.turn_id; bundle.dataset.messageId=item.message_id; bundle.open=open.has(item.turn_id);
            const title=doc.createElement("summary");title.textContent="Public progress from this completed turn";
            bundle.appendChild(title);container.appendChild(bundle);
          }
          bundle.appendChild(article);
        } else {bundle=null;container.appendChild(article);}
      }
      if (reading) {
        const replacement = anchorId && Array.from(container.children).find(e=>e.dataset.messageId===anchorId);
        if (replacement && replacement.getBoundingClientRect) reading.scrollTop += replacement.getBoundingClientRect().top-reading.getBoundingClientRect().top-anchorOffset;
        else reading.scrollTop=offset;
        if (nearEnd && !append) reading.scrollTop=reading.scrollHeight;
        if (newActivity) newActivity.hidden=nearEnd || append;
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
      if (page.hidden || refreshing || busy) return;
      refreshing = true;
      try {
        const value = projection(await request(URL));
        if (current && value.thread_id !== current.thread_id) throw new Error("Worker session changed; do not send to an unverified replacement");
        current = value; lastSuccess = Date.now();
        learnTurns(value);
        byId("worker-session-identity").textContent = "Session " + value.thread_id + " · Verified " + value.verified_at;
        const final = value.latest_final;
        if (final) {
          if (byId("worker-final-message").textContent !== final.text) byId("worker-final-message").textContent = final.text;
          byId("worker-final-identity").textContent = "Final message " + final.message_id + " · Turn " + final.turn_id;
        } else {
          byId("worker-final-message").textContent = "No exact final message was available in the bounded lookup. Browse the retained conversation; no summary has been substituted.";
          byId("worker-final-identity").textContent = "Latest final message unavailable";
        }
        if (!historyCursorInitialized) {olderCursor=value.next_cursor;historyCursorInitialized=pageIds(value).length>0;}
        headCache.messages=retainedMessages;
        advanceHead(headCache,value);
        if (headCache.gap) {
          const more=projection(await request(URL+"?cursor="+encodeURIComponent(headCache.gap.cursor)));
          if(more.thread_id!==value.thread_id) throw new Error("History belongs to a different Worker");
          learnTurns(more);
          advanceHead(headCache,more,true);
        }
        const unknown=missingCompletion();
        if (unknown.some(id=>!completionTargets.has(id))) {
          completionTargets=new Set(unknown);completionCursor=value.next_turn_cursor || null;completionSeen=new Set();
        }
        if (unknown.length && completionCursor) {
          const requested=completionCursor;
          const evidence=projection(await request(URL+"?turn_cursor="+encodeURIComponent(requested)));
          if(evidence.thread_id!==value.thread_id) throw new Error("Turn evidence belongs to a different Worker");
          const following=evidence.next_turn_cursor || null;
          if(following && (following===requested || completionSeen.has(following))) throw new Error("Turn evidence pagination did not advance; retained commentary is not relabeled completed");
          learnTurns(evidence);completionSeen.add(requested);completionCursor=following;
        }
        const signature = JSON.stringify([headCache.messages.map(m => [m.message_id, m.content_sha256]),Array.from(completedTurns)]);
        if (signature !== currentHistory) { history(headCache.messages, false); currentHistory = signature; }
        const historyState=byId("worker-history-state");
        if(historyState) historyState.textContent=headCache.gap ? "Syncing intervening history · retained messages remain available"
          : missingCompletion().length ? (completionCursor ? "Checking older turn completion · original progress remains visible" : "Older turn completion evidence unavailable · original progress remains visible")
          : olderCursor ? "Scroll upward to load earlier conversation." : "";
        // The independently verified final remains readable even when the
        // initial public page contains only a long active turn's tool items.
        const fallback=byId("worker-final-fallback");
        if(fallback) {
          fallback.hidden=!final || retainedMessages.some(m=>m.message_id===final.message_id);
          if(final) byId("worker-final-fallback-text").textContent=final.text;
        }
        byId("worker-older").disabled = !olderCursor;
        byId("worker-older").hidden = !olderCursor;
        if (progress) {
          const activeIds=new Set(value.active_turn_ids || []);
          const latestProgress = value.messages.concat(retainedMessages).find(m=>m.role==="worker"&&m.phase==="commentary"&&activeIds.has(m.turn_id));
          progress.hidden = !latestProgress || value.state !== "active";
          progress.textContent = latestProgress ? "Public progress · " + latestProgress.text : "";
        }
      } catch (error) {
        lastSuccess = 0; state.dataset.connection = "disconnected";
        state.textContent = "Disconnected · retained text is last known";
        replyResult.textContent = error.message + (pendingReply ? " · Reply identity retained; no automatic resend." : "");
        if(progress && !progress.hidden) progress.textContent="Last known · "+progress.textContent.replace(/^(Last known · )+/, "");
      } finally { refreshing = false; controls(); }
      // Receipt latency must not hold the projection or clipboard controls.
      // Only one observation is in flight; POSTs retain their own serialization.
      reconcileReply();
      if (reading && olderCursor && reading.scrollHeight<=reading.clientHeight+50) loadOlder();
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
    async function loadOlder() {
      if (!olderCursor || busy || refreshing) return; busy = true; controls();
      try { const value = projection(await request(URL + "?cursor=" + encodeURIComponent(olderCursor)));
        if (!current || value.thread_id !== current.thread_id) throw new Error("History belongs to a different Worker");
        learnTurns(value);
        history(value.messages, true); olderCursor = value.next_cursor; byId("worker-older").disabled = !olderCursor; byId("worker-older").hidden = !olderCursor;
      } catch (error) { replyResult.textContent = error.message; } finally { busy = false; controls(); }
    }
    byId("worker-older").addEventListener("click",loadOlder);
    if(reading)reading.addEventListener("scroll",()=>{if(reading.scrollTop<80)loadOlder();},{passive:true});
    byId("worker-newest").addEventListener("click", () => { readingOlder = false; currentHistory = ""; refresh(); });
    if (newActivity) newActivity.addEventListener("click",()=>{reading.scrollTop=reading.scrollHeight;newActivity.hidden=true;});
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
  return {projection, message, copyStatus, insertKey, mergeMessages, advanceHead, boot};
});

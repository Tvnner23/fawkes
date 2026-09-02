const OUTBOX_KEY = "capture_outbox";
const RETRY_ALARM = "fawkes_capture_retry";
let outboxMutation = Promise.resolve();

function loadOutbox() {
  return chrome.storage.local.get(OUTBOX_KEY).then((stored) => {
    const outbox = stored[OUTBOX_KEY];
    return Array.isArray(outbox) ? outbox : [];
  });
}

function saveOutbox(outbox) {
  return chrome.storage.local.set({ [OUTBOX_KEY]: outbox });
}

function mutateOutbox(mutator) {
  const operation = outboxMutation.then(async () => {
    const outbox = await loadOutbox();
    const updated = mutator(outbox);
    await saveOutbox(updated);
    return updated;
  });

  outboxMutation = operation.catch(() => {});
  return operation;
}

async function enqueueCapture(request) {
  await mutateOutbox((outbox) => {
    if (
      !outbox.some(
        (item) => item.capture_event_id === request.capture_event_id
      )
    ) {
      outbox.push(request);
    }
    return outbox;
  });
}

async function acknowledgeCapture(captureEventId) {
  await mutateOutbox((outbox) =>
    outbox.filter((item) => item.capture_event_id !== captureEventId)
  );
}

async function deliverCapture(request) {
  const response = await fetch(request.url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify(request.body)
  });

  const data = await response.json();

  if (!response.ok || !data?.acknowledged) {
    throw new Error(
      data?.error ?? `Capture receiver returned HTTP ${response.status}`
    );
  }

  await acknowledgeCapture(request.capture_event_id);

  return {
    ok: true,
    status: response.status,
    data
  };
}

async function retryOutbox() {
  const outbox = await loadOutbox();

  for (const request of outbox) {
    try {
      await deliverCapture(request);
    } catch (error) {
      console.error("Fawkes queued capture retry failed:", String(error));
    }
  }
}

chrome.runtime.onInstalled.addListener(() => {
  chrome.alarms.create(RETRY_ALARM, { periodInMinutes: 1 });
  retryOutbox();
});

chrome.runtime.onStartup.addListener(() => {
  chrome.alarms.create(RETRY_ALARM, { periodInMinutes: 1 });
  retryOutbox();
});

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === RETRY_ALARM) {
    retryOutbox();
  }
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (
    message?.type !== "fawkes_capture" &&
    message?.type !== "fawkes_message_capture"
  ) {
    return;
  }

  chrome.storage.local.get(
    ["instance_id", "conversation_id"],
    (identity) => {
      const instanceId = identity.instance_id ?? null;
      const conversationId =
        message.conversation_id ??
        identity.conversation_id ??
        null;

      let url;
      let body;
      const captureEventId = message.capture_event_id;

      if (!captureEventId) {
        sendResponse({
          ok: false,
          error: "capture_event_id is required"
        });
        return;
      }

      if (message.type === "fawkes_message_capture") {
        url = "http://127.0.0.1:8765/capture-message";
        body = {
          title: message.title,
          conversation_id: conversationId,
          message_id: message.message_id,
          role: message.role,
          text: message.text,
          model_slug: message.model_slug ?? null,
          instance_id: instanceId,
          capture_event_id: captureEventId
        };
      } else {
        url = "http://127.0.0.1:8765/capture";
        body = {
          title: message.title,
          conversation: message.conversation,
          source: "browser_live",
          capture_type: "near_live",
          encoding: "utf-8",
          instance_id: instanceId,
          conversation_id: conversationId,
          capture_event_id: captureEventId
        };
      }

      const request = {
        capture_event_id: captureEventId,
        url,
        body,
        queued_at: new Date().toISOString()
      };

      enqueueCapture(request)
        .then(() => deliverCapture(request))
        .then(sendResponse)
        .catch((error) => {
          sendResponse({
            ok: false,
            queued: true,
            capture_event_id: captureEventId,
            error: String(error)
          });
        });
    }
  );

  return true;
});

chrome.alarms.create(RETRY_ALARM, { periodInMinutes: 1 });
retryOutbox();

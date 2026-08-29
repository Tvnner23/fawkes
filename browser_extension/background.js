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

      if (message.type === "fawkes_message_capture") {
        url = "http://127.0.0.1:8765/capture-message";
        body = {
          title: message.title,
          conversation_id: conversationId,
          message_id: message.message_id,
          role: message.role,
          text: message.text,
          model_slug: message.model_slug ?? null,
          instance_id: instanceId
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
          conversation_id: conversationId
        };
      }

      fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify(body)
      })
        .then(async (response) => {
          const data = await response.json();

          sendResponse({
            ok: response.ok,
            status: response.status,
            data
          });
        })
        .catch((error) => {
          sendResponse({
            ok: false,
            error: String(error)
          });
        });
    }
  );

  return true;
});

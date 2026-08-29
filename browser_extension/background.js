chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message?.type !== "fawkes_capture") {
    return;
  }

  chrome.storage.local.get(
    ["instance_id", "conversation_id"],
    (identity) => {
      fetch("http://127.0.0.1:8765/capture", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          title: message.title,
          conversation: message.conversation,
          conversation_id: message.conversation_id ?? identity.conversation_id ?? null,
          source: "browser_live",
          capture_type: "near_live",
          encoding: "utf-8",
          instance_id: identity.instance_id ?? null,
          conversation_id: identity.conversation_id ?? null
        })
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

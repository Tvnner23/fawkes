chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message?.type !== "fawkes_capture") {
    return;
  }

  fetch("http://127.0.0.1:8765/capture", {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      title: message.title,
      conversation: message.conversation
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

  return true;
});

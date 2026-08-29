(() => {
  let lastCapturedText = "";
  let captureTimer = null;

  function getConversationTitle() {
    const title = document.title?.trim();

    if (title && title !== "ChatGPT") {
      return title.replace(/\s*-\s*ChatGPT\s*$/i, "").trim();
    }

    return "ChatGPT Conversation";
  }

  function buildConversation() {
    const messages = document.querySelectorAll(
      '[data-message-author-role="user"], [data-message-author-role="assistant"]'
    );

    const parts = [];

    for (const message of messages) {
      const role = message.getAttribute("data-message-author-role");
      const text = message.innerText?.trim();

      if (!text) {
        continue;
      }

      const label = role === "user" ? "User" : "Fawkes";
      parts.push(`${label}: ${text}`);
    }

    return parts.join("\n\n");
  }

  function captureConversation() {
    const conversation = buildConversation();

    if (!conversation || conversation === lastCapturedText) {
      return;
    }

    lastCapturedText = conversation;

    chrome.runtime.sendMessage(
      {
        type: "fawkes_capture",
        title: getConversationTitle(),
        conversation
      },
      (response) => {
        if (chrome.runtime.lastError) {
          console.error(
            "Fawkes capture error:",
            chrome.runtime.lastError.message
          );
          return;
        }

        if (!response?.ok) {
          console.error("Fawkes capture failed:", response);
          return;
        }

        console.log("Fawkes capture successful:", response.data);
      }
    );
  }

  function scheduleCapture() {
    clearTimeout(captureTimer);
    captureTimer = setTimeout(captureConversation, 2000);
  }

  const observer = new MutationObserver(scheduleCapture);

  observer.observe(document.body, {
    childList: true,
    subtree: true,
    characterData: true
  });

  scheduleCapture();

  console.log("Fawkes Live Capture loaded.");
})();

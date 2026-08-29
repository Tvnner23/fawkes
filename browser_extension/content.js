(() => {
  let lastCapturedText = "";
  let snapshotTimer = null;
  let messageTimer = null;

  const lastMessageStates = new Map();

  function getConversationTitle() {
    const title = document.title?.trim();

    if (title && title !== "ChatGPT") {
      return title.replace(/\s*-\s*ChatGPT\s*$/i, "").trim();
    }

    return "ChatGPT Conversation";
  }

  function getConversationId() {
    const match = window.location.pathname.match(
      /^\/c\/([0-9a-f-]{36})\/?$/i
    );

    return match ? match[1] : null;
  }

  function getRenderedMessages() {
    return document.querySelectorAll(
      '[data-message-author-role="user"], [data-message-author-role="assistant"]'
    );
  }

  function buildConversation() {
    const parts = [];

    for (const message of getRenderedMessages()) {
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
        conversation,
        conversation_id: getConversationId()
      },
      (response) => {
        if (chrome.runtime.lastError) {
          console.error(
            "Fawkes snapshot capture error:",
            chrome.runtime.lastError.message
          );
          return;
        }

        if (!response?.ok) {
          console.error("Fawkes snapshot capture failed:", response);
          return;
        }

        console.log(
          "Fawkes snapshot capture successful:",
          response.data
        );
      }
    );
  }

  function extractText(content) {
    if (
      content?.content_type !== "text" ||
      !Array.isArray(content.parts)
    ) {
      return null;
    }

    const textParts = content.parts.filter(
      (part) => typeof part === "string"
    );

    if (!textParts.length) {
      return null;
    }

    return textParts.join("");
  }

  function captureStructuredMessages(messages) {
    const conversationId = getConversationId();

    if (!conversationId || !Array.isArray(messages)) {
      return;
    }

    for (const message of messages) {
      const messageId = message?.id;
      const role = message?.author?.role;
      const text = extractText(message?.content);
      const modelSlug =
        message?.metadata?.resolved_model_slug ??
        message?.metadata?.model_slug ??
        null;

      if (
        !messageId ||
        (role !== "user" && role !== "assistant") ||
        !text ||
        !text.trim()
      ) {
        continue;
      }

      const state = JSON.stringify({
        role,
        modelSlug,
        text
      });

      if (lastMessageStates.get(messageId) === state) {
        continue;
      }

      lastMessageStates.set(messageId, state);

      chrome.runtime.sendMessage(
        {
          type: "fawkes_message_capture",
          title: getConversationTitle(),
          conversation_id: conversationId,
          message_id: messageId,
          role,
          text,
          model_slug: modelSlug
        },
        (response) => {
          if (chrome.runtime.lastError) {
            console.error(
              "Fawkes structured capture error:",
              chrome.runtime.lastError.message
            );
            return;
          }

          if (!response?.ok) {
            console.error(
              "Fawkes structured capture failed:",
              response
            );
            return;
          }

          console.log(
            "Fawkes structured capture successful:",
            response.data
          );
        }
      );
    }
  }

  function requestStructuredMessages() {
    window.postMessage(
      {
        source: "fawkes_content_script",
        type: "request_structured_messages"
      },
      "*"
    );
  }

  window.addEventListener("message", (event) => {
    if (
      event.source !== window ||
      event.data?.source !== "fawkes_page_bridge" ||
      event.data?.type !== "structured_messages"
    ) {
      return;
    }

    captureStructuredMessages(event.data.messages);
  });

  function scheduleCapture() {
    clearTimeout(messageTimer);
    messageTimer = setTimeout(requestStructuredMessages, 250);

    clearTimeout(snapshotTimer);
    snapshotTimer = setTimeout(captureConversation, 2000);
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

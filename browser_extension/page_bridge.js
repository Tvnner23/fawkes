(() => {
  function findStructuredMessage(element) {
    const fiberKey = Object.keys(element).find(
      (key) => key.startsWith("__reactFiber$")
    );

    if (!fiberKey) {
      return null;
    }

    let fiber = element[fiberKey];

    for (let depth = 0; fiber && depth < 20; depth++, fiber = fiber.return) {
      const message = fiber.memoizedProps?.message;

      if (message?.id && message?.content) {
        return message;
      }
    }

    return null;
  }

  function emitStructuredMessages() {
    const elements = document.querySelectorAll(
      '[data-message-author-role="user"], [data-message-author-role="assistant"]'
    );

    const messages = [];

    for (const element of elements) {
      const message = findStructuredMessage(element);

      if (!message) {
        continue;
      }

      messages.push({
        id: message.id,
        author: message.author ?? null,
        create_time: message.create_time ?? null,
        update_time: message.update_time ?? null,
        content: message.content ?? null,
        status: message.status ?? null,
        end_turn: message.end_turn ?? null,
        weight: message.weight ?? null,
        recipient: message.recipient ?? null,
        channel: message.channel ?? null,
        metadata: message.metadata ?? null
      });
    }

    window.postMessage(
      {
        source: "fawkes_page_bridge",
        type: "structured_messages",
        messages
      },
      "*"
    );
  }

  window.addEventListener("message", (event) => {
    if (event.source !== window) {
      return;
    }

    if (event.data?.source !== "fawkes_content_script") {
      return;
    }

    if (event.data?.type === "request_structured_messages") {
      emitStructuredMessages();
    }
  });

  console.log("Fawkes page bridge loaded.");
})();

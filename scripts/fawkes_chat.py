from src.runtime.chat import FawkesChatRuntime


def main():
    fawkes = FawkesChatRuntime()

    history = []

    print()
    print("============================================================")
    print("                     FAWKES MK I")
    print("============================================================")
    print("Crude conversational runtime online.")
    print("Type 'exit' to shut down.")
    print()

    while True:
        try:
            user_message = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not user_message:
            continue

        if user_message.lower() in {"exit", "quit"}:
            break

        result = fawkes.respond(
            user_message=user_message,
            conversation_history=history,
        )

        print()
        print(f"Fawkes: {result['text']}")
        print()

        history.append(
            {
                "role": "user",
                "content": user_message,
            }
        )

        history.append(
            {
                "role": "assistant",
                "content": result["text"],
            }
        )


if __name__ == "__main__":
    main()

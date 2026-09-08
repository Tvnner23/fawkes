import uuid

from src.conversations import (
    create_conversation,
    get_latest_conversation,
)
from src.instances import get_or_create_default_instance
from src.memory.archive_context import build_archive_context
from src.memory.archive_retrieval import ensure_archive_index
from src.memory.ledger import discover_candidate, update_work_item
from src.runtime.chat import FawkesChatRuntime
from src.runtime.context_receipts import save_context_receipt
from src.runtime.expression import shutdown_signoff, startup_greeting
from src.runtime.persistence import persist_live_message


def main():
    print()
    print("============================================================")
    print("                    FAWKES MK I")
    print("============================================================")
    print()
    print("Type 'exit' to disconnect.".center(60))
    print(f"Fawkes: {startup_greeting()}")
    print()

    phoenix = get_or_create_default_instance()
    instance_id = phoenix["instance_id"]
    ensure_archive_index(
        instance_id=instance_id,
        include_unscoped=True,
    )
    conversation = get_latest_conversation(instance_id=instance_id)

    if conversation is None:
        conversation = create_conversation(
            title="Fawkes CLI Session",
            instance_id=instance_id,
        )

    conversation_id = conversation["conversation_id"]
    runtime = None
    # Recover canonical continuity before entering the loop without requiring
    # provider credentials merely to start and exit the CLI.
    conversation_history = list(
        build_archive_context(conversation_id, max_messages=20)
    )

    while True:
        try:
            user_message = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\nFawkes: {shutdown_signoff()}")
            break

        if not user_message:
            continue

        if user_message.lower() in {"exit", "quit"}:
            print(f"Fawkes: {shutdown_signoff()}")
            break

        try:
            if runtime is None:
                # Delay provider construction until a real turn. This keeps
                # startup, history recovery, and clean shutdown independent of
                # provider availability.
                runtime = FawkesChatRuntime(
                    instance_id=instance_id,
                    # Existing pre-instance records belong to the first Fawkes migration.
                    include_unscoped_memories=True,
                )
                if runtime.context_messages != 20:
                    conversation_history = list(
                        build_archive_context(
                            conversation_id,
                            max_messages=runtime.context_messages,
                        )
                    )

            estimated = runtime.paid_call_guard.estimate(
                model=runtime.model,
                reason="Fawkes complete conversational turn",
                estimated_calls=5,
            )

            if estimated.estimated_cost > 0:
                print()
                print(
                    "PAID PROVIDER CALL: "
                    f"{estimated.provider}/{estimated.model}"
                )
                print(
                    f"Estimated maximum cost for this turn: "
                    f"${estimated.estimated_cost:.4f}"
                )
                print(
                    f"Maximum provider calls covered: "
                    f"{estimated.estimated_calls}"
                )

                answer = input(
                    "Authorize this call? [y/N]: "
                ).strip().lower()

                if answer not in {"y", "yes"}:
                    print("Fawkes: Call cancelled. No API request made.")
                    print()
                    continue

                runtime.paid_call_guard.require_confirmation = False

            message_id = str(uuid.uuid4())

            user_archive = persist_live_message(
                instance_id=instance_id,
                conversation_id=conversation_id,
                message_id=message_id,
                role="user",
                text=user_message,
                model_slug=runtime.model,
            )

            work_item = discover_candidate(
                instance_id=instance_id,
                conversation_id=conversation_id,
                message_id=message_id,
                canonical_revision=user_archive["archive_id"],
                source_archive_ids=(user_archive["archive_id"],),
                candidate_content=user_message,
                candidate_created_at=user_archive["created_at"],
            )
            update_work_item(
                work_item["work_item_id"],
                status="queued",
            )

            result = runtime.respond(
                user_message=user_message,
                conversation_id=conversation_id,
                conversation_history=conversation_history,
                current_message_id=message_id,
            )

            assistant_message_id = str(uuid.uuid4())

            assistant_persisted = True
            assistant_archive = None
            try:
                assistant_archive = persist_live_message(
                    instance_id=instance_id,
                    conversation_id=conversation_id,
                    message_id=assistant_message_id,
                    role="assistant",
                    text=result["text"],
                    model_slug=runtime.model,
                )
            except Exception as exc:
                assistant_persisted = False
                result.setdefault("warnings", []).append(
                    "The response was generated but could not be archived "
                    f"({type(exc).__name__}: {exc})."
                )

            try:
                save_context_receipt(
                    instance_id=instance_id,
                    conversation_id=conversation_id,
                    request_message_id=message_id,
                    response_message_id=assistant_message_id,
                    response_archive_id=(
                        assistant_archive["archive_id"]
                        if assistant_archive is not None
                        else None
                    ),
                    model=runtime.model,
                    memories=result.get("memories", ()),
                    archive_passages=result.get("archive_passages", ()),
                    conversation_context=result.get(
                        "conversation_context", ()
                    ),
                    development_sources=(
                        result["development"].get("record", {}).get(
                            "proposal_id"
                        ),
                    )
                    if result.get("development")
                    and result["development"].get("record")
                    else (),
                )
            except Exception as exc:
                result.setdefault("warnings", []).append(
                    "The response context receipt could not be archived "
                    f"({type(exc).__name__}: {exc})."
                )

            conversation_history.append(
                {
                    "role": "user",
                    "content": user_message,
                }
            )

            if assistant_persisted:
                conversation_history.append(
                    {
                        "role": "assistant",
                        "content": result["text"],
                    }
                )

            print()
            print(f"Fawkes: {result['text']}")
            for warning in result.get("warnings", ()):
                print(f"[warning] {warning}")
            print()

        except PermissionError as exc:
            print()
            print(f"Fawkes: {exc}")
            print()

        except Exception as exc:
            print()
            print(f"Fawkes encountered an error: {exc}")
            print()

        finally:
            if runtime is not None:
                runtime.paid_call_guard.require_confirmation = True

    print()


if __name__ == "__main__":
    main()

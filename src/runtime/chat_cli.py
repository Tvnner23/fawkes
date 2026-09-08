from dataclasses import replace
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
from src.runtime.personal_recording import CATEGORIES, RecordingPolicyError, RecordingPolicyStore


def _resume_conversation(instance_id, *, private):
    if private:
        return "private-" + str(uuid.uuid4()), []
    ensure_archive_index(instance_id=instance_id, include_unscoped=True)
    conversation = get_latest_conversation(instance_id=instance_id)
    if conversation is None:
        conversation = create_conversation(title="Fawkes CLI Session", instance_id=instance_id)
    conversation_id = conversation["conversation_id"]
    if str(conversation_id).startswith("private-"):
        raise RecordingPolicyError("A private conversation cannot become retained history")
    return conversation_id, list(build_archive_context(conversation_id, max_messages=20))


def _bounded_private_history(messages):
    bounded = [{"role": item["role"], "content": item["content"][:50_000]}
               for item in messages[-20:]]
    while sum(len(item["content"]) for item in bounded) > 100_000:
        bounded.pop(0)
    return bounded


def _restrict_draft_policy(draft, current):
    """A pending draft can gain restrictions, never new retention permission."""
    if draft.instance_id != current.instance_id:
        raise RecordingPolicyError("Draft recording policies belong to different instances")
    private = draft.mode == "private" or current.mode == "private"
    return replace(current, mode="private" if private else "retained", **{
        name: False if private else getattr(draft, name) and getattr(current, name)
        for name in CATEGORIES
    })


def main():
    print()
    print("============================================================")
    print("                    FAWKES MK I")
    print("============================================================")
    print()
    print("Type 'exit' to disconnect; /private or /retained selects future turns.")
    print(f"Fawkes: {startup_greeting()}")
    print()

    phoenix = get_or_create_default_instance()
    instance_id = phoenix["instance_id"]
    policy_store = RecordingPolicyStore(instance_id)
    requested_mode = None
    try:
        initial_policy = policy_store.latch()
        current_mode = initial_policy.mode
        conversation_id, conversation_history = _resume_conversation(
            instance_id, private=current_mode == "private")
    except RecordingPolicyError:
        print("Fawkes: Recording settings are unavailable. No conversation was sent.")
        return
    runtime = None
    # Recover canonical continuity before entering the loop without requiring
    # provider credentials merely to start and exit the CLI.

    while True:
        try:
            # input() can block while another client changes the defaults. The
            # draft's initial privacy/categories remain an upper retention bound.
            draft_policy = policy_store.latch(mode=requested_mode)
            print(f"Draft recording: {draft_policy.mode} (policy revision {draft_policy.policy_revision})")
            user_message = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\nFawkes: {shutdown_signoff()}")
            break
        except RecordingPolicyError:
            print("Fawkes: Recording settings are unavailable. No conversation was sent.")
            break

        if not user_message:
            continue

        if user_message.lower() in {"exit", "quit"}:
            print(f"Fawkes: {shutdown_signoff()}")
            break

        if user_message.lower() in {"/private", "/retained"}:
            requested_mode = user_message.lower()[1:]
            print("Fawkes: Requested mode applies to future turns; configured restrictions still apply.")
            continue

        try:
            policy = _restrict_draft_policy(draft_policy, policy_store.latch(mode=requested_mode))
            new_runtime = runtime is None
            if new_runtime:
                # Delay provider construction until a real turn. This keeps
                # startup, history recovery, and clean shutdown independent of
                # provider availability.
                runtime = FawkesChatRuntime(
                    instance_id=instance_id,
                    # Existing pre-instance records belong to the first Fawkes migration.
                    include_unscoped_memories=True,
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

            # Paid confirmation is another blocking input, not submission. Take
            # current restrictions before selecting context or writing either role.
            policy = _restrict_draft_policy(policy, policy_store.latch(mode=requested_mode))
            private = policy.mode == "private"
            if policy.mode != current_mode:
                # Never promote the prior private buffer to Archive or a
                # retained turn's context when the effective mode changes.
                conversation_id, conversation_history = _resume_conversation(instance_id, private=private)
                current_mode = policy.mode
            if new_runtime and not private and runtime.context_messages != 20:
                conversation_history = list(build_archive_context(
                    conversation_id, max_messages=runtime.context_messages))
            print(f"Recording: {policy.mode} (policy revision {policy.policy_revision})")

            message_id = str(uuid.uuid4())

            user_archive = None
            if not private:
                user_archive = persist_live_message(
                    instance_id=instance_id,
                    conversation_id=conversation_id,
                    message_id=message_id,
                    role="user",
                    text=user_message,
                    model_slug=runtime.model,
                    recording_policy=policy,
                )

            if policy.memory_learning:
                work_item = discover_candidate(
                    instance_id=instance_id,
                    conversation_id=conversation_id,
                    message_id=message_id,
                    canonical_revision=user_archive["archive_id"],
                    source_archive_ids=(user_archive["archive_id"],),
                    candidate_content=user_message,
                    candidate_created_at=user_archive["created_at"],
                )
                update_work_item(work_item["work_item_id"], status="queued")

            result = runtime.respond(
                user_message=user_message,
                conversation_id=conversation_id,
                conversation_history=conversation_history if not private else (),
                current_message_id=message_id,
                recording_policy=policy,
                **({"ephemeral_context": tuple(dict(item) for item in conversation_history)} if private else {}),
            )

            assistant_message_id = str(uuid.uuid4())

            assistant_persisted = True
            assistant_archive = None
            try:
                if not private:
                    assistant_archive = persist_live_message(
                        instance_id=instance_id,
                        conversation_id=conversation_id,
                        message_id=assistant_message_id,
                        role="assistant",
                        text=result["text"],
                        model_slug=runtime.model,
                        recording_policy=policy,
                    )
            except Exception as exc:
                assistant_persisted = False
                result.setdefault("warnings", []).append(
                    "The response was generated but could not be archived "
                    f"({type(exc).__name__}: {exc})."
                )

            try:
                if policy.personal_diagnostics:
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
                        conversation_context=result.get("conversation_context", ()),
                        development_sources=(result["development"].get("record", {}).get("proposal_id"),)
                        if result.get("development") and result["development"].get("record") else (),
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
            if private:
                conversation_history = _bounded_private_history(conversation_history)

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

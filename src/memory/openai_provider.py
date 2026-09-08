import json
import os

from openai import OpenAI

from src.memory.semantic import SemanticMemoryAssessment
from src.memory.development import DevelopmentProposal


class OpenAISemanticMemoryProvider:
    """
    OpenAI-backed semantic memory provider.

    This is an implementation detail behind the provider-independent
    semantic memory contract.
    """

    def __init__(self, client=None, model=None):
        self.client = client or OpenAI()
        self.model = model or os.getenv(
            "FAWKES_MEMORY_MODEL",
            "gpt-5.6-luna",
        )

    def evaluate_memory(
        self,
        *,
        content: str,
        conversation_context=(),
    ) -> SemanticMemoryAssessment:
        context_text = json.dumps(
            list(conversation_context),
            ensure_ascii=False,
        )

        response = self.client.responses.create(
            model=self.model,
            input=[
                {
                    "role": "system",
                    "content": (
                        "You are the semantic memory evaluator for Fawkes. "
                        "Determine whether the supplied user statement contains "
                        "durable information worth remembering. "
                        "Use conversation context only to clarify or disambiguate "
                        "the candidate. Context must not silently contribute facts "
                        "that the candidate does not support. Every assertion in "
                        "meaning must be directly supported by the messages named "
                        "in supporting_message_ids. The candidate message must be "
                        "one of those supporting messages. If the conclusion truly "
                        "depends on multiple messages, list every supporting message "
                        "ID and its source archive ID. If the candidate does not "
                        "support a durable assertion, set should_remember false. "
                        "Do not rely on keyword prefixes. "
                        "Keep related facts distinct when they answer different "
                        "questions. In particular, education_institution, degree, "
                        "career_direction, and career_goal are separate memory "
                        "types and must not be collapsed into one broad career "
                        "memory. A field the user wants to work in is not evidence "
                        "of the name of their degree. "
                        "Relationship continuity matters too: preserve "
                        "inside jokes, recurring playful bits, shared references, "
                        "and meaningful relationship moments when the conversation "
                        "shows that they are genuinely shared or recurring. "
                        "Do not classify a one-off joke as an inside joke merely "
                        "because it is funny; use the surrounding context and "
                        "recurrence evidence. "
                        "Return only valid JSON with these fields: "
                        "should_remember, memory_type, meaning, confidence, "
                        "importance, reasoning, supporting_message_ids, "
                        "supporting_archive_ids."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Conversation context:\n{context_text}\n\n"
                        f"Candidate:\n{content}"
                    ),
                },
            ],
        )

        data = json.loads(response.output_text)

        return SemanticMemoryAssessment(
            should_remember=bool(data["should_remember"]),
            memory_type=data.get("memory_type"),
            meaning=data.get("meaning"),
            confidence=float(data["confidence"]),
            importance=float(data["importance"]),
            reasoning=data.get("reasoning"),
            supporting_message_ids=tuple(
                data.get("supporting_message_ids", ())
            ),
            supporting_archive_ids=tuple(
                data.get("supporting_archive_ids", ())
            ),
        )


    def compare(
        self,
        *,
        new_meaning,
        new_memory_type,
        existing_memory,
        conversation_context=(),
    ):
        """
        Semantically compare newly extracted durable meaning against
        an existing memory.
        """
        context_text = json.dumps(
            list(conversation_context),
            ensure_ascii=False,
        )

        existing_text = json.dumps(
            {
                "memory_id": existing_memory.get("memory_id"),
                "memory_type": existing_memory.get("memory_type"),
                "content": existing_memory.get("content"),
                "importance": existing_memory.get("importance"),
                "confidence": existing_memory.get("confidence"),
            },
            ensure_ascii=False,
        )

        system_prompt = (
            "You are the semantic memory comparison component for Fawkes. "
            "Compare a newly extracted durable memory against one existing "
            "durable memory. Determine the semantic relationship based on "
            "meaning, not wording or keyword overlap.\n\n"
            "Use exactly one of these relations: duplicate, supports, "
            "related, revises, supersedes, contradicts.\n\n"
            "duplicate means both memories represent essentially the same "
            "underlying durable idea, even when worded differently. "
            "Do not create a new memory merely because wording differs.\n\n"
            "supports means the new memory is distinct evidence reinforcing "
            "the existing memory.\n\n"
            "related means the memories are conceptually related but "
            "independently useful and should both remain.\n\n"
            "revises means the new memory refines or updates the existing "
            "memory while remaining fundamentally about the same subject.\n\n"
            "supersedes means the new memory replaces the old memory as the "
            "user's current position.\n\n"
            "contradicts means the memories express incompatible positions "
            "and the conflict should not be silently resolved.\n\n"
            "Pay particular attention to semantic duplicates. For example, "
            "'the user chose networking as their career direction' and "
            "'focus primarily on networking' should normally be considered "
            "duplicate.\n\n"
            "Return only valid JSON with these fields: "
            "relation, confidence, reasoning."
        )

        response = self.client.responses.create(
            model=self.model,
            input=[
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": (
                        f"Conversation context:\n{context_text}\n\n"
                        f"New memory type:\n{new_memory_type}\n\n"
                        f"New meaning:\n{new_meaning}\n\n"
                        f"Existing memory:\n{existing_text}"
                    ),
                },
            ],
        )

        data = json.loads(response.output_text)

        from src.memory.compare import MemoryComparison

        return MemoryComparison(
            relation=data["relation"],
            confidence=float(data["confidence"]),
            reasoning=data.get("reasoning"),
        )


    def rank_memories(
        self,
        *,
        query,
        memories,
    ):
        """
        Semantically rank candidate memories for a user query.

        The model receives the actual memory content and determines which
        memories are conceptually relevant. It is not constrained by
        keyword overlap or memory-type prefixes.
        """
        memory_text = json.dumps(
            [
                {
                    "memory_id": memory.get("memory_id"),
                    "memory_type": memory.get("memory_type"),
                    "content": memory.get("content"),
                    "importance": memory.get("importance"),
                    "confidence": memory.get("confidence"),
                }
                for memory in memories
            ],
            ensure_ascii=False,
        )

        response = self.client.responses.create(
            model=self.model,
            input=[
                {
                    "role": "system",
                    "content": (
                        "You are the semantic memory retrieval component "
                        "for Fawkes. "
                        "Given a user query and a set of durable memories, "
                        "identify memories that are genuinely relevant to "
                        "answering the query. "
                        "Match by meaning, context, relationships, and "
                        "conceptual relevance rather than exact keywords. "
                        "Do not require the query to contain the same words "
                        "used in a memory. "
                        "For broad questions about the user, retrieve "
                        "memories that collectively describe who the user "
                        "is, their background, preferences, goals, plans, "
                        "relationships, projects, and meaningful history. "
                        "Do not invent memories. "
                        "Return only valid JSON in this form: "
                        '{"ranked_ids": ["memory-id", "..."]}'
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"User query:\n{query}\n\n"
                        f"Candidate memories:\n{memory_text}"
                    ),
                },
            ],
        )

        data = json.loads(response.output_text)

        ranked_ids = data.get("ranked_ids", [])

        by_id = {
            memory["memory_id"]: memory
            for memory in memories
            if memory.get("memory_id")
        }

        return [
            by_id[memory_id]
            for memory_id in ranked_ids
            if memory_id in by_id
        ]


    def evaluate_development(
        self,
        *,
        experience,
        prior_development=(),
    ):
        prior_text = json.dumps(
            list(prior_development),
            ensure_ascii=False,
        )

        response = self.client.responses.create(
            model=self.model,
            input=[
                {
                    "role": "system",
                    "content": (
                        "You are the developmental evaluator for Fawkes. "
                        "Analyze a new experience and determine whether it reveals "
                        "a meaningful improvement Fawkes should consider. "
                        "Use prior developmental history to recognize lessons "
                        "Fawkes has already encountered. "
                        "Do not propose the same improvement unnecessarily. "
                        "If prior history already provides an adequate solution, "
                        "consider whether the experience should reinforce or "
                        "extend that existing lesson instead of creating redundant "
                        "development. "
                        "Do not modify code. "
                        "Do not assume every problem requires a change. "
                        "Return only valid JSON with these fields: "
                        "should_propose, category, observation, proposed_change, "
                        "rationale, confidence."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"New experience:\n{experience}\n\n"
                        f"Prior developmental history:\n{prior_text}"
                    ),
                },
            ],
        )

        data = json.loads(response.output_text)

        if not data["should_propose"]:
            return None

        return DevelopmentProposal(
            category=data["category"],
            observation=data["observation"],
            proposed_change=data["proposed_change"],
            rationale=data["rationale"],
            confidence=float(data["confidence"]),
        )

    def rank_development(
        self,
        *,
        experience,
        proposals,
    ):
        proposal_text = json.dumps(
            list(proposals),
            ensure_ascii=False,
        )

        response = self.client.responses.create(
            model=self.model,
            input=[
                {
                    "role": "system",
                    "content": (
                        "You are the developmental-history retrieval component "
                        "for Fawkes. Identify which previous development "
                        "proposals are conceptually relevant to the supplied "
                        "new experience. Rank only genuinely related proposals. "
                        "Return only valid JSON in this form: "
                        '{"ranked_ids": ["proposal-id", "..."]}'
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"New experience:\n{experience}\n\n"
                        f"Previous development proposals:\n{proposal_text}"
                    ),
                },
            ],
        )

        data = json.loads(response.output_text)

        ranked_ids = data.get("ranked_ids", [])

        by_id = {
            proposal["proposal_id"]: proposal
            for proposal in proposals
            if proposal.get("proposal_id")
        }

        return [
            by_id[proposal_id]
            for proposal_id in ranked_ids
            if proposal_id in by_id
        ]


    def evaluate_correction(
        self,
        *,
        user_message,
        conversation_context=(),
    ):
        context_text = json.dumps(
            list(conversation_context),
            ensure_ascii=False,
        )

        response = self.client.responses.create(
            model=self.model,
            input=[
                {
                    "role": "system",
                    "content": (
                        "You are the correction-recognition component for Fawkes. "
                        "Determine whether the user's current message is explicitly "
                        "correcting, criticizing, or instructing Fawkes to change "
                        "how he is behaving, reasoning, responding, or operating. "
                        "Use conversation context to understand what the user is "
                        "referring to. "
                        "Do not classify ordinary questions, disagreement about "
                        "facts, requests for information, or casual conversation "
                        "as corrections unless the user is clearly telling Fawkes "
                        "that his behavior or answer was wrong and needs to change. "
                        "Return only valid JSON with these fields: "
                        "is_correction, confidence, reasoning."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Conversation context:\n{context_text}\n\n"
                        f"Current user message:\n{user_message}"
                    ),
                },
            ],
        )

        data = json.loads(response.output_text)

        from src.memory.correction import CorrectionAssessment

        return CorrectionAssessment(
            is_correction=bool(data["is_correction"]),
            confidence=float(data["confidence"]),
            reasoning=data.get("reasoning"),
        )

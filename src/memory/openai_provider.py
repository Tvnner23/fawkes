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
                        "Use conversation context to resolve references. "
                        "Do not rely on keyword prefixes. "
                        "Relationship continuity matters too: preserve "
                        "inside jokes, recurring playful bits, shared references, "
                        "and meaningful relationship moments when the conversation "
                        "shows that they are genuinely shared or recurring. "
                        "Do not classify a one-off joke as an inside joke merely "
                        "because it is funny; use the surrounding context and "
                        "recurrence evidence. "
                        "Return only valid JSON with these fields: "
                        "should_remember, memory_type, meaning, confidence, "
                        "importance, reasoning."
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
        )


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

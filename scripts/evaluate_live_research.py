"""Explicit live-provider evaluation; not an offline test or no-write guarantee."""

import argparse
import json
import os
import tempfile
from pathlib import Path

from openai import OpenAI

from src.capabilities.research_evaluation import (
    ResearchEvaluationScenario,
    evaluate_research_scenario,
)
from src.capabilities.research_orchestrator import (
    ConversationalResearchOrchestrator,
    OpenAIResearchAssessor,
    OpenAIResearchPlanner,
)
from src.capabilities.web_research import OpenAIWebResearchProvider, WebResearchCapability
from src.memory.correction import CorrectionAssessment
from src.runtime.chat import FawkesChatRuntime


class _EmptyRetriever:
    def rank(self, **kwargs):
        return []


class _NoCorrection:
    def evaluate_correction(self, **kwargs):
        return CorrectionAssessment(
            is_correction=False, confidence=1.0, reasoning="Live research evaluation"
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("prompt")
    parser.add_argument("--expected-mode", choices=("simple", "standard", "deep"))
    parser.add_argument("--preferred-domain", action="append", default=[])
    parser.add_argument("--claim-marker", action="append", default=[])
    parser.add_argument("--max-searches", type=int, default=6)
    parser.add_argument("--max-duration", type=float, default=75)
    parser.add_argument("--query-timeout", type=float, default=25)
    parser.add_argument("--show-answer", action="store_true")
    args = parser.parse_args()

    client = OpenAI()
    model = os.getenv("FAWKES_RESEARCH_MODEL") or os.getenv(
        "FAWKES_CHAT_MODEL", "gpt-5.6-luna"
    )
    with tempfile.TemporaryDirectory(prefix="fawkes-live-research-") as tmp:
        root = Path(tmp)
        capability = WebResearchCapability(
            provider=OpenAIWebResearchProvider(client=client, model=model),
            research_dir=root / "research",
            receipt_dir=root / "receipts",
        )
        orchestrator = ConversationalResearchOrchestrator(
            planner=OpenAIResearchPlanner(client=client, model=model),
            assessor=OpenAIResearchAssessor(client=client, model=model),
            capability=capability,
            sessions_dir=root / "sessions",
            max_searches=args.max_searches,
            max_duration_seconds=args.max_duration,
            query_timeout_seconds=args.query_timeout,
        )
        runtime = FawkesChatRuntime(
            client=client,
            model=model,
            instance_id="live-research-evaluation",
            research_orchestrator=orchestrator,
        )
        runtime.semantic_retriever = _EmptyRetriever()
        runtime.correction_evaluator = _NoCorrection()
        result = runtime.respond(user_message=args.prompt)

        scenario = ResearchEvaluationScenario(
            scenario_id="live-ad-hoc",
            prompt=args.prompt,
            expected_research=True,
            expected_mode=args.expected_mode,
            preferred_domains=tuple(args.preferred_domain),
            expected_claim_markers=tuple(args.claim_marker),
            max_searches=args.max_searches,
        )
        metrics = evaluate_research_scenario(
            scenario,
            {
                "response": result["text"],
                "research": result.get("research"),
                "citation_validation": result.get("citation_validation", {}),
            },
        )
        output = {
            "model": model,
            "metrics": metrics,
            "research_session": (
                result.get("research", {}).get("session", {})
                if result.get("research") else None
            ),
            "answer": result["text"] if args.show_answer else None,
            "storage_scope": (
                "Research, provider receipts and sessions use the temporary evaluation directory. "
                "Other runtime state boundaries require their own isolation; no blanket no-write claim."
            ),
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

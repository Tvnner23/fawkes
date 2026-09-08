from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from zoneinfo import ZoneInfo

from src.capabilities.awareness import CapabilityAwareness
from src.capabilities.continuity import (
    CONTINUITY_RETRIEVAL_DEFINITION, ContinuityRetriever,
    is_continuity_reference, timestamp_bounds,
)
from src.capabilities.core import CapabilityAvailabilityCatalog, CapabilityDefinition
from src.memory.archive_retrieval import index_canonical_message


class SemanticRanker:
    def __init__(self, wanted): self.wanted = wanted
    def rank_memories(self, *, query, memories):
        return [item for item in memories if self.wanted in item["content"]]


class ContinuityRetrievalTests(unittest.TestCase):
    def add(self, path, *, conversation, message, content, created):
        index_canonical_message(instance_id="fawkes", conversation_id=conversation,
            message_id=message, role="user", content=content, created_at=created,
            source_archive_id="archive-" + message, path=path)

    def test_older_same_conversation_reference_is_retrievable(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "index.sqlite3"
            self.add(path, conversation="same", message="before", content="We were organizing the BOOX.", created="2026-08-30T19:04:00+00:00")
            self.add(path, conversation="same", message="course", content="I want the AI class in my first seven-week block so I can understand Fawkes better.", created="2026-08-30T19:04:49+00:00")
            self.add(path, conversation="same", message="after", content="We should verify the course and instructor.", created="2026-08-30T19:05:00+00:00")
            result = ContinuityRetriever(instance_id="fawkes", semantic_provider=SemanticRanker("seven-week"), index_path=path).retrieve(
                "Do you think that AI professor is qualified?", exclude_message_ids=("after",))
        self.assertEqual(result["status"], "found")
        self.assertIn("course", [item["message_id"] for item in result["passages"]])
        self.assertNotIn("after", [item["message_id"] for item in result["passages"]])

    def test_cross_conversation_reference_remains_supported(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "index.sqlite3"
            self.add(path, conversation="older", message="decision", content="We decided Atlas will use the blue enclosure because it is easier to service.", created="2026-08-29T10:00:00+00:00")
            result = ContinuityRetriever(instance_id="fawkes", semantic_provider=SemanticRanker("blue enclosure"), index_path=path).retrieve("Why did we make that Atlas decision?")
        self.assertEqual(result["passages"][0]["conversation_id"], "older")
        self.assertIn("easier to service", result["passages"][0]["content"])

    def test_timestamp_clue_uses_rider_timezone_and_preserves_neighbor_context(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "index.sqlite3"
            self.add(path, conversation="same", message="target", content="The AI class belongs in the first block for a meaningful reason.", created="2026-08-30T19:04:49+00:00")
            now = datetime(2026, 8, 30, 19, 45, tzinfo=ZoneInfo("America/Chicago"))
            result = ContinuityRetriever(instance_id="fawkes", index_path=path).retrieve("the first message was at 2:04 PM today", now=now)
        self.assertEqual(result["ranking"], "timestamp")
        self.assertEqual(result["passages"][0]["message_id"], "target")

    def test_no_match_does_not_claim_not_stored(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "index.sqlite3"
            result = ContinuityRetriever(instance_id="fawkes", index_path=path).retrieve("that missing discussion")
        self.assertEqual(result["status"], "no_match")
        self.assertIn("does not prove", result["limitations"])

    def test_awareness_selects_references_but_not_casual_conversation(self):
        catalog = CapabilityAvailabilityCatalog(); catalog.advertise(CONTINUITY_RETRIEVAL_DEFINITION, effects="read only")
        awareness = CapabilityAwareness(catalog.manifests())
        self.assertIn("continuity.retrieve", {x.capability_id for x in awareness.select("What was the reason behind that decision?")})
        self.assertEqual(awareness.select("Tell me a joke."), ())
        self.assertFalse(is_continuity_reference("That sounds good."))

    def test_qualification_reference_composes_continuity_and_research(self):
        catalog = CapabilityAvailabilityCatalog()
        catalog.advertise(CONTINUITY_RETRIEVAL_DEFINITION, effects="read only")
        catalog.advertise(CapabilityDefinition(
            name="web.research", version="1", description="current public research",
        ), effects="evidence only")
        selected = {
            item.capability_id for item in CapabilityAwareness(catalog.manifests()).select(
                "Is that professor qualified to review the architecture?"
            )
        }
        self.assertEqual(selected, {"continuity.retrieve", "web.research"})


if __name__ == "__main__": unittest.main()

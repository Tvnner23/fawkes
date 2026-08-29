import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import src.memory.store as store
from src.memory.retrieval import retrieve_memories


class FawkesMemoryRetrievalTests(unittest.TestCase):
    def test_retrieval_returns_relevant_active_memories(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            records = root / "records"
            events = root / "events"

            with patch.object(store, "MEMORY_RECORDS_DIR", records), \
                 patch.object(store, "MEMORY_EVENTS_DIR", events):

                relevant = store.create_memory(
                    memory_type="goal",
                    content="The rider is pursuing a cybersecurity degree.",
                    confidence=0.90,
                    importance=0.90,
                )

                unrelated = store.create_memory(
                    memory_type="preference",
                    content="The rider prefers salmon for dinner.",
                    confidence=0.90,
                    importance=0.50,
                )

                results = retrieve_memories(
                    "What is the rider's cybersecurity degree goal?"
                )

                self.assertTrue(results)
                self.assertEqual(results[0]["memory_id"], relevant.memory_id)
                self.assertNotEqual(results[0]["memory_id"], unrelated.memory_id)

    def test_retrieval_excludes_superseded_memories(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            records = root / "records"
            events = root / "events"

            with patch.object(store, "MEMORY_RECORDS_DIR", records), \
                 patch.object(store, "MEMORY_EVENTS_DIR", events):

                old = store.create_memory(
                    memory_type="goal",
                    content="Focus on cybersecurity.",
                )

                new = store.supersede_memory(
                    old.memory_id,
                    "goal",
                    "Focus primarily on networking.",
                )

                results = retrieve_memories("What is the current career focus?")

                result_ids = [memory["memory_id"] for memory in results]

                self.assertNotIn(old.memory_id, result_ids)
                self.assertIn(new.memory_id, result_ids)

    def test_retrieval_respects_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            records = root / "records"
            events = root / "events"

            with patch.object(store, "MEMORY_RECORDS_DIR", records), \
                 patch.object(store, "MEMORY_EVENTS_DIR", events):

                for index in range(5):
                    store.create_memory(
                        memory_type="goal",
                        content=f"The rider has a cybersecurity networking goal number {index}.",
                        importance=0.8,
                        confidence=0.9,
                    )

                results = retrieve_memories(
                    "cybersecurity networking goal",
                    limit=2,
                )

                self.assertEqual(len(results), 2)

    def test_irrelevant_query_returns_no_memories(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            records = root / "records"
            events = root / "events"

            with patch.object(store, "MEMORY_RECORDS_DIR", records), \
                 patch.object(store, "MEMORY_EVENTS_DIR", events):

                store.create_memory(
                    memory_type="goal",
                    content="The rider is pursuing a cybersecurity degree.",
                )

                results = retrieve_memories("favorite pizza toppings")

                self.assertEqual(results, [])


if __name__ == "__main__":
    unittest.main()

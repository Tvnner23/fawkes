import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import src.memory.store as store
from src.memory.retrieval import retrieve_memories


class FawkesMemoryRetrievalTests(unittest.TestCase):
    def _directories(self, tmp):
        root = Path(tmp)
        return root / "records", root / "events"

    def test_retrieval_returns_relevant_active_memories(self):
        with tempfile.TemporaryDirectory() as tmp:
            records, events = self._directories(tmp)

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
                self.assertNotEqual(
                    results[0]["memory_id"],
                    unrelated.memory_id,
                )

    def test_degree_query_does_not_substitute_related_career_direction(self):
        with tempfile.TemporaryDirectory() as tmp:
            records, events = self._directories(tmp)
            with patch.object(store, "MEMORY_RECORDS_DIR", records), patch.object(
                store, "MEMORY_EVENTS_DIR", events
            ):
                degree = store.create_memory(
                    memory_type="degree",
                    content="The rider is pursuing a B.S. in Cybersecurity Technology.",
                )
                career = store.create_memory(
                    memory_type="career_direction",
                    content="The rider chose networking as a career direction.",
                )

                results = retrieve_memories("What degree am I pursuing?")

            self.assertTrue(results)
            self.assertEqual(results[0]["memory_id"], degree.memory_id)
            self.assertNotEqual(results[0]["memory_id"], career.memory_id)

    def test_retrieval_excludes_superseded_memories(self):
        with tempfile.TemporaryDirectory() as tmp:
            records, events = self._directories(tmp)

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

                results = retrieve_memories(
                    "What is the current career focus?"
                )

                result_ids = [memory["memory_id"] for memory in results]

                self.assertNotIn(old.memory_id, result_ids)
                self.assertIn(new.memory_id, result_ids)

    def test_retrieval_respects_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            records, events = self._directories(tmp)

            with patch.object(store, "MEMORY_RECORDS_DIR", records), \
                 patch.object(store, "MEMORY_EVENTS_DIR", events):

                for index in range(5):
                    store.create_memory(
                        memory_type="goal",
                        content=(
                            "The rider has a cybersecurity "
                            f"networking goal number {index}."
                        ),
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
            records, events = self._directories(tmp)

            with patch.object(store, "MEMORY_RECORDS_DIR", records), \
                 patch.object(store, "MEMORY_EVENTS_DIR", events):

                store.create_memory(
                    memory_type="goal",
                    content="The rider is pursuing a cybersecurity degree.",
                )

                results = retrieve_memories("favorite pizza toppings")

                self.assertEqual(results, [])

    def test_durable_memory_can_outlive_recency(self):
        with tempfile.TemporaryDirectory() as tmp:
            records, events = self._directories(tmp)

            with patch.object(store, "MEMORY_RECORDS_DIR", records), \
                 patch.object(store, "MEMORY_EVENTS_DIR", events):

                old_goal = store.create_memory(
                    memory_type="goal",
                    content="The rider wants to become a network engineer.",
                    importance=1.0,
                    confidence=1.0,
                )

                recent_note = store.create_memory(
                    memory_type="knowledge",
                    content=(
                        "The rider is currently researching "
                        "network engineer careers."
                    ),
                    importance=0.3,
                    confidence=0.8,
                )

                results = retrieve_memories(
                    "What is the rider's network engineering career goal?"
                )

                self.assertTrue(results)
                self.assertEqual(
                    results[0]["memory_id"],
                    old_goal.memory_id,
                )
                self.assertIn(
                    recent_note.memory_id,
                    [memory["memory_id"] for memory in results],
                )


if __name__ == "__main__":
    unittest.main()

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import src.memory.development_observations as observations


def canonical(instance_id="fawkes-1"):
    return [
        {
            "message_id": "user-1",
            "role": "user",
            "content": "That joke landed perfectly.",
            "instance_id": instance_id,
            "source_archive_id": "archive-user-1",
        },
        {
            "message_id": "fawkes-1",
            "role": "assistant",
            "content": "I may be getting the hang of our particular nonsense.",
            "instance_id": instance_id,
            "source_archive_id": "archive-fawkes-1",
        },
        {
            "message_id": "user-2",
            "role": "user",
            "content": "No, that felt forced this time.",
            "instance_id": instance_id,
            "source_archive_id": "archive-user-2",
        },
    ]


class DevelopmentObservationTests(unittest.TestCase):
    def _storage(self, root):
        return (
            patch.object(observations, "RECORDS_DIR", root / "records"),
            patch.object(observations, "EVENTS_DIR", root / "events"),
            patch.object(observations, "canonical_messages", return_value=canonical()),
        )

    def test_observation_preserves_canonical_conversation_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            patches = self._storage(Path(tmp))
            with patches[0], patches[1], patches[2]:
                record = observations.create_development_observation(
                    instance_id="fawkes-1",
                    category="phoenix_behavior",
                    interpretation="A shared humor pattern may be emerging.",
                    uncertainty="One successful exchange is not yet a stable tendency.",
                    conversation_id="conversation-1",
                    message_ids=("user-1", "fawkes-1"),
                )

        self.assertEqual(record["status"], "tentative")
        self.assertEqual(record["effect"], "observational_only")
        self.assertEqual(
            [item["source_archive_id"] for item in record["evidence"]],
            ["archive-user-1", "archive-fawkes-1"],
        )
        self.assertEqual(record["evidence"][1]["content"], canonical()[1]["content"])
        self.assertNotIn("proposed_change", record)
        self.assertNotIn("confidence", record)

    def test_supporting_and_contradicting_evidence_accumulate(self):
        with tempfile.TemporaryDirectory() as tmp:
            patches = self._storage(Path(tmp))
            with patches[0], patches[1], patches[2]:
                record = observations.create_development_observation(
                    instance_id="fawkes-1",
                    category="relationship_development",
                    interpretation="A shared humor pattern may be emerging.",
                    uncertainty="Tentative and context-dependent.",
                    conversation_id="conversation-1",
                    message_ids=("user-1",),
                )
                record = observations.add_observation_evidence(
                    record["observation_id"],
                    instance_id="fawkes-1",
                    conversation_id="conversation-1",
                    message_ids=("user-2",),
                    relation="contradicting",
                )
                record = observations.revise_observation(
                    record["observation_id"],
                    instance_id="fawkes-1",
                    interpretation="The humor pattern is inconsistent and may be mirroring.",
                    uncertainty="Evidence now points in both directions.",
                    status="contested",
                    reason="The later exchange contradicted the initial reading.",
                )
                history = observations.observation_history(
                    record["observation_id"], instance_id="fawkes-1"
                )

        self.assertEqual([item["relation"] for item in record["evidence"]], ["supporting", "contradicting"])
        self.assertEqual(record["status"], "contested")
        self.assertEqual(
            [event["event_type"] for event in history],
            ["observation_created", "evidence_added", "interpretation_revised"],
        )
        self.assertEqual(
            history[-1]["details"]["previous"]["interpretation"],
            "A shared humor pattern may be emerging.",
        )

    def test_evidence_and_listing_are_strictly_instance_scoped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(observations, "RECORDS_DIR", root / "records"), patch.object(
                observations, "EVENTS_DIR", root / "events"
            ), patch.object(observations, "canonical_messages", return_value=canonical()):
                record = observations.create_development_observation(
                    instance_id="fawkes-1",
                    category="system_defect",
                    interpretation="A response may expose an infrastructure defect.",
                    uncertainty="The cause has not been reproduced.",
                    conversation_id="conversation-1",
                    message_ids=("fawkes-1",),
                )
                self.assertEqual(len(observations.list_development_observations(instance_id="fawkes-1")), 1)
                self.assertEqual(observations.list_development_observations(instance_id="sibling-2"), [])
                self.assertIsNone(observations.get_development_observation(record["observation_id"], instance_id="sibling-2"))
                with patch.object(observations, "canonical_messages", return_value=canonical("sibling-2")):
                    with self.assertRaisesRegex(ValueError, "does not belong"):
                        observations.add_observation_evidence(
                            record["observation_id"],
                            instance_id="fawkes-1",
                            conversation_id="sibling-conversation",
                            message_ids=("user-1",),
                            relation="supporting",
                        )

    def test_all_required_categories_exist_without_trait_dimensions(self):
        self.assertTrue(
            {"observed_response_pattern", "phoenix_behavior", "relationship_development", "system_defect", "base_phoenix_candidate"}.issubset(
                observations.OBSERVATION_CATEGORIES
            )
        )
        self.assertNotIn("established", observations.OBSERVATION_STATUSES)

    def test_response_pattern_keeps_rider_signal_separate_from_phoenix_interpretation(self):
        with tempfile.TemporaryDirectory() as tmp:
            patches = self._storage(Path(tmp))
            with patches[0], patches[1], patches[2]:
                record = observations.create_development_observation(
                    instance_id="fawkes-1",
                    category="observed_response_pattern",
                    interpretation="The response used substantial paraphrasing.",
                    observed_pattern="Conversational mirroring/paraphrasing",
                    rider_evaluation="undesired",
                    rider_reason="It felt like being copied by a robot.",
                    development_signal="discourage",
                    longitudinal_status="isolated",
                    confidence_state="tentative",
                    uncertainty="One observed interaction.",
                    conversation_id="conversation-1",
                    message_ids=("user-1", "fawkes-1"),
                    observed_by="rider",
                )

        self.assertEqual(record["observed_pattern"], "Conversational mirroring/paraphrasing")
        self.assertEqual(record["rider_evaluation"], "undesired")
        self.assertEqual(record["development_signal"], "discourage")
        self.assertEqual(record["longitudinal_status"], "isolated")
        self.assertEqual(record["confidence_state"], "tentative")
        self.assertIsNone(record["phoenix_interpretation"])
        self.assertEqual(record["effect"], "observational_only")
        self.assertNotIn("personality_change", record)

    def test_dimension_revision_is_audited_and_does_not_reclassify_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            patches = self._storage(Path(tmp))
            with patches[0], patches[1], patches[2]:
                record = observations.create_development_observation(
                    instance_id="fawkes-1",
                    category="phoenix_behavior",
                    interpretation="Mirroring may be developing behavior.",
                    uncertainty="One interaction.",
                    conversation_id="conversation-1",
                    message_ids=("user-1", "fawkes-1"),
                    observed_by="rider",
                )
                evidence_before = record["evidence"]
                record = observations.revise_observation_dimensions(
                    record["observation_id"],
                    instance_id="fawkes-1",
                    category="observed_response_pattern",
                    observed_pattern="Conversational mirroring/paraphrasing",
                    rider_evaluation="undesired",
                    rider_reason="It felt robotic rather than individual.",
                    development_signal="discourage",
                    longitudinal_status="isolated",
                    confidence_state="tentative",
                    reason="A witnessed response is not by itself a personality tendency.",
                )
                history = observations.observation_history(
                    record["observation_id"], instance_id="fawkes-1"
                )

        self.assertEqual(record["evidence"], evidence_before)
        self.assertEqual(record["category"], "observed_response_pattern")
        self.assertIsNone(record["phoenix_interpretation"])
        self.assertEqual(record["effect"], "observational_only")
        self.assertEqual(history[-1]["event_type"], "observation_dimensions_revised")
        self.assertEqual(history[-1]["details"]["previous"]["category"], "phoenix_behavior")
        self.assertEqual(
            history[-1]["details"]["current"]["development_signal"], "discourage"
        )

    def test_structured_observer_attribution_preserves_future_peer_boundary(self):
        with tempfile.TemporaryDirectory() as tmp:
            patches = self._storage(Path(tmp))
            with patches[0], patches[1], patches[2]:
                rider = observations.create_development_observation(
                    instance_id="fawkes-1",
                    category="observed_response_pattern",
                    interpretation="A response pattern was observed.",
                    uncertainty="One interaction.",
                    conversation_id="conversation-1",
                    message_ids=("fawkes-1",),
                    observed_by="rider",
                )
                with self.assertRaisesRegex(ValueError, "consent context"):
                    observations.create_development_observation(
                        instance_id="fawkes-1",
                        category="relationship_development",
                        interpretation="A peer noticed a pattern.",
                        uncertainty="Peer interpretation is tentative.",
                        conversation_id="conversation-1",
                        message_ids=("fawkes-1",),
                        observed_by="peer",
                        observer_attribution={
                            "actor_type": "peer_phoenix",
                            "actor_id": "sibling-2",
                            "phoenix_instance_id": "sibling-2",
                        },
                    )

        self.assertEqual(rider["observer_attribution"]["actor_type"], "rider")
        self.assertIsNone(rider["observer_attribution"]["phoenix_instance_id"])
        self.assertNotIn("score", rider["observer_attribution"])

    def test_progression_is_read_only_chronology_scoped_to_one_phoenix(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(observations, "RECORDS_DIR", root / "records"), patch.object(
                observations, "EVENTS_DIR", root / "events"
            ), patch.object(observations, "canonical_messages", return_value=canonical()):
                record = observations.create_development_observation(
                    instance_id="fawkes-1",
                    category="phoenix_behavior",
                    interpretation="A tendency may be emerging.",
                    uncertainty="Only one exchange supports it.",
                    conversation_id="conversation-1",
                    message_ids=("fawkes-1",),
                )
                before = (root / "records" / f"{record['observation_id']}.json").read_bytes()
                progression = observations.development_progression(instance_id="fawkes-1")
                sibling = observations.development_progression(instance_id="sibling-2")
                after = (root / "records" / f"{record['observation_id']}.json").read_bytes()

        self.assertEqual(len(progression), 1)
        self.assertEqual(progression[0]["event_type"], "observation_created")
        self.assertEqual(sibling, [])
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()

import unittest

from src.memory.taxonomy import (
    MEMORY_TYPES,
    RELATIONSHIP_TYPES,
    TEMPORAL_STATES,
    all_memory_types,
    all_relationship_types,
    all_temporal_states,
    is_valid_memory_type,
    is_valid_relationship_type,
    is_valid_temporal_state,
)


class FawkesMemoryTaxonomyTests(unittest.TestCase):
    def test_memory_types_are_extensible(self):
        self.assertIn("user_fact", MEMORY_TYPES)
        self.assertIn("personality_development", MEMORY_TYPES)
        self.assertIn("self_history", MEMORY_TYPES)

    def test_education_and_career_concepts_are_distinct_types(self):
        self.assertIn("education_institution", MEMORY_TYPES)
        self.assertIn("degree", MEMORY_TYPES)
        self.assertIn("career_direction", MEMORY_TYPES)
        self.assertIn("career_goal", MEMORY_TYPES)
        self.assertEqual(
            len(
                {
                    "education_institution",
                    "degree",
                    "career_direction",
                    "career_goal",
                }
            ),
            4,
        )

    def test_relationship_types_exist(self):
        self.assertIn("supports", RELATIONSHIP_TYPES)
        self.assertIn("contradicts", RELATIONSHIP_TYPES)
        self.assertIn("supersedes", RELATIONSHIP_TYPES)
        self.assertIn("same_concept_as", RELATIONSHIP_TYPES)

    def test_temporal_states_exist(self):
        self.assertIn("current", TEMPORAL_STATES)
        self.assertIn("historical", TEMPORAL_STATES)
        self.assertIn("superseded", TEMPORAL_STATES)

    def test_validation(self):
        self.assertTrue(is_valid_memory_type("goal"))
        self.assertFalse(is_valid_memory_type("not_a_real_memory_type"))

        self.assertTrue(is_valid_relationship_type("supports"))
        self.assertFalse(is_valid_relationship_type("not_a_relationship"))

        self.assertTrue(is_valid_temporal_state("current"))
        self.assertFalse(is_valid_temporal_state("not_a_temporal_state"))

    def test_catalog_functions_match_definitions(self):
        self.assertEqual(
            set(all_memory_types()),
            set(MEMORY_TYPES),
        )

        self.assertEqual(
            set(all_relationship_types()),
            set(RELATIONSHIP_TYPES),
        )

        self.assertEqual(
            set(all_temporal_states()),
            set(TEMPORAL_STATES),
        )


if __name__ == "__main__":
    unittest.main()


class FawkesRelationshipMemoryTaxonomyTests(unittest.TestCase):
    def test_relationship_memory_types_exist(self):
        from src.memory.taxonomy import all_memory_types

        catalog = all_memory_types()

        self.assertIn("inside_joke", catalog)
        self.assertIn("shared_reference", catalog)
        self.assertIn("relationship_moment", catalog)


if __name__ == "__main__":
    unittest.main()

import unittest

from src.runtime.expression import (
    EXPRESSION_LAYER_REPLACEMENT_TARGET,
    EXPRESSION_LAYER_STATUS,
    SHUTDOWN_SIGNOFFS,
    STARTUP_GREETINGS,
    shutdown_signoff,
    startup_greeting,
)


class FawkesRuntimeExpressionTests(unittest.TestCase):
    def test_expression_layer_is_declared_temporary_and_replaceable(self):
        self.assertEqual(EXPRESSION_LAYER_STATUS, "temporary_placeholder")
        self.assertEqual(
            EXPRESSION_LAYER_REPLACEMENT_TARGET,
            "developed_personality_expression",
        )

    def test_startup_expression_uses_small_bounded_pool(self):
        selected = startup_greeting(chooser=lambda options: options[1])

        self.assertEqual(selected, STARTUP_GREETINGS[1])
        self.assertGreaterEqual(len(STARTUP_GREETINGS), 2)
        self.assertLessEqual(len(STARTUP_GREETINGS), 8)

    def test_until_next_time_remains_an_available_signoff(self):
        self.assertIn("Until next time.", SHUTDOWN_SIGNOFFS)
        selected = shutdown_signoff(chooser=lambda options: options[0])
        self.assertEqual(selected, "Until next time.")

    def test_expression_pool_contains_no_context_or_memory_claims(self):
        for expression in (*STARTUP_GREETINGS, *SHUTDOWN_SIGNOFFS):
            lowered = expression.lower()
            self.assertNotIn("remember", lowered)
            self.assertNotIn("last time", lowered)
            self.assertNotIn("we were working", lowered)


if __name__ == "__main__":
    unittest.main()

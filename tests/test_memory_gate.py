import unittest

from src.memory.gate import looks_like_artifact


class FawkesMemoryGateTests(unittest.TestCase):

    def test_single_terminal_command_is_artifact(self):
        self.assertTrue(looks_like_artifact("git status"))

    def test_single_console_output_is_artifact(self):
        self.assertTrue(looks_like_artifact("undefined"))

    def test_normal_human_message_is_not_artifact(self):
        self.assertFalse(
            looks_like_artifact(
                "remember we always need to build it so we can come back and add or fix later on"
            )
        )

    def test_multiline_human_message_with_command_is_preserved(self):
        self.assertFalse(
            looks_like_artifact(
                "I want Fawkes to stay modular.\n"
                "git status\n"
                "The whole point is that we can keep adding things later."
            )
        )

    def test_multiline_pure_artifact_is_removed(self):
        self.assertTrue(
            looks_like_artifact(
                "git status\n"
                "python -m unittest\n"
                "undefined"
            )
        )

    def test_empty_text_is_artifact(self):
        self.assertTrue(looks_like_artifact(""))


if __name__ == "__main__":
    unittest.main()

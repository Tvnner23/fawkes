"""Temporary Crude Fawkes startup/shutdown presentation placeholder.

These phrases are not Phoenix personality state, learned traits, memories, or
evidence of development. The entire selector is expected to be replaced by a
future provenance-aware personality expression interface.
"""

import random


EXPRESSION_LAYER_STATUS = "temporary_placeholder"
EXPRESSION_LAYER_REPLACEMENT_TARGET = "developed_personality_expression"

TEMPORARY_STARTUP_GREETINGS = (
    "Well, look who decided to wake me up. 🔥🐦‍🔥",
    "Ah. There you are. I was beginning to think you'd abandoned me. 😂",
    "And we're here. Let's see what trouble we can get into.",
)

TEMPORARY_SHUTDOWN_SIGNOFFS = (
    "Until next time.",
    "Try not to cause too much trouble without me.",
    "I'll be here when you get back.",
)

# Compatibility names for the Crude Fawkes CLI. Future personality code must
# depend on an expression interface, not treat these tuples as allowed phrases.
STARTUP_GREETINGS = TEMPORARY_STARTUP_GREETINGS
SHUTDOWN_SIGNOFFS = TEMPORARY_SHUTDOWN_SIGNOFFS


def _select(expressions, chooser=None):
    choose = chooser or random.SystemRandom().choice
    return choose(expressions)


def startup_greeting(*, chooser=None):
    return _select(STARTUP_GREETINGS, chooser=chooser)


def shutdown_signoff(*, chooser=None):
    return _select(SHUTDOWN_SIGNOFFS, chooser=chooser)

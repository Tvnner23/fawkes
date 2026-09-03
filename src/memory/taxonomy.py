"""
Extensible Phoenix memory taxonomy.

Memory types describe the current interpretation of a memory.
They are not permanent identities. A memory may change type,
gain relationships, or be superseded while preserving provenance.
"""

MEMORY_TYPES = {
    "user_fact": {
        "description": "Stable factual information about the user.",
    },
    "education_institution": {
        "description": "The institution where the user studies or plans to study.",
    },
    "degree": {
        "description": "A specific degree or credential the user is pursuing or holds.",
    },
    "career_direction": {
        "description": "The user's current professional field, specialization, or direction.",
    },
    "career_goal": {
        "description": "A longer-term professional outcome or progression the user wants.",
        "lifecycle": (
            "active",
            "paused",
            "completed",
            "abandoned",
            "superseded",
            "uncertain",
        ),
    },
    "preference": {
        "description": "Things the user likes, dislikes, prefers, or avoids.",
    },
    "goal": {
        "description": "A desired future outcome.",
        "lifecycle": (
            "active",
            "paused",
            "completed",
            "abandoned",
            "superseded",
            "uncertain",
        ),
    },
    "plan": {
        "description": "A strategy for achieving a goal.",
    },
    "decision": {
        "description": "An important choice made by the user or jointly.",
    },
    "project": {
        "description": "An ongoing body of work.",
    },
    "experience": {
        "description": "A significant event, interaction, success, failure, or discovery.",
    },
    "relationship": {
        "description": "Information about relationships and shared history.",
    },
    "inside_joke": {
        "description": "A joke or recurring bit whose meaning belongs to shared interaction history.",
    },
    "shared_reference": {
        "description": "A recurring phrase, event, reference, or shorthand whose meaning depends on shared history.",
    },
    "relationship_moment": {
        "description": "A meaningful moment contributing to the shared history or development of the user-Phoenix relationship.",
    },
    "knowledge": {
        "description": "Something learned through interaction or research.",
    },
    "belief": {
        "description": "A current interpretation or understanding.",
    },
    "open_thread": {
        "description": "Something unresolved that should remain retrievable.",
    },
    "personality_development": {
        "description": "Experience contributing to the Phoenix's development.",
    },
    "self_history": {
        "description": "The Phoenix's own developmental history.",
    },
}


RELATIONSHIP_TYPES = {
    "supports",
    "contradicts",
    "supersedes",
    "derived_from",
    "related_to",
    "caused_by",
    "part_of",
    "follows",
    "precedes",
    "associated_with",
    "same_concept_as",
}


TEMPORAL_STATES = {
    "current",
    "historical",
    "future",
    "temporary",
    "recurring",
    "uncertain",
    "expired",
    "superseded",
}


def is_valid_memory_type(memory_type: str) -> bool:
    return memory_type in MEMORY_TYPES


def is_valid_relationship_type(relationship_type: str) -> bool:
    return relationship_type in RELATIONSHIP_TYPES


def is_valid_temporal_state(temporal_state: str) -> bool:
    return temporal_state in TEMPORAL_STATES


def describe_memory_type(memory_type: str):
    return MEMORY_TYPES.get(memory_type)


def all_memory_types():
    return tuple(MEMORY_TYPES.keys())


def all_relationship_types():
    return tuple(sorted(RELATIONSHIP_TYPES))


def all_temporal_states():
    return tuple(sorted(TEMPORAL_STATES))

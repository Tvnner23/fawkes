class SemanticMemoryRetriever:
    """
    Provider-independent interface for retrieving memories by meaning.

    Candidate generation remains local and cheap. The provider is used only
    to rank the supplied candidates semantically.
    """

    def __init__(self, provider):
        self.provider = provider

    def rank(
        self,
        *,
        query,
        memories,
        limit=8,
    ):
        if not memories:
            return []

        results = self.provider.rank_memories(
            query=query,
            memories=tuple(memories),
        )

        if not isinstance(results, (list, tuple)):
            raise TypeError(
                "Semantic memory retrieval provider must return "
                "a list or tuple"
            )

        return list(results)[:limit]

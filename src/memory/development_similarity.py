class DevelopmentSimilarity:
    """
    Provider-independent contract for finding development experiences
    that are conceptually related to a new experience.
    """

    def __init__(self, provider):
        self.provider = provider

    def rank(
        self,
        *,
        experience,
        proposals,
        limit=5,
    ):
        if not proposals:
            return []

        results = self.provider.rank_development(
            experience=experience,
            proposals=tuple(proposals),
        )

        if not isinstance(results, (list, tuple)):
            raise TypeError(
                "Development similarity provider must return a list or tuple"
            )

        return list(results)[:limit]

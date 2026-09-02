"""Provider- and client-neutral registry of installed visual communication formats."""

from dataclasses import dataclass

from src.capabilities.core import CapabilityDefinition
from src.capabilities.multimodal import AuthorityContract, MultimodalCapabilityContract


VISUAL_CATEGORIES = {
    "structured_data", "data_visualization", "structural_diagram",
    "temporal_visualization", "technical_diagram", "educational_visualization",
}


@dataclass(frozen=True)
class VisualizationFormat:
    name: str
    category: str
    data_contract: str

    def __post_init__(self):
        if not self.name or self.category not in VISUAL_CATEGORIES or not self.data_contract:
            raise ValueError("invalid visualization format")


class VisualizationRegistry:
    def __init__(self):
        self._formats = {}

    def register(self, definition):
        if not isinstance(definition, VisualizationFormat):
            raise TypeError("definition must be a VisualizationFormat")
        if definition.name in self._formats:
            raise ValueError(f"visualization format already registered: {definition.name}")
        self._formats[definition.name] = definition

    def resolve(self, name):
        try:
            return self._formats[name]
        except KeyError as exc:
            raise ValueError(f"unsupported visualization format: {name}") from exc

    def names(self):
        return tuple(self._formats)

    def manifest(self):
        return tuple({
            "name": item.name, "category": item.category,
            "data_contract": item.data_contract,
        } for item in self._formats.values())


def default_visualization_registry():
    registry = VisualizationRegistry()
    for name, category, contract in (
        ("table", "structured_data", "columns_rows"),
        ("flow", "structural_diagram", "nodes_edges"),
        ("bar", "data_visualization", "labeled_series"),
        ("grouped_bar", "data_visualization", "aligned_labeled_series"),
        ("stacked_bar", "data_visualization", "aligned_nonnegative_series"),
        ("line", "data_visualization", "ordered_labeled_series"),
        ("area", "data_visualization", "ordered_labeled_series"),
        ("pie", "data_visualization", "single_nonnegative_series"),
        ("donut", "data_visualization", "single_nonnegative_series"),
        ("scatter", "data_visualization", "xy_series"),
        ("timeline", "temporal_visualization", "ordered_events"),
    ):
        registry.register(VisualizationFormat(name, category, contract))
    return registry


DEFAULT_VISUALIZATION_REGISTRY = default_visualization_registry()

VISUALIZATION_CAPABILITY = CapabilityDefinition(
    name="presentation.visualize", version="2.0",
    description="Choose and produce validated accessible visual communication when it improves understanding.",
    effect="derived_presentation",
    modalities=MultimodalCapabilityContract(
        input_modalities=("text", "chart", "diagram"),
        output_modalities=("text", "chart", "diagram"),
    ),
    authority=AuthorityContract(
        actions=("analyze", "create"), execution_boundary="internal",
        authorization_mode="pre_granted",
    ),
    privacy_handling="inherits_source_provenance_no_new_storage",
    features=DEFAULT_VISUALIZATION_REGISTRY.names(),
    display_name="Visual communication",
    appropriate_use=("explicit supported visual request", "comparison", "trend", "part-to-whole", "correlation", "process", "chronology"),
    inappropriate_use=("decoration that does not improve comprehension", "data is unavailable or would need to be invented", "ordinary prose is clearer"),
    limitations=("at most four visual blocks per response", "only registered formats render", "factual charts require rider-supplied or sourced numeric data"),
    presentation_options=("table", "diagram", "timeline", "bar", "grouped_bar", "stacked_bar", "line", "area", "pie", "donut", "scatter"),
    provenance_requirements=("canonical text fallback", "source URLs for researched data", "label estimates and illustrative values"),
)

"""Ensure explicit rider visualization requests reach validated presentation output."""

from dataclasses import dataclass
import json
import re

from src.presentation.registry import DEFAULT_VISUALIZATION_REGISTRY


_COUNT_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4}
_FORMAT_PATTERNS = (
    ("grouped_bar", r"\bgrouped\s+bar\b"),
    ("stacked_bar", r"\bstacked\s+bar\b"),
    ("donut", r"\bdonut\b"),
    ("pie", r"\bpie\b"),
    ("scatter", r"\bscatter(?:\s+plot)?\b"),
    ("area", r"\barea\s+chart\b"),
    ("line", r"\bline\s+(?:chart|graph)\b"),
    ("bar", r"\bbar\s+(?:chart|graph)\b"),
    ("timeline", r"\btimeline\b"),
    ("flow", r"\bflow\s*chart\b"),
    ("flow", r"\b(?:network|architecture|sequence|state|decision tree)(?:\s+diagram)?\b"),
    ("flow", r"\bdiagram\b"),
    ("bubble", r"\bbubble\s+chart\b"),
    ("histogram", r"\bhistogram\b"),
    ("box_plot", r"\bbox\s+plot\b"),
    ("violin", r"\bviolin\s+plot\b"),
    ("heatmap", r"\bheat\s*map\b"),
    ("radar", r"\b(?:radar|spider)\s+chart\b"),
    ("waterfall", r"\bwaterfall\s+chart\b"),
    ("funnel", r"\bfunnel\s+chart\b"),
    ("treemap", r"\btreemap\b"),
    ("gauge", r"\bgauge\s+chart\b"),
    ("gantt", r"\bgantt\b"),
    ("sankey", r"\bsankey\b"),
    ("map", r"\b(?:geographic\s+)?map\b"),
)
_ACTION = re.compile(
    r"\b(make|create|draw|plot|graph|visuali[sz]e|show|turn)\b|^\s*(?:chart|diagram)\s+(?:this|that|it)\b",
    re.IGNORECASE,
)
_VISUAL_NOUN = re.compile(
    r"\b(chart|charts|graph|graphs|plot|plots|diagram|diagrams|flowchart|timeline|"
    r"visual|visually|network|histogram|heatmap|treemap|gantt|sankey|map)\b",
    re.IGNORECASE,
)
_COUNT = re.compile(
    r"\b(1|2|3|4|one|two|three|four)\s+(?:separate\s+|different\s+)?"
    r"(?:charts?|graphs?|plots?|diagrams?|visuals?|visualizations?)\b",
    re.IGNORECASE,
)
_FOLLOWUP = re.compile(
    r"\b(?:try|do|make|show)(?:\s+(?:it|that|them|those|the\s+charts?))?\s+again\b|"
    r"\bagain\s+for\s+me\b|\b(?:do(?:n['’]?t| not)|can(?:n['’]?t| not))\s+see\b|"
    r"\bnothing\s+(?:showed|rendered|appeared)\b|\bnot\s+(?:showing|rendering)\b|"
    r"\bonly\s+described\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class VisualizationIntent:
    explicit: bool
    count: int = 0
    requested_block_type: str | None = None
    requested_formats: tuple[str, ...] = ()
    unavailable_formats: tuple[str, ...] = ()

    def as_dict(self):
        return {
            "explicit": self.explicit,
            "count": self.count,
            "requested_block_type": self.requested_block_type,
            "requested_formats": list(self.requested_formats),
            "unavailable_formats": list(self.unavailable_formats),
        }


def detect_visualization_intent(message, *, conversation_context=(), registry=None):
    """Detect an explicit rider request, not a passing mention of a visual."""
    registry = registry or DEFAULT_VISUALIZATION_REGISTRY
    text = str(message or "")
    explicit = bool(_ACTION.search(text) and _VISUAL_NOUN.search(text))
    if not explicit:
        if _FOLLOWUP.search(text):
            for item in reversed(tuple(conversation_context)[-8:]):
                if not isinstance(item, dict) or item.get("role") != "user":
                    continue
                inherited = detect_visualization_intent(
                    item.get("content", ""), conversation_context=(), registry=registry
                )
                if inherited.explicit:
                    return inherited
        return VisualizationIntent(False)
    count_match = _COUNT.search(text)
    if count_match:
        raw = count_match.group(1).lower()
        count = int(raw) if raw.isdigit() else _COUNT_WORDS[raw]
    else:
        count = 1
    requested = []
    for name, pattern in _FORMAT_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE) and name not in requested:
            requested.append(name)
    installed = set(registry.names())
    unavailable = tuple(name for name in requested if name not in installed)
    if re.search(r"\b(?:charts?|graphs?|plots?)\b", text, re.IGNORECASE):
        block_type = "chart"
    elif re.search(r"\b(?:diagrams?|flow\s*charts?|network)\b", text, re.IGNORECASE):
        block_type = "diagram"
    elif re.search(r"\btimeline\b", text, re.IGNORECASE):
        block_type = "timeline"
    else:
        block_type = None
    return VisualizationIntent(
        True, min(4, count), block_type,
        tuple(name for name in requested if name in installed), unavailable
    )


def visualization_fulfillment(intent, blocks):
    if not intent.explicit:
        return {"status": "not_requested", "requested": intent.as_dict()}
    rendered = []
    for block in blocks:
        if block.get("type") == "chart":
            rendered.append(block.get("chart_type"))
        elif block.get("type") == "diagram":
            rendered.append("flow")
        else:
            rendered.append(block.get("type"))
    missing = [name for name in intent.requested_formats if name not in rendered]
    eligible = [block for block in blocks if (
        intent.requested_block_type is None or block.get("type") == intent.requested_block_type
    )]
    if intent.unavailable_formats:
        status = "unsupported"
    elif len(eligible) >= intent.count and not missing:
        status = "fulfilled"
    else:
        status = "incomplete"
    return {
        "status": status,
        "requested": intent.as_dict(),
        "rendered_count": len(blocks),
        "matching_block_count": len(eligible),
        "rendered_formats": rendered,
        "missing_formats": missing,
    }


class OpenAIPresentationPlanner:
    """One provider adapter; the orchestration contract remains provider-neutral."""

    def __init__(self, *, client, model, timeout_seconds=30):
        self.client, self.model = client, model
        self.timeout_seconds = float(timeout_seconds)

    def create_blocks(self, *, intent, user_message, conversation_context, draft_answer,
                      approved_source_urls):
        count = max(1, min(4, intent.count))
        block_types = [intent.requested_block_type] if intent.requested_block_type else [
            "chart", "diagram", "timeline", "table"
        ]
        point = {
            "type": "object", "additionalProperties": False,
            "required": ["label", "value", "x", "y"],
            "properties": {
                "label": {"type": "string"},
                "value": {"type": ["number", "null"]},
                "x": {"type": ["number", "null"]},
                "y": {"type": ["number", "null"]},
            },
        }
        schema = {
            "type": "object", "additionalProperties": False,
            "required": ["blocks"],
            "properties": {"blocks": {
                "type": "array", "minItems": count, "maxItems": count,
                "items": {
                    "type": "object", "additionalProperties": False,
                    "required": [
                        "type", "title", "caption", "fallback", "source_scope",
                        "source_urls", "columns", "rows", "direction", "nodes",
                        "edges", "chart_type", "x_label", "y_label", "series", "items",
                    ],
                    "properties": {
                        "type": {"type": "string", "enum": block_types},
                        "title": {"type": "string"}, "caption": {"type": "string"},
                        "fallback": {"type": "string"},
                        "source_scope": {"type": "string", "enum": ["research", "user_supplied", "reasoning", "illustrative"]},
                        "source_urls": {"type": "array", "items": {"type": "string"}},
                        "columns": {"type": "array", "items": {"type": "string"}},
                        "rows": {"type": "array", "items": {"type": "array", "items": {"type": "string"}}},
                        "direction": {"type": "string", "enum": ["vertical", "horizontal"]},
                        "nodes": {"type": "array", "items": {
                            "type": "object", "additionalProperties": False,
                            "required": ["id", "label"], "properties": {
                                "id": {"type": "string"}, "label": {"type": "string"},
                            },
                        }},
                        "edges": {"type": "array", "items": {
                            "type": "object", "additionalProperties": False,
                            "required": ["from", "to", "label"], "properties": {
                                "from": {"type": "string"}, "to": {"type": "string"}, "label": {"type": "string"},
                            },
                        }},
                        "chart_type": {"type": "string", "enum": [
                            "bar", "grouped_bar", "stacked_bar", "line", "area", "pie", "donut", "scatter"
                        ]},
                        "x_label": {"type": "string"}, "y_label": {"type": "string"},
                        "series": {"type": "array", "items": {
                            "type": "object", "additionalProperties": False,
                            "required": ["name", "points"], "properties": {
                                "name": {"type": "string"},
                                "points": {"type": "array", "items": point},
                            },
                        }},
                        "items": {"type": "array", "items": {
                            "type": "object", "additionalProperties": False,
                            "required": ["date", "label", "detail"], "properties": {
                                "date": {"type": "string"}, "label": {"type": "string"}, "detail": {"type": "string"},
                            },
                        }},
                    },
                },
            }},
        }
        response = self.client.responses.create(
            model=self.model,
            timeout=self.timeout_seconds,
            store=False,
            input=[{
                "role": "system",
                "content": (
                    "Create the complete set of missing validated Fawkes presentation blocks for an explicit "
                    "rider request. Produce exactly the requested number (maximum four) and honor every "
                    "requested installed format. Supported formats and contracts are supplied below. "
                    "Use research scope only with an approved URL; use user_supplied only for values "
                    "present in rider-authored evidence. Values created by Fawkes in a draft or prior "
                    "assistant message are not rider-supplied. For deliberately playful, hypothetical, "
                    "or explanatory made-up values, use source_scope illustrative and make the title, "
                    "caption, and fallback explicitly say the values are illustrative—not measured facts. "
                    "Never use illustrative scope to imply current or factual measurements. Every block "
                    "needs type, title, fallback, caption, source_scope, and source_urls. Charts use "
                    "chart_type and series. Flow diagrams use sequential nodes/edges. Timelines use items. "
                    "When the rider asks generally, choose bar for ranking/comparison, line for change over time, "
                    "pie or donut only for a defensible part-to-whole composition, scatter for paired numeric "
                    "relationships, flow for a process or structure, timeline for chronology, and table when exact "
                    "repeated fields matter more than shape. An explicit supported format overrides this heuristic. "
                    "Do not emit HTML, JavaScript, SVG, CSS, or Mermaid."
                ),
            }, {
                "role": "user",
                "content": (
                    f"Request contract: {json.dumps(intent.as_dict())}\n"
                    "Installed formats: table, flow, bar, grouped_bar, stacked_bar, line, area, "
                    "pie, donut, scatter, timeline.\n"
                    f"Approved research URLs: {json.dumps(list(approved_source_urls))}\n"
                    f"Recent conversation: {conversation_context}\n"
                    f"Rider request: {user_message}\n"
                    f"Draft answer: {draft_answer}"
                ),
            }],
            text={"format": {
                "type": "json_schema", "name": "fawkes_presentation_blocks",
                "strict": True, "schema": schema,
            }},
        )
        value = getattr(response, "output_text", None)
        if not isinstance(value, str) or not value.strip():
            raise ValueError("presentation planner returned no blocks")
        if value.lstrip().startswith("```fawkes-presentation"):
            # Provider-neutral test/custom planners may already return the
            # validated transport form. The OpenAI adapter normally uses the
            # strict JSON schema below.
            return value.strip()
        payload = json.loads(value)
        clean = []
        for raw in payload["blocks"]:
            block = {key: raw[key] for key in (
                "type", "title", "caption", "fallback", "source_scope", "source_urls"
            )}
            if raw["type"] == "chart":
                block.update({key: raw[key] for key in ("chart_type", "x_label", "y_label")})
                block["series"] = []
                for series in raw["series"]:
                    if raw["chart_type"] == "scatter":
                        points = [{"label": item["label"], "x": item["x"], "y": item["y"]} for item in series["points"]]
                    else:
                        points = [{"label": item["label"], "value": item["value"]} for item in series["points"]]
                    block["series"].append({"name": series["name"], "points": points})
            elif raw["type"] == "diagram":
                block.update(direction=raw["direction"], nodes=raw["nodes"], edges=raw["edges"])
            elif raw["type"] == "timeline":
                block["items"] = raw["items"]
            else:
                block.update(columns=raw["columns"], rows=raw["rows"])
            clean.append(block)
        return "```fawkes-presentation\n" + json.dumps(clean, ensure_ascii=False) + "\n```"

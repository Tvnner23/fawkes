"""Validate model-requested presentation without accepting executable markup."""

from math import isfinite
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
import json
import re

from src.capabilities.research_orchestrator import approved_research_urls
from src.presentation.registry import DEFAULT_VISUALIZATION_REGISTRY


PRESENTATION_VERSION = 2
MAX_BLOCKS = 4
MAX_TABLE_ROWS = 30
MAX_CHART_POINTS = 60
_BLOCK = re.compile(r"```fawkes-presentation\s*\n(?P<body>.*?)\n```", re.DOTALL | re.IGNORECASE)
_MARKDOWN_LINK = re.compile(r"\[([^\]]{1,180})\]\((https?://[^)\s]+)\)")
_SAFE_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,39}$")
_TRACKING_KEYS = {"fbclid", "gclid", "mc_cid", "mc_eid", "msclkid"}


def clean_display_url(url):
    """Remove known tracking parameters while retaining provenance separately."""
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise ValueError("presentation links must be http or https URLs")
    query = [
        (key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in _TRACKING_KEYS
    ]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _text(value, *, maximum=600, required=True):
    if not isinstance(value, str):
        raise ValueError("presentation text must be a string")
    value = value.strip()
    if required and not value:
        raise ValueError("presentation text is required")
    if len(value) > maximum:
        raise ValueError("presentation text is too long")
    return value


def _sources(raw_sources, approved):
    if not isinstance(raw_sources, list):
        raise ValueError("presentation source_urls must be a list")
    sources = []
    display_equivalents = {}
    for approved_url in approved:
        try: display_equivalents.setdefault(clean_display_url(approved_url), approved_url)
        except ValueError: continue
    for url in raw_sources:
        canonical = url if isinstance(url, str) and url in approved else (
            display_equivalents.get(clean_display_url(url)) if isinstance(url, str) else None
        )
        if not canonical:
            raise ValueError("presentation source is not approved research provenance")
        if canonical not in sources:
            sources.append(canonical)
    return sources


def _base(raw, approved):
    if not isinstance(raw, dict) or raw.get("type") not in {"table", "diagram", "chart", "timeline"}:
        raise ValueError("unsupported presentation block")
    allowed = {
        "type", "title", "caption", "fallback", "source_scope", "source_urls",
        "columns", "rows", "direction", "nodes", "edges", "chart_type",
        "x_label", "y_label", "series",
        "items",
    }
    unsupported = sorted(set(raw) - allowed)
    if unsupported:
        raise ValueError(
            "presentation block contains unsupported fields: " + ", ".join(unsupported)
        )
    scope = raw.get("source_scope", "reasoning")
    if scope not in {"research", "user_supplied", "reasoning", "illustrative"}:
        raise ValueError("invalid presentation source scope")
    source_urls = _sources(raw.get("source_urls", []), approved)
    if scope == "research" and not source_urls:
        raise ValueError("research-derived visuals require approved source URLs")
    if scope == "illustrative" and source_urls:
        raise ValueError("illustrative visuals cannot claim research sources")
    return {
        "type": raw["type"], "title": _text(raw.get("title", ""), maximum=160),
        "caption": _text(raw.get("caption", ""), maximum=400, required=False),
        "fallback": _text(raw.get("fallback", ""), maximum=1200),
        "source_scope": scope, "source_urls": source_urls,
    }


def _validate_table(raw, block):
    columns, rows = raw.get("columns"), raw.get("rows")
    if not isinstance(columns, list) or not 2 <= len(columns) <= 8:
        raise ValueError("tables require two to eight columns")
    columns = [_text(item, maximum=80) for item in columns]
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_TABLE_ROWS:
        raise ValueError("table row count is outside the safe limit")
    clean_rows = []
    for row in rows:
        if not isinstance(row, list) or len(row) != len(columns):
            raise ValueError("table rows must match the column count")
        clean_rows.append([_text(str(item), maximum=240, required=False) for item in row])
    return {**block, "columns": columns, "rows": clean_rows}


def _validate_diagram(raw, block):
    nodes, edges = raw.get("nodes"), raw.get("edges")
    if not isinstance(nodes, list) or not 2 <= len(nodes) <= 12:
        raise ValueError("diagrams require two to twelve nodes")
    clean_nodes, ids = [], set()
    for node in nodes:
        if not isinstance(node, dict) or set(node) != {"id", "label"}:
            raise ValueError("diagram nodes require only id and label")
        node_id = node["id"]
        if not isinstance(node_id, str) or not _SAFE_ID.fullmatch(node_id) or node_id in ids:
            raise ValueError("diagram node ID is invalid or duplicated")
        ids.add(node_id)
        clean_nodes.append({"id": node_id, "label": _text(node["label"], maximum=100)})
    if not isinstance(edges, list) or len(edges) > 20:
        raise ValueError("diagram edges exceed the safe limit")
    clean_edges = []
    for edge in edges:
        if not isinstance(edge, dict) or set(edge) - {"from", "to", "label"}:
            raise ValueError("diagram edge contains unsupported fields")
        if edge.get("from") not in ids or edge.get("to") not in ids:
            raise ValueError("diagram edge references an unknown node")
        clean_edges.append({
            "from": edge["from"], "to": edge["to"],
            "label": _text(edge.get("label", ""), maximum=80, required=False),
        })
    expected_edges = [
        (clean_nodes[index]["id"], clean_nodes[index + 1]["id"])
        for index in range(len(clean_nodes) - 1)
    ]
    actual_edges = [(edge["from"], edge["to"]) for edge in clean_edges]
    if actual_edges != expected_edges:
        raise ValueError("current flow diagrams require sequential edges in node order")
    direction = raw.get("direction", "vertical")
    if direction not in {"vertical", "horizontal"}:
        raise ValueError("diagram direction is invalid")
    return {**block, "direction": direction, "nodes": clean_nodes, "edges": clean_edges}


def _validate_chart(raw, block):
    chart_type = raw.get("chart_type")
    DEFAULT_VISUALIZATION_REGISTRY.resolve(chart_type)
    if chart_type not in {
        "bar", "grouped_bar", "stacked_bar", "line", "area", "pie", "donut", "scatter"
    }:
        raise ValueError("unsupported chart format")
    if block["source_scope"] == "reasoning":
        raise ValueError("charts require research, rider-supplied, or clearly illustrative data provenance")
    series = raw.get("series")
    if not isinstance(series, list) or not 1 <= len(series) <= 4:
        raise ValueError("charts require one to four series")
    total, clean_series = 0, []
    for item in series:
        if not isinstance(item, dict) or set(item) != {"name", "points"}:
            raise ValueError("chart series require only name and points")
        points = item["points"]
        if not isinstance(points, list) or not points:
            raise ValueError("chart series must contain points")
        clean_points = []
        for point in points:
            if chart_type == "scatter":
                if not isinstance(point, dict) or set(point) - {"label", "x", "y"} or not {"x", "y"} <= set(point):
                    raise ValueError("scatter points require x and y with optional label")
                x, y = point["x"], point["y"]
                if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) for value in (x, y)):
                    raise ValueError("scatter coordinates must be finite numbers")
                clean_points.append({
                    "label": _text(point.get("label", ""), maximum=60, required=False),
                    "x": x, "y": y,
                })
            else:
                if not isinstance(point, dict) or set(point) != {"label", "value"}:
                    raise ValueError("chart points require label and value")
                value = point["value"]
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
                    raise ValueError("chart values must be finite numbers")
                if chart_type in {"pie", "donut", "stacked_bar"} and value < 0:
                    raise ValueError("this chart format requires nonnegative values")
                clean_points.append({"label": _text(point["label"], maximum=60), "value": value})
        total += len(clean_points)
        clean_series.append({"name": _text(item["name"], maximum=80), "points": clean_points})
    if total > MAX_CHART_POINTS:
        raise ValueError("chart contains too many data points")
    if chart_type in {"pie", "donut"}:
        if len(clean_series) != 1 or sum(point["value"] for point in clean_series[0]["points"]) <= 0:
            raise ValueError("pie and donut charts require one positive-total series")
    if chart_type in {"grouped_bar", "stacked_bar"}:
        labels = [[point["label"] for point in item["points"]] for item in clean_series]
        if len(clean_series) < 2 or any(item != labels[0] for item in labels[1:]):
            raise ValueError("grouped and stacked bars require aligned labels across series")
    return {
        **block, "chart_type": chart_type,
        "x_label": _text(raw.get("x_label", ""), maximum=80, required=False),
        "y_label": _text(raw.get("y_label", ""), maximum=80, required=False),
        "series": clean_series,
    }


def _validate_timeline(raw, block):
    DEFAULT_VISUALIZATION_REGISTRY.resolve("timeline")
    items = raw.get("items")
    if not isinstance(items, list) or not 2 <= len(items) <= 24:
        raise ValueError("timelines require two to twenty-four events")
    clean = []
    for item in items:
        if not isinstance(item, dict) or set(item) - {"label", "date", "detail"} or not {"label", "date"} <= set(item):
            raise ValueError("timeline events require label and date")
        clean.append({
            "label": _text(item["label"], maximum=100),
            "date": _text(item["date"], maximum=80),
            "detail": _text(item.get("detail", ""), maximum=240, required=False),
        })
    return {**block, "items": clean}


def _validate_block(raw, approved):
    block = _base(raw, approved)
    if block["type"] == "table":
        return _validate_table(raw, block)
    if block["type"] == "diagram":
        return _validate_diagram(raw, block)
    if block["type"] == "chart":
        return _validate_chart(raw, block)
    return _validate_timeline(raw, block)


def _research_source_catalog(research):
    catalog = {}
    if not research:
        return catalog
    latest = (research.get("session", {}).get("assessment_history") or [{}])[-1]
    roles = {item.get("url"): item.get("source_role") for item in latest.get("source_assessments", ())}
    for result in research.get("results", ()):
        record = result.get("research", {})
        for source in (*record.get("citations", ()), *record.get("consulted_sources", ())):
            url = source.get("url")
            if url and url not in catalog:
                catalog[url] = {
                    "title": _text(source.get("title") or urlsplit(url).netloc, maximum=180),
                    "source_role": roles.get(url, "unknown"),
                }
    return catalog


def prepare_response_presentation(response_text, research=None):
    """Return archive-safe fallback text and a validated, non-executable envelope."""
    if not isinstance(response_text, str) or not response_text.strip():
        raise ValueError("response text is required")
    approved, blocks, rejected = approved_research_urls(research), [], []

    def consume(match):
        if len(blocks) >= MAX_BLOCKS:
            rejected.append("block_limit")
            return ""
        try:
            raw = json.loads(match.group("body"))
            candidates = raw if isinstance(raw, list) else [raw]
            for item in candidates:
                if len(blocks) >= MAX_BLOCKS:
                    raise ValueError("presentation block limit exceeded")
                blocks.append(_validate_block(item, approved))
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            rejected.append(str(exc) or type(exc).__name__)
        return ""

    display_text = _BLOCK.sub(consume, response_text).strip()
    catalog, citations, seen = _research_source_catalog(research), [], set()
    for label, url in _MARKDOWN_LINK.findall(display_text):
        if url not in approved or url in seen:
            continue
        seen.add(url)
        source = catalog.get(url, {})
        citations.append({
            "citation_id": f"source-{len(citations) + 1}", "label": _text(label, maximum=180),
            "title": source.get("title") or _text(label, maximum=180), "url": url,
            "display_url": clean_display_url(url),
            "source_role": source.get("source_role", "unknown"),
        })
    fallback_lines = [display_text]
    fallback_lines.extend(f"Visual — {block['title']}: {block['fallback']}" for block in blocks)
    return {
        "archive_text": "\n\n".join(item for item in fallback_lines if item).strip(),
        "presentation": {
            "schema_version": PRESENTATION_VERSION, "text": display_text,
            "blocks": blocks, "citations": citations, "rejected_blocks": rejected,
        },
    }

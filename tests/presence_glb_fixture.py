"""Synthetic GLB contract fixture. It is test geometry, never a Phoenix asset."""

import json
import struct


def synthetic_presence_glb():
    binary = bytearray()
    views = []

    def view(payload, target=None):
        while len(binary) % 4:
            binary.append(0)
        offset = len(binary)
        binary.extend(payload)
        item = {"buffer": 0, "byteOffset": offset, "byteLength": len(payload)}
        if target is not None:
            item["target"] = target
        views.append(item)
        return len(views) - 1

    position_view = view(struct.pack("<9f", -0.8, -0.55, 0, 0.8, -0.55, 0, 0, 0.85, 0), 34962)
    index_view = view(struct.pack("<3H", 0, 1, 2), 34963)
    time_view = view(struct.pack("<2f", 0, 1))
    rotation_view = view(struct.pack("<8f", 0, 0, 0, 1, 0, 0.173648, 0, 0.984808))
    joints_view = view(bytes([1, 0, 0, 0] * 3), 34962)
    weights_view = view(struct.pack("<12f", *(value for _ in range(3) for value in (1, 0, 0, 0))), 34962)
    inverse_bind_view = view(struct.pack("<96f", *([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1] * 6)))
    accessors = [
        {"bufferView": position_view, "componentType": 5126, "count": 3, "type": "VEC3",
         "min": [-0.8, -0.55, 0], "max": [0.8, 0.85, 0]},
        {"bufferView": index_view, "componentType": 5123, "count": 3, "type": "SCALAR"},
        {"bufferView": time_view, "componentType": 5126, "count": 2, "type": "SCALAR", "min": [0], "max": [1]},
        {"bufferView": rotation_view, "componentType": 5126, "count": 2, "type": "VEC4"},
        {"bufferView": joints_view, "componentType": 5121, "count": 3, "type": "VEC4"},
        {"bufferView": weights_view, "componentType": 5126, "count": 3, "type": "VEC4"},
        {"bufferView": inverse_bind_view, "componentType": 5126, "count": 6, "type": "MAT4"},
    ]
    materials = [
        {"name": "plumage_primary", "pbrMetallicRoughness": {"baseColorFactor": [1, 1, 1, 1], "metallicFactor": 0, "roughnessFactor": 0.8}},
        {"name": "plumage_secondary", "pbrMetallicRoughness": {"baseColorFactor": [1, 1, 1, 1], "metallicFactor": 0, "roughnessFactor": 0.8}},
        {"name": "expression_crest", "pbrMetallicRoughness": {"baseColorFactor": [1, 1, 1, 1], "metallicFactor": 0, "roughnessFactor": 0.8}},
        {"name": "expression_feather_tips", "pbrMetallicRoughness": {"baseColorFactor": [1, 1, 1, 1], "metallicFactor": 0, "roughnessFactor": 0.8}},
        {"name": "flame_accent", "pbrMetallicRoughness": {"baseColorFactor": [1, 1, 1, 1]}, "emissiveFactor": [1, 1, 1]},
    ]
    animations = [{"name": f"presence.{name}", "samplers": [{"input": 2, "output": 3, "interpolation": "LINEAR"}],
                   "channels": [{"sampler": 0, "target": {"node": 0, "path": "rotation"}}]}
                  for name in ("idle", "invoked", "thinking", "responding", "task_complete")]
    document = {
        "asset": {"version": "2.0", "generator": "Fawkes synthetic Presence test fixture; not an embodiment"},
        "scene": 0, "scenes": [{"nodes": [0]}], "nodes": [
            {"name": "phoenix_root", "children": [1, 6]},
            {"name": "body", "children": [2, 3, 4, 5]},
            {"name": "head"}, {"name": "wing_left"}, {"name": "wing_right"}, {"name": "tail"},
            {"name": "synthetic_contract_fixture", "mesh": 0, "skin": 0},
        ],
        "skins": [{"inverseBindMatrices": 6, "skeleton": 0, "joints": [0, 1, 2, 3, 4, 5]}],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0, "JOINTS_0": 4, "WEIGHTS_0": 5}, "indices": 1, "material": index} for index in range(5)]}],
        "materials": materials, "animations": animations, "accessors": accessors, "bufferViews": views,
        "buffers": [{"byteLength": len(binary)}],
    }
    encoded = json.dumps(document, separators=(",", ":")).encode("utf-8")
    encoded += b" " * ((4 - len(encoded) % 4) % 4)
    while len(binary) % 4:
        binary.append(0)
    total = 12 + 8 + len(encoded) + 8 + len(binary)
    return (struct.pack("<4sII", b"glTF", 2, total)
            + struct.pack("<II", len(encoded), 0x4E4F534A) + encoded
            + struct.pack("<II", len(binary), 0x004E4942) + bytes(binary))


def synthetic_workshop_glb():
    """Static renderable GLB without Presence v1 semantic rig claims."""
    payload = synthetic_presence_glb()
    json_length, json_kind = struct.unpack_from("<II", payload, 12)
    document = json.loads(payload[20:20 + json_length].rstrip(b" \x00"))
    document["asset"]["generator"] = "Fawkes synthetic static workshop fixture; not an embodiment"
    document.pop("animations", None)
    document.pop("skins", None)
    document["nodes"] = [{"name": "workshop_preview", "mesh": 0}]
    document["scenes"] = [{"nodes": [0]}]
    document["meshes"][0]["primitives"] = [{"attributes": {"POSITION": 0}, "indices": 1}]
    document.pop("materials", None)
    encoded = json.dumps(document, separators=(",", ":")).encode("utf-8")
    encoded += b" " * ((4 - len(encoded) % 4) % 4)
    binary_offset = 20 + json_length
    binary_length, binary_kind = struct.unpack_from("<II", payload, binary_offset)
    binary = payload[binary_offset + 8:binary_offset + 8 + binary_length]
    total = 12 + 8 + len(encoded) + 8 + len(binary)
    return (struct.pack("<4sII", b"glTF", 2, total)
            + struct.pack("<II", len(encoded), json_kind) + encoded
            + struct.pack("<II", len(binary), binary_kind) + binary)

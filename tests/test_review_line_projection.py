"""Exact-body and resource boundaries for the versioned provider presentation."""
import base64
import copy
import hashlib
import json
import unittest
from unittest.mock import patch
from src.runtime import wsl_codex_reviewer as w


class LineProjectionTests(unittest.TestCase):
    @staticmethod
    def _encoded_projection(value):
        value["record_sha256"] = w._digest(
            {key: item for key, item in value.items() if key != "record_sha256"})
        return (json.dumps(value, sort_keys=True, ensure_ascii=False,
                           separators=(",", ":")) + "\n").encode("utf-8")

    def test_unicode_line_endings_and_literals(self):
        for text in ('', 'a\r\nπ🌻\nlast', '+a\r\n-π🌻\n', '\x00\n', 'x' * 50000):
            with self.subTest(length=len(text)):
                recipe = w._line_recipe(text, 'a\r\nπ🌻\n', 'body', 'src/a.py', [0, 0])
                self.assertEqual(w._resolve_line_recipe(recipe, 'a\r\nπ🌻\n', 'body', 'src/a.py', [0, 0]), text)

    def test_strict_reference_fields_and_types(self):
        good = w._line_recipe('a\n', 'a\n', 'body', 'src/a.py', [0, 0])
        for key in good:
            bad = copy.deepcopy(good); del bad[key]
            with self.subTest(missing=key), self.assertRaises(ValueError):
                w._resolve_line_recipe(bad, 'a\n', 'body', 'src/a.py', [0, 0])
        for key, value in [('byte_length', True), ('byte_length', -1), ('byte_length', 4500001),
                           ('path', 'src/neighbor.py'), ('section_id', 'other'), ('sha256', '0'*64),
                           ('sha256', 'Z'*64), ('parts', {}), ('extra', 'unexpected')]:
            bad = copy.deepcopy(good); bad[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                w._resolve_line_recipe(bad, 'a\n', 'body', 'src/a.py', [0, 0])

    def test_dangling_cyclic_shaped_and_tampered_parts(self):
        good = w._line_recipe('a\n', 'a\n', 'body', 'src/a.py', [0, 0])
        for parts in ([[True, 1, '']], [[0, True, '']], [[1, 1, '']], [[0, 0, '']],
                      [[0, 2, '']], [[0, 1, 'bad']], [{'reference': 'self'}], ['changed'],
                      [[0, 1, ''], [0, 1, '']]):
            bad = copy.deepcopy(good); bad['parts'] = parts
            with self.subTest(parts=parts), self.assertRaises(ValueError):
                w._resolve_line_recipe(bad, 'a\n', 'body', 'src/a.py', [0, 0])

    def test_aggregate_work_and_bytes(self):
        for cap in (0, 1):
            with patch.object(w, 'MAX_PROVIDER_LINE_OPERATIONS', cap), self.assertRaises(ValueError):
                w._line_recipe('a\nb\n', 'a\n', 'body', 'p', [0, 0])
        budget = [0, 0]
        with patch.object(w, 'MAX_PROVIDER_BODY_BYTES', 4):
            w._line_recipe('a\n', 'a\n', 'body', 'p', budget)
            with self.assertRaises(ValueError):
                w._line_recipe('', 'a\n', 'body', 'p', budget)

    def test_duplicate_json_and_external_identity_fail_closed(self):
        for data in (b'{"a":1,"a":2}', b'[]'):
            with self.assertRaises(ValueError):
                w._resolve_provider_review_projection(data, expected_canonical_sha256=hashlib.sha256(data).hexdigest(), expected_canonical_byte_length=len(data))
        for length in (True, -1, 4500001):
            with self.assertRaises(ValueError):
                w._resolve_provider_review_projection(b'{}', expected_canonical_sha256='0'*64, expected_canonical_byte_length=length)

    def test_reserved_field_cannot_reconstruct_a_second_value(self):
        recipe = w._line_recipe('a', '', None, 'p', [0, 0])
        change = {'path': 'p', 'before_base64': '', 'before_body_recipe': recipe}
        with self.assertRaises(ValueError):
            w._restore_line_bodies([change], {})

    def test_nested_duplicate_keys_fail_closed_through_projection_roundtrip(self):
        body = ("x" * 350_000 + "\n").encode("utf-8")
        path = "src/large.py"
        node = {"schema": "fawkes.filesystem_node.v1", "state": "present",
                "file_type": "regular", "mode": 0o644,
                "body_length": len(body), "body_sha256": hashlib.sha256(body).hexdigest()}
        change = {"path": path, "status": "modified", "after_type": "regular",
                  "after_mode": 0o644, "after_symlink_target": None,
                  "after_base64": base64.b64encode(body).decode("ascii"),
                  "after_node_binding": node,
                  "before_base64": base64.b64encode(body).decode("ascii"),
                  "text_diff": body.decode("utf-8")}
        header = json.dumps({"path": path, "sha256": hashlib.sha256(body).hexdigest(),
                             "byte_length": len(body)}, sort_keys=True, separators=(",", ":"))
        package = {"record_type": "worker_exchange_package", "included_sections": [
            {"section_id": "exact-change-evidence",
             "content": json.dumps([change], sort_keys=True, separators=(",", ":"))},
            {"section_id": "changed-artifact-1", "content": header
             + "\n----- BEGIN EXACT UTF-8 ARTIFACT -----\n" + body.decode("utf-8")
             + "\n----- END EXACT UTF-8 ARTIFACT -----"},
        ]}
        logical = (json.dumps(package, sort_keys=True, separators=(",", ":")) + "\n").encode()
        binding = {"expected_canonical_sha256": hashlib.sha256(logical).hexdigest(),
                   "expected_canonical_byte_length": len(logical)}

        projection = w._provider_review_projection(logical)
        self.assertNotEqual(projection, logical)
        projected = json.loads(projection)
        self.assertEqual(projected["schema_version"], 1)
        self.assertEqual(w._resolve_provider_review_projection(projection, **binding), logical)

        duplicate_reference = copy.deepcopy(projected)
        exact = duplicate_reference["package"]["included_sections"][0]
        exact["content"] = exact["content"].replace(
            '"section_id":"changed-artifact-1"',
            '"section_id":"changed-artifact-wrong","section_id":"changed-artifact-1"', 1)
        with self.assertRaisesRegex(ValueError, "exact change evidence is malformed"):
            w._resolve_provider_review_projection(
                self._encoded_projection(duplicate_reference), **binding)

        duplicate_header = copy.deepcopy(projected)
        artifact = duplicate_header["package"]["included_sections"][1]
        artifact["content"] = artifact["content"].replace(
            '"path":"src/large.py"',
            '"path":"src/wrong.py","path":"src/large.py"', 1)
        with self.assertRaisesRegex(ValueError, "header is malformed"):
            w._resolve_provider_review_projection(
                self._encoded_projection(duplicate_header), **binding)

        line_projection = json.loads(w._project_line_bodies(copy.deepcopy(projected)))
        self.assertEqual(line_projection["schema_version"], 2)
        exact = line_projection["package"]["included_sections"][0]
        exact["content"] = exact["content"].replace(
            '"parts":[', '"parts":["wrong"],"parts":[', 1)
        with self.assertRaisesRegex(ValueError, "exact change evidence is malformed"):
            w._resolve_provider_review_projection(
                self._encoded_projection(line_projection), **binding)

"""Offline checks for the inline Markdown links used by the contributor docs.

Fixtures are in-memory Markdown; no runtime imports, network or file writes.
This is a focused link checker, not a general Markdown renderer.
"""

import re
import unittest
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parent.parent
DOCUMENTS = ("README.md", "CONTRIBUTING.md", "docs/REPOSITORY_LAYOUT.md")
INLINE_LINK = re.compile(r"!?\[[^\]\n]*\]\(\s*(?:<([^>\n]+)>|([^\s)]+))\s*\)")


def prose(markdown):
    """Exclude fenced examples so illustrative links are not navigation."""
    lines = []
    fence = None
    for line in markdown.splitlines():
        marker = re.match(r"^\s{0,3}(`{3,}|~{3,})", line)
        if fence:
            if marker and marker[1][0] == fence[0] and len(marker[1]) >= len(fence):
                fence = None
            continue
        if marker:
            fence = marker[1]
        else:
            lines.append(line)
    return "\n".join(lines)


def heading_ids(markdown):
    """GitHub-style IDs for the ATX headings used in these documents."""
    identifiers = set()
    for line in prose(markdown).splitlines():
        match = re.match(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$", line)
        if not match:
            continue
        base = re.sub(r"[^\w\- ]", "", match[1].lower()).replace(" ", "-")
        identifier = base
        suffix = 0
        while identifier in identifiers:
            suffix += 1
            identifier = f"{base}-{suffix}"
        identifiers.add(identifier)
    return identifiers


def local_links(markdown):
    for match in INLINE_LINK.finditer(prose(markdown)):
        destination = match[1] or match[2]
        url = urlsplit(destination)
        if not url.scheme and not url.netloc:
            yield destination, unquote(url.path), unquote(url.fragment)


def broken_links(document, markdown):
    failures = []
    for destination, path, fragment in local_links(markdown):
        target = (document.parent / path).resolve() if path else document.resolve()
        if not target.is_relative_to(ROOT):
            failures.append((destination, "outside repository"))
        elif not target.exists():
            failures.append((destination, "missing target"))
        elif fragment:
            if target.suffix.lower() != ".md" or not target.is_file():
                failures.append((destination, "unsupported fragment target"))
            elif fragment not in heading_ids(target.read_text(encoding="utf-8")):
                failures.append((destination, "missing heading"))
    return failures


class RepositoryDocumentationTests(unittest.TestCase):
    def test_local_links_in_all_three_documents_resolve(self):
        for relative in DOCUMENTS:
            with self.subTest(document=relative):
                document = ROOT / relative
                self.assertTrue(document.is_file(), f"Missing document: {relative}")
                markdown = document.read_text(encoding="utf-8")
                self.assertTrue(list(local_links(markdown)), f"No local links: {relative}")
                self.assertEqual([], broken_links(document, markdown))

    def test_readme_links_to_both_contributor_entry_points(self):
        markdown = (ROOT / "README.md").read_text(encoding="utf-8")
        targets = {(ROOT / path).resolve() for _, path, _ in local_links(markdown)}
        for relative in DOCUMENTS[1:]:
            with self.subTest(target=relative):
                self.assertIn(ROOT / relative, targets)

    def test_negative_fixture_reports_missing_file_and_heading(self):
        fixture = (
            "[valid](../README.md#project-fawkes)\n"
            "[missing](../docs/__missing_navigation_fixture__.md)\n"
            "[broken heading](../README.md#__missing_navigation_heading__)\n"
        )
        self.assertEqual(
            [
                ("../docs/__missing_navigation_fixture__.md", "missing target"),
                ("../README.md#__missing_navigation_heading__", "missing heading"),
            ],
            broken_links(ROOT / "docs/REPOSITORY_LAYOUT.md", fixture),
        )

    def test_relative_file_directory_and_encoded_fragment_targets(self):
        fixture = (
            "[file](../README.md)\n"
            "[directory](../src/)\n"
            "[heading](<../README.md#project%2Dfawkes>)\n"
            "[same document](#repository-layout)\n"
        )
        self.assertEqual([], broken_links(ROOT / "docs/REPOSITORY_LAYOUT.md", fixture))

    def test_external_links_and_fenced_examples_are_not_checked(self):
        fixture = (
            "[web](https://example.invalid/missing)\n"
            "[web](//example.invalid/missing)\n"
            "[mail](mailto:nobody@example.invalid)\n"
            "```markdown\n[example](__missing_example__.md)\n```\n"
            "~~~markdown\n[example](__missing_example__.md)\n~~~\n"
        )
        self.assertEqual([], list(local_links(fixture)))

    def test_outside_repository_target_is_rejected(self):
        self.assertEqual(
            [("../__outside_navigation_fixture__.md", "outside repository")],
            broken_links(ROOT / "README.md", "[outside](../__outside_navigation_fixture__.md)"),
        )

    def test_heading_ids_handle_punctuation_and_duplicates(self):
        self.assertEqual(
            {"same-heading", "same-heading-1", "code-heading"},
            heading_ids("# Same heading!\n## Same heading!\n### `Code` heading\n"),
        )


if __name__ == "__main__":
    unittest.main()

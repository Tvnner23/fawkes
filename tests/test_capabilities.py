import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from src.capabilities.core import (
    CapabilityAvailabilityCatalog,
    CapabilityDefinition,
    CapabilityExecutor,
    CapabilityRegistry,
    CapabilityRequest,
)
from src.capabilities.web_research import (
    OpenAIWebResearchProvider,
    ResearchProviderChain,
    WebResearchCapability,
)
from src.capabilities.multimodal import (
    AuthorityContract,
    MediaEvidenceReference,
    MultimodalCapabilityContract,
    PrivacyLabel,
    ensure_delegated_permissions,
)


class CapabilityKernelTests(unittest.TestCase):
    def test_availability_catalog_only_advertises_registered_runtime_capabilities(self):
        definition = CapabilityDefinition(
            name="available.read", version="1", description="Read available data."
        )
        catalog = CapabilityAvailabilityCatalog()
        self.assertEqual(catalog.manifests(), ())
        catalog.advertise(definition, effects="read only")
        self.assertEqual(catalog.manifests()[0]["name"], "available.read")
        self.assertEqual(catalog.manifests()[0]["availability"], "live")

    def test_dynamic_health_is_distinct_from_acceptance_evidence(self):
        definition = CapabilityDefinition("health.test", "1", "Health test")
        catalog = CapabilityAvailabilityCatalog()
        catalog.advertise(definition, effects="read only")
        catalog.set_health("health.test", "degraded", reason="last provider attempt failed",
                           failure_code="TimeoutError")
        manifest = catalog.manifests(acceptance_statuses={"health.test": "pass"})[0]
        self.assertEqual(manifest["availability"], "degraded")
        self.assertEqual(manifest["health"]["failure_code"], "TimeoutError")
        self.assertEqual(manifest["acceptance_status"], "pass")
        for state in ("rate_limited", "permission_blocked", "disabled", "untested",
                      "environmentally_unverifiable"):
            catalog.set_health("health.test", state, reason="fixture")
            self.assertEqual(catalog.manifests()[0]["health"]["status"], state)

    def test_input_and_output_modalities_are_independent(self):
        contract = MultimodalCapabilityContract(
            input_modalities=("text", "image", "pdf"),
            output_modalities=("text", "diagram"),
        )
        self.assertIn("image", contract.input_modalities)
        self.assertNotIn("image", contract.output_modalities)

    def test_public_capability_manifest_exposes_scope_not_permissions_or_provider(self):
        definition = CapabilityDefinition(
            name="media.inspect", version="1", description="Inspect an image.",
            permissions=("private-media.read",),
            modalities=MultimodalCapabilityContract(
                input_modalities=("image",), output_modalities=("text", "diagram")
            ),
            authority=AuthorityContract(
                actions=("read", "analyze"), execution_boundary="internal",
                authorization_mode="pre_granted",
            ),
            privacy_handling="rider_visible_private_media",
        )
        manifest = definition.public_manifest()
        self.assertEqual(manifest["input_modalities"], ["image"])
        self.assertEqual(manifest["output_modalities"], ["text", "diagram"])
        self.assertNotIn("permissions", manifest)
        self.assertNotIn("provider", manifest)

    def test_consequential_authority_cannot_be_mislabeled_as_pregranted(self):
        with self.assertRaisesRegex(ValueError, "requires confirmation"):
            AuthorityContract(
                actions=("communicate_external",),
                execution_boundary="external_write",
                authorization_mode="pre_granted",
            )

    def test_executor_enforces_task_and_confirmation_authorization_modes(self):
        registry = CapabilityRegistry()
        registry.register(
            CapabilityDefinition(
                "external.read", "1", "External read",
                authority=AuthorityContract(
                    actions=("read",), execution_boundary="external_read",
                    authorization_mode="task_request",
                ),
            ),
            lambda request: {},
        )
        registry.register(
            CapabilityDefinition(
                "external.send", "1", "External message",
                authority=AuthorityContract(
                    actions=("communicate_external",), execution_boundary="external_write",
                    authorization_mode="explicit_confirmation",
                ),
            ),
            lambda request: {},
        )
        with tempfile.TemporaryDirectory() as tmp:
            executor = CapabilityExecutor(registry, receipt_dir=tmp)
            with self.assertRaisesRegex(PermissionError, "rider's task"):
                executor.execute(CapabilityRequest("fawkes", "external.read", {}))
            executor.execute(CapabilityRequest(
                "fawkes", "external.read", {}, task_authorized=True
            ))
            with self.assertRaisesRegex(PermissionError, "explicit rider"):
                executor.execute(CapabilityRequest("fawkes", "external.send", {}))
            executor.execute(CapabilityRequest(
                "fawkes", "external.send", {}, explicitly_confirmed=True
            ))

    def test_self_created_workflow_cannot_expand_parent_permissions(self):
        self.assertEqual(
            ensure_delegated_permissions(
                ("library.read", "workspace.create"), ("library.read",)
            ),
            ("library.read",),
        )
        with self.assertRaisesRegex(PermissionError, "cannot grant"):
            ensure_delegated_permissions(
                ("library.read",), ("library.read", "device.control")
            )

    def test_media_evidence_requires_visible_revisable_privacy_and_locator(self):
        reference = MediaEvidenceReference(
            source_id="library-source-1", modality="video",
            locator_kind="video_segment",
            locator={"start_seconds": 42, "end_seconds": 57},
            derivation="Transcript and frame analysis",
            privacy=PrivacyLabel(
                classification="potentially_private",
                reason="The recording may contain student information.",
                assigned_by="rider",
            ),
        )
        self.assertEqual(reference.as_dict()["locator"]["start_seconds"], 42)
        self.assertTrue(reference.as_dict()["privacy"]["rider_visible"])
        with self.assertRaisesRegex(ValueError, "source locator"):
            MediaEvidenceReference(
                source_id="source-2", modality="image", locator_kind="image_region",
                locator={}, derivation="Visual analysis",
            )
    def test_permissions_are_enforced_before_handler_execution(self):
        called = []
        registry = CapabilityRegistry()
        registry.register(
            CapabilityDefinition(
                name="web.research",
                version="1",
                description="Research",
                permissions=("external_web_search",),
            ),
            lambda request: called.append(request) or {},
        )
        with tempfile.TemporaryDirectory() as tmp:
            executor = CapabilityExecutor(registry, receipt_dir=tmp)
            with self.assertRaisesRegex(PermissionError, "external_web_search"):
                executor.execute(
                    CapabilityRequest("fawkes", "web.research", {"query": "x"})
                )
        self.assertEqual(called, [])

    def test_receipt_is_instance_scoped_and_contains_digest_not_raw_arguments(self):
        registry = CapabilityRegistry()
        registry.register(
            CapabilityDefinition("test.read", "1", "Read", ("read",)),
            lambda request: {"result_references": [{"id": "result-1"}]},
        )
        with tempfile.TemporaryDirectory() as tmp:
            executor = CapabilityExecutor(registry, receipt_dir=tmp)
            result = executor.execute(
                CapabilityRequest(
                    "fawkes", "test.read",
                    {"sensitive_input": "synthetic-redaction-probe"},
                ),
                granted_permissions=("read",),
            )
            receipt_path = Path(tmp) / "fawkes" / f"{result['capability_receipt_id']}.json"
            receipt = json.loads(receipt_path.read_text())
        self.assertEqual(receipt["instance_id"], "fawkes")
        self.assertIn("argument_sha256", receipt)
        self.assertNotIn("secret", json.dumps(receipt))
        self.assertEqual(receipt["input_modalities"], ["text"])
        self.assertEqual(receipt["authority_actions"], ["read"])

    def test_instance_scope_cannot_escape_receipt_directory(self):
        registry = CapabilityRegistry()
        registry.register(CapabilityDefinition("test.read", "1", "Read"), lambda request: {})
        with tempfile.TemporaryDirectory() as tmp:
            executor = CapabilityExecutor(registry, receipt_dir=tmp)
            with self.assertRaisesRegex(ValueError, "unsafe"):
                executor.execute(CapabilityRequest("../../sibling", "test.read", {}))
        self.assertEqual(list(Path(tmp).rglob("*.json")), [])

    def test_failed_execution_is_receipted_without_exception_details(self):
        registry = CapabilityRegistry()
        registry.register(
            CapabilityDefinition("test.fail", "1", "Fail"),
            lambda request: (_ for _ in ()).throw(RuntimeError("provider secret")),
        )
        with tempfile.TemporaryDirectory() as tmp:
            executor = CapabilityExecutor(registry, receipt_dir=tmp)
            with self.assertRaisesRegex(RuntimeError, "capability execution failed"):
                executor.execute(CapabilityRequest("fawkes", "test.fail", {}))
            receipts = list(Path(tmp).rglob("*.json"))
            receipt_text = receipts[0].read_text()
        self.assertEqual(len(receipts), 1)
        self.assertIn('"status": "failed"', receipt_text)
        self.assertNotIn("provider secret", receipt_text)


class FakeProvider:
    name = "fake_web"

    def research(self, query, *, allowed_domains=(), timeout_seconds=None):
        return {
            "provider": self.name,
            "model": "fake-model",
            "provider_response_id": "provider-1",
            "answer": "Grounded answer [1].",
            "citations": [{"source_id": "web-1", "url": "https://example.com/a"}],
            "consulted_sources": [{"source_id": "web-1", "url": "https://example.com/a"}],
        }


class WebResearchCapabilityTests(unittest.TestCase):
    def test_provider_chain_falls_back_without_expanding_permission_scope(self):
        class Failing:
            name = "primary"
            def research(self, query, *, allowed_domains=(), timeout_seconds=None):
                raise ConnectionError("private provider detail")

        chain = ResearchProviderChain((Failing(), FakeProvider()))
        result = chain.research("What changed?")
        self.assertEqual(result["provider"], "fake_web")
        self.assertEqual(
            [(item["provider"], item["status"]) for item in result["provider_attempts"]],
            [("primary", "failed"), ("fake_web", "completed")],
        )
        self.assertNotIn("private provider detail", str(result))

    def test_paid_research_uses_existing_authorization_boundary(self):
        from src.runtime.paid_call import PaidCallGuard

        capability = WebResearchCapability(
            provider=FakeProvider(),
            paid_call_guard=PaidCallGuard(cost_per_call=0.01),
        )
        with self.assertRaisesRegex(PermissionError, "Explicit authorization"):
            capability.run(instance_id="fawkes", query="What changed?")

    def test_research_is_separate_instance_scoped_evidence_not_memory_or_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "archive"
            archive.mkdir()
            marker = archive / "historical.txt"
            marker.write_bytes(b"immutable evidence")
            before = marker.read_bytes()
            capability = WebResearchCapability(
                provider=FakeProvider(),
                research_dir=root / "research",
                receipt_dir=root / "receipts",
            )
            result = capability.run(
                instance_id="fawkes",
                query="What changed?",
                conversation_id="conversation-1",
                request_message_id="message-1",
                task_authorized=True,
            )
            after = marker.read_bytes()
            sibling_records = list((root / "research" / "sibling").glob("*.json"))

        record = result["research"]
        self.assertEqual(before, after)
        self.assertEqual(record["instance_id"], "fawkes")
        self.assertEqual(record["effect"], "research_evidence_only")
        self.assertEqual(record["archive_mutation"], "none")
        self.assertEqual(record["memory_promotion"], "none")
        self.assertEqual(sibling_records, [])

    def test_domain_filters_reject_urls_and_excessive_scope(self):
        capability = WebResearchCapability(provider=FakeProvider())
        with self.assertRaisesRegex(ValueError, "bare domains"):
            capability.run(
                instance_id="fawkes",
                query="query",
                allowed_domains=("https://example.com",),
            )

    def test_openai_adapter_requests_search_and_extracts_provenance(self):
        response = SimpleNamespace(
            id="response-1",
            output_text="A cited claim.",
            model_dump=lambda: {
                "id": "response-1",
                "output": [
                    {
                        "type": "web_search_call",
                        "action": {"sources": [{"url": "https://EXAMPLE.com/page#x", "title": "Primary"}]},
                    },
                    {
                        "type": "message",
                        "content": [{
                            "type": "output_text",
                            "annotations": [{
                                "type": "url_citation",
                                "url": "https://example.com/page#fragment",
                                "title": "Primary",
                                "start_index": 0,
                                "end_index": 13,
                            }],
                        }],
                    },
                ],
            },
        )
        client = SimpleNamespace(
            responses=SimpleNamespace(create=lambda **kwargs: response)
        )
        provider = OpenAIWebResearchProvider(client=client, model="test-model")
        result = provider.research("question", allowed_domains=("example.com",))

        self.assertEqual(result["provider_response_id"], "response-1")
        self.assertEqual(result["citations"][0]["cited_text"], "A cited claim")
        self.assertEqual(result["citations"][0]["url"], "https://example.com/page")
        self.assertEqual(result["consulted_sources"][0]["url"], "https://example.com/page")

    def test_openai_adapter_tolerates_null_optional_action_collections(self):
        response = SimpleNamespace(
            id="response-null", output_text="No source was returned.",
            model_dump=lambda: {"id": "response-null", "output": [{
                "type": "web_search_call", "action": {"type": "search", "queries": None, "sources": None},
            }]},
        )
        provider = OpenAIWebResearchProvider(
            client=SimpleNamespace(responses=SimpleNamespace(create=lambda **kwargs: response)), model="test-model",
        )
        result = provider.research("question")
        self.assertEqual(result["provider_actions"][0]["queries"], [])
        self.assertEqual(result["consulted_sources"], [])


if __name__ == "__main__":
    unittest.main()

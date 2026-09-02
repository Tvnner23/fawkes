import hashlib
import json
import struct
import tempfile
import unittest
from pathlib import Path

from src.capabilities.phoenix_presence import (
    PRESENCE_DEFINITION, PresenceProfileStore, default_presence_profile,
    normalize_invocation_phrase, presence_health, validate_profile,
    inspect_presence_glb, upgrade_presence_profile,
    WORKSHOP_STATIC_CONTRACT_VERSION,
)
from src.runtime.phase0_integrity import (
    create_complete_state_backup, restore_complete_state_backup,
)
from tests.presence_glb_fixture import synthetic_presence_glb, synthetic_workshop_glb


class PhoenixPresenceProfileTests(unittest.TestCase):
    @staticmethod
    def glb_fixture():
        return synthetic_presence_glb()

    def test_default_profile_is_instance_bound_fallback_and_not_identity_memory(self):
        profile = default_presence_profile("fawkes-one")
        self.assertEqual(profile["phoenix_instance_id"], "fawkes-one")
        self.assertIsNone(profile["asset"])
        self.assertEqual(presence_health(profile)["status"], "unavailable")
        self.assertFalse({"memory", "personality", "traits"}.intersection(profile))
        self.assertFalse(PRESENCE_DEFINITION.public_manifest()["authorization_mode"] == "explicit_confirmation")

    def test_ensure_persists_instance_scoped_profile_without_continuity_claim(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = PresenceProfileStore("one", root=tmp)
            profile = store.ensure()
            self.assertTrue(store.path.is_file())
            self.assertEqual(store.ensure(), profile)
            self.assertNotIn("continuity", json.dumps(profile).lower())

    def test_schema_one_profile_gets_narrow_provenanced_material_upgrade(self):
        legacy = default_presence_profile("one")
        legacy["schema_version"] = 1
        legacy["rig"]["material_channels"] = ["plumage_primary", "plumage_secondary", "flame_accent"]
        del legacy["palette"]["channels"]["expression_crest"]
        del legacy["palette"]["channels"]["expression_feather_tips"]
        upgraded = upgrade_presence_profile(legacy)
        self.assertEqual(upgraded["schema_version"], 2)
        self.assertEqual(upgraded["profile_revision"], 2)
        self.assertEqual(upgraded["palette"]["channels"]["expression_crest"]["role"], "transient_expression_crest")
        self.assertEqual(upgraded["provenance"]["prior_schema_version"], 1)
        self.assertEqual(upgraded["provenance"]["change_kind"], "schema_upgrade_1_to_2_material_segmentation")

    def test_cross_phoenix_profile_is_rejected(self):
        with self.assertRaises(PermissionError):
            validate_profile(default_presence_profile("one"), expected_instance_id="two")

    def test_preferences_are_bounded_revisioned_and_invocation_is_not_auth(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = PresenceProfileStore("one", root=tmp)
            updated = store.update_preferences(
                {"enabled": False, "motion": "off", "reduced_motion": True,
                 "invocation_phrase": "  Wake   Fawkes  "},
                actor_principal_id="authenticated-rider:one",
            )
            self.assertEqual(updated["profile_revision"], 2)
            self.assertEqual(updated["presentation_policy"]["invocation_phrase"], "Wake Fawkes")
            self.assertEqual(updated["provenance"]["prior_revision"], 1)
            self.assertEqual(store.public()["health"]["status"], "disabled")
            self.assertFalse(store.public()["invocation_is_authentication"])
            with self.assertRaises(ValueError): store.update_preferences({"personality": "amused"}, actor_principal_id="rider")
            with self.assertRaises(ValueError): normalize_invocation_phrase("x" * 81)

    def test_missing_or_tampered_asset_never_becomes_live(self):
        with tempfile.TemporaryDirectory() as tmp:
            asset_root = Path(tmp) / "assets"
            profile = default_presence_profile("one")
            profile["asset"] = {
                "asset_id": "fawkes.dev", "revision": 1, "status": "development_asset",
                "filename": "fawkes-development.glb", "sha256": "0" * 64,
                "rig_contract_version": "presence-rig-1",
                "rights": {"license": "project-owned-development"},
            }
            self.assertEqual(presence_health(profile, asset_root=asset_root)["status"], "unavailable")
            asset_root.mkdir(); (asset_root / "fawkes-development.glb").write_bytes(b"not-the-declared-asset")
            self.assertEqual(presence_health(profile, asset_root=asset_root)["status"], "failed")

    def test_matching_local_asset_is_live_without_executing_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); payload = b"synthetic-glb-fixture"
            (root / "fixture.glb").write_bytes(payload)
            profile = default_presence_profile("one")
            profile["asset"] = {
                "asset_id": "fixture", "revision": 1, "status": "development_asset",
                "filename": "fixture.glb", "sha256": hashlib.sha256(payload).hexdigest(),
                "rig_contract_version": "presence-rig-1",
                "rights": {"license": "synthetic-test-only"},
                "metadata": {"script": "must-not-execute()"},
            }
            self.assertEqual(presence_health(profile, asset_root=root)["status"], "live")

    def test_development_glb_registration_validates_semantics_rights_and_revision(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source = root / "source.glb"; source.write_bytes(self.glb_fixture())
            store = PresenceProfileStore("one", root=root / "profiles", asset_root=root / "assets")
            profile = store.install_development_asset(source, asset_id="fawkes.dev", revision=1,
                rights={"license": "synthetic-test-only", "creator": "test"}, actor_principal_id="developer:test")
            self.assertEqual(profile["asset"]["status"], "development_asset")
            self.assertEqual(profile["profile_revision"], 2)
            self.assertEqual(presence_health(profile, asset_root=root / "assets")["status"], "live")
            self.assertEqual(inspect_presence_glb(source.read_bytes())["format"], "glTF 2.0 binary")
            broken = bytearray(source.read_bytes()); broken[0:4] = b"nope"
            with self.assertRaises(ValueError): inspect_presence_glb(bytes(broken))

    def test_static_workshop_asset_is_renderable_but_never_claims_production_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source = root / "workshop.glb"; source.write_bytes(synthetic_workshop_glb())
            store = PresenceProfileStore("one", root=root / "profiles", asset_root=root / "assets")
            with self.assertRaises(ValueError):
                store.install_development_asset(source, asset_id="fixture.workshop", revision=1,
                    rights={"license": "synthetic-test-only", "creator": "test"},
                    actor_principal_id="developer:test")
            profile = store.install_development_asset(source, asset_id="fixture.workshop", revision=1,
                rights={"license": "synthetic-test-only", "creator": "test"},
                actor_principal_id="developer:test", contract_version=WORKSHOP_STATIC_CONTRACT_VERSION)
            asset = profile["asset"]
            self.assertEqual(asset["status"], "development_asset")
            self.assertEqual(asset["rig_contract_version"], WORKSHOP_STATIC_CONTRACT_VERSION)
            self.assertFalse(asset["inspection"]["production_contract_complete"])
            self.assertEqual(asset["inspection"]["mesh_count"], 1)
            self.assertEqual(asset["inspection"]["external_resource_count"], 0)
            self.assertEqual(presence_health(profile, asset_root=root / "assets")["status"], "live")

    def test_workshop_asset_rejects_external_dependencies(self):
        payload = synthetic_workshop_glb()
        json_length = int.from_bytes(payload[12:16], "little")
        document = json.loads(payload[20:20 + json_length].rstrip(b" \x00"))
        document["images"] = [{"uri": "https://example.invalid/private.png"}]
        encoded = json.dumps(document, separators=(",", ":")).encode(); encoded += b" " * ((4 - len(encoded) % 4) % 4)
        old_binary_offset = 20 + json_length
        binary_length = int.from_bytes(payload[old_binary_offset:old_binary_offset + 4], "little")
        binary = payload[old_binary_offset + 8:old_binary_offset + 8 + binary_length]
        total = 12 + 8 + len(encoded) + 8 + len(binary)
        altered = (struct.pack("<4sII", b"glTF", 2, total) + struct.pack("<II", len(encoded), 0x4E4F534A)
                   + encoded + struct.pack("<II", len(binary), 0x004E4942) + binary)
        with self.assertRaisesRegex(ValueError, "external resources"):
            inspect_presence_glb(altered, contract_version=WORKSHOP_STATIC_CONTRACT_VERSION)


class PresenceRecoveryTests(unittest.TestCase):
    def test_complete_state_backup_restores_only_owning_presence_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "live"
            (root / "instances").mkdir(parents=True)
            (root / "instances/registry.json").write_text(json.dumps({
                "schema_version": 1, "instances": [
                    {"instance_id": "one", "name": "One", "instance_type": "phoenix"},
                    {"instance_id": "two", "name": "Two", "instance_type": "phoenix"},
                ]}) + "\n")
            for owner in ("one", "two"):
                store = PresenceProfileStore(owner, root=root / "database/presentation")
                store.update_preferences({"invocation_phrase": f"Wake {owner}"}, actor_principal_id=f"rider:{owner}")
                if owner == "one":
                    source = Path(tmp) / "synthetic-contract-fixture.glb"; source.write_bytes(synthetic_presence_glb())
                    store.install_development_asset(source, asset_id="synthetic.test.fixture", revision=1,
                        rights={"license": "synthetic-test-only", "creator": "automated-test"},
                        actor_principal_id="developer:test")
            backup, _ = create_complete_state_backup("one", Path(tmp) / "backups", source_root=root)
            restored = Path(tmp) / "restored"
            restore_complete_state_backup(backup, restored, instance_id="one")
            self.assertTrue((restored / "database/presentation/one/profile.json").is_file())
            restored_profile = json.loads((restored / "database/presentation/one/profile.json").read_text())
            self.assertTrue((restored / "database/presentation/one/assets" / restored_profile["asset"]["filename"]).is_file())
            self.assertFalse((restored / "database/presentation/two/profile.json").exists())


if __name__ == "__main__": unittest.main()

#!/usr/bin/env python3
"""Run the first Tanner-approved bounded autonomous Development campaign."""

from pathlib import Path
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.runtime.codex_development_campaign import CodexDevelopmentCampaign

INSTANCE_ID = "9b816885-df8b-4e75-8a4a-02d9d35771d5"
CAMPAIGN_ID = "first-autonomous-notification-metadata-v7"
BACKUP_ID = "49b624cd-3657-40f6-9476-02ad9ffae9c7"
BACKUP_MANIFEST = Path("/tmp/fawkes-disposable-write-campaign-v7/phoenix-9b816885-df8b-4e75-8a4a-02d9d35771d5-cc971ac6-50c0-48ae-93d7-edae01b87df1/manifest.json")


def main():
    manifest_sha = hashlib.sha256(BACKUP_MANIFEST.read_bytes()).hexdigest()
    campaign = CodexDevelopmentCampaign(INSTANCE_ID)
    payload = {
        "instance_id": INSTANCE_ID, "campaign_id": CAMPAIGN_ID,
        "target_builder": "codex_repo", "objective_mode": "repository_write",
        "objective": ("Strengthen the existing autonomous-campaign notification metadata regression "
            "coverage without implementing SMS or any notification provider. Prefer a test-only change."),
        "acceptance_condition_ids": [
            "interval-10800", "progress-descriptive", "progress-does-not-pause",
            "progress-does-not-create-needs-tanner", "needs-tanner-separate",
            "no-notification-provider", "focused-tests-pass", "scope-held",
        ],
        "acceptance_conditions": {
            "interval-10800": "The campaign presentation verifies periodic_progress_interval_seconds equals exactly 10800.",
            "progress-descriptive": "Periodic progress metadata is explicitly descriptive observation metadata.",
            "progress-does-not-pause": "Periodic progress metadata cannot pause the autonomous campaign.",
            "progress-does-not-create-needs-tanner": "Periodic progress metadata alone does not create needs_tanner.",
            "needs-tanner-separate": "Immediate Human Review or escalation remains independently represented by needs_tanner.",
            "no-notification-provider": "No SMS, Twilio, push provider, notification daemon, or delivery infrastructure is introduced.",
            "focused-tests-pass": "Focused autonomous Development campaign tests pass.",
            "scope-held": "No repository file outside tests/test_codex_development_campaign.py is mutated by the builder.",
        },
        "allowed_scope": ["tests/test_codex_development_campaign.py"],
        "validation_commands": [[".venv/bin/python", "-m", "unittest",
                                 "tests.test_codex_development_campaign"]],
        "source_sections": [{"section_id": "rider-objective", "title": "Exact Tanner objective boundary",
            "content": ("TEST-ONLY preferred. Verify 10800 seconds, descriptive/non-pausing progress, "
                "no needs_tanner creation, separate immediate Human Review, and no notification provider.")}],
        "rider_authorization_reference": "tanner-first-autonomous-campaign-2026-09-01",
        "recovery_references": [{"reference_type": "complete_phoenix_state_backup",
            "reference_id": BACKUP_ID, "sha256": manifest_sha}],
        "explicitly_authorized": True,
    }
    try:
        record = campaign.store.load(CAMPAIGN_ID)
    except (FileNotFoundError, KeyError):
        record = campaign.create(payload, authenticated_rider=True)
    record = campaign.run_to_terminal(CAMPAIGN_ID)
    presentation = campaign.presentation(CAMPAIGN_ID)
    output = {"campaign_id": CAMPAIGN_ID, "status": record["status"],
        "iteration": record["iteration"], "builder_runs": record["builder_runs"],
        "reviews": record["reviews"], "acceptance_satisfied": record["acceptance_satisfied"],
        "needs_tanner": record["needs_tanner"], "cancelled": record["cancelled"],
        "operational_learning_observations": presentation["operational_learning_observations"],
        "notification_signals": presentation["notification_signals"],
        "automatic_promotion": record["automatic_promotion"], "creates_authority": record["creates_authority"]}
    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0 if record["status"] == "succeeded" else 2


if __name__ == "__main__": raise SystemExit(main())

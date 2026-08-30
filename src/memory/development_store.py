import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from src.memory.development import DevelopmentProposal


ROOT = Path(__file__).resolve().parent.parent.parent
DEVELOPMENT_DIR = ROOT / "memory" / "development"


def save_development_proposal(proposal: DevelopmentProposal):
    DEVELOPMENT_DIR.mkdir(parents=True, exist_ok=True)

    proposal_id = str(uuid4())

    record = {
        "proposal_id": proposal_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "category": proposal.category,
        "observation": proposal.observation,
        "proposed_change": proposal.proposed_change,
        "rationale": proposal.rationale,
        "confidence": proposal.confidence,
        "source_memory_ids": list(proposal.source_memory_ids),
        "source_message_ids": list(proposal.source_message_ids),
        "status": "proposed",
    }

    path = DEVELOPMENT_DIR / f"{proposal_id}.json"

    path.write_text(
        json.dumps(record, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return record

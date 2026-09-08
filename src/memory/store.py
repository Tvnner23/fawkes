from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import math
import uuid

from src.memory.mutation import MemoryRecoveryRequired, transactional, write_json, read_json, json_paths


ROOT = Path(__file__).resolve().parent.parent.parent
MEMORY_ROOT = ROOT / "memory"
MEMORY_RECORDS_DIR = MEMORY_ROOT / "records"
MEMORY_EVENTS_DIR = MEMORY_ROOT / "events"
DEFAULT_MEMORY_RECORDS_DIR = MEMORY_RECORDS_DIR
DEFAULT_MEMORY_EVENTS_DIR = MEMORY_EVENTS_DIR
_transactional = transactional(lambda: (MEMORY_RECORDS_DIR, MEMORY_EVENTS_DIR))


class IncompleteMemoryMutation(ValueError):
    """Historical partial state has no sufficient durable recovery evidence."""


class MemoryOwnershipReview(ValueError):
    """An explicit ownership or legacy migration decision is required."""


@dataclass
class Memory:
    memory_id: str
    memory_type: str
    content: str
    created_at: str
    updated_at: str
    schema_version: int = 1
    status: str = "active"
    importance: float = 0.5
    confidence: float = 1.0
    source_message_ids: tuple = ()
    source_archive_ids: tuple = ()
    supersedes: str | None = None
    instance_id: str | None = None
    source_work_item_ids: tuple = ()

    def to_dict(self):
        return asdict(self)


def _ensure_memory_dir():
    MEMORY_RECORDS_DIR.mkdir(parents=True, exist_ok=True)
    MEMORY_EVENTS_DIR.mkdir(parents=True, exist_ok=True)


def _memory_path(memory_id: str) -> Path:
    return MEMORY_RECORDS_DIR / f"{memory_id}.json"



def _event_path(event_id: str) -> Path:
    return MEMORY_EVENTS_DIR / f"{event_id}.json"


def _write_json(path: Path, payload):
    """Stage complete record/event postimages in the current local mutation."""
    _validate_evidence(payload,path,event=path.parent==MEMORY_EVENTS_DIR)
    write_json(path, payload)


def _retained_evidence(path, *, event=False):
    """Validate the fields consumed by Memory readers before filtering/using them.

    Historical optional fields may remain absent; malformed present fields are
    not defaults, guessed ownership or retryable storage outages.
    """
    value=read_json(path)
    if value is None:
        return None
    return _validate_evidence(value,path,event=event)


def _validate_evidence(value,path,*,event=False):
    def invalid(field):
        raise MemoryRecoveryRequired('Malformed retained Memory '+field+'; explicit recovery required')
    if not isinstance(value,dict):
        invalid('object')
    required=('event_id','memory_id','event_type','created_at') if event else (
        'memory_id','memory_type','content','created_at','updated_at')
    for field in required:
        if not isinstance(value.get(field),str) or (field!='content' and not value[field]):
            invalid(field)
    identity='event_id' if event else 'memory_id'
    if value[identity]!=path.stem:
        invalid(identity+' file binding')
    for field in ('instance_id','supersedes','superseded_by'):
        if field in value and value[field] is not None and (
                not isinstance(value[field],str) or not value[field]):
            invalid(field)
    for field in ('source_work_item_ids','source_message_ids','source_archive_ids'):
        if field in value and (not isinstance(value[field],(list,tuple)) or
                any(not isinstance(item,str) or not item for item in value[field])):
            invalid(field)
    for field in ('confidence','importance'):
        if field in value:
            try:valid=type(value[field]) in (int,float) and math.isfinite(value[field])
            except OverflowError:valid=False
            if not valid:invalid(field)
    if not event and 'confidence' not in value:
        invalid('confidence')
    if 'schema_version' in value and (type(value['schema_version']) is not int or value['schema_version']<0):
        invalid('schema_version')
    if 'status' in value and not isinstance(value['status'],str):
        invalid('status')
    if 'completed_work_item_events' in value:
        mapping=value['completed_work_item_events']
        if not isinstance(mapping,dict) or any(not isinstance(k,str) or not k or
                not isinstance(v,str) or not v for k,v in mapping.items()):
            invalid('completed_work_item_events')
    if 'data' in value and not isinstance(value['data'],dict):
        invalid('data')
    return value


@_transactional
def append_memory_event(
    memory_id: str,
    event_type: str,
    *,
    data=None,
    source_message_ids=(),
    source_archive_ids=(),
    instance_id=None,
    source_work_item_ids=(),
    legacy_unscoped=False,
):
    if not isinstance(instance_id, str) or not instance_id.strip():
        isolated_legacy_harness = (
            MEMORY_RECORDS_DIR != DEFAULT_MEMORY_RECORDS_DIR
            or MEMORY_EVENTS_DIR != DEFAULT_MEMORY_EVENTS_DIR
        )
        if not legacy_unscoped and not isolated_legacy_harness:
            raise ValueError("instance_id is required for new Memory events")
        instance_id = None
    _ensure_memory_dir()

    now = datetime.now(timezone.utc).isoformat()
    event_id = str(uuid.uuid4())

    event = {
        "schema_version": 1,
        "event_id": event_id,
        "memory_id": memory_id,
        "event_type": event_type,
        "created_at": now,
        "data": data or {},
        "source_message_ids": tuple(source_message_ids),
        "source_archive_ids": tuple(source_archive_ids),
        "instance_id": instance_id,
        "source_work_item_ids": tuple(source_work_item_ids),
    }

    path = _event_path(event_id)
    _write_json(path, event)

    return event


@_transactional
def create_memory(
    memory_type: str,
    content: str,
    *,
    importance: float = 0.5,
    confidence: float = 1.0,
    source_message_ids=(),
    source_archive_ids=(),
    supersedes=None,
    instance_id=None,
    source_work_item_ids=(),
    legacy_unscoped=False,
):
    if not isinstance(instance_id, str) or not instance_id.strip():
        isolated_legacy_harness = (
            MEMORY_RECORDS_DIR != DEFAULT_MEMORY_RECORDS_DIR
            or MEMORY_EVENTS_DIR != DEFAULT_MEMORY_EVENTS_DIR
        )
        if not legacy_unscoped and not isolated_legacy_harness:
            raise ValueError("instance_id is required for new Memory records")
        instance_id = None
    _ensure_memory_dir()

    # Deterministic last-line protection against duplicate active memories.
    # This runs locally and never requires a model/provider call.
    candidate = {
        "memory_type": memory_type,
        "content": content,
    }

    candidate_fingerprint = memory_fingerprint(candidate)

    for existing in list_memories_for_context(
        status="active",
        instance_id=instance_id,
        include_unscoped=instance_id is None,
    ):
        if memory_fingerprint(existing) == candidate_fingerprint:
            strengthened = strengthen_memory(
                existing["memory_id"],
                confidence=confidence,
                source_message_ids=source_message_ids,
                source_archive_ids=source_archive_ids,
                source_work_item_ids=source_work_item_ids,
                instance_id=instance_id,
            )

            if strengthened is None:
                return None

            return Memory(
                memory_id=strengthened["memory_id"],
                memory_type=strengthened["memory_type"],
                content=strengthened["content"],
                created_at=strengthened["created_at"],
                updated_at=strengthened["updated_at"],
                schema_version=int(strengthened.get("schema_version", 0)),
                status=strengthened.get("status", "active"),
                importance=float(
                    strengthened.get("importance", importance)
                ),
                confidence=float(
                    strengthened.get("confidence", confidence)
                ),
                source_message_ids=tuple(
                    strengthened.get("source_message_ids", ())
                ),
                source_archive_ids=tuple(
                    strengthened.get("source_archive_ids", ())
                ),
                supersedes=strengthened.get("supersedes"),
                instance_id=strengthened.get("instance_id"),
                source_work_item_ids=tuple(
                    strengthened.get("source_work_item_ids", ())
                ),
            )

    now = datetime.now(timezone.utc).isoformat()

    memory_id = str(uuid.uuid4())

    memory = Memory(
        memory_id=memory_id,
        memory_type=memory_type,
        content=content,
        created_at=now,
        updated_at=now,
        importance=importance,
        confidence=confidence,
        source_message_ids=tuple(source_message_ids),
        source_archive_ids=tuple(source_archive_ids),
        supersedes=supersedes,
        instance_id=instance_id,
        source_work_item_ids=tuple(source_work_item_ids),
    )

    path = _memory_path(memory_id)
    payload = memory.to_dict()

    _write_json(path, payload)

    event = append_memory_event(
        memory.memory_id,
        "created",
        data={
            "memory_type": memory.memory_type,
            "content": memory.content,
            "importance": memory.importance,
            "confidence": memory.confidence,
            "status": memory.status,
            "supersedes": memory.supersedes,
        },
        source_message_ids=memory.source_message_ids,
        source_archive_ids=memory.source_archive_ids,
        instance_id=memory.instance_id,
        source_work_item_ids=memory.source_work_item_ids,
        legacy_unscoped=legacy_unscoped,
    )

    _bind_completed_work(payload,event,(),source_work_item_ids)

    return memory


@_transactional
def revise_memory(
    memory_id: str,
    *,
    content=None,
    memory_type=None,
    importance=None,
    confidence=None,
    status=None,
    source_message_ids=(),
    source_archive_ids=(),
    source_work_item_ids=(),
    instance_id=None,
):
    current = load_memory(memory_id)

    if current is None:
        return None

    previous = dict(current)

    if instance_id is not None:
        current_instance = current.get("instance_id")
        if current_instance is None:
            raise ValueError("legacy unscoped memory requires an explicit migration decision")
        if current_instance != instance_id:
            raise ValueError("Cannot revise memory owned by another instance")
    elif current.get("instance_id") is not None:
        raise ValueError("instance_id is required to revise a scoped memory")

    if content is not None:
        current["content"] = content
    if memory_type is not None:
        current["memory_type"] = memory_type
    if importance is not None:
        current["importance"] = importance
    if confidence is not None:
        current["confidence"] = confidence
    if status is not None:
        current["status"] = status

    current["source_message_ids"] = sorted(
        set(current.get("source_message_ids", ())) | set(source_message_ids)
    )
    current["source_archive_ids"] = sorted(
        set(current.get("source_archive_ids", ())) | set(source_archive_ids)
    )
    current["source_work_item_ids"] = sorted(
        set(current.get("source_work_item_ids", ())) | set(source_work_item_ids)
    )

    current["updated_at"] = datetime.now(timezone.utc).isoformat()

    path = _memory_path(memory_id)
    _write_json(path, current)

    event = append_memory_event(
        memory_id,
        "revised",
        data={
            "previous": previous,
            "current": current,
        },
        source_message_ids=source_message_ids,
        source_archive_ids=source_archive_ids,
        instance_id=current.get("instance_id"),
        source_work_item_ids=source_work_item_ids,
    )

    _bind_completed_work(current,event,previous.get('source_work_item_ids',()),source_work_item_ids)

    return current


@_transactional
def strengthen_memory(
    memory_id: str,
    *,
    confidence: float,
    source_message_ids=(),
    source_archive_ids=(),
    source_work_item_ids=(),
    instance_id=None,
    _inherited_work_items=False,
    _inherited_from_memory_id=None,
):
    current = load_memory(memory_id)
    if current is None:
        return None

    if instance_id is not None:
        current_instance = current.get("instance_id")
        if current_instance is None:
            raise ValueError("legacy unscoped memory requires an explicit migration decision")
        if current_instance != instance_id:
            raise ValueError("Cannot strengthen memory owned by another instance")
    elif current.get("instance_id") is not None:
        raise ValueError("instance_id is required to strengthen a scoped memory")

    if _inherited_work_items:
        donor=load_memory(_inherited_from_memory_id) if _inherited_from_memory_id else None
        if (donor is None or donor.get('instance_id')!=instance_id
            or donor['memory_id']==memory_id
            or not set(source_work_item_ids)<=set(donor.get('source_work_item_ids',()))):
            raise IncompleteMemoryMutation('Inherited work requires its actual owned donor record')

    old_confidence = float(current["confidence"])
    evidence_confidence = max(0.0, min(1.0, float(confidence)))

    existing_message_ids = set(
        current.get("source_message_ids", ())
    )
    existing_archive_ids = set(
        current.get("source_archive_ids", ())
    )
    existing_work_item_ids = set(
        current.get("source_work_item_ids", ())
    )

    new_messages = set(source_message_ids) - existing_message_ids
    new_archives = set(source_archive_ids) - existing_archive_ids
    new_work_items = set(source_work_item_ids) - existing_work_item_ids
    if not (new_messages or new_archives or new_work_items):
        return current
    replayed_work = bool(set(source_work_item_ids) & existing_work_item_ids)
    # When immutable Archive IDs exist, a new message alias for the same
    # archived evidence is not independent corroboration.
    # Both known identity dimensions must be independently new when supplied.
    # Adding an Archive attribution to an already known message is provenance
    # completion, not additional corroboration (historical mapping is unknown).
    new_evidence = bool(new_archives if source_archive_ids else new_messages) and not replayed_work
    if source_message_ids and set(source_message_ids) & existing_message_ids:
        new_evidence = False
    if set(source_archive_ids) & existing_archive_ids:
        new_evidence = False
    new_confidence = (
        1.0 - ((1.0 - old_confidence) * (1.0 - evidence_confidence))
        if new_evidence else old_confidence
    )

    existing_message_ids.update(source_message_ids)
    existing_archive_ids.update(source_archive_ids)
    previous_work_items = set(existing_work_item_ids)
    existing_work_item_ids.update(source_work_item_ids)

    current["confidence"] = new_confidence
    current["source_message_ids"] = sorted(existing_message_ids)
    current["source_archive_ids"] = sorted(existing_archive_ids)
    current["source_work_item_ids"] = sorted(existing_work_item_ids)
    current["updated_at"] = datetime.now(timezone.utc).isoformat()

    path = _memory_path(memory_id)
    _write_json(path, current)

    event = append_memory_event(
        memory_id,
        "strengthened",
        data={
            "previous_confidence": old_confidence,
            "evidence_confidence": evidence_confidence,
            "current_confidence": new_confidence,
        },
        source_message_ids=source_message_ids,
        source_archive_ids=source_archive_ids,
        instance_id=current.get("instance_id"),
        source_work_item_ids=source_work_item_ids,
    )

    if not _inherited_work_items:
        _bind_completed_work(current,event,previous_work_items,source_work_item_ids)
    elif source_work_item_ids:
        # Newly staged merge provenance, not a claim that this target executed
        # the donor's work. Historical events are never retrofitted.
        event['data']['inherited_from_memory_id']=_inherited_from_memory_id
        _write_json(_event_path(event['event_id']),event)

    return current


@_transactional
def quarantine_memory(memory_id: str, *, reason: str, actor: str, instance_id=None):
    """Remove derived memory from active retrieval without deleting history."""
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("quarantine reason is required")
    if not isinstance(actor, str) or not actor.strip():
        raise ValueError("quarantine actor is required")
    current = load_memory(memory_id)
    if current is None:
        return None
    _require_owner(current, instance_id)
    if current.get("status") == "quarantined":
        return current
    if current.get("status") != "active":
        raise ValueError("only active memories may be quarantined")

    previous = dict(current)
    now = datetime.now(timezone.utc).isoformat()
    current["status"] = "quarantined"
    current["updated_at"] = now
    current["quarantined_at"] = now
    current["quarantine_reason"] = reason.strip()
    current["quarantined_by"] = actor.strip()
    _write_json(_memory_path(memory_id), current)
    append_memory_event(
        memory_id,
        "quarantined",
        data={
            "previous_status": previous.get("status"),
            "current_status": "quarantined",
            "reason": reason.strip(),
            "actor": actor.strip(),
        },
        source_message_ids=current.get("source_message_ids", ()),
        source_archive_ids=current.get("source_archive_ids", ()),
        instance_id=current.get("instance_id"),
        source_work_item_ids=current.get("source_work_item_ids", ()),
    )
    return current


def _require_owner(current, instance_id):
    if current.get('instance_id') != instance_id:
        raise MemoryOwnershipReview('Explicit matching instance_id or legacy migration decision is required for Memory mutation')


def _bind_completed_work(current, event, previous_work_items, operation_work_items):
    """Bind newly introduced work to its actual event in this same transaction.

    Existing provenance without a completion binding cannot be repaired merely
    by copying it into a later event. Quarantine/merge history is not completion.
    """
    mapping = dict(current.get('completed_work_item_events', {}))
    introduced = set(operation_work_items) - set(previous_work_items)
    for work_id in introduced:
        mapping[work_id] = event['event_id']
    if operation_work_items:
        # This is a newly staged event, never a retrofit to historical evidence.
        # Older created/strengthened events could have been only the first half
        # of supersession; their operation type must not be inferred on replay.
        event['data']['work_completion_kind'] = (
            'supersession' if event['event_type']=='supersession_completed' else 'record_change')
        event['data']['completed_work_item_ids']=sorted(introduced)
        _write_json(_event_path(event['event_id']),event)
    if mapping:
        current['completed_work_item_events'] = mapping
        _write_json(_memory_path(current['memory_id']),current)


@_transactional
def supersede_memory(
    memory_id: str,
    memory_type: str,
    content: str,
    *,
    importance: float = 0.5,
    confidence: float = 1.0,
    source_message_ids=(),
    source_archive_ids=(),
    instance_id=None,
    source_work_item_ids=(),
):
    old = load_memory(memory_id)

    if old is None:
        return None

    _require_owner(old, instance_id)
    if old.get('status') != 'active':
        raise ValueError('Only active Memory may be superseded')
    if memory_fingerprint(old) == memory_fingerprint({'memory_type':memory_type,'content':content}):
        raise ValueError('A Memory cannot supersede itself with identical content')
    for work_id in source_work_item_ids:
        if find_memory_by_work_item(work_id,instance_id=instance_id) is not None:
            raise IncompleteMemoryMutation('Supersession work already has a completed operation; reconcile rather than rebind it')

    # Observe replacement-side history before this operation, under the same
    # transaction lock. Reuse may strengthen a record or leave it unchanged.
    fingerprint=memory_fingerprint({'memory_type':memory_type,'content':content})
    previous_events={item['memory_id']:{event['event_id'] for event in list_memory_events(item['memory_id'])}
        for item in list_memories_for_context(instance_id=instance_id)
        if memory_fingerprint(item)==fingerprint}

    new_memory = create_memory(
        memory_type,
        content,
        importance=importance,
        confidence=confidence,
        source_message_ids=source_message_ids,
        source_archive_ids=source_archive_ids,
        supersedes=memory_id,
        instance_id=instance_id,
        # Creation or strengthening is not completion of the retirement.
        source_work_item_ids=(),
    )
    emitted=[event for event in list_memory_events(new_memory.memory_id)
             if event['event_id'] not in previous_events.get(new_memory.memory_id,set())]
    if new_memory.memory_id not in previous_events:
        expected='created'
    elif emitted:
        expected='strengthened'
    else:
        expected='unchanged_reuse'
    if expected=='unchanged_reuse':
        replacement_change={'kind':expected,'event_id':None,'event_sha256':None}
    else:
        if len(emitted)!=1 or emitted[0]['event_type']!=expected:
            raise IncompleteMemoryMutation('Supersession replacement has an ambiguous mutation history')
        replacement_change={'kind':expected,'event_id':emitted[0]['event_id'],
                            'event_sha256':_event_digest(emitted[0])}

    old["status"] = "superseded"
    old["superseded_by"] = new_memory.memory_id
    old["updated_at"] = datetime.now(timezone.utc).isoformat()

    old_path = _memory_path(memory_id)
    _write_json(old_path, old)

    retirement = append_memory_event(
        memory_id,
        "superseded",
        data={
            "superseded_by": new_memory.memory_id,
        },
        source_message_ids=source_message_ids,
        source_archive_ids=source_archive_ids,
        instance_id=old.get("instance_id"),
        source_work_item_ids=source_work_item_ids,
    )

    replacement = load_memory(new_memory.memory_id)
    previous_work = replacement.get('source_work_item_ids',())
    completion = append_memory_event(
        new_memory.memory_id,'supersession_completed',
        data={'retired_memory_id':memory_id,'retirement_event_id':retirement['event_id'],
              'replacement_memory_id':new_memory.memory_id,
              'replacement_change':replacement_change,
              'retirement_event_sha256':_event_digest(retirement)},
        source_message_ids=source_message_ids,source_archive_ids=source_archive_ids,
        source_work_item_ids=source_work_item_ids,instance_id=instance_id)
    replacement['source_work_item_ids'] = sorted(set(previous_work) | set(source_work_item_ids))
    replacement['updated_at'] = completion['created_at']
    _write_json(_memory_path(new_memory.memory_id),replacement)
    _bind_completed_work(replacement,completion,previous_work,source_work_item_ids)
    new_memory.source_work_item_ids = tuple(replacement['source_work_item_ids'])
    new_memory.updated_at = replacement['updated_at']

    return new_memory


@_transactional
def load_memory(memory_id: str):
    path = _memory_path(memory_id)

    return _retained_evidence(path)


@_transactional
def list_memory_events(memory_id: str):
    """Return the append-only derivation history for one memory."""
    _ensure_memory_dir()
    events = []
    for path in json_paths(MEMORY_EVENTS_DIR):
        event = _retained_evidence(path,event=True)
        if event is None:
            raise MemoryRecoveryRequired('Listed Memory event disappeared during a serialized read')
        if event.get("memory_id") == memory_id:
            events.append(event)
    return sorted(events, key=lambda event: event.get("created_at", ""))


@_transactional
def list_memories(
    status="active",
    *,
    instance_id=None,
    include_unscoped=False,
):
    _ensure_memory_dir()

    memories = []

    for path in json_paths(MEMORY_RECORDS_DIR):
        # Absence must not be inferred from a storage error: that would hide a
        # prior work-item mutation and permit duplicate processing on retry.
        memory = _retained_evidence(path)
        if memory is None:
            raise MemoryRecoveryRequired('Listed Memory record disappeared during a serialized read')

        if status is not None and memory.get("status") != status:
            continue

        if instance_id is not None:
            memory_instance_id = memory.get("instance_id")
            if memory_instance_id != instance_id and not (
                include_unscoped and memory_instance_id is None
            ):
                continue

        memories.append(memory)

    return memories


def list_memories_for_context(*, status="active", instance_id=None, include_unscoped=False):
    """Select processing context; None means legacy, not administrative all-owners.

    Explicit include_unscoped permits reading legacy context alongside a named
    owner, not mutating or assigning that context to the named owner.
    list_memories retains its administrative all-owner listing contract.
    """
    memories = list_memories(status=status, instance_id=instance_id, include_unscoped=include_unscoped)
    if instance_id is None:
        return [memory for memory in memories if memory.get("instance_id") is None]
    return memories


@_transactional
def find_memory_by_work_item(work_item_id: str, *, instance_id: str):
    """Find a prior memory mutation so a retried work item is harmless."""
    completed = []
    inherited = False
    # A missing result record is not proof that no operation happened: the
    # append-only events may still identify it. Never duplicate known work just
    # because its record/provenance half is absent after an incomplete restore.
    work_events=[];event_records={};inherited_edges={};verified_retirements=set()
    _ensure_memory_dir()
    for path in json_paths(MEMORY_EVENTS_DIR):
        event=_retained_evidence(path,event=True)
        if event is None:
            raise MemoryRecoveryRequired('Listed Memory event disappeared during a serialized read')
        if event.get('instance_id')==instance_id and work_item_id in event.get('source_work_item_ids',()):
            work_events.append(event)
            record=load_memory(event['memory_id'])
            if record is None or record.get('instance_id')!=instance_id:
                raise IncompleteMemoryMutation('Work-item event has no matching owned Memory record; explicit recovery required')
            event_records[record['memory_id']]=record
            if event['event_type']!='superseded' and work_item_id not in record.get('source_work_item_ids',()):
                raise IncompleteMemoryMutation('Retained work operation conflicts with its record preimage; explicit recovery required')
            data=event.get('data',{});kind=data.get('work_completion_kind')
            if kind is not None:
                expected='supersession' if event['event_type']=='supersession_completed' else 'record_change'
                declared=data.get('completed_work_item_ids',event.get('source_work_item_ids',()))
                if (event['event_type'] not in ('created','revised','strengthened','supersession_completed')
                    or kind!=expected or not isinstance(declared,(list,tuple))
                    or not declared and event['event_type'] not in ('revised','strengthened')
                    or any(not isinstance(v,str) or not v for v in declared)
                    or len(set(declared))!=len(declared)
                    or not set(declared)<=set(event.get('source_work_item_ids',()))):
                    raise IncompleteMemoryMutation('Work operation declaration is malformed')
                if any(record.get('completed_work_item_events',{}).get(item)!=event['event_id'] for item in declared):
                    raise IncompleteMemoryMutation('Declared work operation lacks its exact record binding')
            donor=data.get('inherited_from_memory_id')
            if donor is not None:
                if (event['event_type']!='strengthened' or not isinstance(donor,str)
                    or not donor or donor==record['memory_id'] or kind is not None):
                    raise IncompleteMemoryMutation('Inherited work declaration is malformed')
                donor_record=load_memory(donor)
                if (donor_record is None or donor_record.get('instance_id')!=instance_id
                    or work_item_id not in donor_record.get('source_work_item_ids',())):
                    raise IncompleteMemoryMutation('Inherited work donor evidence is unavailable')
                inherited_edges.setdefault(record['memory_id'],set()).add(donor)
    inherited_records=set()
    for memory in list_memories(status=None, instance_id=instance_id):
        if work_item_id in memory.get("source_work_item_ids", ()):
            events = list_memory_events(memory['memory_id'])
            completion = memory.get('completed_work_item_events',{})
            if not isinstance(completion,dict):
                raise IncompleteMemoryMutation('Memory work-item completion binding is malformed')
            bound_event = completion.get(work_item_id)
            if not bound_event:
                # A merge copies provenance, not the donor's completion. Keep
                # searching for the actual donor regardless of filename order.
                inherited = True
                inherited_records.add(memory['memory_id'])
                continue
            matching = [event for event in events if event.get('event_id')==bound_event
                       and event.get('event_type') in {'created','revised','strengthened','supersession_completed'}
                       and work_item_id in event.get('source_work_item_ids',())
                       and event.get('instance_id')==instance_id]
            if len(matching)!=1:
                raise IncompleteMemoryMutation('Memory work-item record lacks its completed event evidence')
            event=matching[0];data=event.get('data',{})
            expected_kind='supersession' if event['event_type']=='supersession_completed' else 'record_change'
            if data.get('work_completion_kind')!=expected_kind:
                raise IncompleteMemoryMutation('Historical work completion lacks an explicit operation declaration; review required')
            if work_item_id not in data.get('completed_work_item_ids',event.get('source_work_item_ids',())):
                raise IncompleteMemoryMutation('Record completion contradicts its declared work operation')
            if expected_kind=='supersession':
                change=data.get('replacement_change')
                if not isinstance(change,dict) or set(change)!={'kind','event_id','event_sha256'}:
                    raise IncompleteMemoryMutation('Supersession lacks an explicit replacement mutation binding')
                if change['kind']=='unchanged_reuse':
                    if change['event_id'] is not None or change['event_sha256'] is not None:
                        raise IncompleteMemoryMutation('Unchanged replacement reuse has contradictory event evidence')
                elif change['kind'] in ('created','strengthened'):
                    replacement_events=[item for item in events
                        if item['event_id']==change['event_id'] and item['event_type']==change['kind']
                        and item.get('instance_id')==instance_id
                        and _event_digest(item)==change['event_sha256']]
                    if len(replacement_events)!=1:
                        raise IncompleteMemoryMutation('Supersession lacks its exact replacement mutation event')
                else:
                    raise IncompleteMemoryMutation('Supersession replacement operation kind is unknown')
                retired_id=data.get('retired_memory_id');retirement_id=data.get('retirement_event_id')
                if (not isinstance(retired_id,str) or not retired_id or retired_id==memory['memory_id']
                    or not isinstance(retirement_id,str) or not retirement_id
                    or data.get('replacement_memory_id')!=memory['memory_id']):
                    raise IncompleteMemoryMutation('Supersession completion has invalid retirement binding')
                retired=load_memory(retired_id)
                retirement=[item for item in list_memory_events(retired_id)
                    if item['event_id']==retirement_id and item['event_type']=='superseded'
                    and item.get('instance_id')==instance_id
                    and work_item_id in item.get('source_work_item_ids',())
                    and item.get('data',{}).get('superseded_by')==memory['memory_id']
                    and _event_digest(item)==data.get('retirement_event_sha256')]
                if (retired is None or retired.get('instance_id')!=instance_id
                    or retired.get('status')!='superseded'
                    or retired.get('superseded_by')!=memory['memory_id'] or len(retirement)!=1):
                    raise IncompleteMemoryMutation('Supersession completion lacks its exact retired record and event')
                verified_retirements.add(retirement_id)
            if memory.get('supersedes'):
                old = load_memory(memory['supersedes'])
                old_events = list_memory_events(memory['supersedes'])
                if old is None or old.get('instance_id') != instance_id or old.get('status') != 'superseded' or old.get('superseded_by') != memory['memory_id'] or not any(
                    event.get('event_type')=='superseded' and event.get('instance_id')==instance_id
                    and event.get('data',{}).get('superseded_by')==memory['memory_id'] for event in old_events
                ):
                    raise IncompleteMemoryMutation('Historical supersession lacks complete retirement evidence; explicit recovery required')
            completed.append(memory)
    if len(completed) > 1:
        raise IncompleteMemoryMutation('Work item has multiple completed Memory operations; explicit reconciliation required')
    if completed:
        # Reconcile every operation half before selecting the surviving result.
        # Inherited merge/quarantine history may point to the actual donor, but
        # cannot provide an alternate completion or hide an unbound operation.
        resolved={completed[0]['memory_id']};pending=set(inherited_records)
        while pending:
            ready={memory_id for memory_id in pending
                   if inherited_edges.get(memory_id) and inherited_edges[memory_id]<=resolved}
            if not ready:
                raise IncompleteMemoryMutation('Unbound work provenance lacks its completed donor lineage')
            resolved.update(ready);pending-=ready
        for event in work_events:
            if event['event_type']=='superseded':
                if event['event_id'] not in verified_retirements:
                    raise IncompleteMemoryMutation('Retained retirement lacks its completed supersession operation')
            elif event['memory_id'] in inherited_records:
                data=event.get('data',{})
                # A later real operation may mention old inherited provenance
                # while explicitly completing only other work (or none). Its
                # declaration and every claimed record binding were validated
                # above. This does not supply the older donor's completion.
                subsequent=(data.get('work_completion_kind')=='record_change'
                            and 'completed_work_item_ids' in data
                            and work_item_id not in data['completed_work_item_ids'])
                if not (event['event_type']=='quarantined' or
                        event['event_type']=='strengthened' and data.get('inherited_from_memory_id')
                        or subsequent):
                    raise IncompleteMemoryMutation('Unbound operation cannot be classified as inherited provenance')
        return completed[0]
    if inherited or work_events:
        raise IncompleteMemoryMutation('Memory work-item record lacks its completed event evidence')
    return None


def _event_digest(event):
    return hashlib.sha256(json.dumps(event,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode('utf-8')).hexdigest()


def memory_fingerprint(memory: dict):
    material = json.dumps(
        {
            "memory_type": memory.get("memory_type"),
            "content": memory.get("content"),
        },
        sort_keys=True,
        ensure_ascii=False,
    )

    return hashlib.sha256(
        material.encode("utf-8")
    ).hexdigest()


@_transactional
def mark_memory_superseded(
    memory_id: str,
    *,
    superseded_by: str,
    source_message_ids=(),
    source_archive_ids=(),
    source_work_item_ids=(),
    instance_id=None,
):
    """
    Mark an existing memory as superseded without creating a replacement.

    Used when consolidating an already-existing duplicate into another
    canonical memory. The historical record remains intact.
    """
    current = load_memory(memory_id)

    if current is None:
        return None
    _require_owner(current, instance_id)
    replacement = load_memory(superseded_by)
    if replacement is None or replacement['memory_id'] == memory_id:
        raise ValueError('A distinct existing replacement Memory is required')
    _require_owner(replacement, instance_id)

    if current.get("status") == "superseded":
        if current.get('superseded_by') != superseded_by:
            raise ValueError('Memory already superseded by a different record')
        return current
    if current.get('status') != 'active' or replacement.get('status') != 'active':
        raise ValueError('Duplicate consolidation requires active Memory records')

    current["status"] = "superseded"
    current["superseded_by"] = superseded_by
    current["updated_at"] = datetime.now(timezone.utc).isoformat()

    path = _memory_path(memory_id)
    _write_json(path, current)

    append_memory_event(
        memory_id,
        "superseded",
        data={
            "superseded_by": superseded_by,
            "reason": "semantic_duplicate_consolidation",
        },
        source_message_ids=source_message_ids,
        source_archive_ids=source_archive_ids,
        instance_id=current.get("instance_id"),
        source_work_item_ids=source_work_item_ids,
    )

    return current


@_transactional
def merge_duplicate_memories(canonical_id, duplicate_id, *, instance_id=None):
    """Publish evidence merge and duplicate retirement as one recoverable unit."""
    canonical = load_memory(canonical_id)
    duplicate = load_memory(duplicate_id)
    if canonical is None or duplicate is None or canonical_id == duplicate_id:
        raise ValueError('Two distinct existing memories are required')
    _require_owner(canonical,instance_id)
    _require_owner(duplicate,instance_id)
    if duplicate.get('status') == 'superseded' and duplicate.get('superseded_by') == canonical_id:
        return canonical
    if canonical.get('status') != 'active' or duplicate.get('status') != 'active':
        raise ValueError('Duplicate merge requires active memories')
    strengthened = strengthen_memory(canonical_id,instance_id=instance_id,
        confidence=float(duplicate.get('confidence',1.0)),
        source_message_ids=duplicate.get('source_message_ids',()),
        source_archive_ids=duplicate.get('source_archive_ids',()),
        source_work_item_ids=duplicate.get('source_work_item_ids',()),_inherited_work_items=True,
        _inherited_from_memory_id=duplicate_id)
    mark_memory_superseded(duplicate_id,superseded_by=canonical_id,instance_id=instance_id)
    return strengthened

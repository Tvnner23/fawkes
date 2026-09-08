import tempfile
import unittest
import json
import hashlib
from unittest.mock import patch
from pathlib import Path

from src.library.store import (
    backup_instance_library, instance_library_paths, register_source,
    restore_instance_library, save_extraction, search_extractions, list_sources,
    list_extractions, record_extraction_failure,
)
from src.library import store as library_store
from src.library.artifacts import retention_intent
from src.library.artifacts import lifecycle_event
from src.library.storage import (
    LocalImmutableBlobStore, create_verified_backup, restore_verified_backup,
)


class FawkesLibraryStoreTests(unittest.TestCase):
    def registration(self, root, instance='one'):
        paths = instance_library_paths(instance, library_root=root)
        return dict(raw_bytes=b'fixture document', title='Fixture', media_type='text/plain',
            instance_id=instance,
            retention_intent=retention_intent(actor_type='rider', principal_id='rider-'+instance),
            originals_dir=paths['originals'], sources_dir=paths['sources'], events_dir=paths['events'],
            correlation_id='original-operation', causation_id='original-message',
            provenance=({'relation':'derived_from','target_kind':'temporary_media','target_id':'original-upload'},))

    def test_registration_rejects_cross_instance_metadata_directory_links(self):
        for name in ('sources', 'events', 'originals'):
            with self.subTest(directory=name), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                one = instance_library_paths('one', library_root=root)
                two = instance_library_paths('two', library_root=root)
                one['root'].mkdir(parents=True)
                two[name].mkdir(parents=True)
                sentinel = two[name]/'sentinel'
                sentinel.write_bytes(b'other instance must stay untouched')
                one[name].symlink_to(two[name], target_is_directory=True)
                with self.assertRaisesRegex(ValueError, 'symlink'):
                    register_source(**self.registration(root))
                self.assertEqual(list(two[name].iterdir()), [sentinel])
                self.assertEqual(sentinel.read_bytes(), b'other instance must stay untouched')

    def test_metadata_catalog_rejects_directory_and_record_symlinks(self):
        for directory in ('sources', 'extractions'):
            for link_kind in ('directory', 'record'):
                with self.subTest(directory=directory, link=link_kind), tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    paths = instance_library_paths('one', library_root=root)
                    other = root/'other'
                    other.mkdir()
                    record = other/'record.json'
                    record.write_text(json.dumps({'schema_version':2,'instance_id':'one',
                        'source_id':'fixture','title':'Fixture','segments':[]}))
                    paths['root'].mkdir(parents=True)
                    if link_kind == 'directory':
                        paths[directory].symlink_to(other, target_is_directory=True)
                    else:
                        paths[directory].mkdir()
                        (paths[directory]/'record.json').symlink_to(record)
                    operations = [lambda: search_extractions('fixture', instance_id='one', library_root=root)]
                    if directory == 'sources':
                        operations.append(lambda: list_sources(instance_id='one', library_root=root))
                    else:
                        operations.append(lambda: list_extractions(instance_id='one', library_root=root))
                    before = record.read_bytes()
                    for operation in operations:
                        with self.assertRaisesRegex(ValueError, 'symlink'):
                            operation()
                    self.assertEqual(record.read_bytes(), before)

    def test_extraction_and_failure_writes_reject_symlink_directories(self):
        for directory in ('sources', 'extractions', 'events'):
            with self.subTest(directory=directory), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                paths = instance_library_paths('one', library_root=root)
                source = register_source(**self.registration(root))
                other = root/'other'
                if paths[directory].exists():
                    paths[directory].rename(other)
                else:
                    other.mkdir()
                paths[directory].symlink_to(other, target_is_directory=True)
                before = {p.name:p.read_bytes() for p in other.iterdir()}
                with self.assertRaisesRegex(ValueError, 'symlink'):
                    save_extraction(source['source_id'], ({'text':'fixture','location':{'page_number':1}},),
                        extractor='fixture', extractor_version='1', instance_id='one',
                        sources_dir=paths['sources'], extractions_dir=paths['extractions'], events_dir=paths['events'])
                if directory == 'events':
                    with self.assertRaisesRegex(ValueError, 'symlink'):
                        record_extraction_failure(source['source_id'], extractor='fixture', extractor_version='1',
                            error_code='synthetic', instance_id='one', events_dir=paths['events'])
                self.assertEqual({p.name:p.read_bytes() for p in other.iterdir()}, before)

    def test_registration_recovers_each_missing_event_from_saved_authority(self):
        for fail_at in (1, 2):
            with self.subTest(event=fail_at), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                kwargs = self.registration(root)
                write_once = library_store._write_json_once
                calls = 0
                def fail_event(path, payload):
                    nonlocal calls
                    if path.parent.name == 'events':
                        calls += 1
                        if calls == fail_at:
                            raise OSError('synthetic event persistence interruption')
                    return write_once(path, payload)
                with patch('src.library.store._write_json_once', side_effect=fail_event):
                    with self.assertRaisesRegex(OSError, 'interruption'):
                        register_source(**kwargs)
                source_path, = kwargs['sources_dir'].glob('*.json')
                before_source = source_path.read_bytes()
                before_events = {p:p.read_bytes() for p in kwargs['events_dir'].glob('*.json')}
                self.assertEqual(len(before_events), fail_at-1)
                # Retry supplies fresh input, but the persisted registration is
                # authoritative for its event identities and attribution.
                retry = {**kwargs, 'correlation_id':'different-retry-operation',
                    'causation_id':'different-retry-message', 'provenance':(),
                    'retention_intent':retention_intent(actor_type='rider', principal_id='rider-one')}
                recovered = register_source(**retry)
                self.assertTrue(recovered['_replayed'])
                self.assertEqual(source_path.read_bytes(), before_source)
                for path, content in before_events.items():
                    self.assertEqual(path.read_bytes(), content)
                events = [json.loads(p.read_text()) for p in kwargs['events_dir'].glob('*.json')]
                self.assertEqual(len(events), 2)
                requested = next(e for e in events if e['event_type']=='library.retention.requested')
                durable = next(e for e in events if e['event_type']=='library.artifact.durable_registered')
                self.assertEqual(requested['correlation_id'], 'original-operation')
                self.assertEqual(requested['causation_id'], 'original-message')
                self.assertEqual(requested['details']['temporary_source_reference'], 'original-upload')
                self.assertEqual(durable['causation_id'], requested['event_id'])
                self.assertEqual(requested['actor']['principal_id'], 'rider-one')
                complete = {p:p.read_bytes() for p in kwargs['events_dir'].glob('*.json')}
                register_source(**retry)
                self.assertEqual({p:p.read_bytes() for p in kwargs['events_dir'].glob('*.json')}, complete)

    def test_existing_event_symlink_and_conflicting_identity_never_replay_as_success(self):
        for alteration in ('symlink', 'conflict'):
            with self.subTest(alteration=alteration), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                kwargs = self.registration(root)
                register_source(**kwargs)
                path = next(kwargs['events_dir'].glob('*.json'))
                original = path.read_bytes()
                if alteration == 'symlink':
                    outside = root/'other-event.json'
                    path.rename(outside)
                    path.symlink_to(outside)
                else:
                    event = json.loads(original)
                    event['actor'] = {'actor_type':'rider','principal_id':'other-owner'}
                    path.write_text(json.dumps(event))
                with self.assertRaises(ValueError):
                    register_source(**kwargs)
                if alteration == 'symlink':
                    self.assertEqual(outside.read_bytes(), original)

    def test_concurrent_record_publication_preserves_first_writer(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'record.json'
            original_link = library_store.os.link
            def racing_link(source, destination):
                destination.write_text('{"winner": "first"}')
                return original_link(source, destination)
            with patch('src.library.store.os.link', side_effect=racing_link):
                saved = library_store._write_json_once(path, {'winner':'late'})
            self.assertEqual(saved, {'winner':'first'})
            self.assertEqual(list(Path(tmp).iterdir()), [path])

    def backup_fixture(self, root):
        live = root / 'live'
        live.mkdir()
        (live/'payload.txt').write_bytes(b'fixture')
        return create_verified_backup(live, root/'backups', instance_id='one')[0]

    def test_restore_rejects_added_removed_symlink_and_changed_size(self):
        for change in ('extra', 'removed', 'symlink', 'size'):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                backup = self.backup_fixture(root)
                payload = backup/'library/payload.txt'
                if change == 'extra':
                    (backup/'library/unlisted.txt').write_bytes(b'extra')
                elif change == 'removed':
                    payload.unlink()
                elif change == 'symlink':
                    payload.unlink()
                    payload.symlink_to(root/'live/payload.txt')
                else:
                    manifest = json.loads((backup/'backup_manifest.json').read_text())
                    manifest['files'][0]['size_bytes'] += 1
                    (backup/'backup_manifest.json').write_text(json.dumps(manifest))
                with self.assertRaisesRegex(ValueError, 'integrity'):
                    restore_verified_backup(backup, root/'restored', instance_id='one')
                self.assertFalse((root/'restored').exists())

    def test_restore_rejects_ambiguous_or_escaping_manifest_entries(self):
        for change in ('duplicate', 'escape', 'absolute', 'empty', 'wrong-size', 'wrong-hash', 'missing-files', 'wrong-instance', 'duplicate-key'):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                backup = self.backup_fixture(root)
                path = backup/'backup_manifest.json'
                manifest = json.loads(path.read_text())
                if change == 'duplicate':
                    manifest['files'].append(dict(manifest['files'][0]))
                elif change in {'escape', 'absolute', 'empty'}:
                    manifest['files'][0]['path'] = {'escape': '../outside', 'absolute': str(root/'outside'), 'empty': ''}[change]
                elif change == 'wrong-size':
                    manifest['files'][0]['size_bytes'] = True
                elif change == 'wrong-hash':
                    manifest['files'][0]['sha256'] = 'unverified'
                elif change == 'missing-files':
                    del manifest['files']
                elif change == 'wrong-instance':
                    manifest['instance_id'] = 'two'
                encoded = json.dumps(manifest)
                if change == 'duplicate-key':
                    encoded = encoded.replace('"files":', '"files": [], "files":')
                path.write_text(encoded)
                with self.assertRaises(ValueError):
                    restore_verified_backup(backup, root/'restored', instance_id='one')
                self.assertFalse((root/'restored').exists())

    def test_restore_into_empty_directory_preserves_receipts_and_every_source_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            backup = self.backup_fixture(root)
            first = root/'first'
            first.mkdir()
            receipt = restore_verified_backup(backup, first, instance_id='one')
            (first/'backup_manifest.json').write_bytes(b'ordinary source file, not the envelope')
            second_backup, manifest = create_verified_backup(first, root/'backups', instance_id='one')
            self.assertIn('backup_manifest.json', {item['path'] for item in manifest['files']})
            second = root/'second'
            restore_verified_backup(second_backup, second, instance_id='one')
            self.assertEqual((second/'backup_manifest.json').read_bytes(), b'ordinary source file, not the envelope')
            self.assertEqual(json.loads((second/'restore_receipt.json').read_text()), receipt)
            self.assertEqual(len(list(second.glob('restore_receipt*.json'))), 2)

    def test_restore_staged_mutation_cannot_publish_unverified_live_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            backup = self.backup_fixture(root)
            import shutil
            original = shutil.copytree
            def altered(*args, **kwargs):
                result = original(*args, **kwargs)
                (Path(result)/'payload.txt').write_bytes(b'changed during copying')
                return result
            with patch('src.library.storage.shutil.copytree', side_effect=altered):
                with self.assertRaisesRegex(ValueError, 'staged copy changed'):
                    restore_verified_backup(backup, root/'restored', instance_id='one')
            self.assertFalse((root/'restored').exists())
            self.assertEqual(len(list(root.glob('.restored.restore-*'))), 1)

    def test_backup_restore_rejects_symlink_roots_and_overlapping_locations(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            backup = self.backup_fixture(root)
            (root/'link').symlink_to(root/'live', target_is_directory=True)
            with self.assertRaises(ValueError):
                create_verified_backup(root/'link', root/'backups', instance_id='one')
            with self.assertRaises(ValueError):
                create_verified_backup(root/'live', root/'live/backups', instance_id='one')
            with self.assertRaises(ValueError):
                restore_verified_backup(backup, backup/'library/nested', instance_id='one')
            with self.assertRaises(ValueError):
                restore_verified_backup(backup, root/'link', instance_id='one')
            with self.assertRaises(ValueError):
                create_verified_backup(root/'live', root/'backups', instance_id='../other')

    def test_blob_references_never_escape_or_follow_links(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            blobs = root/'blobs'
            blobs.mkdir()
            outside = root/'outside'
            outside.write_bytes(b'outside')
            (blobs/'link').symlink_to(outside)
            store = LocalImmutableBlobStore(blobs)
            digest = hashlib.sha256(b'outside').hexdigest()
            for reference in ('../outside', str(outside), 'link', 'a/../outside', '', 'a//b', 'a\\b'):
                for operation in ('put', 'verify', 'open_bytes'):
                    with self.subTest(reference=reference, operation=operation), self.assertRaises(ValueError):
                        if operation == 'put':
                            store.put(b'outside', filename=reference)
                        else:
                            getattr(store, operation)(reference, digest)
            store.put(b'valid', filename='nested/valid.bin')
            self.assertEqual(store.open_bytes('nested/valid.bin', hashlib.sha256(b'valid').hexdigest()), b'valid')
            self.assertEqual(outside.read_bytes(), b'outside')

    def test_extraction_source_reference_cannot_escape_to_sibling_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sources = root/'sources'
            sources.mkdir()
            (root/'outside.json').write_text(json.dumps({'instance_id': 'one', 'sha256': '0'*64}))
            with self.assertRaisesRegex(ValueError, 'storage reference'):
                save_extraction('../outside', ({'text':'text','location':{'page_number':1}},),
                    extractor='fixture', extractor_version='1', instance_id='one',
                    sources_dir=sources, extractions_dir=root/'extractions', events_dir=root/'events')
            self.assertFalse((root/'extractions').exists())

    def test_source_original_is_immutable_content_addressed_and_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            kwargs = {
                "raw_bytes": b"a textbook payload",
                "title": "Networking Fundamentals",
                "media_type": "application/pdf",
                "original_filename": "networking.pdf",
                "instance_id": "fawkes",
                "retention_intent": retention_intent(actor_type="rider", principal_id="rider-tanner"),
                "originals_dir": root / "originals",
                "sources_dir": root / "sources",
                "events_dir": root / "events",
            }
            first = register_source(**kwargs)
            second = register_source(**kwargs)

            self.assertEqual(first["source_id"], second["source_id"])
            self.assertTrue(second["_replayed"])
            self.assertEqual(
                (root / "originals" / first["original_blob"]).read_bytes(),
                b"a textbook payload",
            )
            self.assertEqual(first["record_type"], "library_source")

    def test_extraction_retains_page_and_document_hierarchy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = register_source(
                b"pdf",
                title="Networking Fundamentals",
                media_type="application/pdf",
                original_filename="book.pdf",
                instance_id="fawkes",
                retention_intent=retention_intent(actor_type="rider", principal_id="rider-tanner"),
                originals_dir=root / "originals",
                sources_dir=root / "sources",
                events_dir=root / "events",
            )
            extraction = save_extraction(
                source["source_id"],
                (
                    {
                        "text": "A subnet mask separates network and host bits.",
                        "location": {
                            "page_number": 143,
                            "page_label": "143",
                            "chapter": "Chapter 6",
                            "section": "Subnetting",
                            "source_locator": "pdf:page=143",
                        },
                    },
                ),
                extractor="test-pdf-extractor",
                extractor_version="1.0",
                sources_dir=root / "sources",
                extractions_dir=root / "extractions",
                events_dir=root / "events",
                instance_id="fawkes",
            )

        location = extraction["segments"][0]["location"]
        self.assertEqual(location["page_number"], 143)
        self.assertEqual(location["chapter"], "Chapter 6")
        self.assertEqual(location["section"], "Subnetting")
        self.assertEqual(extraction["status"], "derived_rebuildable")

    def test_extraction_rejects_text_without_source_location(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = register_source(
                b"manual",
                title="Manual",
                media_type="text/plain",
                instance_id="fawkes",
                retention_intent=retention_intent(actor_type="rider", principal_id="rider-tanner"),
                originals_dir=root / "originals",
                sources_dir=root / "sources",
                events_dir=root / "events",
            )
            with self.assertRaisesRegex(ValueError, "source location"):
                save_extraction(
                    source["source_id"],
                    ({"text": "Unlocated text", "location": {}},),
                    extractor="test",
                    extractor_version="1",
                    sources_dir=root / "sources",
                    extractions_dir=root / "extractions",
                    events_dir=root / "events",
                    instance_id="fawkes",
                )

    def test_extraction_rejects_invalid_locators_before_publishing_or_events(self):
        cases = [{'page_number':value} for value in (True, False, 0, -1, 1.5, '1')]
        cases += [{field:value} for field in ('page_label','chapter','section','subsection','source_locator')
                  for value in ('', ' \t\n', [], {}, 1, True)]
        cases += [{'unknown_location':'unsupported'}, {'source_locator':None}]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            kwargs = self.registration(root)
            source = register_source(**kwargs)
            paths = instance_library_paths('one',library_root=root)
            before = {p:p.read_bytes() for p in paths['events'].glob('*.json')}
            for location in cases:
                with self.subTest(location=location), self.assertRaises(ValueError):
                    save_extraction(source['source_id'], ({'text':'fixture text','location':location},),
                        extractor='fixture',extractor_version='1',instance_id='one',
                        sources_dir=paths['sources'],extractions_dir=paths['extractions'],events_dir=paths['events'])
                self.assertFalse(paths['extractions'].exists())
                self.assertEqual({p:p.read_bytes() for p in paths['events'].glob('*.json')},before)

    def test_valid_typed_locators_remain_searchable_and_retain_meaning(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = register_source(**self.registration(root))
            paths = instance_library_paths('one',library_root=root)
            cases = [{'page_number':1},{'page_number':2,'page_label':''}]+[{field:' appendix A '} for field in
                ('page_label','chapter','section','subsection','source_locator')]
            for ordinal,location in enumerate(cases):
                result = save_extraction(source['source_id'], ({'text':'fixture text','location':location},),
                    extractor='fixture',extractor_version=str(ordinal),instance_id='one',
                    sources_dir=paths['sources'],extractions_dir=paths['extractions'],events_dir=paths['events'])
                for field,value in location.items():
                    self.assertEqual(result['segments'][0]['location'][field],(value.strip() or None) if isinstance(value,str) else value)
            self.assertEqual(len(search_extractions('fixture',instance_id='one',library_root=root)),len(cases))

    def test_default_library_blobs_are_physically_isolated_per_phoenix(self):
        with tempfile.TemporaryDirectory() as tmp:
            one = instance_library_paths("phoenix-one", library_root=tmp)
            two = instance_library_paths("phoenix-two", library_root=tmp)
        self.assertNotEqual(one["originals"], two["originals"])
        self.assertIn("phoenix-one", str(one["originals"]))

    def test_library_retrieval_preserves_source_and_page_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = instance_library_paths("fawkes", library_root=root)
            source = register_source(
                b"pdf", title="Networking", media_type="application/pdf",
                original_filename="networking.pdf", instance_id="fawkes",
                retention_intent=retention_intent(actor_type="rider", principal_id="rider-tanner"),
                originals_dir=paths["originals"], sources_dir=paths["sources"],
                events_dir=paths["events"],
            )
            save_extraction(
                source["source_id"], ({
                    "text": "ARP resolves an IPv4 address to a MAC address.",
                    "location": {"page_number": 142, "page_label": "128", "section": "ARP"},
                },), extractor="fixture", extractor_version="1",
                sources_dir=paths["sources"], extractions_dir=paths["extractions"],
                events_dir=paths["events"],
                instance_id="fawkes",
            )
            results = search_extractions(
                "Where is ARP explained?", instance_id="fawkes", library_root=root
            )
        self.assertEqual(results[0]["source_title"], "Networking")
        self.assertEqual(results[0]["location"]["page_number"], 142)
        self.assertEqual(results[0]["location"]["page_label"], "128")
        self.assertEqual(results[0]["trust"], "untrusted_library_content")

    def test_new_source_requires_explicit_owner_and_retention(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "instance_id"):
                register_source(b"x", title="X", media_type="text/plain",
                                retention_intent=retention_intent(actor_type="rider", principal_id="rider-one"),
                                originals_dir=Path(tmp) / "o", sources_dir=Path(tmp) / "s",
                                events_dir=Path(tmp) / "e")
            with self.assertRaisesRegex(ValueError, "Keep in Library"):
                register_source(b"x", title="X", media_type="text/plain", instance_id="one",
                                originals_dir=Path(tmp) / "o", sources_dir=Path(tmp) / "s",
                                events_dir=Path(tmp) / "e")

    def test_custom_library_storage_cannot_split_lifecycle_events_to_default_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "custom Library storage requires"):
                register_source(
                    b"x", title="X", media_type="text/plain", instance_id="one",
                    retention_intent=retention_intent(
                        actor_type="rider", principal_id="rider-one"
                    ),
                    originals_dir=Path(tmp) / "originals",
                    sources_dir=Path(tmp) / "sources",
                )

    def test_two_phoenixes_are_isolated_even_for_identical_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = register_source(
                b"same", title="One", media_type="text/plain", instance_id="one",
                retention_intent=retention_intent(actor_type="rider", principal_id="rider-one"),
                originals_dir=Path(tmp) / "one" / "originals", sources_dir=Path(tmp) / "one" / "sources",
                events_dir=Path(tmp) / "one" / "events")
            second = register_source(
                b"same", title="Two", media_type="text/plain", instance_id="two",
                retention_intent=retention_intent(actor_type="rider", principal_id="rider-two"),
                originals_dir=Path(tmp) / "two" / "originals", sources_dir=Path(tmp) / "two" / "sources",
                events_dir=Path(tmp) / "two" / "events")
        self.assertNotEqual(first["source_id"], second["source_id"])
        self.assertEqual(first["artifact"]["owner_principal_id"], "rider-one")
        self.assertEqual(second["artifact"]["owner_principal_id"], "rider-two")

    def test_backup_restore_verifies_and_preserves_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "live"
            register_source(
                b"recoverable", title="Book", media_type="text/plain", instance_id="one",
                retention_intent=retention_intent(actor_type="rider", principal_id="rider-one"),
                originals_dir=instance_library_paths("one", library_root=root)["originals"],
                sources_dir=instance_library_paths("one", library_root=root)["sources"],
                events_dir=instance_library_paths("one", library_root=root)["events"])
            backup, manifest = backup_instance_library("one", Path(tmp) / "backups", library_root=root)
            restored_root = Path(tmp) / "restored"
            restore_instance_library("one", backup, library_root=restored_root)
            restored = list((restored_root / "instances" / "one" / "sources").glob("*.json"))
        self.assertTrue(manifest["files"])
        self.assertEqual(len(restored), 1)

    def test_tampered_backup_is_rejected_without_partial_restore(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "live"
            paths = instance_library_paths("one", library_root=root)
            register_source(b"safe", title="Book", media_type="text/plain", instance_id="one",
                retention_intent=retention_intent(actor_type="rider", principal_id="rider-one"),
                originals_dir=paths["originals"], sources_dir=paths["sources"], events_dir=paths["events"])
            backup, _ = backup_instance_library("one", Path(tmp) / "backups", library_root=root)
            next((backup / "library" / "originals").iterdir()).write_bytes(b"tampered")
            restored_root = Path(tmp) / "restored"
            with self.assertRaisesRegex(ValueError, "integrity"):
                restore_instance_library("one", backup, library_root=restored_root)
            self.assertFalse((restored_root / "instances" / "one").exists())

    def test_legacy_source_is_read_without_silent_migration(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = instance_library_paths("one", library_root=tmp)
            paths["sources"].mkdir(parents=True)
            legacy_path = paths["sources"] / "legacy.json"
            legacy = {"schema_version": 1, "record_type": "library_source", "source_id": "legacy",
                      "instance_id": "one", "title": "Legacy", "sha256": "0" * 64}
            legacy_path.write_text(json.dumps(legacy))
            before = legacy_path.read_bytes()
            from src.library.store import list_sources
            loaded = list_sources(instance_id="one", library_root=tmp)
            after = legacy_path.read_bytes()
        self.assertEqual(loaded[0]["source_id"], "legacy")
        self.assertEqual(before, after)

    def test_lifecycle_rejects_impossible_transition(self):
        with self.assertRaisesRegex(ValueError, "disallowed"):
            lifecycle_event(instance_id="one", artifact_id="artifact-one",
                event_type="invalid", from_state="received_temporary", to_state="searchable",
                actor={"actor_type": "runtime"}, idempotency_key="event-one")


if __name__ == "__main__":
    unittest.main()

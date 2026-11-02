"""Explicit identity review never changes source files or live databases."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from test_legacy_import import flowlines
from inspection_app.imports import preview_import, apply_import
from inspection_app.store import Store
from inspection_app.exports import export_workbook


class ImportResolutionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'duplicates.xlsx'
        self.store = Store(Path(self.tmp.name) / 'plan.db')
        flowlines(self.path, records=[['AG-101', 'Yes', 'Oil', None, 300, None, None, None, '2020-01', '2030-01', None, None, 'First report'], ['AG-101', 'No', 'Oil', None, 400, None, None, None, '2021-02', '2031-02', None, None, 'Second report']])

    def resolve(self, preview, decisions):
        from inspection_app.imports import resolve_import
        return resolve_import(self.store, preview['token'], decisions)

    def asset_rows(self, store=None):
        store = store or self.store
        with closing(sqlite3.connect(store.db_path)) as conn:
            return [store.get_asset(row[0]) for row in conn.execute('SELECT id FROM assets ORDER BY id')]

    def separate(self, preview):
        return [{'row_key': row['row_key'], 'action': 'separate'} for row in preview['conflicts']]

    def test_preview_exposes_original_rows_and_distinct_keys_without_database_changes(self):
        preview = preview_import(self.store, self.path)
        self.assertEqual(len(preview['conflicts']), 2)
        self.assertEqual({row['source_row'] for row in preview['conflicts']}, {4, 5})
        self.assertEqual(len({row['row_key'] for row in preview['conflicts']}), 2)
        self.assertEqual(preview['conflicts'][0]['asset']['service_status_original'], 'Yes')
        self.assertEqual(preview['conflicts'][1]['inspections'][0]['next_inspection_month'], '2031-02')
        self.assertEqual(preview['conflicts'][0]['notes'][0]['note_text'], 'First report')
        self.assertTrue(preview['errors'])
        self.assertEqual(self.asset_rows(), [])

    def test_keep_both_as_separate_assets_and_remember_choices(self):
        first = preview_import(self.store, self.path)
        reviewed = self.resolve(first, self.separate(first))
        self.assertFalse(reviewed['errors'])
        self.assertNotEqual(first['token'], reviewed['token'])
        self.assertEqual(reviewed['additions'], 2)
        self.assertEqual(reviewed['unresolved_count'], 0)
        self.assertEqual(self.asset_rows(), [])
        with self.assertRaises(ValueError): apply_import(self.store, first['token'])
        result = apply_import(self.store, reviewed['token'])
        self.assertTrue(Path(result['backup']).exists())
        rows = self.asset_rows()
        self.assertEqual(len(rows), 2)
        self.assertEqual(len({a['id'] for a in rows}), 2)
        self.assertEqual({a['service_status_original'] for a in rows}, {'Yes', 'No'})
        again = preview_import(self.store, self.path)
        self.assertFalse(again['errors'])
        self.assertEqual(again['remembered_count'], 2)
        self.assertEqual(again['additions'], 0)
        self.assertEqual(again['updates'], 2)

    def test_reviewing_saved_separate_choices_does_not_create_more_assets(self):
        first = preview_import(self.store, self.path)
        reviewed = self.resolve(first, self.separate(first))
        apply_import(self.store, reviewed['token'])
        again = preview_import(self.store, self.path)
        reviewed = self.resolve(again, self.separate(again))
        self.assertEqual(reviewed['additions'], 0)
        self.assertEqual(reviewed['updates'], 2)

    def test_unnamed_asset_can_match_by_preserved_oracle_description(self):
        from inspection_app.imports import _resolve_legacy_ids
        asset = self.store.save_asset(None, {'name': '(unnamed asset)', 'family': 'Vessel / tank', 'source_sheet': 'Vessels & TKs', 'oracle_description': 'Sep-204'}, None)
        data = {name: [] for name in ('Assets', 'Inspection Plan', 'Technical Details', 'Notes & Actions', 'Review Items', 'Source Cells')}
        data['Assets'] = [{'asset_id': 'A01-0265', 'source_sheet': 'Vessels & TKs', 'source_row': 265, 'asset_family': 'Vessel / tank', 'asset_description': None, 'oracle_description': 'Sep-204'}]
        self.assertFalse(_resolve_legacy_ids(self.store, data))
        self.assertEqual(data['Assets'][0]['asset_id'], asset['id'])

    def test_skip_one_preserves_its_source_evidence_and_never_deletes_existing_assets(self):
        existing = self.store.save_asset(None, {'name': 'Existing retained', 'family': 'Flowline', 'source_sheet': 'FLs'}, None)
        preview = preview_import(self.store, self.path)
        decisions = self.separate(preview); decisions[1]['action'] = 'skip'
        reviewed = self.resolve(preview, decisions)
        self.assertFalse(reviewed['errors'])
        self.assertEqual(reviewed['counts']['Assets'], 1)
        self.assertEqual(reviewed['skipped_count'], 1)
        self.assertTrue(reviewed['partial'])
        with self.assertRaises(ValueError): apply_import(self.store, reviewed['token'], 'replace')
        apply_import(self.store, reviewed['token'])
        self.assertEqual(self.store.get_asset(existing['id'])['name'], 'Existing retained')
        with closing(sqlite3.connect(self.store.db_path)) as conn:
            evidence = json.loads(conn.execute("SELECT contents FROM import_reference WHERE name='Source Cells'").fetchone()[0])
        skipped = [r for r in evidence if r['source_sheet'] == 'FLs' and r['source_row'] == 5]
        self.assertTrue(skipped)
        self.assertTrue(all(r['asset_id'] is None for r in skipped))
        self.assertTrue(all(r['row_role'] == 'Skipped by import review' for r in skipped))
        again = preview_import(self.store, self.path)
        self.assertFalse(again['errors'])
        self.assertEqual(again['skipped_count'], 1)
        self.assertEqual(again['updates'], 1)

    def test_explicit_existing_match_updates_only_chosen_record(self):
        first = self.store.save_asset(None, {'name': 'AG-101', 'family': 'Flowline', 'source_sheet': 'FLs'}, None)
        second = self.store.save_asset(None, {'name': 'AG-101', 'family': 'Flowline', 'source_sheet': 'FLs'}, None)
        preview = preview_import(self.store, self.path)
        self.assertEqual({c['id'] for c in preview['conflicts'][0]['candidates']}, {first['id'], second['id']})
        decisions = [
            {'row_key': preview['conflicts'][0]['row_key'], 'action': 'match', 'asset_id': second['id']},
            {'row_key': preview['conflicts'][1]['row_key'], 'action': 'skip'},
        ]
        reviewed = self.resolve(preview, decisions)
        self.assertFalse(reviewed['errors'])
        self.assertEqual(reviewed['updates'], 1)
        apply_import(self.store, reviewed['token'])
        self.assertEqual(self.store.get_asset(first['id'])['version'], first['version'])
        self.assertEqual(self.store.get_asset(second['id'])['notes'][0]['note_text'], 'First report')

    def test_two_rows_cannot_update_same_existing_asset(self):
        asset = self.store.save_asset(None, {'name': 'AG-101', 'family': 'Flowline', 'source_sheet': 'FLs'}, None)
        preview = preview_import(self.store, self.path)
        reviewed = self.resolve(preview, [{'row_key': row['row_key'], 'action': 'match', 'asset_id': asset['id']} for row in preview['conflicts']])
        self.assertTrue(reviewed['errors'])
        with self.assertRaises(ValueError): apply_import(self.store, reviewed['token'])

    def test_unknown_keys_actions_and_targets_are_rejected(self):
        for change in ({'row_key': 'forged', 'action': 'skip'}, {'action': 'merge'}, {'action': 'match', 'asset_id': 'missing'}, {'action': 'separate', 'asset_id': 'forged'}):
            with self.subTest(change=change):
                preview = preview_import(self.store, self.path)
                decision = {'row_key': preview['conflicts'][0]['row_key'], **change}
                with self.assertRaises(ValueError): self.resolve(preview, [decision])
        preview = preview_import(self.store, self.path)
        decision = {'row_key': preview['conflicts'][0]['row_key'], 'action': 'skip'}
        with self.assertRaises(ValueError): self.resolve(preview, [decision, decision])

    def test_separate_never_overwrites_occupied_source_row_id(self):
        # An existing cleaned record can already own the proposed row-based ID.
        with closing(sqlite3.connect(self.store.db_path)) as conn, conn:
            conn.execute('INSERT INTO assets(id,name,family,version,details) VALUES(?,?,?,?,?)', ('A09-0004', 'Unrelated asset', 'Flowline', 1, '{}'))
        preview = preview_import(self.store, self.path)
        reviewed = self.resolve(preview, self.separate(preview))
        apply_import(self.store, reviewed['token'])
        self.assertEqual(self.store.get_asset('A09-0004')['name'], 'Unrelated asset')
        self.assertEqual(len(self.asset_rows()), 3)

    def test_changed_or_moved_source_rows_do_not_reuse_saved_decisions(self):
        preview = preview_import(self.store, self.path)
        reviewed = self.resolve(preview, self.separate(preview))
        apply_import(self.store, reviewed['token'])
        import openpyxl
        book = openpyxl.load_workbook(self.path)
        book['FLs']['M4'] = 'A different report'
        book.save(self.path); book.close()
        changed = preview_import(self.store, self.path)
        self.assertTrue(changed['errors'])
        self.assertGreater(changed['unresolved_count'], 0)
        self.assertEqual(changed['remembered_count'], 1)

    def test_moved_rows_require_new_decisions(self):
        preview = preview_import(self.store, self.path)
        reviewed = self.resolve(preview, self.separate(preview)); apply_import(self.store, reviewed['token'])
        import openpyxl
        book = openpyxl.load_workbook(self.path); book['FLs'].insert_rows(4)
        book.save(self.path); book.close()
        moved = preview_import(self.store, self.path)
        self.assertTrue(moved['errors'])
        self.assertEqual(moved['remembered_count'], 0)
        self.assertEqual({r['source_row'] for r in moved['conflicts']}, {5, 6})

    def test_stale_resolution_does_not_change_database(self):
        preview = preview_import(self.store, self.path)
        self.store.save_asset(None, {'name': 'New manual asset', 'family': 'Flowline'}, None)
        with self.assertRaisesRegex(ValueError, 'stale'):
            self.resolve(preview, self.separate(preview))
        self.assertEqual(len(self.asset_rows()), 1)

    def test_decisions_survive_full_export_and_cleaned_reimport(self):
        preview = preview_import(self.store, self.path)
        reviewed = self.resolve(preview, self.separate(preview))
        apply_import(self.store, reviewed['token'])
        output = Path(self.tmp.name) / 'export.xlsx'
        export_workbook(self.store, output)
        other = Store(Path(self.tmp.name) / 'restored.db')
        clean = preview_import(other, output)
        apply_import(other, clean['token'])
        again = preview_import(other, self.path)
        self.assertFalse(again['errors'])
        self.assertEqual(again['remembered_count'], 2)
        self.assertEqual(again['additions'], 0)

    def test_skipped_decision_survives_export_and_excluded_tab_reimport(self):
        preview = preview_import(self.store, self.path)
        decisions = self.separate(preview); decisions[1]['action'] = 'skip'
        reviewed = self.resolve(preview, decisions); apply_import(self.store, reviewed['token'])
        reference = preview_import(self.store, self.path, selected_sheets=['Coolers'])
        apply_import(self.store, reference['token'])
        output = Path(self.tmp.name) / 'skipped.xlsx'; export_workbook(self.store, output)
        other = Store(Path(self.tmp.name) / 'skipped.db')
        clean = preview_import(other, output); apply_import(other, clean['token'])
        again = preview_import(other, self.path)
        self.assertFalse(again['errors'])
        self.assertEqual(again['skipped_count'], 1)
        self.assertEqual(again['remembered_count'], 2)
        self.assertEqual(again['additions'], 0)

    def test_resetting_choice_to_review_blocks_apply_again(self):
        preview = preview_import(self.store, self.path)
        reviewed = self.resolve(preview, self.separate(preview))
        reset = self.resolve(reviewed, [{'row_key': reviewed['conflicts'][0]['row_key'], 'action': 'review'}])
        self.assertEqual(reset['unresolved_count'], 1)
        with self.assertRaises(ValueError): apply_import(self.store, reset['token'])

    def test_saved_choices_cannot_redirect_to_unrelated_asset_in_same_tab(self):
        for action in ('match', 'separate'):
            with self.subTest(action=action):
                store = Store(Path(self.tmp.name) / f'forged-{action}.db')
                unrelated = store.save_asset(None, {'name': 'Completely different line', 'family': 'Flowline', 'source_sheet': 'FLs'}, None)
                first = preview_import(store, self.path)
                key = first['conflicts'][0]['row_key']
                forged = {'row_key': key, 'source_sheet': 'FLs', 'source_row': 4, 'action': action, 'asset_id': unrelated['id']}
                with closing(sqlite3.connect(store.db_path)) as conn, conn:
                    conn.execute('CREATE TABLE import_reference(name TEXT PRIMARY KEY, contents TEXT NOT NULL)')
                    conn.execute('INSERT INTO import_reference VALUES(?,?)', ('Import Decisions', json.dumps([forged])))
                preview = preview_import(store, self.path)
                row = next(r for r in preview['conflicts'] if r['row_key'] == key)
                self.assertFalse(row['resolved'])
                self.assertFalse(row['remembered'])
                self.assertEqual(preview['remembered_count'], 0)
                with self.assertRaises(ValueError): apply_import(store, preview['token'])
                self.assertEqual(store.get_asset(unrelated['id'])['name'], 'Completely different line')

    def test_matching_tag_with_conflicting_location_requires_identity_review(self):
        from inspection_app.import_identity import match_legacy
        self.store.save_asset(None,{'name':'North production line','family':'Flowline','source_sheet':'Flow Lines','tag_original':'T1','location_from':'North'},None)
        data={name:[] for name in ('Assets','Inspection Plan','Notes & Actions','Source Cells','Technical Details','Review Items','Field Map')}
        data['Assets']=[{'asset_id':'incoming','asset_description':'South injection line','asset_family':'Flowline','source_sheet':'Flow Lines','source_row':4,'tag_original':'T1','location_from':'South'}]
        errors,review=match_legacy(self.store,data)
        self.assertTrue(errors)
        self.assertTrue(review['conflicts'])


if __name__ == '__main__': unittest.main()

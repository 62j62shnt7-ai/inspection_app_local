import json
from datetime import date
from contextlib import closing
import sqlite3
import tempfile
import unittest
from pathlib import Path
from openpyxl import load_workbook
from inspection_app.store import Store
from inspection_app import excel_io

class ExcelTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.store=Store(self.root/'test.db')
        self.asset=self.store.save_asset(None,dict(name='Vessel A',family='Vessel',tag_original='V-01',record_status='Active',custom={'retain':0},inspections=[dict(inspection_id='i1',inspection_type='OSI',applicable='Yes',last_inspection_month='2025-01',next_inspection_month='2026-01')],notes=[dict(note_id='n1',note_type='Remark',note_text='=literal')],technical_details=[dict(field_id='pressure',field_label='Pressure',value=0)]),None)
        self.path=self.root/'full.xlsx'
    def export(self):
        excel_io.export_full_workbook(self.store,self.path)
    def cell(self, book, heading, row=4):
        sheet = book['Unassigned']
        headings = [cell.value for cell in sheet[3]]
        return sheet.cell(row, headings.index(heading) + 1)

    def edit(self, heading, value, row=4):
        with closing(load_workbook(self.path)) as book:
            self.cell(book, heading, row).value = value
            book.save(self.path)

    def add_asset(self, name, **fields):
        with closing(load_workbook(self.path)) as book:
            sheet = book['Unassigned']
            values = {
                'New asset ID · use new: label': 'new:a',
                'Asset name': name,
                'Asset family': 'Vessel',
                'Record status': 'Active',
                **fields,
            }
            sheet.append([values.get(cell.value) for cell in sheet[3]])
            for table in sheet.tables.values():
                table.ref = f'A3:{sheet.cell(sheet.max_row, sheet.max_column).coordinate}'
            book.save(self.path)

    def omit_asset_row(self):
        with closing(load_workbook(self.path)) as book:
            book['Unassigned'].delete_rows(4)
            book.save(self.path)

    def preview(self):return excel_io.preview_sync(self.store,self.path)
    def apply(self,p=None,resolutions=None):return excel_io.apply_sync(self.store,(p or self.preview())['token'],resolutions or {})
    def test_unmodified_roundtrip_and_literal(self):
        self.export();b=load_workbook(self.path)
        self.assertEqual(self.cell(b, 'Note 1 · text').data_type, 's')
        self.assertEqual(b['Master Plan']['M5'].data_type, 's')
        b.close()
        p=self.preview();self.assertEqual(p['changes'],[]);self.apply(p)
        self.assertEqual(self.store.get_asset(self.asset['id']),self.asset)
    def test_threeway_conflict_and_stale_preview(self):
        self.export();self.edit('Asset name','Excel')
        a=self.store.save_asset(self.asset['id'],{'name':'App'},self.asset['version'])
        p=self.preview();self.assertEqual(len(p['conflicts']),1)
        with self.assertRaises(ValueError):self.apply(p)
        self.apply(p,{p['conflicts'][0]['key']:{'choice':'excel'}})
        self.assertEqual(self.store.get_asset(a['id'])['name'],'Excel')
        self.assertEqual(self.store.get_asset(a['id'])['custom'],{'retain':0})
    def test_app_only_change_and_missing_asset_row_preserved(self):
        self.export();self.store.save_asset(self.asset['id'],{'name':'App'},self.asset['version'])
        self.omit_asset_row()
        self.apply();a=self.store.get_asset(self.asset['id']);self.assertEqual(a['name'],'App');self.assertEqual(a['notes'][0]['note_text'],'=literal')
    def test_new_assets_children_and_repeat_no_duplicates(self):
        self.export()
        self.add_asset('New', **{'OSI · Applicable': 'Yes', 'OSI · Next month': '2027-03'})
        self.apply()
        self.apply()
        with closing(sqlite3.connect(self.store.db_path)) as c:rows=c.execute('SELECT details FROM assets').fetchall()
        self.assertEqual(len(rows),2);new=[json.loads(r[0]) for r in rows if json.loads(r[0]).get('inspections',[{}])[0].get('next_inspection_month')=='2027-03'][0]
        self.assertTrue(new['inspections'][0]['inspection_id'])
    def test_invalid_month_tampering_and_formula_rejected(self):
        self.export();self.edit('OSI · Next month','bad')
        self.assertTrue(self.preview()['errors'])
        with self.assertRaises(ValueError):self.apply()
        self.export();self.edit('Asset name', '=1+1')
        with self.assertRaises(ValueError):self.preview()
    def test_recovery_retains_business_and_ids(self):
        self.export();target=Store(self.root/'other.db')
        p=excel_io.preview_recovery(target,self.path);excel_io.apply_recovery(target,p['token'],True)
        recovered=target.get_asset(self.asset['id']);self.assertEqual(recovered,self.asset)
        with closing(sqlite3.connect(target.db_path)) as c:self.assertGreater(c.execute('SELECT count(*) FROM correction_events').fetchone()[0],0)
    def test_long_notes_and_repeated_cycles(self):
        text='long note '*8000
        self.store.save_asset(self.asset['id'],{'notes':[dict(note_id='n1',note_type='Remark',note_text=text)]},self.asset['version'])
        self.export();self.assertEqual(self.preview()['changes'],[])
        for name in ['One','Two','Three']:
            self.edit('Asset name',name);result=self.apply()
            self.assertTrue(Path(result['workbook']).is_file())
            self.path=Path(result['workbook']);self.assertEqual(self.store.get_asset(self.asset['id'])['name'],name)
        self.assertEqual(self.store.get_asset(self.asset['id'])['notes'][0]['note_text'],text)
    def test_preview_revision_guard(self):
        self.export();self.edit('Asset name','Excel');p=self.preview()
        self.store.save_asset(self.asset['id'],{'name':'Later'},self.asset['version'])
        with self.assertRaises(ValueError):self.apply(p)

class ExcelFailureTests(ExcelTests):
    def test_stale_new_rows_with_later_edits_are_not_silently_discarded(self):
        self.export()
        self.add_asset('First')
        self.apply()
        self.edit('Asset name', 'Later', row=5)
        p=self.preview();self.assertTrue(p['errors'] or p['conflicts'],'Stale creation edits require explicit review or reconciliation')
    def test_identity_recovery_allows_previous_stale_creation_without_duplication(self):
        self.export()
        self.add_asset('New')
        old = self.path.read_bytes()
        self.apply()
        self.export();target=Store(self.root/'recover.db');p=excel_io.preview_recovery(target,self.path);excel_io.apply_recovery(target,p['token'],True)
        self.path.write_bytes(old)
        p=excel_io.preview_sync(target,self.path)
        excel_io.apply_sync(target,p['token'])
        from contextlib import closing
        with closing(sqlite3.connect(target.db_path)) as c:self.assertEqual(c.execute('SELECT count(*) FROM assets').fetchone()[0],2)
    def test_failure_during_live_merge_rolls_back_everything(self):
        from unittest.mock import patch
        self.export();self.edit('Asset name','Changed');p=self.preview()
        original=excel_io.record_event;calls=[]
        def event(*args,**kwargs):
            calls.append(1)
            if len(calls)==2:raise RuntimeError('Injected live failure')
            return original(*args,**kwargs)
        with patch.object(excel_io,'record_event',side_effect=event):
            with self.assertRaises(RuntimeError):self.apply(p)
        self.assertEqual(self.store.get_asset(self.asset['id']),self.asset)
        self.assertTrue(list((self.root/'backups').glob('*.db')))
    def test_duplicate_asset_row_and_child_without_asset_identity(self):
        self.export()
        with closing(load_workbook(self.path)) as book:
            sheet = book['Unassigned']
            for cell in sheet[4]:
                sheet.cell(5, cell.column, cell.value).data_type = cell.data_type
            book.save(self.path)
        with self.assertRaisesRegex(ValueError, 'Duplicate asset row'):
            self.preview()
        self.export()
        self.edit('Note 1 · text', 'Orphan note', row=5)
        with self.assertRaisesRegex(ValueError, 'Use New asset ID'):
            self.preview()
    def test_baseline_tampering(self):
        self.export();b=load_workbook(self.path);b['Export Baseline']['B2']='{}';b.save(self.path);b.close()
        with self.assertRaises(ValueError):self.preview()
    def test_valid_manual_conflict_and_invalid_resolution(self):
        self.export();self.edit('OSI · Next month','2028-01')
        self.store.save_asset(self.asset['id'],{'inspections':[dict(self.asset['inspections'][0],next_inspection_month='2029-01')]},self.asset['version'])
        p=self.preview();key=p['conflicts'][0]['key']
        with self.assertRaises(ValueError):self.apply(p,{key:{'choice':'manual','value':'invalid'}})
        self.apply(p,{key:{'choice':'manual','value':'2030-01'}})
        self.assertEqual(self.store.get_asset(self.asset['id'])['inspections'][0]['next_inspection_month'],'2030-01')

class ExcelCalculationTests(ExcelTests):
    def test_native_excel_date_is_normalized_on_sync(self):
        self.export()
        self.edit('OSI · Next month', date(2028, 3, 15))
        self.apply()
        asset = self.store.get_asset(self.asset['id'])
        self.assertEqual(asset['inspections'][0]['next_inspection_month'], '2028-03')

    def test_duplicate_unidentified_notes_are_preserved_but_ambiguous_edits_block(self):
        notes=[{'note_type':'Remark','note_text':'same'},{'note_type':'Remark','note_text':'same'}]
        self.store.save_asset(self.asset['id'],{'notes':notes},self.asset['version'])
        self.export();self.assertEqual(self.preview()['changes'],[])
        self.edit('Note 1 · text','edited')
        self.assertTrue(self.preview()['errors'])
    def test_empty_conflict_choice_cannot_apply(self):
        self.export();self.edit('Asset name','Excel');self.store.save_asset(self.asset['id'],{'name':'App'},self.asset['version']);p=self.preview()
        with self.assertRaises(ValueError):self.apply(p,{p['conflicts'][0]['key']:{}})

class ExcelEdgeTests(ExcelTests):
    def test_missing_asset_row_with_long_text_does_not_delete_or_block(self):
        self.store.save_asset(self.asset['id'],{'notes':[dict(note_id='n1',note_type='Remark',note_text='x'*40000)]},self.asset['version'])
        self.export();self.omit_asset_row()
        p=self.preview();self.assertFalse(p['errors']);self.apply(p)
        self.assertEqual(self.store.get_asset(self.asset['id'])['notes'][0]['note_text'],'x'*40000)
    def test_month_validation_covers_current_and_new_rows(self):
        self.export()
        with closing(load_workbook(self.path)) as book:
            cell = self.cell(book, 'OSI · Next month')
            new_cell = self.cell(book, 'OSI · Next month', row=5)
            validation = next(
                rule for rule in cell.parent.data_validations.dataValidation
                if cell.coordinate in rule and new_cell.coordinate in rule
            )
            self.assertEqual(validation.type, 'custom')
            self.assertIn(f'ISNUMBER({cell.coordinate})', validation.formula1)


class ExcelOoxmlTests(ExcelTests):
    def test_source_tab_has_one_table_filter_and_no_dynamic_array_parts(self):
        import zipfile

        self.export()
        with zipfile.ZipFile(self.path) as archive:
            self.assertNotIn('xl/metadata.xml', archive.namelist())
        with closing(load_workbook(self.path)) as book:
            sheet = book['Unassigned']
            table, = sheet.tables.values()
            self.assertEqual(table.ref, f'A3:{sheet.cell(4, sheet.max_column).coordinate}')
            self.assertEqual(table.autoFilter.ref, table.ref)
            self.assertIsNone(sheet.auto_filter.ref)

class ExcelPrecisionTests(ExcelTests):
    def test_excel_numeric_serialization_does_not_create_false_edits(self):
        value=1.1174930829819165
        self.store.save_asset(self.asset['id'],{'technical_details':[{'field_id':'pressure','field_label':'Pressure','value':value}]},self.asset['version'])
        self.export();p=self.preview();self.assertEqual(p['changes'],[])
        self.apply(p);self.assertEqual(self.store.get_asset(self.asset['id'])['technical_details'][0]['value'],value)
        self.edit('Tech · Pressure',0);self.apply();self.assertEqual(self.store.get_asset(self.asset['id'])['technical_details'][0]['value'],0)

class ExcelDesktopFormatTests(ExcelTests):
    def test_validation_formula_size_and_unambiguous_table_row_references(self):
        self.export();b=load_workbook(self.path)
        for ws in b:
            for validation in ws.data_validations.dataValidation:self.assertLessEqual(len(validation.formula1 or ''),255)
            for table in ws.tables.values():
                for column in table.tableColumns:
                    if column.calculatedColumnFormula:self.assertNotIn('[@',column.calculatedColumnFormula.attr_text)
        b.close()

class ExcelResetTests(ExcelTests):
    def test_working_reset_removes_excel_previews_and_creation_history(self):
        from inspection_app.cleanup import _mutate
        self.export();self.preview()
        with closing(sqlite3.connect(self.store.db_path)) as c,c:
            _mutate(c,{'category':'reset','ids':[]},999)
            self.assertEqual(c.execute('SELECT count(*) FROM excel_previews').fetchone()[0],0)
            self.assertEqual(c.execute('SELECT count(*) FROM excel_exports').fetchone()[0],0)

class ExcelLegacyIdentityTests(ExcelTests):
    def test_inspections_without_old_ids_have_stable_export_identity_and_field_conflicts(self):
        self.store.save_asset(self.asset['id'],{'inspections':[{'inspection_type':'OSI','applicable':'Yes','last_inspection_month':'2025-01','next_inspection_month':'2026-01'}]},self.asset['version'])
        self.export()
        with closing(load_workbook(self.path)) as book:
            ident = self.cell(book, '_osi_id').value
        self.assertTrue(ident)
        self.edit('OSI · Next month','2028-01')
        a=self.store.get_asset(self.asset['id']);self.store.save_asset(a['id'],{'inspections':[dict(a['inspections'][0],next_inspection_month='2029-01')]},a['version'])
        p=self.preview();self.assertFalse(p['errors']);self.assertEqual(len(p['conflicts']),1)
        self.apply(p,{p['conflicts'][0]['key']:{'choice':'excel'}})
        self.assertEqual(self.store.get_asset(a['id'])['inspections'][0]['inspection_id'],ident)

class ExcelEvidenceTests(ExcelTests):
    def test_reconciled_workbook_contains_exact_committed_audit_events(self):
        self.export();self.edit('Asset name','Changed');result=self.apply()
        _,baseline,_=excel_io._read(result['workbook'])
        with closing(sqlite3.connect(self.store.db_path)) as c:current=excel_io._snapshot(c)
        self.assertEqual(baseline['snapshot']['correction_events'],current['correction_events'])
        self.assertEqual(baseline['snapshot']['sqlite_sequence'],current['sqlite_sequence'])

class ExcelOriginalEvidenceTests(ExcelTests):
    def test_unknown_source_date_evidence_survives_sync(self):
        asset = self.store.get_asset(self.asset['id'])
        self.store.save_asset(asset['id'], {'inspections': [dict(
            asset['inspections'][0], last_inspection_month=None,
            last_original='Unclear source month',
        )]}, asset['version'])
        self.export()
        with closing(load_workbook(self.path)) as book:
            self.assertIsNone(self.cell(book, 'OSI · Last month').value)
        self.edit('OSI · Next month', '2028-01')
        self.apply()
        inspection = self.store.get_asset(asset['id'])['inspections'][0]
        self.assertEqual(inspection['last_original'], 'Unclear source month')
        self.assertIsNone(inspection['last_inspection_month'])


if __name__ == '__main__':
    unittest.main()

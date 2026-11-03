import tempfile
import unittest
from pathlib import Path
from inspection_app.store import Store
from inspection_app.imports import preview_import, apply_import

WORKBOOK = Path(__file__).resolve().parent.parent / 'reference' / 'Master_Inspection_Plan_Cleaned_Draft.xlsx'

class RoundTripTests(unittest.TestCase):
    def test_full_export_import_preserves_edited_data_and_source(self):
        from inspection_app.exports import export_workbook
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = Store(root / 'one.db')
            p = preview_import(store, WORKBOOK)
            apply_import(store, p['token'])
            a = store.get_asset('A03-0015')
            a['name'] = 'Updated line'
            store.save_asset(a['id'], a, a['version'])
            export_workbook(store, root / 'export.xlsx')
            restored = Store(root / 'two.db')
            preview = preview_import(restored, root / 'export.xlsx')
            self.assertFalse(preview['errors'])
            apply_import(restored, preview['token'])
            b = restored.get_asset(a['id'])
            self.assertEqual(b['name'], 'Updated line')
            self.assertEqual(b['inspections'], a['inspections'])
            self.assertEqual(b['source_cells'], a['source_cells'])
            self.assertEqual(b['notes'], a['notes'])

    def test_selected_deletion_export_reimports_with_unassigned_evidence(self):
        from inspection_app import cleanup
        from inspection_app.exports import export_workbook
        from inspection_app.imports import read_workbook
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); source=Store(root/'source.db')
            cell={'source_sheet':'Original','source_row':8,'source_cell':'H8','row_role':'asset','original_value':'=SUM(A1:A2)\nraw','excel_type':'f','original_annotation':'{"comment":"keep","cached_value":42}'}
            removed=source.save_asset(None,{'name':'Removed','family':'Flowline','source_cells':[cell]},None)
            survivor=source.save_asset(None,{'name':'Survivor','family':'Flowline'},None)
            imported=Store(root/'imported.db'); book=export_workbook(source,root/'initial.xlsx')
            preview=preview_import(imported,book); self.assertFalse(preview['errors']);apply_import(imported,preview['token'])
            plan=cleanup.preview_cleanup(imported,{'category':'assets','ids':[removed['id']]})
            cleanup.apply_cleanup(imported,plan['preview_id'],plan['confirmation'])
            output=export_workbook(imported,root/'deleted.xlsx')
            rows=read_workbook(output)['Source Cells']; self.assertEqual(len(rows),1)
            self.assertIsNone(rows[0]['asset_id']);self.assertEqual(rows[0]['historical_asset_id'],removed['id'])
            for key,value in cell.items(): self.assertEqual(rows[0][key],value)
            restored=Store(root/'restored.db'); preview=preview_import(restored,output)
            self.assertFalse(preview['errors']);apply_import(restored,preview['token'])
            self.assertEqual(restored.get_asset(survivor['id'])['name'],'Survivor')
            with self.assertRaises(KeyError):restored.get_asset(removed['id'])
            again=read_workbook(export_workbook(restored,root/'again.xlsx'))['Source Cells']
            self.assertEqual(rows,again)

    def test_unassigned_review_items_survive_roundtrip(self):
        from openpyxl import load_workbook
        from inspection_app.exports import export_workbook
        from inspection_app.imports import read_workbook
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); source=Store(root/'source.db')
            source.save_asset(None,{'name':'Survivor','family':'Flowline'},None)
            path=export_workbook(source,root/'initial.xlsx');book=load_workbook(path)
            sheet=book['Review Items'];sheet.append(['review-1',None,'Sheet 1',12,'scope','=raw\nsecond','Review','Confirm\n=detail']);book.save(path)
            # Literal strings must remain literal, including formula-like evidence.
            sheetbook=load_workbook(path);ws=sheetbook['Review Items']
            for col in (6,8):ws.cell(2,col).data_type='s'
            sheetbook.save(path)
            expected=read_workbook(path)['Review Items']
            for i in range(2):
                target=Store(root/f'target{i}.db'); preview=preview_import(target,path)
                self.assertFalse(preview['errors']);apply_import(target,preview['token'])
                path=export_workbook(target,root/f'out{i}.xlsx')
                self.assertEqual(read_workbook(path)['Review Items'],expected)

    def test_consolidation_preserves_historical_source_id_across_roundtrips(self):
        from inspection_app.consolidation import preview_consolidation,apply_consolidation
        from inspection_app.exports import export_workbook
        from inspection_app.imports import read_workbook
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); producer=Store(root/'producer.db')
            a=producer.save_asset(None,{'name':'A','family':'Flowline'},None)
            b=producer.save_asset(None,{'name':'B','family':'Flowline','source_cells':[{'source_sheet':'S','source_row':2,'source_cell':'B2','original_value':'Evidence','excel_type':'s','original_annotation':'comment'}]},None)
            store=Store(root/'master.db')
            initial=export_workbook(producer,root/'initial.xlsx'); staged=preview_import(store,initial)
            self.assertFalse(staged['errors']);apply_import(store,staged['token'])
            p=preview_consolidation(store,a['id'],b['id'])
            apply_consolidation(store,p['preview_id'],p['revision'],{c['field']:'survivor' for c in p['conflicts']},'Same item')
            path=export_workbook(store,root/'consolidated.xlsx')
            for i in range(2):
                rows=read_workbook(path)['Source Cells'];self.assertEqual(len(rows),1)
                self.assertEqual(rows[0]['asset_id'],a['id']);self.assertEqual(rows[0]['historical_asset_id'],b['id'])
                target=Store(root/f'copy{i}.db');p=preview_import(target,path);self.assertFalse(p['errors']);apply_import(target,p['token'])
                with self.assertRaises(KeyError): target.get_asset(b['id'])
                path=export_workbook(target,root/f'copy{i}.xlsx')

    def test_older_workbook_without_historical_asset_id_still_imports(self):
        from openpyxl import load_workbook
        from inspection_app.exports import export_workbook
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); store=Store(root/'source.db')
            asset=store.save_asset(None,{'name':'A','family':'Flowline','source_cells':[{'source_sheet':'S','source_cell':'A1','original_value':'Original'}]},None)
            path=export_workbook(store,root/'legacy.xlsx');book=load_workbook(path)
            sheet=book['Source Cells']; columns={c.value:c.column for c in sheet[1]}
            sheet.delete_cols(columns['historical_asset_id']);book.save(path)
            target=Store(root/'target.db');preview=preview_import(target,path)
            self.assertFalse(preview['errors']);apply_import(target,preview['token'])
            self.assertEqual(target.get_asset(asset['id'])['source_cells'][0]['original_value'],'Original')

    def test_long_unicode_note_roundtrips_without_excel_truncation(self):
        from inspection_app.exports import export_workbook
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); source=Store(root/'source.db')
            text='Engineering evidence\n'+'é'*40000+' IMPORTANT END'
            asset=source.save_asset(None,{'name':'Long evidence','family':'Flowline','notes':[{'note_id':'n1','note_type':'Remark','note_text':text}]},None)
            path=export_workbook(source,root/'long.xlsx')
            target=Store(root/'target.db')
            apply_import(target,preview_import(target,path)['token'])
            self.assertEqual(target.get_asset(asset['id'])['notes'][0]['note_text'],text)

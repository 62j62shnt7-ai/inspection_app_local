"""Standalone Excel reports use actual obligations and never sync identities."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from openpyxl import load_workbook
from inspection_app.store import Store
from inspection_app import annual_excel


class AnnualExcelTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name) / 'test.db')
        self.path = Path(self.temp.name) / 'annual.xlsx'
        self.add('A', 'North', [('OSI','2027-01'), ('Internal','2027-02')])
        self.add('B', 'South', [('OSI','2026-12')])
        self.add('C', 'North', [('OSI',None)])
        self.add('D', 'North', [('OSI','2028-01')])
        self.add('E', 'North', [('OSI','2027-03')], archived=True)
        self.add('F', 'North', [('OSI','2027-04')], applicable='No')

    def add(self, name, area, inspections, archived=False, applicable='Yes'):
        data={'location_from':area,'record_status':'Archived' if archived else 'Active',
              'tag_original':'TAG-'+name,'source_sheet':'Tanks','source_row':2,
              'notes':[{'note_id':'n'+name,'note_text':'=untrusted\nFull remarks'}],
              'inspections':[{'inspection_id':name+kind,'inspection_type':kind,'applicable':applicable,
                              'next_inspection_month':due} for kind,due in inspections]}
        with closing(sqlite3.connect(self.store.db_path)) as conn, conn:
            conn.execute('INSERT INTO assets VALUES (?,?,?,?,?)',(name,'Asset '+name,'Tank',1,json.dumps(data)))

    def export(self, **options):
        annual_excel.export_annual_workbook(self.store,self.path,{'year':2027,'reference_month':'2027-02',**options})
        book=load_workbook(self.path)
        self.addCleanup(book.close)
        return book

    def values(self, book, name):
        return list(book[name].values)

    def test_overview_selection_panes_match_vertical_freeze(self):
        book=self.export();view=book['01 - Annual Overview'].sheet_view
        if not view.pane.xSplit:
            self.assertTrue(all(s.pane in (None,'topLeft','bottomLeft') for s in view.selection))

    def test_chart_labels_are_visible_for_management_reporting(self):
        book=self.export();chart=book['01 - Annual Overview']._charts[0]
        self.assertEqual(chart.x_axis.tickLblPos,'nextTo')
        self.assertEqual(chart.y_axis.tickLblPos,'nextTo')

    def test_year_counts_independent_obligations_and_old_overdue_separation(self):
        book=self.export(monthly_sheets=True)
        master=self.values(book,'02 - Master Annual Plan')
        self.assertEqual(len(master)-5,2)
        self.assertEqual(master[5][5],'OSI')
        self.assertEqual(master[6][5],'Internal')
        monthly=self.values(book,'03 - Monthly Schedule')
        self.assertEqual(monthly[5][:4],('January',1,0,1))
        self.assertEqual(monthly[6][:4],('February',0,1,1))
        overdue=self.values(book,'04 - Overdue Inspections')
        self.assertEqual({r[0] for r in overdue[5:]},{'A','B'})
        self.assertNotIn('B',{r[0] for r in master[5:]})
        self.assertEqual(self.values(book,'Jan')[5][0],'A')
        self.assertEqual(self.values(book,'Mar')[5][0],'No scheduled inspections')
        self.assertEqual(book['Report Metadata']['B2'].value,'annual_report')
        self.assertNotIn('Assets',book.sheetnames)

    def test_filters_and_no_empty_optional_sheets(self):
        book=self.export(inspection_type='Internal',area='North',family='Tank',tag='TAG-A',include_overdue=False,include_unscheduled=False,include_summary=False)
        self.assertEqual(len(self.values(book,'02 - Master Annual Plan'))-5,1)
        self.assertNotIn('04 - Overdue Inspections',book.sheetnames)
        self.assertNotIn('05 - Unscheduled Review',book.sheetnames)
        self.assertNotIn('Jan',book.sheetnames)
        self.assertNotIn('03 - Monthly Schedule',book.sheetnames)

    def test_review_conditions_and_current_due_not_overdue(self):
        with closing(sqlite3.connect(self.store.db_path)) as conn, conn:
            raw=conn.execute('SELECT details FROM assets WHERE id="C"').fetchone()[0]
            data=json.loads(raw);data['inspections'][0]['scheduling_condition']='At next shutdown'
            conn.execute('UPDATE assets SET details=? WHERE id="C"',(json.dumps(data),))
        book=self.export()
        unresolved=self.values(book,'05 - Unscheduled Review')
        self.assertEqual(len(unresolved)-5,1)
        self.assertIn('At next shutdown',str(unresolved[-1]))
        self.assertNotIn('AInternal',{r[-1] for r in self.values(book,'04 - Overdue Inspections')[5:]})

    def test_professional_format_and_formula_injection_protection(self):
        book=self.export()
        master=book['02 - Master Annual Plan']
        self.assertEqual(master.freeze_panes,'C6')
        self.assertTrue(master.tables)
        self.assertEqual(master.page_setup.orientation,'landscape')
        self.assertEqual(master.print_title_rows,'$5:$5')
        self.assertTrue(master.print_area)
        self.assertTrue(master.conditional_formatting)
        self.assertTrue(book['01 - Annual Overview']._charts)
        remarks=master.cell(6,13)
        self.assertIn('=untrusted',remarks.value)
        self.assertEqual(remarks.data_type,'s')

    def test_invalid_options_do_not_deliver_partial_workbook(self):
        self.path.write_bytes(b'prior report')
        for options in ({'year':0},{'year':2027,'inspection_type':'Bad'},{'year':2027,'reference_month':'bad'},{'year':True}):
            with self.assertRaises(ValueError):annual_excel.export_annual_workbook(self.store,self.path,options)
            self.assertEqual(self.path.read_bytes(),b'prior report')

    def test_report_year_selection_does_not_depend_on_current_year(self):
        book=self.export(year=2028, reference_month='2028-01')
        self.assertEqual(self.values(book,'02 - Master Annual Plan')[5][0],'D')
        self.assertEqual(len(self.values(book,'02 - Master Annual Plan'))-5,1)

    def test_full_length_report_notes_have_complete_non_formula_chunks(self):
        text='=LONG\n'+'n'*70000
        with closing(sqlite3.connect(self.store.db_path)) as conn, conn:
            data=json.loads(conn.execute('SELECT details FROM assets WHERE id="A"').fetchone()[0])
            data['notes'][0]['note_text']=text
            conn.execute('UPDATE assets SET details=? WHERE id="A"',(json.dumps(data),))
        book=self.export()
        self.assertIn('Full Report Text',book.sheetnames)
        chunks=[r for r in book['Full Report Text'].values if r[0]=='02 - Master Annual Plan' and r[2]=='AOSI']
        self.assertEqual(''.join(r[5] for r in chunks),text)
        for row in book['Full Report Text'].iter_rows(min_row=2):
            self.assertEqual(row[5].data_type,'s')

    def test_current_review_items_do_not_enter_planned_or_overdue_counts(self):
        with closing(sqlite3.connect(self.store.db_path)) as conn, conn:
            data=json.loads(conn.execute('SELECT details FROM assets WHERE id="A"').fetchone()[0])
            data['inspections'][0].update(review_status='Review',review_reason='Check source conflict')
            conn.execute('UPDATE assets SET details=? WHERE id="A"',(json.dumps(data),))
        book=self.export()
        self.assertEqual(len(self.values(book,'02 - Master Annual Plan'))-5,1)
        overdue=self.values(book,'04 - Overdue Inspections')
        self.assertEqual({r[0] for r in overdue[5:]},{'B'})
        unresolved=self.values(book,'05 - Unscheduled Review')
        self.assertIn('AOSI',{r[-1] for r in unresolved[5:]})

    def test_empty_database_has_no_placeholder_obligations(self):
        with closing(sqlite3.connect(self.store.db_path)) as conn, conn:conn.execute('DELETE FROM assets')
        book=self.export()
        self.assertEqual(book['02 - Master Annual Plan']['A6'].value,'No scheduled inspections')
        self.assertFalse(book['02 - Master Annual Plan'].tables)
        self.assertEqual(book['01 - Annual Overview']['B5'].value,0)
        self.assertNotIn('04 - Overdue Inspections',book.sheetnames)
        self.assertNotIn('05 - Unscheduled Review',book.sheetnames)

    def test_failed_write_preserves_previous_report(self):
        from unittest.mock import patch
        self.path.write_bytes(b'previous')
        with patch('inspection_app.annual_excel.Workbook.save',side_effect=OSError('disk full')):
            with self.assertRaises(OSError):self.export()
        self.assertEqual(self.path.read_bytes(),b'previous')
        self.assertFalse(list(self.path.parent.glob('.inspection-report-*.xlsx')))

    def test_filtered_register_respects_archived_selection(self):
        annual_excel.export_filtered_workbook(self.store,self.path,{'filters':{'status':'archived'}})
        book=load_workbook(self.path);self.addCleanup(book.close)
        self.assertEqual(book['Asset Register']['A6'].value,'E')
        self.assertEqual(book['Asset Register']['J6'].value,'Archived')

    def test_other_modes_explicit_report_scope(self):
        annual_excel.export_filtered_workbook(self.store,self.path,{'area':'South'})
        book=load_workbook(self.path);self.addCleanup(book.close)
        self.assertEqual(book['Report Metadata']['B2'].value,'filtered_register')
        self.assertEqual(book['Asset Register']['A6'].value,'B')
        annual_excel.export_management_workbook(self.store,self.path,{'year':2027,'reference_month':'2027-02'})
        summary=load_workbook(self.path);self.addCleanup(summary.close)
        self.assertEqual(summary['Report Metadata']['B2'].value,'management_summary')
        self.assertNotIn('02 - Master Annual Plan',summary.sheetnames)


if __name__=='__main__':unittest.main()

import unittest
from inspection_app.months import validate_month, due_bucket, parse_month

class MonthTests(unittest.TestCase):
    def test_month_boundary(self):
        self.assertEqual(due_bucket('2027-06', '2027-06', True, False), 'due_this_month')
        self.assertEqual(due_bucket('2027-06', '2027-07', True, False), 'overdue')
    def test_undated_and_excluded(self):
        self.assertEqual(due_bucket(None, '2027-07', True, False), 'undated')
        self.assertEqual(due_bucket('2027-06', '2027-07', False, False), 'excluded')
        self.assertEqual(due_bucket('2027-06', '2027-07', True, True), 'excluded')
    def test_validation(self):
        self.assertIsNone(validate_month(''))
        for value in ('2027', '2027-13', '2027-6', '2027-06-01'):
            with self.assertRaises(ValueError): validate_month(value)

    def test_import_month_year_with_hyphen(self):
        for raw in ('2-2026', '02-2026', '2/2026'):
            with self.subTest(raw=raw):
                self.assertEqual(parse_month(raw), '2026-02')
        for raw in ('0-2026', '13-2026', '2-26', '2-0000'):
            with self.subTest(raw=raw):
                self.assertIsNone(parse_month(raw))

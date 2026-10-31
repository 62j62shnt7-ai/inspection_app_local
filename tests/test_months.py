import unittest
from inspection_app.months import validate_month, due_bucket

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

import re

def validate_month(value):
    if value is None or value == '':
        return None
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', value) or value[:4] == '0000':
        raise ValueError('Expected a month in YYYY-MM format')
    return value

def due_bucket(due_month, current_month, applicable, archived):
    current = validate_month(current_month)
    if current is None:
        raise ValueError('Current month is required')
    due = validate_month(due_month)
    if not applicable or archived:
        return 'excluded'
    if due is None:
        return 'undated'
    if due < current:
        return 'overdue'
    return 'due_this_month' if due == current else 'future'

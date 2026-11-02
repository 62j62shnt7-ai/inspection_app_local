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


from datetime import date, datetime

def parse_month(value):
    if isinstance(value, (date, datetime)):
        return value.strftime('%Y-%m')
    text = str(value or '').strip()
    match = re.fullmatch(r'(\d{4})[-/](\d{1,2})(?:[-/](\d{1,2}))?', text)
    if match:
        y, m = int(match[1]), int(match[2])
        try:
            date(y, m, int(match[3] or 1))
            return f'{y:04d}-{m:02d}'
        except ValueError:
            return None
    # Month names and month/year are unambiguous; two-digit years are not inferred.
    match = re.fullmatch(r'(\d{1,2})/(\d{4})', text)
    if match:
        return parse_month(f'{match[2]}-{match[1]}')
    for fmt in ('%b-%Y', '%B-%Y', '%b %Y', '%B %Y', '%B -%Y'):
        try:
            return datetime.strptime(text, fmt).strftime('%Y-%m')
        except ValueError:
            pass
    return None

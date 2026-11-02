"""Reproducible engineering data findings; no inferred corrections."""
import hashlib
import json
import re
from .months import validate_month

RULES_VERSION = '2'


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def source_review_fields(asset, inspection):
    """Recognize only an importer summary fully represented by retained items."""
    kind = inspection.get('inspection_type')
    parts = []
    fields = []
    for label in ('last inspection', 'next inspection', 'date order'):
        items = [item for item in asset.get('review_items', [])
                 if item.get('review_status') == 'Review' and item.get('field') == f'{kind}: {label}']
        if len(items) != 1 or not items[0].get('reason'):
            continue
        item = items[0]
        parts.append(item['reason'] if label == 'date order' else label+': '+item['reason'])
        fields.append('review_items.'+str(item.get('review_id') or fingerprint(item)))
    return fields if parts and ' '.join(parts) == inspection.get('review_reason') else []


_EMPTY_SCHEDULE = {'', 'undated', 'dated', 'unknown', 'xx', '-', '—', 'none', 'null', 'n/a', 'na'}
_IMPORT_DATE_REASONS = {
    'No unambiguous month; original value retained for review.',
    'Next inspection precedes last inspection; verify the original dates. No correction was inferred.',
}


def scheduling_condition_present(value):
    text = str(value or '').strip()
    # Exclude imported empty markers and date-like text, not years within conditions.
    date_like = re.search(r'\d\s*[-/.]\s*\d', text) or re.fullmatch(r'\d+', text) or (
        re.search(r'\d', text) and re.search(
            r'\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b', text, re.I))
    return text.casefold() not in _EMPTY_SCHEDULE and not date_like


def imported_date_item(asset, item):
    if item.get('reason') not in _IMPORT_DATE_REASONS:
        return False
    return any(item.get('field') in {i.get('inspection_type','')+': '+label for label in ('last inspection','next inspection','date order')}
               for i in asset.get('inspections', []))


def ambiguous_original(inspection, key):
    if inspection.get(key):
        return False  # A current normalized value supersedes historical source text.
    raw = str(inspection.get('last_original' if key == 'last_inspection_month' else 'next_original') or '').strip()
    if raw.casefold() in {'', 'none', 'null', 'undated'}:
        return False
    if key == 'last_inspection_month' and raw.casefold() in {'never','never inspected','not inspected'}:
        return False
    if raw.casefold() in {'oos','out of service','out of scope','insulated','not applicable','n/a','na','w/eval','w/evaluation','waiting evaluation','awaiting evaluation','next sd','sd','next shutdown','at next shutdown'}:
        return False
    if key == 'next_inspection_month' and scheduling_condition_present(raw) and scheduling_condition_present(inspection.get('scheduling_condition')):
        return False
    return True


def validate_record(asset, current_month=None):
    findings = []
    def add(rule, field, message, severity='blocking'):
        findings.append({'rule_id': rule, 'asset_id': asset['id'], 'field': field, 'severity': severity,
                         'message': message, 'value_fingerprint': fingerprint(asset.get(field)), 'rules_version': RULES_VERSION})
    for field in ('name', 'family', 'record_status'):
        if not str(asset.get(field) or '').strip() or (field=='name' and asset.get(field)=='(unnamed asset)') or (field=='family' and asset.get(field)=='Unknown'):
            add('required-'+field, field, 'Supply '+field.replace('_',' '))
    inspections = asset.get('inspections', [])
    if not inspections:
        add('required-applicability', 'inspections', 'Explicitly check inspection applicability')
    if inspections and not any(i.get('inspection_type')=='OSI' for i in inspections):
        add('required-osi-applicability', 'inspections', 'Explicitly check OSI applicability')
    is_vessel = bool(re.search(r'\b(tank|tanks|vessel|vessels)\b', str(asset.get('family','')), re.I))
    if not any(f['rule_id']=='required-family' for f in findings) and not is_vessel and str(asset.get('family') or '').strip().casefold() not in ('piping','flowline','trunkline','gas lift line','pipeline','manifold'):
        add('unclassified-family','family','Classify the asset family against the supported engineering families')
    if inspections and is_vessel and not any(i.get('inspection_type')=='Internal' for i in inspections):
        add('required-internal-applicability', 'inspections', 'Explicitly check internal inspection applicability')
    for inspection in inspections:
        prefix = 'inspections.'+str(inspection.get('inspection_type'))+'.'
        last, due = inspection.get('last_inspection_month'), inspection.get('next_inspection_month')
        for key in ('last_inspection_month','next_inspection_month','condition_review_by'):
            try: validate_month(inspection.get(key))
            except ValueError: add('invalid-month', prefix+key, 'Use a valid month in YYYY-MM format')
        if inspection.get('applicable') not in ('Yes','No'):
            add('required-applicability', prefix+'applicable', 'Explicitly choose Yes or No for inspection applicability')
        if inspection.get('applicable')!='Yes': continue
        for key in ('last_inspection_month','next_inspection_month'):
            if ambiguous_original(inspection,key):
                add('ambiguous-date', prefix+key, 'Invalid or ambiguous source date; check the current inspection schedule')
        if inspection.get('inspection_type')=='Internal' and not is_vessel:
            add('internal-family', prefix+'applicable', 'Review family: internal inspections require a recognized tank or vessel')
        if last and due and not any(f['field'] in (prefix+'last_inspection_month',prefix+'next_inspection_month') for f in findings) and due < last:
            add('chronology', prefix+'next_inspection_month', 'Next month precedes last inspection; review the source and retained overdue schedule')
        if not due:
            if not scheduling_condition_present(inspection.get('scheduling_condition')):
                if not any(f['field']==prefix+'next_inspection_month' for f in findings):
                    add('missing-schedule', prefix+'next_inspection_month', 'Supply a next month or scheduling condition')
        source_fields = source_review_fields(asset, inspection)
        if inspection.get('review_status')=='Review' and not source_fields:
            add('source-review', prefix+'review_status', inspection.get('review_reason') or 'Review inspection source evidence')
    for cell in asset.get('source_cells',[]):
        if cell.get('excel_type')!='f':continue
        try:annotation=json.loads(cell.get('original_annotation') or '{}')
        except (ValueError,TypeError):annotation={}
        if not isinstance(annotation,dict) or annotation.get('cached_value') is None:
            add('formula-cache-missing','source_cells.'+str(cell.get('source_cell')),'Formula has no cached result in '+str(cell.get('source_sheet') or '')+' '+str(cell.get('source_cell') or '')+'; original formula retained','warning')
    for item in asset.get('review_items', []):
        if item.get('review_status')=='Review' and not imported_date_item(asset,item):
            add('source-review-item', 'review_items.'+str(item.get('review_id') or fingerprint(item)), item.get('reason') or 'Review source evidence')
    return findings


def reconcile_import_reviews(asset):
    """Resolve generated duplicate date warnings from current values, keeping evidence."""
    findings = validate_record(asset)
    for inspection in asset.get('inspections', []):
        kind = inspection.get('inspection_type')
        linked_summary = bool(source_review_fields(asset, inspection)) or inspection.get('review_summary_generated', False)
        if linked_summary:
            inspection['review_summary_generated'] = True
        prefix = 'inspections.' + str(kind) + '.'
        for item in asset.get('review_items', []):
            if item.get('review_status') not in ('Review', 'Resolved') or not imported_date_item(asset, item):
                continue
            label = str(item.get('field', '')).removeprefix(str(kind) + ': ')
            keys = {'last inspection': ('last_inspection_month',),
                    'next inspection': ('next_inspection_month',),
                    'date order': ('last_inspection_month', 'next_inspection_month')}.get(label)
            if keys is None:
                continue
            related = [f for f in findings if f['field'] in {prefix + key for key in keys} and f['severity']=='blocking']
            item['review_status'] = 'Review' if related else 'Resolved'
        if linked_summary:
            remaining = []
            for label in ('last inspection', 'next inspection', 'date order'):
                for item in asset.get('review_items', []):
                    if item.get('field') == str(kind)+': '+label and item.get('review_status')=='Review':
                        remaining.append(item['reason'] if label=='date order' else label+': '+item['reason'])
            inspection['review_status'] = 'Review' if remaining else None
            inspection['review_reason'] = ' '.join(remaining)
    return asset

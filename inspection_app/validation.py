"""Reproducible engineering data findings; no inferred corrections."""
import hashlib
import json
import re
from .months import validate_month

RULES_VERSION = '1'


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def validate_record(asset, current_month=None):
    findings = []
    def add(rule, field, message, severity='blocking'):
        findings.append({'rule_id': rule, 'asset_id': asset['id'], 'field': field, 'severity': severity,
                         'message': message, 'value_fingerprint': fingerprint(asset.get(field)), 'rules_version': RULES_VERSION})
    for field in ('name', 'family', 'record_status'):
        if not str(asset.get(field) or '').strip() or (field=='name' and asset.get(field)=='(unnamed asset)') or (field=='family' and asset.get(field)=='Unknown'):
            add('required-'+field, field, 'Supply and verify '+field.replace('_',' '))
    if not any(str(asset.get(k) or '').strip() for k in ('location_from','unit_or_location_to','plant','field','parent_group')):
        add('required-context', 'context', 'Supply an identifiable location or context')
    inspections = asset.get('inspections', [])
    if not inspections:
        add('required-applicability', 'inspections', 'Explicitly check inspection applicability')
    if not any(i.get('inspection_type')=='OSI' for i in inspections):
        add('required-osi-applicability', 'inspections', 'Explicitly check OSI applicability')
    is_vessel = bool(re.search(r'\b(tank|tanks|vessel|vessels)\b', str(asset.get('family','')), re.I))
    if not is_vessel and str(asset.get('family') or '').strip().casefold() not in ('piping','flowline','trunkline','gas lift line','pipeline','manifold'):
        add('unclassified-family','family','Classify the asset family against the supported engineering families')
    if is_vessel and not any(i.get('inspection_type')=='Internal' for i in inspections):
        add('required-internal-applicability', 'inspections', 'Explicitly check internal inspection applicability')
    for inspection in inspections:
        prefix = 'inspections.'+str(inspection.get('inspection_type'))+'.'
        last, due = inspection.get('last_inspection_month'), inspection.get('next_inspection_month')
        for key in ('last_inspection_month','next_inspection_month','condition_review_by'):
            try: validate_month(inspection.get(key))
            except ValueError: add('invalid-month', prefix+key, 'Use a valid month in YYYY-MM format')
        if inspection.get('applicable')!='Yes': continue
        if inspection.get('inspection_type')=='Internal' and not is_vessel:
            add('internal-family', prefix+'applicable', 'Review family: internal inspections require a recognized tank or vessel')
        if last and due and due < last:
            add('chronology', prefix+'next_inspection_month', 'Next month precedes last inspection; review the source and retained overdue schedule')
        if not due:
            if not inspection.get('scheduling_condition'):
                add('missing-schedule', prefix+'next_inspection_month', 'Supply a next month or verified scheduling condition')
            elif not inspection.get('condition_review_by'):
                add('condition-review-required', prefix+'condition_review_by', 'A scheduling condition requires a review-by month')
            elif current_month and inspection['condition_review_by'] <= current_month:
                add('condition-review-due', prefix+'condition_review_by', 'Scheduling condition is due for review', 'warning')
        if inspection.get('review_status')=='Review':
            add('source-review', prefix+'review_status', inspection.get('review_reason') or 'Review inspection source evidence')
    for cell in asset.get('source_cells',[]):
        if cell.get('excel_type')!='f':continue
        try:annotation=json.loads(cell.get('original_annotation') or '{}')
        except (ValueError,TypeError):annotation={}
        if not isinstance(annotation,dict) or annotation.get('cached_value') is None:
            add('formula-cache-missing','source_cells.'+str(cell.get('source_cell')),'Formula has no cached result in '+str(cell.get('source_sheet') or '')+' '+str(cell.get('source_cell') or '')+'; original formula retained','warning')
    for item in asset.get('review_items', []):
        if item.get('review_status')=='Review':
            add('source-review-item', 'review_items.'+str(item.get('review_id') or fingerprint(item)), item.get('reason') or 'Review source evidence')
    return findings

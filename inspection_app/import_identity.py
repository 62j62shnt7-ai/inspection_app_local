"""Conservative original-plan matching and explicitly reviewed identity choices."""
from . import payloads
from collections import defaultdict
from contextlib import closing
import hashlib
import json
import re
import sqlite3

from .legacy import normalized

DECISION_SHEET = 'Import Decisions'  # Optional: older seven-table exports still work.


def identities(asset):
    scope = (asset.get('source_sheet'), normalized(asset.get('asset_family') or asset.get('family')))
    def usable(value):
        value = normalized(value)
        return value if value not in ('', 'na', 'n/a', 'none', '-', 'unknown', 'null', '(unnamed asset)') and any(c.isalnum() for c in value) else ''
    strong = [(scope, key, usable(asset.get(key))) for key in ('asset_number_original', 'tag_original') if usable(asset.get(key))]
    description = usable(asset.get('asset_description')) or usable(asset.get('name')) or usable(asset.get('oracle_description'))
    context = tuple(usable(asset.get(key)) for key in ('pack_original', 'location_from', 'unit_or_location_to', 'source_group', 'source_sequence'))
    return strong, (scope, description, context) if description else None


def conflicting_context(prior, incoming):
    fields=('location_from','unit_or_location_to','plant','field')
    if any(normalized(prior.get(k)) and normalized(incoming.get(k)) and normalized(prior[k])!=normalized(incoming[k]) for k in fields):return True
    old=normalized(prior.get('name') or prior.get('asset_description'))
    new=normalized(incoming.get('asset_description') or incoming.get('name'))
    return bool(old and new and old!=new)


def validate_decisions(rows):
    if not isinstance(rows, list) or len(rows) > 10000:
        raise ValueError('Invalid import decisions')
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get('row_key'), str) or not re.fullmatch(r'[a-f0-9]{64}', row['row_key']) or row['row_key'] in seen:
            raise ValueError('Invalid or duplicate import decision row key')
        if row.get('action') not in ('separate', 'skip', 'match') or not isinstance(row.get('source_sheet'), str) or not isinstance(row.get('source_row'), int) or row['source_row'] < 1:
            raise ValueError('Invalid saved import decision')
        if row['action'] != 'skip' and (not isinstance(row.get('asset_id'), str) or not row['asset_id']):
            raise ValueError('Saved import decision needs an asset ID')
        if row['action'] == 'skip' and row.get('asset_id'):
            raise ValueError('A skipped row cannot update an asset')
        seen.add(row['row_key'])


def saved_decisions(store):
    with closing(sqlite3.connect(store.db_path)) as conn:
        exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='import_reference'").fetchone()
        row = conn.execute('SELECT contents FROM import_reference WHERE name=?', (DECISION_SHEET,)).fetchone() if exists else None
    rows = payloads.loads(row[0]) if row else []
    validate_decisions(rows)
    return {r['row_key']: r for r in rows}


def snapshot(asset):
    keys = ('source_sheet', 'source_row', 'tag_original', 'asset_number_original', 'service_status_original', 'source_sequence', 'source_group', 'location_from', 'unit_or_location_to', 'pack_original', 'oracle_description')
    return {'id': asset.get('id') or asset.get('asset_id'), 'name': asset.get('name') or asset.get('asset_description') or asset.get('oracle_description') or '(unnamed asset)',
            'family': asset.get('family') or asset.get('asset_family'), **{k: asset.get(k) for k in keys},
            'inspections': asset.get('inspections', []), 'notes': asset.get('notes', [])}


def match_legacy(store, data, resolutions=None):
    """Resolve on server-owned raw tables. Choices are persisted only on apply."""
    with closing(sqlite3.connect(store.db_path)) as conn:
        prior = [{'id': r[0], 'name': r[1], 'family': r[2], **json.loads(r[3])} for r in conn.execute('SELECT id,name,family,details FROM assets')]
        baselines={asset_id:payloads.loads(raw) for asset_id,raw in conn.execute('SELECT asset_id,contents FROM source_baselines')}
        aliases=dict(conn.execute('SELECT retired_id,survivor_id FROM asset_aliases'))
    prior_by_id = {a['id']: a for a in prior}
    strong_index, exact_index, epf_index = defaultdict(set), defaultdict(set), defaultdict(set)
    for asset in prior:
        strong, exact = identities(asset)
        for key in strong: strong_index[key].add(asset['id'])
        if exact: exact_index[exact].add(asset['id'])
        if asset.get('source_sheet') == 'EPFs' and normalized(asset.get('location_from')) == 'mop' and exact:
            epf_index[(exact[0], exact[1], normalized(asset.get('source_sequence')))].add(asset['id'])
    children = {}
    for table in ('Inspection Plan', 'Notes & Actions', 'Source Cells'):
        grouped = defaultdict(list)
        for row in data[table]: grouped[row.get('asset_id')].append(row)
        children[table] = grouped
    for asset_id,baseline in baselines.items():
        asset_id=aliases.get(asset_id,asset_id)
        if asset_id not in prior_by_id:continue
        strong,exact=identities(baseline)
        for key in strong:strong_index[key].add(asset_id)
        if exact:exact_index[exact].add(asset_id)
    accepted_scopes=defaultdict(set)
    for asset_id,asset in prior_by_id.items():accepted_scopes[asset_id].add((asset.get('source_sheet'),normalized(asset.get('family'))))
    for asset_id,baseline in baselines.items():accepted_scopes[aliases.get(asset_id,asset_id)].add((baseline.get('source_sheet'),normalized(baseline.get('asset_family') or baseline.get('family'))))
    saved = saved_decisions(store)
    requested = resolutions or {}
    entries, duplicate_groups, suggested_targets = [], defaultdict(list), defaultdict(list)
    for asset in data['Assets']:
        source_id = asset['asset_id']
        strong, exact = identities(asset)
        fingerprint = {'asset': {k: v for k, v in asset.items() if k != 'asset_id'},
                       'cells': [{k: v for k, v in r.items() if k != 'asset_id'} for r in children['Source Cells'][source_id]],
                       'inspections': [{k: v for k, v in r.items() if k not in ('asset_id', 'inspection_id')} for r in children['Inspection Plan'][source_id]]}
        key = hashlib.sha256(json.dumps(fingerprint, sort_keys=True, default=str, ensure_ascii=False).encode()).hexdigest()
        matches = [strong_index[k] for k in strong if strong_index[k]]
        candidates = set.intersection(*matches) if matches else (exact_index.get(exact, set()) if not strong else set())
        if not strong and not candidates and asset.get('source_sheet') == 'EPFs' and exact:
            candidates = epf_index.get((exact[0], exact[1], normalized(asset.get('source_sequence'))), set())
        if len(candidates) > 1 and exact:
            narrowed = candidates & exact_index.get(exact, set())
            if narrowed: candidates = narrowed
        reasons = []
        if (matches and not candidates) or len(candidates) > 1:
            reasons.append('More than one possible match, or identifiers disagree.')
        target = next(iter(candidates)) if len(candidates) == 1 else None
        if target:
            if (strong or target in baselines) and conflicting_context(prior_by_id[target],asset):
                reasons.append('Identifier matches but description or location differs. Verify equipment identity before updating.')
            prior_strong, _ = identities(prior_by_id[target])
            prior_keys = {field: value for _, field, value in prior_strong}
            if any(field in prior_keys and prior_keys[field] != value for _, field, value in strong):
                reasons.append('One identifier matches but another identifier differs.')
        possible = set(candidates)
        for match in matches: possible.update(match)
        row = {'asset': asset, 'source_id': source_id, 'row_key': key, 'reasons': reasons, 'candidates': possible,
               'suggested': target, 'target': target, 'action': None, 'remembered': False}
        entries.append(row)
        duplicate_groups[(tuple(strong), exact)].append(row)
        if target: suggested_targets[target].append(row)
    for group in duplicate_groups.values():
        if len(group) > 1:
            for entry in group:
                entry['reasons'].append('These incoming rows have indistinguishable asset identities: ' + ', '.join(str(r['asset']['source_row']) for r in group) + '.')
    for group in suggested_targets.values():
        if len(group) > 1:
            for entry in group: entry['reasons'].append('Several incoming rows would update the same existing asset.')

    with closing(sqlite3.connect(store.db_path)) as conn:
        retired={r[0] for r in conn.execute('SELECT retired_id FROM asset_aliases')}
    occupied, assigned = set(prior_by_id)|retired, set()
    def new_id(entry):
        proposed = entry['source_id']
        if proposed not in occupied and proposed not in assigned: return proposed
        base = proposed.split('-')[0] + '-R' + entry['row_key'][:20]
        target, suffix = base, 1
        while target in occupied or target in assigned:
            target = base + '-' + str(suffix); suffix += 1
        return target

    decision_rows = []
    def compatible_saved(entry, target):
        if not target or target['id'] not in entry['candidates']: return False
        asset = entry['asset']
        if (target.get('source_sheet'), normalized(target.get('family'))) != (asset.get('source_sheet'), normalized(asset.get('asset_family'))): return False
        if conflicting_context(target,asset):return False
        incoming_strong, _ = identities(asset)
        old_strong, _ = identities(target)
        old_keys = {field: value for _, field, value in old_strong}
        return not any(field in old_keys and old_keys[field] != value for _, field, value in incoming_strong)

    for entry in entries:
        key, asset = entry['row_key'], entry['asset']
        explicit = key in requested
        decision = requested.get(key) if explicit else saved.get(key)
        if decision and not explicit and decision.get('action') != 'skip':
            target = prior_by_id.get(decision.get('asset_id'))
            if not compatible_saved(entry, target):
                entry['reasons'].append('The saved decision no longer matches the existing asset. Review this row again.')
                decision = None
        if decision and decision.get('action') != 'review':
            action = decision['action']
            target = None
            if action == 'match':
                target = decision.get('asset_id')
                if target not in prior_by_id or (explicit and target not in entry['candidates']):
                    raise ValueError('Choose one of this row\'s existing asset matches.')
                existing = prior_by_id[target]
                if (asset.get('source_sheet'),normalized(asset.get('asset_family'))) not in accepted_scopes[target]:
                    raise ValueError('Existing asset must have a compatible accepted source tab and family.')
            elif action == 'separate':
                if explicit and decision.get('asset_id'):
                    raise ValueError('A separate asset cannot reuse a supplied existing ID.')
                previous = saved.get(key)
                previous_target = prior_by_id.get(previous.get('asset_id')) if previous else None
                compatible = compatible_saved(entry, previous_target)
                if explicit and previous and previous['action'] == 'separate' and compatible:
                    target = previous['asset_id']
                else:
                    target = new_id(entry) if explicit else decision['asset_id']
            elif action != 'skip':
                raise ValueError('Invalid duplicate resolution action')
            entry.update(action=action, target=target, remembered=not explicit)
            decision_rows.append({'row_key': key, 'source_sheet': asset['source_sheet'], 'source_row': asset['source_row'], 'action': action, 'asset_id': target})
        elif not entry['target']:
            entry['target'] = new_id(entry)
        if entry['action'] != 'skip': assigned.add(entry['target'])

    by_target = defaultdict(list)
    for entry in entries:
        if entry['action'] != 'skip': by_target[entry['target']].append(entry)
    collision_keys = set()
    for target, group in by_target.items():
        if len(group) > 1:
            for entry in group:
                entry['reasons'].append('Two selected rows target the same asset. Choose a different match, keep separate, or skip one.')
                collision_keys.add(entry['row_key'])
    conflicts, unresolved = [], 0
    for entry in entries:
        if not entry['reasons']: continue
        decided = bool(entry['action']) and entry['row_key'] not in collision_keys
        if not decided: unresolved += 1
        asset = entry['asset']; source_id = entry['source_id']
        conflicts.append({'row_key': entry['row_key'], 'source_sheet': asset['source_sheet'], 'source_row': asset['source_row'],
                          'asset': snapshot(asset), 'inspections': children['Inspection Plan'][source_id], 'notes': children['Notes & Actions'][source_id],
                          'reasons': list(dict.fromkeys(entry['reasons'])),
                          'candidates': [snapshot(prior_by_id[i]) for i in sorted(entry['candidates'])],
                          'decision': {'action': entry['action'], 'asset_id': entry['target'] if entry['action'] == 'match' else None} if entry['action'] else None,
                          'resolved': decided, 'remembered': entry['remembered']})
    # Metadata snapshots must remain pristine after remapping/pruning the tables.
    conflicts = json.loads(json.dumps(conflicts, default=str, ensure_ascii=False))
    assignments = {e['source_id']: e['target'] for e in entries if e['action'] != 'skip'}
    # Keep provisional tables internally consistent while unresolved target
    # collisions remain blocked, avoiding a cascade of duplicate-ID messages.
    provisional = set()
    for entry in entries:
        if entry['action'] == 'skip': continue
        target = assignments[entry['source_id']]
        if target in provisional: assignments[entry['source_id']] = 'PREVIEW-' + entry['row_key']
        provisional.add(assignments[entry['source_id']])
    skipped = {e['source_id'] for e in entries if e['action'] == 'skip'}
    data['Assets'] = [a for a in data['Assets'] if a['asset_id'] not in skipped]
    for asset in data['Assets']: asset['asset_id'] = assignments[asset['asset_id']]
    for table in ('Inspection Plan', 'Technical Details', 'Notes & Actions', 'Review Items', 'Source Cells'):
        if table != 'Source Cells': data[table] = [r for r in data[table] if r.get('asset_id') not in skipped]
        for row in data[table]:
            old = row.get('asset_id')
            if old in skipped:
                row.update(asset_id=None, row_role='Skipped by import review')
            elif old in assignments:
                row['asset_id'] = assignments[old]
                for key in ('inspection_id', 'note_id', 'review_id'):
                    if row.get(key, '').startswith(old + '-'): row[key] = assignments[old] + row[key][len(old):]
    data[DECISION_SHEET] = decision_rows
    errors = [f'{unresolved} incoming rows need identity decisions. Resolve the rows below and update the preview.'] if unresolved else []
    return errors, {'conflicts': conflicts, 'unresolved_count': unresolved, 'skipped_count': len(skipped),
                    'remembered_count': sum(e['remembered'] for e in entries)}

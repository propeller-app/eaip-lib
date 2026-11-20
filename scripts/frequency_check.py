"""
Write a manual-review list of airspace entries whose chosen frequency is
ambiguous (more than one distinct non-secondary frequency in the record).

Run from the repository root::

    PYTHONPATH=. uv run python scripts/frequency_check.py
"""
import os
import pathlib
import re
import sys

from eaip.airspace.boundary import parse_boundaries
from eaip.enr21 import parse_enr21
from eaip.export import (_is_secondary_frequency, _parse_frequency,
                         export_airspaces)

FIXTURE = (pathlib.Path(__file__).resolve().parent.parent
           / 'tests' / 'fixtures' / 'EG-ENR-2.1.html')
OUTPUT = (pathlib.Path(__file__).resolve().parent.parent
          / 'out' / 'frequency_check.txt')


def _record_frequencies(record):
    """
    Every non-secondary frequency as (value, unit callsign, annotation).
    """
    rows = []
    for unit in record['units']:
        frequencies = unit['frequencies']
        annotations = unit.get('frequency_annotations') or [None] * len(frequencies)
        for text, annotation in zip(frequencies, annotations):
            if _is_secondary_frequency(annotation):
                continue
            rows.append((_parse_frequency(text, record['name']),
                         unit.get('callsign') or '', annotation or ''))
    return rows


def frequency_report(html: str) -> str:
    """
    The report text for the ambiguous exported airspace entries.
    """
    records = parse_enr21(html)
    boundaries, failed = parse_boundaries(records)
    if failed:
        raise ValueError(f'boundaries failed to parse: {failed}')
    exported = export_airspaces(records, boundaries)
    entries = exported['ctas'] + exported['ctrs'] + exported['tma']

    by_name = {record['name']: record for record in records}
    ambiguous = {}
    for entry in entries:
        if entry['frequency_ambiguous']:
            ambiguous.setdefault(entry['name'], entry)

    lines = [
        f'Ambiguous entries: {sum(1 for e in entries if e["frequency_ambiguous"])}'
        f' / {len(entries)} exported',
        '',
    ]
    for name in sorted(ambiguous):
        entry = ambiguous[name]
        lines.append(name)
        lines.append(
            f'  picked: {entry["frequency"]}  '
            f'"{entry["frequency_annotation"]}"')
        for value, callsign, annotation in _record_frequencies(by_name[name]):
            if value == entry['frequency']:
                continue
            lines.append(f'  other:  {value}  {callsign}  "{annotation}"')
        lines.append('')
    return '\n'.join(lines)


def main() -> None:
    html = FIXTURE.read_text(encoding='utf-8')
    text = frequency_report(html)
    os.makedirs(OUTPUT.parent, exist_ok=True)
    OUTPUT.write_text(text, encoding='utf-8')
    print(f'wrote {OUTPUT} ({len(text.splitlines())} lines)')


if __name__ == '__main__':
    sys.exit(main())

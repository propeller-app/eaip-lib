import json
import os
import re
import typing

from eaip.airspace.boundary import parse_boundaries
from eaip.enr21 import parse_enr21


_SOURCE = 'ENR-2.1'
_KEYWORDS = ('TMA', 'CTR', 'CTA')
_TARGETS = {'TMA': 'tma', 'CTR': 'ctrs', 'CTA': 'ctas'}
_FILES = (('ctas', 'ctas.json'), ('ctrs', 'ctrs.json'),
          ('tma', 'tma.json'), ('skipped', 'skipped_airspaces.json'))
_FL_RE = re.compile(r'^FL\s+(\d+)$')
_FREQUENCY_RE = re.compile(r'^(\d+(?:\.\d+)?)\s*(?:MHz)?$')
_CLASS_RE = re.compile(r'^[A-G]$')
_SKIPPED_REASON = 'FIR/UIR/OCA or no CTA/CTR/TMA keyword'


def _route(name: str) -> typing.Optional[str]:
    """
    The caa-map file a record belongs to, from the keyword in its name.

    ``TMA`` goes to ``tma``, ``CTR`` to ``ctrs`` and ``CTA`` to ``ctas``.
    A name matching more than one keyword is ambiguous and raises; a name
    matching none (FIR, UIR, OCA) returns None.
    """
    found = [keyword for keyword in _KEYWORDS
             if re.search(r'\b' + keyword + r'\b', name)]
    if len(found) > 1:
        raise ValueError(
            f'{name}: ambiguous airspace type: {", ".join(found)}')
    return found[0] if found else None


def _normalise_limit(text: typing.Any, name: str) -> str:
    """
    Whitespace-normalised printed limit with only ``FL 195`` -> ``FL195``.
    """
    if not isinstance(text, str) or not text.strip():
        raise ValueError(f'{name}: missing or invalid vertical limit {text!r}')
    value = re.sub(r'\s+', ' ', text).strip()
    match = _FL_RE.match(value)
    if match is not None:
        value = f'FL{match.group(1)}'
    return value


def _class(value: typing.Any, name: str) -> str:
    """
    The band's single-letter airspace class, A to G.
    """
    if not isinstance(value, str) or _CLASS_RE.match(value) is None:
        raise ValueError(f'{name}: invalid class {value!r}')
    return value


def _parse_frequency(text: typing.Any, name: str) -> float:
    """
    Printed frequency to MHz as a float. Accepts a trailing ``MHz`` unit
    (used by the BRIZE NORTON CTR rows).
    """
    if not isinstance(text, str):
        raise ValueError(f'{name}: unparseable frequency {text!r}')
    match = _FREQUENCY_RE.match(text.strip())
    if match is None:
        raise ValueError(f'{name}: unparseable frequency {text!r}')
    return float(match.group(1))


def _frequencies(record: typing.Mapping[str, typing.Any]) -> typing.List[float]:
    """
    Every distinct frequency in document order, as MHz floats.
    """
    values = []
    for unit in record.get('units') or []:
        for text in unit.get('frequencies') or []:
            value = _parse_frequency(text, record['name'])
            if value not in values:
                values.append(value)
    return values


def _frequency(record: typing.Mapping[str, typing.Any]) -> typing.Union[float, str]:
    """
    The first unit's first frequency, or ``''`` when there is none.
    """
    units = record.get('units') or []
    if units and units[0].get('frequencies'):
        return _parse_frequency(units[0]['frequencies'][0], record['name'])
    return ''


def _boundary(record: typing.Mapping[str, typing.Any],
              boundaries: typing.Mapping[str, typing.Mapping[str, typing.Any]]
              ) -> typing.Tuple[typing.List[dict], typing.List[str]]:
    """
    The closed point ring and exclusions for a record, from parse_boundaries.
    """
    name = record['name']
    parsed = boundaries.get(name)
    if parsed is None:
        raise ValueError(f'{name}: missing boundary')
    points = parsed.get('points')
    if not points:
        raise ValueError(f'{name}: empty boundary')
    return points, list(parsed.get('exclusions') or [])


def export_airspaces(
        records: typing.Iterable[typing.Mapping[str, typing.Any]],
        boundaries: typing.Mapping[str, typing.Mapping[str, typing.Any]],
) -> typing.Dict[str, typing.List[dict]]:
    """
    Export ENR-2.1 records in caa-map's CTA, CTR and TMA JSON shapes.

    Each band becomes one entry, so a record with two bands yields two
    entries that share the same boundary; ``band_index`` is 0-based. Records
    whose name contains no CTA/CTR/TMA keyword (FIR, UIR, OCA) are listed in
    ``skipped`` with a reason. Name routing raises when a name matches more
    than one keyword.

    Entry keys are always ``name``, ``upper_limit``, ``lower_limit``,
    ``_class``, ``frequency``, ``squawk``, ``boundary``, ``band_index``,
    ``frequencies``, ``exclusions`` and ``source``. ``frequency`` is a MHz
    float or ``''``; ``frequencies`` is every distinct MHz float in document
    order; ``squawk`` is always ``''`` because ENR-2.1 has no machine-readable
    squawk. Boundary points are WGS84 decimal degrees and the ring is closed
    (first point equals last).

    :param records: Records from :func:`eaip.enr21.parse_enr21`.
    :param boundaries: The parsed mapping from
        :func:`eaip.airspace.boundary.parse_boundaries` (first element of its
        return value), keyed by record name.
    :return: ``{'ctas': [...], 'ctrs': [...], 'tma': [...],
        'skipped': [{'name', 'reason'}]}`` in document order.
    """
    result = {'ctas': [], 'ctrs': [], 'tma': [], 'skipped': []}

    for record in records:
        name = record['name']
        keyword = _route(name)
        if keyword is None:
            result['skipped'].append(
                {'name': name, 'reason': _SKIPPED_REASON})
            continue

        frequencies = _frequencies(record)
        frequency = _frequency(record)
        points, exclusions = _boundary(record, boundaries)

        for index, band in enumerate(record['bands']):
            result[_TARGETS[keyword]].append({
                'name': name,
                'upper_limit': _normalise_limit(band.get('upper'), name),
                'lower_limit': _normalise_limit(band.get('lower'), name),
                '_class': _class(band.get('class'), name),
                'frequency': frequency,
                'squawk': '',
                'boundary': [dict(point) for point in points],
                'band_index': index,
                'frequencies': list(frequencies),
                'exclusions': exclusions,
                'source': _SOURCE,
            })

    return result


def write_airspace_files(html: str, out_dir: str) -> typing.Dict[str, list]:
    """
    Parse an ENR-2.1 document and write the four caa-map JSON files.

    Files are ``ctas.json``, ``ctrs.json``, ``tma.json`` and
    ``skipped_airspaces.json``, written with UTF-8 and one-space indentation.
    The directory is created if needed. A boundary parse failure raises
    instead of writing a partial export.

    :param html: The eAIP ENR-2.1 HTML document.
    :param out_dir: Directory to write the four files into.
    :return: The same dict as :func:`export_airspaces`.
    :raises ValueError: If a boundary fails to parse, or a record is invalid.
    """
    records = parse_enr21(html)
    boundaries, failed = parse_boundaries(records)
    if failed:
        raise ValueError(
            f'{len(failed)} boundaries failed to parse: {failed}')

    result = export_airspaces(records, boundaries)
    os.makedirs(out_dir, exist_ok=True)
    for key, filename in _FILES:
        with open(os.path.join(out_dir, filename), 'w',
                  encoding='utf-8') as handle:
            json.dump(result[key], handle, ensure_ascii=False, indent=1)
    return result

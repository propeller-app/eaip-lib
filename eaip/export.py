import json
import os
import re
import typing

from eaip.airspace.boundary import parse_boundaries
from eaip.enr21 import parse_enr21
from eaip.enr41 import parse_enr41
from eaip.enr51 import parse_enr51, parse_enr51_boundaries


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


# Annotations that mark a frequency as a secondary channel. Only these two
# phrases are excluded; "As directed", "directed by ATC", DOC and notes are
# operational descriptions and stay eligible.
SECONDARY_FREQUENCY_MARKERS = ('instructed by atc', 'emergency')


def _is_secondary_frequency(annotation: typing.Optional[str]) -> bool:
    text = (annotation or '').lower()
    return any(marker in text for marker in SECONDARY_FREQUENCY_MARKERS)


def _unit_frequencies(record: typing.Mapping[str, typing.Any],
                      unit: typing.Mapping[str, typing.Any]
                      ) -> typing.List[typing.Tuple[str, typing.Optional[str]]]:
    """
    A unit's printed frequencies paired with their annotations.
    """
    frequencies = unit.get('frequencies') or []
    annotations = unit.get('frequency_annotations')
    if annotations is None:
        annotations = [None] * len(frequencies)
    if len(annotations) != len(frequencies):
        raise ValueError(
            f'{record["name"]}: frequency_annotations is not aligned with '
            'frequencies')
    return list(zip(frequencies, annotations))


def select_frequency(
        record: typing.Mapping[str, typing.Any]
) -> typing.Tuple[str, str, bool]:
    """
    Choose one frequency for an ENR-2.1 record and report its annotation.

    The pick is the first non-secondary frequency in the first unit that has
    one. A frequency is secondary when its annotation contains one of
    :data:`SECONDARY_FREQUENCY_MARKERS` (case-insensitive); nothing else is
    excluded. If every frequency is secondary the very first frequency is
    used. A record with no frequency returns ``('', '', False)``.

    ``ambiguous`` is True when the record has more than one distinct
    non-secondary frequency across all its units.

    :return: ``(printed_frequency, annotation_or_"", ambiguous)``.
    """
    units = record.get('units') or []
    picked = None
    non_secondary = []

    for unit in units:
        for text, annotation in _unit_frequencies(record, unit):
            value = _parse_frequency(text, record['name'])
            if _is_secondary_frequency(annotation):
                continue
            if value not in non_secondary:
                non_secondary.append(value)
            if picked is None:
                picked = (text, annotation or '')

    if picked is None:
        for unit in units:
            for text, annotation in _unit_frequencies(record, unit):
                _parse_frequency(text, record['name'])
                picked = (text, annotation or '')
                break
            if picked is not None:
                break

    if picked is None:
        return '', '', False
    return picked[0], picked[1], len(non_secondary) > 1


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
    ``_class``, ``frequency``, ``frequency_annotation``,
    ``frequency_ambiguous``, ``squawk``, ``boundary``, ``band_index``,
    ``frequencies``, ``exclusions`` and ``source``. ``frequency`` is a MHz
    float or ``''``; ``frequency_annotation`` is the chosen frequency's
    annotation (``''`` when none); ``frequency_ambiguous`` is True when the
    record has more than one distinct non-secondary frequency;
    ``frequencies`` is every distinct MHz float in document order; ``squawk``
    is always ``''`` because ENR-2.1 has no machine-readable squawk. Boundary
    points are WGS84 decimal degrees and the ring is closed (first point
    equals last).

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
        frequency_text, frequency_annotation, frequency_ambiguous = (
            select_frequency(record))
        frequency = (_parse_frequency(frequency_text, name)
                     if frequency_text else '')
        points, exclusions = _boundary(record, boundaries)

        for index, band in enumerate(record['bands']):
            result[_TARGETS[keyword]].append({
                'name': name,
                'upper_limit': _normalise_limit(band.get('upper'), name),
                'lower_limit': _normalise_limit(band.get('lower'), name),
                '_class': _class(band.get('class'), name),
                'frequency': frequency,
                'frequency_annotation': frequency_annotation,
                'frequency_ambiguous': frequency_ambiguous,
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


# Positive PIL Image.rotate turns the image counter-clockwise. An easterly
# variation puts magnetic north east of true north, so the rose must turn
# clockwise: rotation = -value. This sign is a chart convention derived from
# the rose image, not something caa-map's code states.
ROSE_ROTATION_SIGN = -1

_DANGER_UPPER_RE = re.compile(r'^(FL\d+|\d+ FT (?:ALT|AGL))$')
_DANGER_LOWER_RE = re.compile(
    r'^(FL\d+|\d+ FT (?:ALT|AGL)|SFC|As Per AUP / UUP)?$')


def _danger_text(text: typing.Optional[str]) -> str:
    """
    Printed limit text, whitespace-normalised and ``FL 195`` -> ``FL195``.
    """
    if text is None:
        return ''
    value = re.sub(r'\s+', ' ', text).strip()
    match = _FL_RE.match(value)
    if match is not None:
        value = f'FL{match.group(1)}'
    return value


def export_danger(
        records: typing.Iterable[typing.Mapping[str, typing.Any]],
        boundaries: typing.Mapping[str, typing.Mapping[str, typing.Any]],
) -> typing.Dict[str, typing.List[dict]]:
    """
    Export ENR-5.1 records in caa-map's danger.json shape.

    Only records whose printed upper limit contains a digit are exported, so
    the renderer's ``re.findall(r'(\\d+)', upper_limit)[0]`` cannot raise.
    ``UNL`` and ``As Per AUP / UUP`` records go to ``skipped`` with the
    printed text as the reason. Lower limits may be ``SFC``, ``FL n``,
    ``n FT ALT/AGL``, ``As Per AUP / UUP`` or absent (exported as ``''``).

    Entry keys are always ``name``, ``upper_limit``, ``lower_limit``,
    ``ident``, ``eaip_ident``, ``boundary``, ``section``, ``approximate``,
    ``exclusions`` and ``source``. ``ident`` is the label form with the leading
    ``EG`` removed (``EGD044`` -> ``D044``) and ``eaip_ident`` is the printed
    ident. Limits are as printed (``FL 195`` -> ``FL195``); boundary points
    are WGS84 decimal degrees and the ring is closed (first equals last). A
    record missing from ``boundaries`` is reported in ``skipped``, not
    raised.

    :param records: Records from :func:`eaip.enr51.parse_enr51`.
    :param boundaries: The parsed mapping from
        :func:`eaip.enr51.parse_enr51_boundaries` (first element of its return
        value), keyed by ident.
    :return: ``{'danger': [...], 'skipped': [{'ident', 'name', 'section',
        'reason'}]}`` in document order.
    :raises ValueError: If an exported limit is not a known printed form, an
        ident does not start with ``EG``, or two exported records share the
        ident after stripping ``EG``.
    """
    result = {'danger': [], 'skipped': []}

    for record in records:
        ident = record['ident']
        name = record['name']
        section = record['section']
        limits = record.get('limits') or {}
        upper_limit = limits.get('upper')
        upper_text = '' if upper_limit is None else (upper_limit.get('text') or '')

        if re.search(r'\d', upper_text) is None:
            result['skipped'].append({
                'ident': ident,
                'name': name,
                'section': section,
                'reason': upper_text or 'missing upper limit',
            })
            continue

        if not isinstance(ident, str) or not ident.startswith('EG'):
            raise ValueError(f'{ident!r}: ident does not start with EG')
        label_ident = ident[2:]

        upper = _danger_text(upper_text)
        lower_limit = limits.get('lower')
        lower = _danger_text(
            None if lower_limit is None else lower_limit.get('text'))
        if _DANGER_UPPER_RE.match(upper) is None:
            raise ValueError(f'{ident}: unknown upper limit {upper!r}')
        if _DANGER_LOWER_RE.match(lower) is None:
            raise ValueError(f'{ident}: unknown lower limit {lower!r}')

        parsed = boundaries.get(ident)
        if parsed is None:
            result['skipped'].append({
                'ident': ident,
                'name': name,
                'section': section,
                'reason': 'missing boundary',
            })
            continue

        result['danger'].append({
            'name': name,
            'upper_limit': upper,
            'lower_limit': lower,
            'ident': label_ident,
            'eaip_ident': ident,
            'boundary': [dict(point) for point in parsed['points']],
            'section': section,
            'approximate': bool(parsed.get('approximate')),
            'exclusions': list(parsed.get('exclusions') or []),
            'source': 'ENR-5.1',
        })

    labels = [entry['ident'] for entry in result['danger']]
    duplicates = sorted({label for label in labels if labels.count(label) > 1})
    if duplicates:
        raise ValueError(
            'duplicate danger ident after stripping EG: '
            + ', '.join(duplicates))
    return result


def export_vors(
        records: typing.Iterable[typing.Mapping[str, typing.Any]]
) -> typing.Dict[str, typing.List[dict]]:
    """
    Export ENR-4.1 rows that have a VOR component in caa-map's vors.json shape.

    Only rows whose ``components`` include ``VOR`` are exported (VOR and
    VOR/DME); DME-only and NDB rows go to ``skipped``. ``frequency`` is the
    printed MHz value as a string (``str(value)``), ``dme`` is True when
    ``DME`` is also a component, and ``rotation`` is
    ``ROSE_ROTATION_SIGN * (declination or magnetic_variation)`` in degrees.

    Entry keys are always ``id``, ``location``, ``frequency``, ``dme``,
    ``rotation``, ``name``, ``type``, ``source`` and ``rotation_source``.

    :param records: Records from :func:`eaip.enr41.parse_enr41`.
    :return: ``{'vors': [...], 'skipped': [{'id', 'name', 'type',
        'reason'}]}`` in document order.
    :raises ValueError: If a VOR row has no declination and no magnetic
        variation, or no frequency.
    """
    result = {'vors': [], 'skipped': []}

    for record in records:
        components = record.get('components') or []
        if 'VOR' not in components:
            result['skipped'].append({
                'id': record['id'],
                'name': record['name'],
                'type': record['type'],
                'reason': 'no VOR component',
            })
            continue

        declination = record.get('declination')
        variation = record.get('magnetic_variation')
        if declination is not None:
            start = declination['value']
            rotation_source = 'declination'
        elif variation is not None:
            start = variation['value']
            rotation_source = 'magnetic_variation'
        else:
            raise ValueError(
                f'{record["id"]}: no declination or magnetic variation')

        frequency = record.get('frequency')
        if frequency is None:
            raise ValueError(f'{record["id"]}: missing frequency')
        location = record['location']

        result['vors'].append({
            'id': record['id'],
            'location': {'lat': location['lat'], 'lng': location['lng']},
            'frequency': str(frequency['value']),
            'dme': 'DME' in components,
            'rotation': ROSE_ROTATION_SIGN * start + 0.0,
            'name': record['name'],
            'type': record['type'],
            'source': 'ENR-4.1',
            'rotation_source': rotation_source,
        })

    return result


def write_danger_vors_files(enr51_html: str, enr41_html: str,
                            out_dir: str) -> typing.Dict[str, dict]:
    """
    Parse ENR-5.1 and ENR-4.1 and write the four caa-map JSON files.

    Files are ``danger.json``, ``danger_skipped.json``, ``vors.json`` and
    ``vors_skipped.json``, written with UTF-8 and one-space indentation. The
    directory is created if needed. Boundary failures raise instead of writing
    a partial export.

    :param enr51_html: The eAIP ENR-5.1 HTML document.
    :param enr41_html: The eAIP ENR-4.1 HTML document.
    :param out_dir: Directory to write the four files into.
    :return: ``{'danger': export_danger(...), 'vors': export_vors(...)}``.
    :raises ValueError: If a boundary fails to parse, or a record is invalid.
    """
    danger_records = parse_enr51(enr51_html)
    boundaries, failed = parse_enr51_boundaries(danger_records)
    if failed:
        raise ValueError(
            f'{len(failed)} boundaries failed to parse: {failed}')

    danger = export_danger(danger_records, boundaries)
    vors = export_vors(parse_enr41(enr41_html))

    os.makedirs(out_dir, exist_ok=True)
    files = (
        ('danger.json', danger['danger']),
        ('danger_skipped.json', danger['skipped']),
        ('vors.json', vors['vors']),
        ('vors_skipped.json', vors['skipped']),
    )
    for filename, value in files:
        with open(os.path.join(out_dir, filename), 'w',
                  encoding='utf-8') as handle:
            json.dump(value, handle, ensure_ascii=False, indent=1)
    return {'danger': danger, 'vors': vors}

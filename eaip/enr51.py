import re
import typing

from bs4 import BeautifulSoup

from eaip.airspace.boundary import (BoundaryError, NM_METRES, _COORD,
                                    _COORD_RE, _coordinate, circle_points,
                                    parse_boundary)
from eaip.enr21 import _text_with_breaks


_SECTIONS = ('Danger Area', 'Prohibited Area', 'Restricted Area')
_LIMIT_LABELS = (('Upper limit:', 'upper'), ('Lower limit:', 'lower'))
_VOLUME_PREFIX = 'TAIRSPACE_VOLUME;'
_EXCLUSION_RE = re.compile(r'\s+Excluding\s+(.+?)\.?\s*$')
_CIRCLE_RE = re.compile(
    r'^A circle, (?P<radius>\d+(?:\.\d+)?) (?P<unit>NM|M|FT) radius, '
    r'centred at ' + _COORD + r'$')
_COASTLINE_RE = re.compile(
    r'(?<=\d[EW]) - (then along [^0-9]*? to) (?=\d{6}[NS])')


def _field(cell, prefix: str) -> typing.Optional[str]:
    """
    Visible value of the ``span.SD`` paired with an ``sdParams`` tag that
    starts with ``prefix``. Empty tooltip spans between the value and its
    metadata are skipped.
    """
    for params in cell.find_all('span', class_='sdParams'):
        if not params.get_text(strip=True).startswith(prefix):
            continue
        span = params.find_previous_sibling('span', class_='SD')
        if span is not None:
            return _text_with_breaks(span)
    return None


def _divider(row) -> typing.Optional[str]:
    """
    Section name for a divider row (``row_id="0"``), else None.
    """
    if row.get('row_id') != '0':
        return None
    cells = row.find_all('td', recursive=False)
    if not cells:
        return None
    label = _text_with_breaks(cells[0])
    return label if label in _SECTIONS else None


def _boundary_text(cell, ident: str, name: typing.Optional[str]) -> str:
    """
    The lateral-limit text with the identification and name removed, kept
    otherwise as printed and whitespace-normalised.
    """
    text = _text_with_breaks(cell)
    text = re.sub(r'^\s*' + re.escape(ident) + r'\s*', '', text, count=1)
    if name:
        text = re.sub(r'^\s*' + re.escape(name) + r'\s*', '', text, count=1)
    return re.sub(r'\s+', ' ', text).strip()


def _limits_cell(cells) -> typing.Optional[typing.Any]:
    """
    The cell holding the printed Upper/Lower limit paragraphs.
    """
    for cell in cells:
        for paragraph in cell.find_all('p'):
            text = _text_with_breaks(paragraph)
            if text.startswith(tuple(label for label, _ in _LIMIT_LABELS)):
                return cell
    return None


def _limit(paragraph, printed: str, key: str) -> dict:
    """
    One vertical limit, built from the hidden volume tags in ``paragraph``.
    ``value``/``uom``/``code`` are None when not printed; ``annotation`` holds
    the printed annotation text, and ``text`` is the whole printed limit.
    """
    upper = key == 'upper'
    suffix = 'UPPER' if upper else 'LOWER'
    value_tag = f'{_VOLUME_PREFIX}VAL_DIST_VER_{suffix}'
    uom_tag = f'{_VOLUME_PREFIX}UOM_DIST_VER_{suffix}'
    code_tag = f'{_VOLUME_PREFIX}CODE_DIST_VER_{suffix}'
    annotation_tag = f'{_VOLUME_PREFIX}ANNOTATION'

    value = uom = code = annotation = None
    for span in paragraph.find_all('span', class_='SD'):
        params = span.find_next_sibling('span', class_='sdParams')
        tag = params.get_text(strip=True) if params is not None else ''
        text = _text_with_breaks(span)
        if tag.startswith(value_tag):
            value = text
        elif tag.startswith(uom_tag):
            uom = text
        elif tag.startswith(code_tag):
            code = text
        elif tag.startswith(annotation_tag):
            annotation = text

    return {
        'value': value,
        'uom': uom,
        'code': code,
        'annotation': annotation,
        'text': printed.strip(),
    }


def _limits(cell) -> typing.Dict[str, typing.Optional[dict]]:
    """
    Parse the Upper/Lower limit paragraphs; absent parts of each limit are
    None and the ``text`` field is always the printed value.
    """
    limits = {'upper': None, 'lower': None}
    if cell is None:
        return limits
    for paragraph in cell.find_all('p'):
        text = _text_with_breaks(paragraph)
        for label, key in _LIMIT_LABELS:
            if text.startswith(label):
                limits[key] = _limit(paragraph, text[len(label):], key)
                break
    return limits


def _activation(cells) -> typing.List[str]:
    """
    Printed activation texts, in document order.
    """
    values = []
    for cell in cells:
        for span in cell.find_all('span', class_='SD'):
            params = span.find_next_sibling('span', class_='sdParams')
            tag = params.get_text(strip=True) if params is not None else ''
            if tag.startswith('TAIRSPACE_ACTIVATION'):
                value = _text_with_breaks(span)
                if value:
                    values.append(value)
    return values


def parse_enr51(html: str) -> typing.List[typing.Dict[str, typing.Any]]:
    """
    Parses an eAIP ENR-5.1 (danger, prohibited and restricted areas) document
    into raw records.

    Boundary geometry stays as printed text; nothing is resolved or parsed into
    coordinates. The section dividers (``Danger Area``, ``Prohibited Area`` and
    ``Restricted Area``) and the column-header rows are not records.

    Example:

    ::

        with open('EG-ENR-5.1-en-GB.html') as f:
            records = parse_enr51(f.read())
        records[0]['ident']
        # Expected output: 'EGD001'

    :param html: The eAIP ENR-5.1 HTML document.
    :return: One record per airspace, in document order. Each record is a dict
        with ``row_id`` (str or None), ``ident`` (str), ``name`` (str),
        ``section`` (str: one of the three divider labels), ``boundary_text``
        (str, whitespace-normalised lateral-limit text, unparsed), ``limits``
        (``{'upper', 'lower'}``, each a dict with ``value``, ``uom``, ``code``,
        ``annotation`` and ``text``; absent parts are None), ``remarks`` (str
        with ``<br>`` turned into newlines, or None) and ``activation`` (list of
        printed activation texts, empty when none).
    """
    soup = BeautifulSoup(html, 'html.parser')
    records = []
    section = None

    for row in soup.find_all('tr'):
        cells = row.find_all('td', recursive=False)
        if not cells:
            continue
        ident = _field(cells[0], 'TAIRSPACE;CODE_ID')
        if ident is None:
            divider = _divider(row)
            if divider is not None:
                section = divider
            continue

        name = _field(cells[0], 'TAIRSPACE;TXT_NAME')
        limits_cell = _limits_cell(cells)
        remarks = _text_with_breaks(cells[-1])
        records.append({
            'row_id': row.get('row_id') or None,
            'ident': ident,
            'name': name,
            'section': section,
            'boundary_text': _boundary_text(cells[0], ident, name),
            'limits': _limits(limits_cell),
            'remarks': None if remarks in ('', '-') else remarks,
            'activation': _activation(cells),
        })

    return records


def _strip_exclusion(text: str) -> typing.Tuple[str, typing.List[str]]:
    """
    Remove a trailing ``Excluding ...`` sentence that follows the last
    coordinate. The captured text keeps its printed wording with the final
    period stripped; no geometry is subtracted.
    """
    match = _EXCLUSION_RE.search(text)
    if match is None:
        return text, []
    coordinates = list(_COORD_RE.finditer(text))
    if not coordinates or match.start() < coordinates[-1].end():
        return text, []
    captured = match.group(1).strip()
    if captured.endswith('.'):
        captured = captured[:-1]
    return text[:match.start()].rstrip(), [captured]


def _circle_boundary(text: str,
                     exclusions: typing.List[str]) -> typing.Dict[str, typing.Any]:
    """
    Parse a strict ``A circle, <radius> <unit> radius, centred at <centre>``
    text into a closed ring. Any other wording, unit or trailing text raises
    :class:`BoundaryError`.
    """
    match = _CIRCLE_RE.match(text)
    if match is None:
        raise BoundaryError(f'unparsed circle: {text[:120]!r}')

    printed_radius = match.group('radius')
    printed_unit = match.group('unit')
    centre = _coordinate(match.groups(), 2)
    radius = float(printed_radius)
    if printed_unit == 'NM':
        radius_nm = radius
    elif printed_unit == 'M':
        radius_nm = radius / NM_METRES
    else:
        radius_nm = radius * 0.3048 / NM_METRES

    return {
        'shape': 'circle',
        'points': circle_points(centre, radius_nm),
        'exclusions': exclusions,
        'approximations': [],
        'approximate': False,
        'circle': {
            'centre': centre,
            'radius_nm': radius_nm,
            'printed_radius': printed_radius,
            'printed_unit': printed_unit,
        },
    }


def _coastline_chords(text: str) -> typing.Tuple[str, typing.List[str]]:
    """
    Replace each printed ``then along ... to`` phrase with a straight chord
    between its two coordinates, returning the removed phrases in order.
    """
    phrases = []

    def replace(match):
        phrases.append(match.group(1))
        return ' - '

    return _COASTLINE_RE.sub(replace, text), phrases


def parse_enr51_boundary(text: str) -> typing.Dict[str, typing.Any]:
    """
    Parse one ENR-5.1 ``boundary_text`` into geometry.

    A trailing ``Excluding ...`` sentence is recorded as an exclusion (no
    geometry is subtracted); a strict ``A circle, ...`` text becomes a ring;
    a ``then along ... to`` coastline/river phrase becomes a straight chord
    and is recorded as an approximation. Everything else is passed to
    :func:`eaip.airspace.boundary.parse_boundary` unchanged.

    :param text: Raw ENR-5.1 boundary text.
    :return: A dict with ``shape`` (``'polygon'`` or ``'circle'``), ``points``
        (closed list of ``{'lat', 'lng'}``), ``exclusions`` (list of str),
        ``approximations`` (list of printed phrases), ``approximate`` (True
        iff ``approximations`` is non-empty) and ``circle`` (None for a
        polygon; for a circle, ``{'centre', 'radius_nm', 'printed_radius',
        'printed_unit'}``).
    :raises BoundaryError: If the text does not fit the grammar.
    """
    text = re.sub(r'\s+', ' ', text).strip()
    text, exclusions = _strip_exclusion(text)

    if text.startswith('A circle,'):
        return _circle_boundary(text, exclusions)

    text, approximations = _coastline_chords(text)
    return {
        'shape': 'polygon',
        'points': parse_boundary(text),
        'exclusions': exclusions,
        'approximations': approximations,
        'approximate': bool(approximations),
        'circle': None,
    }


def parse_enr51_boundaries(
        records: typing.Iterable[typing.Mapping[str, typing.Any]]
) -> typing.Tuple[typing.Dict[str, typing.Dict[str, typing.Any]],
                  typing.List[typing.Tuple[str, str]]]:
    """
    Parse every ENR-5.1 record into geometry, keyed by ``ident``.

    :param records: Records from :func:`parse_enr51`, with ``ident``, ``name``
        and ``boundary_text``.
    :return: ``(parsed, failures)``. ``parsed`` maps ``ident`` to the
        :func:`parse_enr51_boundary` result plus ``ident`` and ``name``, in
        document order. ``failures`` is a list of ``(ident, error message)``
        for records that raised :class:`BoundaryError`; one failure does not
        stop the others.
    """
    parsed = {}
    failures = []
    for record in records:
        ident = record['ident']
        try:
            boundary = parse_enr51_boundary(record['boundary_text'])
        except BoundaryError as error:
            failures.append((ident, str(error)))
            continue
        boundary['ident'] = ident
        boundary['name'] = record['name']
        parsed[ident] = boundary
    return parsed, failures

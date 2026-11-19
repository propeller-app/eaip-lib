import re
import typing

from bs4 import BeautifulSoup

from eaip.enr21 import _text_with_breaks


_TYPE_COMPONENTS = {
    'VOR/DME': ('VOR', 'DME'),
    'VOR': ('VOR',),
    'DME': ('DME',),
    'NDB': ('NDB',),
}
_ROW_TYPES = {
    'VORDME': 'VOR/DME',
    'VOR': 'VOR',
    'DME': 'DME',
    'NDB': 'NDB',
}
_LAT_RE = re.compile(
    r'^(?P<deg>\d{2})(?P<min>\d{2})(?P<sec>\d{2}(?:\.\d+)?)'
    r'(?P<dir>[NS])$')
_LON_RE = re.compile(
    r'^(?P<deg>\d{3})(?P<min>\d{2})(?P<sec>\d{2}(?:\.\d+)?)'
    r'(?P<dir>[EW])$')
_VARIATION_RE = re.compile(
    r'^(?P<value>\d+(?:\.\d+)?)°(?P<direction>[EW])?$')


def _visible(params) -> typing.Optional[str]:
    """
    Visible value paired with an ``sdParams`` tag.
    """
    span = params.find_previous_sibling('span', class_='SD')
    return _text_with_breaks(span) if span is not None else None


def _field(cell, prefix: str) -> typing.Optional[str]:
    """
    First visible value whose ``sdParams`` tag starts with ``prefix``.
    """
    for params in cell.find_all('span', class_='sdParams'):
        if params.get_text(strip=True).startswith(prefix):
            return _visible(params)
    return None


def _fields(cell, prefix: str) -> typing.List[str]:
    """
    All visible values whose ``sdParams`` tag starts with ``prefix``.
    """
    values = []
    for params in cell.find_all('span', class_='sdParams'):
        if not params.get_text(strip=True).startswith(prefix):
            continue
        value = _visible(params)
        if value is not None:
            values.append(value)
    return values


def _field_suffix(cell, suffix: str) -> typing.Optional[str]:
    """
    First visible value whose ``sdParams`` tag has the given field name.
    """
    for params in cell.find_all('span', class_='sdParams'):
        parts = params.get_text(strip=True).split(';')
        if len(parts) > 1 and parts[1] == suffix:
            return _visible(params)
    return None


def _require(value: typing.Optional[str], label: str, field: str) -> str:
    if value is None or not value.strip():
        raise ValueError(f'{label}: missing {field}')
    return value


def _parse_type(cell_text: str, row_id: typing.Optional[str]) -> str:
    """
    Printed type from the first cell, cross-checked against the row id.
    """
    lines = [line.strip() for line in cell_text.split('\n') if line.strip()]
    if len(lines) < 2:
        raise ValueError(f'{row_id}: cannot find type')
    type_text = lines[1]
    if type_text not in _TYPE_COMPONENTS:
        raise ValueError(f'{row_id}: unknown type {type_text!r}')
    if row_id:
        parts = row_id.split('-')
        expected = _ROW_TYPES.get(parts[1]) if len(parts) > 1 else None
        if expected is not None and expected != type_text:
            raise ValueError(
                f'{row_id}: type {type_text!r} disagrees with row id')
    return type_text


def _dms_value(match: re.Match, maximum: int, text: str) -> float:
    degrees = int(match.group('deg'))
    minutes = int(match.group('min'))
    seconds = float(match.group('sec'))
    direction = match.group('dir')
    if not 0 <= degrees <= maximum:
        raise ValueError(f'{text}: degrees out of range')
    if not 0 <= minutes < 60:
        raise ValueError(f'{text}: minutes out of range')
    if not 0 <= seconds < 60:
        raise ValueError(f'{text}: seconds out of range')
    if degrees == maximum and (minutes or seconds):
        raise ValueError(f'{text}: degrees/minutes/seconds out of range')
    value = degrees + minutes / 60 + seconds / 3600
    return -value if direction in ('S', 'W') else value


def _parse_coordinate(text: str,
                      label: str = 'coordinate') -> typing.Tuple[float, float]:
    """
    Parse ``DDMMSS.ssN DDDMMSS.ssE`` into WGS84 decimal degrees.
    """
    tokens = text.split()
    if len(tokens) != 2:
        raise ValueError(f'{label}: unparseable coordinate {text!r}')
    lat_matches = [m for token in tokens if (m := _LAT_RE.match(token))]
    lon_matches = [m for token in tokens if (m := _LON_RE.match(token))]
    if len(lat_matches) != 1 or len(lon_matches) != 1:
        raise ValueError(f'{label}: unparseable coordinate {text!r}')
    lat = _dms_value(lat_matches[0], 90, text)
    lng = _dms_value(lon_matches[0], 180, text)
    return lat, lng


def _parse_variation(text: str, label: str = 'variation') -> float:
    """
    Convert ``D.DD°E`` / ``D.DD°W`` to signed degrees, east positive.
    """
    match = _VARIATION_RE.match(text)
    if match is None:
        raise ValueError(f'{label}: unparseable variation/declination {text!r}')
    value = float(match.group('value'))
    direction = match.group('direction')
    if direction is None:
        if value != 0:
            raise ValueError(
                f'{label}: variation/declination without direction {text!r}')
        return 0.0
    return -value if direction == 'W' else value


def _frequency(cell, prefix: str, value_field: str, unit_field: str,
               label: str) -> typing.Optional[dict]:
    text = _field(cell, f'{prefix};{value_field}')
    if text is None:
        return None
    unit = _field(cell, f'{prefix};{unit_field}')
    if unit is None:
        raise ValueError(f'{label}: frequency without a unit')
    return {'text': text, 'value': float(text), 'unit': unit}


def _elevation(cell, label: str) -> typing.Optional[dict]:
    text = _field_suffix(cell, 'VAL_ELEV')
    if text is None:
        return None
    cell_text = _text_with_breaks(cell)
    match = re.match(r'^' + re.escape(text) + r'\s+(?P<unit>\S+)$', cell_text)
    if match is None:
        raise ValueError(f'{label}: unparseable elevation {cell_text!r}')
    return {'text': text, 'value': float(text), 'unit': match.group('unit')}


def _variation(cell, suffix: str,
               label: str) -> typing.Optional[dict]:
    text = _field_suffix(cell, suffix)
    if text is None:
        return None
    year_text = _field_suffix(cell, 'DATE_MAG_VAR')
    return {
        'text': text,
        'value': _parse_variation(text, label),
        'year': int(year_text) if year_text else None,
    }


def parse_enr41(html: str) -> typing.List[typing.Dict[str, typing.Any]]:
    """
    Parses an eAIP ENR-4.1 (radio navigation aids - en-route) document into
    raw records.

    Each table row is one record. A VOR/DME row keeps both components in
    ``components``; the row is not split into separate records. The printed
    type is used, and unknown types raise ``ValueError``.

    Example:

    ::

        with open('EG-ENR-4.1-en-GB.html') as f:
            records = parse_enr41(f.read())
        records[0]['id']
        # Expected output: 'ADN'

    :param html: The eAIP ENR-4.1 HTML document.
    :return: One record per printed navaid row, in document order. Each record
        is a dict with ``row_id``, ``id``, ``name``, ``type``, ``components``,
        ``frequency``, ``paired_frequency``, ``dme``, ``location``,
        ``elevation``, ``magnetic_variation``, ``declination``, ``hours``,
        ``hours_annotations``, ``fra_relevance`` and ``remarks``. Absent parts
        are None or an empty list. Coordinates are WGS84 decimal degrees.
    """
    soup = BeautifulSoup(html, 'html.parser')
    records = []

    for row in soup.find_all('tr'):
        cells = row.find_all('td', recursive=False)
        if not cells:
            continue
        row_id = row.get('id') or None
        name = _require(_field_suffix(cells[0], 'TXT_NAME'), row_id, 'name')
        ident = _require(_field_suffix(cells[1], 'CODE_ID'), row_id, 'id')
        label = f'{row_id} ({ident})'

        type_text = _parse_type(_text_with_breaks(cells[0]), row_id)
        cell_text = _text_with_breaks(cells[4])
        location_text = ' '.join(cell_text.split())
        if not location_text:
            raise ValueError(f'{label}: missing co-ordinates')
        lat, lng = _parse_coordinate(location_text, label)

        frequency = None
        if type_text == 'NDB':
            frequency = _frequency(
                cells[2], 'TNDB', 'VAL_FREQ', 'UOM_FREQ', label)
        elif 'VOR' in type_text:
            frequency = _frequency(
                cells[2], 'TVOR', 'VAL_FREQ', 'UOM_FREQ', label)
        paired_frequency = _frequency(
            cells[2], 'TDME', 'VAL_GHOST_FREQ', 'UOM_GHOST_FREQ', label)

        channel = _field_suffix(cells[2], 'CODE_CHANNEL')
        declination_text = _field(cells[0], 'TVOR;VAL_DECLINATION')
        declination = None
        if declination_text is not None:
            year_text = _field(cells[0], 'TVOR;CUSTOM_ATT1')
            declination = {
                'text': declination_text,
                'value': _parse_variation(declination_text, label),
                'year': int(year_text) if year_text else None,
            }

        hours = _field(cells[3], 'TNAVAID_STS;CODE_STS')
        fra_relevance = _field(cells[6], 'TNAVAID;CUSTOM_ATT1')
        remarks = _text_with_breaks(cells[7]) or None
        if remarks == '-':
            remarks = None

        records.append({
            'row_id': row_id,
            'id': ident,
            'name': name,
            'type': type_text,
            'components': list(_TYPE_COMPONENTS[type_text]),
            'frequency': frequency,
            'paired_frequency': paired_frequency,
            'dme': {'channel': channel} if channel is not None else None,
            'location': {
                'text': location_text,
                'lat': lat,
                'lng': lng,
            },
            'elevation': _elevation(cells[5], label),
            'magnetic_variation': _variation(cells[0], 'VAL_MAG_VAR', label),
            'declination': declination,
            'hours': hours,
            'hours_annotations': _fields(
                cells[3], 'TNAVAID_STS;ANNOTATION'),
            'fra_relevance': fra_relevance,
            'remarks': remarks,
        })

    return records

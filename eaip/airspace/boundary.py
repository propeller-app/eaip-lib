"""
Parse eAIP lateral boundary text into closed lists of WGS84 points.

The input is the raw ``boundary_text`` produced by :func:`eaip.enr21.parse_enr21`
(and, later, the equivalent text from AD 2.17). It is one string, with all
whitespace equivalent, containing vertices separated by ``-``, arcs of the form
``<start> thence clockwise|anti-clockwise by the arc of a circle radius R NM
centred on <centre> to <end>`` and lines of latitude of the form
``<start> following the line of latitude to <end>``.

No coordinates are guessed: any fragment the grammar does not recognise (for
example "Same extent as ...", "but excluding ...", or a compass-worded arc)
raises :class:`BoundaryError` with the fragment in the message.
:func:`parse_boundaries` handles the first two cases for whole records:
trailing exclusions are recorded, and same-extent references are resolved by
copying the target record's points.
"""

import math
import re
import typing


NM_METRES = 1852.0
EARTH_RADIUS_METRES = 6_371_000.0
ARC_RADIUS_TOLERANCE_NM = 0.1
MAX_ARC_STEP_DEGREES = 3.0
MAX_PARALLEL_STEP_DEGREES = 0.5
_LATITUDE_TOLERANCE_DEGREES = 1e-6
_CLOSURE_TOLERANCE_DEGREES = 1e-9

_COORD = r'(\d{2})(\d{2})(\d{2})([NS])\s+(\d{3})(\d{2})(\d{2})([EW])'
_COORD_RE = re.compile(_COORD)
_ARC_RE = re.compile(
    r'\s*(?:-\s*)?thence\s+(clockwise|anti-clockwise)\s+by\s+the\s+arc\s+of\s+a\s+circle\s+'
    r'radius\s+(\d+(?:\.\d+)?)\s*NM\s+cent(?:red|ered)\s+on\s+'
    + _COORD + r'\s+to\s+(?:-\s*)?' + _COORD,
    re.IGNORECASE)
_PARALLEL_RE = re.compile(
    r'\s*(?:-\s*)?following\s+the\s+line\s+of\s+latitude\s+to\s+(?:-\s*)?' + _COORD,
    re.IGNORECASE)
_LABEL_RE = re.compile(r'\s*\([^()]*\)')
_SAME_EXTENT_RE = re.compile(r'^\s*Same\s+extent\s+as\s+(?P<target>.+?)\.?\s*$',
                             re.IGNORECASE)
_EXCLUSION_RE = re.compile(r'\s*\bbut\s+excluding\s+the\s+(?P<name>.+?)\.\s*$',
                           re.IGNORECASE)


class BoundaryError(ValueError):
    """
    Raised when boundary text cannot be parsed without guessing.
    """


def _coordinate(groups, offset: int = 0) -> typing.Dict[str, float]:
    """
    Build a point from eight DMS groups starting at ``offset``.
    """
    lat_deg, lat_min, lat_sec, lat_dir = groups[offset:offset + 4]
    lng_deg, lng_min, lng_sec, lng_dir = groups[offset + 4:offset + 8]
    lat = int(lat_deg) + int(lat_min) / 60 + int(lat_sec) / 3600
    lng = int(lng_deg) + int(lng_min) / 60 + int(lng_sec) / 3600
    if lat_dir.upper() == 'S':
        lat = -lat
    if lng_dir.upper() == 'W':
        lng = -lng
    return {'lat': lat, 'lng': lng}


def _distance_nm(a: typing.Dict[str, float], b: typing.Dict[str, float]) -> float:
    """
    Great-circle distance between two points, in nautical miles.
    """
    lat1, lon1 = math.radians(a['lat']), math.radians(a['lng'])
    lat2, lon2 = math.radians(b['lat']), math.radians(b['lng'])
    h = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 2 * EARTH_RADIUS_METRES * math.asin(math.sqrt(h)) / NM_METRES


def _bearing_degrees(centre: typing.Dict[str, float],
                     point: typing.Dict[str, float]) -> float:
    """
    Initial bearing from ``centre`` to ``point``, in degrees clockwise from north.
    """
    lat1, lon1 = math.radians(centre['lat']), math.radians(centre['lng'])
    lat2, lon2 = math.radians(point['lat']), math.radians(point['lng'])
    dlon = lon2 - lon1
    y = math.sin(dlon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def _destination(centre: typing.Dict[str, float], bearing: float,
                 distance_nm: float) -> typing.Dict[str, float]:
    """
    Point ``distance_nm`` from ``centre`` along ``bearing`` on the sphere.
    """
    lat1, lon1 = math.radians(centre['lat']), math.radians(centre['lng'])
    theta = math.radians(bearing)
    angular = distance_nm * NM_METRES / EARTH_RADIUS_METRES
    lat2 = math.asin(math.sin(lat1) * math.cos(angular)
                     + math.cos(lat1) * math.sin(angular) * math.cos(theta))
    lon2 = lon1 + math.atan2(math.sin(theta) * math.sin(angular) * math.cos(lat1),
                             math.cos(angular) - math.sin(lat1) * math.sin(lat2))
    return {'lat': math.degrees(lat2),
            'lng': (math.degrees(lon2) + 540) % 360 - 180}


def _same_point(a: typing.Dict[str, float], b: typing.Dict[str, float]) -> bool:
    return (abs(a['lat'] - b['lat']) <= _CLOSURE_TOLERANCE_DEGREES
            and abs(a['lng'] - b['lng']) <= _CLOSURE_TOLERANCE_DEGREES)


def _arc_points(start: typing.Dict[str, float], end: typing.Dict[str, float],
                centre: typing.Dict[str, float], radius: float,
                direction: str) -> typing.List[typing.Dict[str, float]]:
    """
    Points from ``start`` to ``end`` along the arc, excluding ``start`` and
    including ``end``. Interior points sit at the stated radius.
    """
    start_distance = _distance_nm(centre, start)
    end_distance = _distance_nm(centre, end)
    if (abs(start_distance - radius) > ARC_RADIUS_TOLERANCE_NM
            or abs(end_distance - radius) > ARC_RADIUS_TOLERANCE_NM):
        raise BoundaryError(
            f'arc radius check failed: stated {radius:g} NM, '
            f'start {start_distance:.4f} NM, end {end_distance:.4f} NM')

    start_bearing = _bearing_degrees(centre, start)
    end_bearing = _bearing_degrees(centre, end)
    if direction == 'clockwise':
        sweep = (end_bearing - start_bearing) % 360.0
        signed_sweep = sweep
    else:
        sweep = (start_bearing - end_bearing) % 360.0
        signed_sweep = -sweep

    if sweep <= 1e-9:
        raise BoundaryError('arc has identical start and end bearings (full circle)')

    steps = max(1, math.ceil(sweep / MAX_ARC_STEP_DEGREES))
    points = [
        _destination(centre, start_bearing + signed_sweep * step / steps, radius)
        for step in range(1, steps)
    ]
    points.append(end)
    return points


def _parallel_points(start: typing.Dict[str, float],
                     end: typing.Dict[str, float]) -> typing.List[typing.Dict[str, float]]:
    """
    Points from ``start`` to ``end`` along the parallel, excluding ``start`` and
    including ``end``. Longitude steps are at most 0.5 degrees.
    """
    if abs(start['lat'] - end['lat']) > _LATITUDE_TOLERANCE_DEGREES:
        raise BoundaryError(
            f'line of latitude endpoints differ in latitude: '
            f"{start['lat']:.6f} vs {end['lat']:.6f}")

    delta_lng = end['lng'] - start['lng']
    if delta_lng > 180:
        delta_lng -= 360
    elif delta_lng < -180:
        delta_lng += 360

    steps = max(1, math.ceil(abs(delta_lng) / MAX_PARALLEL_STEP_DEGREES))
    points = [
        {'lat': start['lat'], 'lng': start['lng'] + delta_lng * step / steps}
        for step in range(1, steps)
    ]
    points.append(end)
    return points


def _skip_spaces(text: str, position: int) -> int:
    while position < len(text) and text[position].isspace():
        position += 1
    return position


def circle_points(centre: typing.Dict[str, float],
                  radius_nm: float) -> typing.List[typing.Dict[str, float]]:
    """
    Closed ring for a circle of ``radius_nm`` around ``centre``.

    The ring starts due north of the centre and runs clockwise in steps of
    ``MAX_ARC_STEP_DEGREES`` (3 degrees), giving 120 segments and 121 points.
    The last point is an exact copy of the first, so the ring is closed
    without floating-point drift.

    :param centre: ``{'lat': float, 'lng': float}`` in decimal degrees.
    :param radius_nm: Radius in nautical miles.
    :return: 121 ``{'lat', 'lng'}`` points, first equal to last.
    """
    points = [
        _destination(centre, step * MAX_ARC_STEP_DEGREES, radius_nm)
        for step in range(120)
    ]
    points.append(dict(points[0]))
    return points


def parse_boundary(text: str) -> typing.List[typing.Dict[str, float]]:
    """
    Parses one eAIP boundary string into a closed list of WGS84 points.

    Whitespace (including newlines) is insignificant. Points are
    ``{'lat': float, 'lng': float}`` in decimal degrees, south and west
    negative. Arcs are expanded with a step of at most 3 degrees at the stated
    radius; lines of latitude are expanded with longitude steps of at most 0.5
    degrees. Both endpoints of every segment are kept exactly as printed.

    Example:

    ::

        points = parse_boundary('512238N 0071903W - 510446N 0065224W '
                                '- 512238N 0071903W')
        points[0]['lat']
        # Expected output: 51.37722222222222

    :param text: Raw boundary text (vertices, arcs, lines of latitude and ``-``).
    :return: The boundary as a closed list, first point equal to last point.
    :raises BoundaryError: If a fragment is not recognised, an arc endpoint is
        more than 0.1 NM off its stated radius, a latitude segment's endpoints
        differ, or the boundary does not close.
    """
    collapsed = re.sub(r'\s+', ' ', text).strip()
    match = _COORD_RE.match(collapsed)
    if match is None:
        raise BoundaryError(f'unparsed boundary start: {collapsed[:120]!r}')

    points = [_coordinate(match.groups())]
    position = match.end()

    while True:
        position = _skip_spaces(collapsed, position)

        label = _LABEL_RE.match(collapsed, position)
        if label is not None:
            position = _skip_spaces(collapsed, label.end())

        if position >= len(collapsed):
            break
        if collapsed[position] == '.':
            remainder = collapsed[position + 1:].strip()
            if remainder:
                raise BoundaryError(
                    f'unparsed fragment after full stop: {remainder[:120]!r}')
            break

        match = _ARC_RE.match(collapsed, position)
        if match is not None:
            groups = match.groups()
            direction = groups[0].lower()
            radius = float(groups[1])
            centre = _coordinate(groups, 2)
            end = _coordinate(groups, 10)
            points.extend(_arc_points(points[-1], end, centre, radius, direction))
            position = match.end()
            continue

        match = _PARALLEL_RE.match(collapsed, position)
        if match is not None:
            end = _coordinate(match.groups())
            points.extend(_parallel_points(points[-1], end))
            position = match.end()
            continue

        if collapsed[position] == '-':
            position = _skip_spaces(collapsed, position + 1)
            match = _COORD_RE.match(collapsed, position)
            if match is None:
                raise BoundaryError(
                    f'unparsed fragment after "-": {collapsed[position:position + 120]!r}')
            points.append(_coordinate(match.groups()))
            position = match.end()
            continue

        raise BoundaryError(f'unparsed fragment: {collapsed[position:position + 120]!r}')

    if len(points) < 2 or not _same_point(points[0], points[-1]):
        first, last = points[0], points[-1]
        raise BoundaryError(
            f'boundary is not closed: first {first["lat"]:.6f},{first["lng"]:.6f} '
            f'last {last["lat"]:.6f},{last["lng"]:.6f}')
    return points


def parse_boundaries(
    records: typing.Iterable[typing.Mapping[str, typing.Any]]
) -> typing.Tuple[typing.Dict[str, typing.Dict[str, typing.Any]],
                  typing.List[typing.Tuple[str, str]]]:
    """
    Applies :func:`parse_boundary` to every record from
    :func:`eaip.enr21.parse_enr21`, then resolves the two pieces of prose that
    the strict single-boundary parser rejects:

    - a trailing ``but excluding the <X>.`` sentence is removed before parsing
      and ``<X>`` is recorded in ``exclusions`` (no geometry is subtracted);
    - ``Same extent as <NAME>`` copies the points of the record called
      ``<NAME>`` and records the reference in ``origin``. References are
      resolved after the direct parse, so a chain resolves as long as it ends
      at a record with real boundary text. Missing targets, targets that
      failed to parse, and reference cycles go to ``failed``.

    Remarks are not read; this function only sees ``name`` and
    ``boundary_text``.

    :param records: Records with ``name`` and ``boundary_text`` keys.
    :return: ``(parsed, failed)``. ``parsed`` maps a record name to
        ``{'name': str, 'points': [{lat, lng}], 'exclusions': [str],
        'origin': str | None}``; ``points`` is closed, ``exclusions`` is
        usually empty, and ``origin`` is the ``Same extent as ...`` sentence
        when the points were copied from another record. ``failed`` is a list
        of ``(name, error message)`` in input order.
    """
    order = []
    results = {}
    failure_messages = {}
    references = {}
    direct_points = {}

    for record in records:
        name = record['name']
        order.append(name)

        text = record['boundary_text']
        exclusions = []
        exclusion = _EXCLUSION_RE.search(text)
        if exclusion is not None:
            exclusions.append(' '.join(exclusion.group('name').split()))
            text = text[:exclusion.start()].rstrip()

        same_extent = _SAME_EXTENT_RE.match(text)
        if same_extent is not None:
            target = ' '.join(same_extent.group('target').split())
            references[name] = (target, f'Same extent as {target}', exclusions)
            continue

        try:
            points = parse_boundary(text)
        except BoundaryError as error:
            failure_messages[name] = str(error)
            continue

        direct_points[name] = points
        results[name] = {
            'name': name,
            'points': points,
            'exclusions': exclusions,
            'origin': None,
        }

    # Resolve references after every direct parse, so order does not matter.
    # Repeated passes let a chain resolve however it is ordered.
    while references:
        progressed = False
        for name in list(references):
            target, origin, exclusions = references[name]
            if target in results:
                results[name] = {
                    'name': name,
                    'points': list(results[target]['points']),
                    'exclusions': exclusions,
                    'origin': origin,
                }
                del references[name]
                progressed = True
            elif target in failure_messages:
                failure_messages[name] = (
                    f'Same extent as {target!r}: target record failed to parse '
                    f'({failure_messages[target]})')
                del references[name]
                progressed = True
        if not progressed:
            for name, (target, _, _) in references.items():
                if target in references:
                    failure_messages[name] = (
                        f'Same extent as {target!r}: circular same-extent reference')
                else:
                    failure_messages[name] = (
                        f'Same extent as {target!r}: no record with that name')
            break

    parsed = {name: results[name] for name in order if name in results}
    failed = [(name, failure_messages[name]) for name in order
              if name in failure_messages]
    return parsed, failed

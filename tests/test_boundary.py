import math
import pathlib
import re
import unittest

from eaip.airspace.boundary import (BoundaryError, _distance_nm, circle_points,
                                    parse_boundaries, parse_boundary)
from eaip.enr21 import parse_enr21


FIXTURE = pathlib.Path(__file__).parent / 'fixtures' / 'EG-ENR-2.1.html'
EARTH_RADIUS_METRES = 6371000.0
NM_METRES = 1852.0

_COORD_TEXT = re.compile(r'(\d{2})(\d{2})(\d{2})([NS]) (\d{3})(\d{2})(\d{2})([EW])')


def _coord(text):
    match = _COORD_TEXT.fullmatch(text)
    lat_deg, lat_min, lat_sec, lat_dir = match.group(1, 2, 3, 4)
    lng_deg, lng_min, lng_sec, lng_dir = match.group(5, 6, 7, 8)
    lat = int(lat_deg) + int(lat_min) / 60 + int(lat_sec) / 3600
    lng = int(lng_deg) + int(lng_min) / 60 + int(lng_sec) / 3600
    if lat_dir == 'S':
        lat = -lat
    if lng_dir == 'W':
        lng = -lng
    return {'lat': lat, 'lng': lng}


def _distance(a, b):
    lat1, lon1 = math.radians(a['lat']), math.radians(a['lng'])
    lat2, lon2 = math.radians(b['lat']), math.radians(b['lng'])
    h = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 2 * EARTH_RADIUS_METRES * math.asin(math.sqrt(h)) / NM_METRES


def _bearing(a, b):
    lat1, lon1 = math.radians(a['lat']), math.radians(a['lng'])
    lat2, lon2 = math.radians(b['lat']), math.radians(b['lng'])
    dlon = lon2 - lon1
    y = math.sin(dlon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def _destination(centre, bearing, distance_nm):
    lat1, lon1 = math.radians(centre['lat']), math.radians(centre['lng'])
    theta = math.radians(bearing)
    angular = distance_nm * NM_METRES / EARTH_RADIUS_METRES
    lat2 = math.asin(math.sin(lat1) * math.cos(angular)
                     + math.cos(lat1) * math.sin(angular) * math.cos(theta))
    lon2 = lon1 + math.atan2(math.sin(theta) * math.sin(angular) * math.cos(lat1),
                             math.cos(angular) - math.sin(lat1) * math.sin(lat2))
    return {'lat': math.degrees(lat2),
            'lng': (math.degrees(lon2) + 540) % 360 - 180}


def _format(point):
    def dms(value, latitude):
        hemi = ('N' if value >= 0 else 'S') if latitude else ('E' if value >= 0 else 'W')
        value = abs(value)
        degrees = int(value)
        minutes = int((value - degrees) * 60)
        seconds = round(((value - degrees) * 60 - minutes) * 60)
        if seconds == 60:
            seconds, minutes = 0, minutes + 1
        if minutes == 60:
            minutes, degrees = 0, degrees + 1
        width = 2 if latitude else 3
        return f'{degrees:0{width}d}{minutes:02d}{seconds:02d}{hemi}'

    return f"{dms(point['lat'], True)} {dms(point['lng'], False)}"


def _arc_text(centre, start_bearing, end_bearing, direction, radius):
    start = _destination(centre, start_bearing, radius)
    end = _destination(centre, end_bearing, radius)
    start_text, end_text = _format(start), _format(end)
    text = (f'{start_text} thence {direction} by the arc of a circle '
            f'radius {radius:g} NM centred on {_format(centre)} to {end_text} - {start_text}')
    return text, _coord(start_text), _coord(end_text)


def _unwrapped(bearings, direction):
    adjusted = [bearings[0]]
    for bearing in bearings[1:]:
        previous = adjusted[-1]
        if direction == 'clockwise':
            while bearing <= previous:
                bearing += 360
        else:
            while bearing >= previous:
                bearing -= 360
        adjusted.append(bearing)
    return adjusted


class TestBoundary(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.records = parse_enr21(FIXTURE.read_text(encoding='utf-8'))
        cls.by_name = {record['name']: record for record in cls.records}

    def record(self, name):
        return self.by_name[name]

    def assert_arc(self, points, centre, radius, direction, crosses_north=False):
        self.assertEqual(points[0], points[-1])
        arc = points[:-1]
        bearings = [_bearing(centre, point) for point in arc]
        adjusted = _unwrapped(bearings, direction)
        differences = [b - a for a, b in zip(adjusted, adjusted[1:])]
        if direction == 'clockwise':
            self.assertTrue(all(difference > 0 for difference in differences))
        else:
            self.assertTrue(all(difference < 0 for difference in differences))
        self.assertLessEqual(max(abs(difference) for difference in differences), 3.0 + 1e-9)
        for point in arc:
            self.assertAlmostEqual(_distance(centre, point), radius, delta=0.1)
        if crosses_north:
            if direction == 'clockwise':
                self.assertGreaterEqual(adjusted[-1], 360.0)
            else:
                self.assertLessEqual(adjusted[-1], 0.0)

    def test_coordinate_conversion(self):
        points = parse_boundary('512238N 0071903W - 512238N 0071903W')
        self.assertAlmostEqual(points[0]['lat'], 51.377222, places=6)
        self.assertAlmostEqual(points[0]['lng'], -7.317500, places=6)

    def test_berry_head_cta_6(self):
        # row 1488, name 1490, boundary 1493
        points = parse_boundary(self.record('BERRY HEAD CTA 6')['boundary_text'])
        self.assertEqual(len(points), 5)
        self.assertEqual(points[0], points[-1])
        self.assertEqual(points[0], _coord('512238N 0071903W'))

    def test_brize_norton_ctr(self):
        # ENR-2.1.1 table: record row 16815, units 16818 + 16823-16827
        text = self.record('BRIZE NORTON CTR')['boundary_text']
        self.assertIn('centered on', text)
        points = parse_boundary(text)
        self.assertEqual(points[0], points[-1])
        self.assertGreater(len(points), 9)
        for centre_text in ('514513N 0013334W', '514443N 0013631W'):
            centre = _coord(centre_text)
            on_arc = [point for point in points[:-1]
                      if abs(_distance(centre, point) - 5.5) < 1e-6]
            self.assertGreater(len(on_arc), 1)

    def test_short_arc_returns_both_endpoints(self):
        # LONDON TMA 1 row 15297, sliver at 15482; sweep is 0.903 degrees
        start_text = '512103N 0004236W'
        end_text = '512112N 0004247W'
        phrase = (f'{start_text} thence clockwise by the arc of a circle radius 12 NM '
                  f'centred on 512812N 0002713W to {end_text}')
        points = parse_boundary(f'{phrase} - {start_text}')
        start, end = _coord(start_text), _coord(end_text)
        centre = _coord('512812N 0002713W')
        self.assertEqual(len(points), 3)
        self.assertEqual(points[0], start)
        self.assertEqual(points[-1], start)
        self.assertEqual(points[-2], end)
        self.assertAlmostEqual(_distance(centre, start), 12, delta=0.1)
        self.assertAlmostEqual(_distance(centre, end), 12, delta=0.1)
        sweep = (_bearing(centre, end) - _bearing(centre, start)) % 360
        self.assertAlmostEqual(sweep, 0.903, delta=0.01)

    def test_real_arc_crossing_north_clockwise(self):
        # ABERDEEN CTA 1 row 755, boundary 759; sweep 284.261 -> 70.477
        start_text = '572100N 0023356W'
        end_text = '572153N 0015835W'
        phrase = (f'{start_text} thence clockwise by the arc of a circle radius 10 NM '
                  f'centred on 571834N 0021602W to - {end_text}')
        points = parse_boundary(f'{phrase} - {start_text}')
        self.assertEqual(points[0], _coord(start_text))
        self.assertEqual(points[-2], _coord(end_text))
        self.assert_arc(points, _coord('571834N 0021602W'), 10, 'clockwise',
                        crosses_north=True)

    def test_real_arc_crossing_north_anticlockwise(self):
        # EDINBURGH CTA 2 row 395, boundary 6327; ends due north at bearing 0.0
        start_text = '555442N 0030503W'
        end_text = '560700N 0032221W'
        phrase = (f'{start_text} thence anti-clockwise by the arc of a circle radius 10 NM '
                  f'centred on 555700N 0032221W to - {end_text}')
        points = parse_boundary(f'{phrase} - {start_text}')
        self.assertEqual(points[0], _coord(start_text))
        self.assertEqual(points[-2], _coord(end_text))
        self.assert_arc(points, _coord('555700N 0032221W'), 10, 'anti-clockwise',
                        crosses_north=True)

    def test_synthetic_arcs(self):
        centre = _coord('510000N 0000000E')
        cases = [
            ('clockwise', 350, 10, True),
            ('anti-clockwise', 10, 350, True),
            ('clockwise', 10, 90, False),
            ('anti-clockwise', 90, 10, False),
        ]
        for direction, start_bearing, end_bearing, crosses_north in cases:
            with self.subTest(direction=direction, start=start_bearing, end=end_bearing):
                text, start, end = _arc_text(centre, start_bearing, end_bearing,
                                             direction, 5)
                points = parse_boundary(text)
                self.assertEqual(points[0], start)
                self.assertEqual(points[-1], start)
                self.assertEqual(points[-2], end)
                self.assert_arc(points, centre, 5, direction, crosses_north)

    def test_arc_with_to_dash(self):
        text = ('510000N 0000000W thence clockwise by the arc of a circle radius 5 NM '
                'centred on 510500N 0000000W to - 511000N 0000000W - 510000N 0000000W')
        points = parse_boundary(text)
        self.assertEqual(points[0], _coord('510000N 0000000W'))
        self.assertEqual(points[-2], _coord('511000N 0000000W'))
        self.assertEqual(points[0], points[-1])

    def test_unknown_direction_word_raises(self):
        text = ('510000N 0000000W thence south by the arc of a circle radius 5 NM '
                'centred on 510500N 0000000W to 511000N 0000000W - 510000N 0000000W')
        with self.assertRaises(BoundaryError) as caught:
            parse_boundary(text)
        self.assertIn('south', str(caught.exception))

    def test_unknown_fragment_raises(self):
        with self.assertRaises(BoundaryError) as caught:
            parse_boundary('510000N 0000000W - 510000N 0000000W nonsense')
        self.assertIn('nonsense', str(caught.exception))

    def test_unclosed_boundary_raises(self):
        with self.assertRaises(BoundaryError) as caught:
            parse_boundary('510000N 0000000W - 511000N 0000000W')
        self.assertIn('not closed', str(caught.exception))

    def test_latitude_endpoints_must_match(self):
        text = ('510000N 0000000W following the line of latitude to '
                '520000N 0010000E - 510000N 0000000W')
        with self.assertRaises(BoundaryError) as caught:
            parse_boundary(text)
        self.assertIn('differ in latitude', str(caught.exception))

    def test_arc_radius_must_match(self):
        text = ('510000N 0000000W thence clockwise by the arc of a circle radius 6 NM '
                'centred on 510500N 0000000W to 511000N 0000000W - 510000N 0000000W')
        with self.assertRaises(BoundaryError) as caught:
            parse_boundary(text)
        self.assertIn('arc radius check failed', str(caught.exception))

    def test_gatwick_excluding_raises(self):
        with self.assertRaises(BoundaryError) as caught:
            parse_boundary(self.record('LONDON GATWICK CTA')['boundary_text'])
        self.assertIn('excluding the Gatwick CTR', str(caught.exception))

    def test_london_uir_same_extent_raises(self):
        with self.assertRaises(BoundaryError) as caught:
            parse_boundary(self.record('LONDON UIR')['boundary_text'])
        self.assertIn('Same extent as LONDON FIR', str(caught.exception))

    def test_daventry_label_ignored(self):
        # row 4876, name 4878, label 4881; the coordinate is a vertex
        text = self.record('DAVENTRY CTA 9')['boundary_text']
        self.assertIn('(Daventry VOR)', text)
        points = parse_boundary(text)
        self.assertEqual(points[0], points[-1])
        self.assertIn(_coord('521049N 0010650W'), points)

    def test_london_fir_closed_and_latitude_segments(self):
        # row 18, name 20; latitude segments in the boundary text
        points = parse_boundary(self.record('LONDON FIR')['boundary_text'])
        self.assertEqual(points[0], points[-1])

        start = _coord('500000N 0001500W')
        end = _coord('500000N 0020000W')
        first = points.index(start)
        last = next(index for index in range(first + 1, len(points)) if points[index] == end)
        self.assertEqual(last - first, 4)
        for point in points[first:last + 1]:
            self.assertAlmostEqual(point['lat'], 50.0, delta=1e-9)

        start = _coord('550000N 0053000W')
        end = _coord('550000N 0050000E')
        first = points.index(start)
        last = next(index for index in range(first + 1, len(points)) if points[index] == end)
        self.assertEqual(last - first, 21)
        for point in points[first:last + 1]:
            self.assertAlmostEqual(point['lat'], 55.0, delta=1e-9)

    def test_all_records(self):
        parsed, failed = parse_boundaries(self.records)
        self.assertEqual(len(parsed) + len(failed), 419)
        self.assertEqual(len(parsed), 419)
        self.assertEqual(failed, [])

        for name, boundary in parsed.items():
            self.assertEqual(boundary['name'], name)
            self.assertEqual(boundary['points'][0], boundary['points'][-1], name)

        self.assertEqual(parsed['LONDON UIR']['points'],
                         parsed['LONDON FIR']['points'])
        self.assertEqual(parsed['SCOTTISH UIR']['points'],
                         parsed['SCOTTISH FIR']['points'])
        self.assertEqual(parsed['LONDON UIR']['origin'], 'Same extent as LONDON FIR')
        self.assertEqual(parsed['SCOTTISH UIR']['origin'], 'Same extent as SCOTTISH FIR')

        gatwick = parsed['LONDON GATWICK CTA']
        self.assertEqual(gatwick['exclusions'], ['Gatwick CTR'])
        self.assertEqual(gatwick['points'][0], gatwick['points'][-1])

        for name in ('BELFAST TMA 1', 'BRIZE NORTON CTR'):
            self.assertEqual(parsed[name]['exclusions'], [])

        with_exclusions = {name for name, boundary in parsed.items()
                           if boundary['exclusions']}
        self.assertEqual(with_exclusions, {'LONDON GATWICK CTA'})
        with_origin = {name for name, boundary in parsed.items()
                       if boundary['origin'] is not None}
        self.assertEqual(with_origin, {'LONDON UIR', 'SCOTTISH UIR'})

    def test_same_extent_missing_target_fails(self):
        parsed, failed = parse_boundaries([
            {'name': 'ORPHAN', 'boundary_text': 'Same extent as MISSING'},
        ])
        self.assertEqual(parsed, {})
        self.assertEqual(len(failed), 1)
        self.assertIn('MISSING', failed[0][1])

    def test_same_extent_target_failed(self):
        parsed, failed = parse_boundaries([
            {'name': 'BROKEN', 'boundary_text': 'not a boundary'},
            {'name': 'REF', 'boundary_text': 'Same extent as BROKEN'},
        ])
        self.assertEqual(parsed, {})
        self.assertEqual([name for name, _ in failed], ['BROKEN', 'REF'])
        self.assertIn('BROKEN', failed[1][1])

    def test_same_extent_chain_handled(self):
        base = '510000N 0000000W - 511000N 0000000W - 510000N 0000000W'
        parsed, failed = parse_boundaries([
            {'name': 'BASE', 'boundary_text': base},
            {'name': 'MID', 'boundary_text': 'Same extent as BASE'},
            {'name': 'TOP', 'boundary_text': 'Same extent as MID'},
        ])
        self.assertEqual(failed, [])
        self.assertEqual(parsed['TOP']['points'], parsed['BASE']['points'])
        self.assertEqual(parsed['TOP']['origin'], 'Same extent as MID')
        self.assertEqual(parsed['MID']['origin'], 'Same extent as BASE')

    def test_general_exclusion_rule(self):
        text = ('510000N 0000000W - 511000N 0000000W - 510000N 0000000W\n\n'
                'but excluding the Somewhere CTR.')
        parsed, failed = parse_boundaries([{'name': 'TEST', 'boundary_text': text}])
        self.assertEqual(failed, [])
        self.assertEqual(parsed['TEST']['exclusions'], ['Somewhere CTR'])
        self.assertEqual(parsed['TEST']['points'][0], parsed['TEST']['points'][-1])

    def test_exclusion_must_be_at_end(self):
        text = ('510000N 0000000W but excluding the Foo CTR. - '
                '511000N 0000000W - 510000N 0000000W')
        parsed, failed = parse_boundaries([{'name': 'TEST', 'boundary_text': text}])
        self.assertEqual(parsed, {})
        self.assertEqual(len(failed), 1)
        self.assertIn('but excluding', failed[0][1])


class TestCirclePoints(unittest.TestCase):

    def check_circle(self, latitude, longitude, radius_nm):
        centre = {'lat': latitude, 'lng': longitude}
        points = circle_points(centre, radius_nm)
        self.assertEqual(len(points), 121)
        self.assertEqual(points[0], points[-1])
        self.assertEqual(points[0]['lng'], centre['lng'])
        self.assertGreater(points[0]['lat'], centre['lat'])
        for point in points[:-1]:
            self.assertLess(abs(_distance_nm(centre, point) - radius_nm), 0.001)
        return points

    def test_circle_three_nm(self):
        self.check_circle(50.0, -5.0, 3.0)

    def test_circle_half_nm(self):
        self.check_circle(51.5, 0.0, 0.5)

    def test_circle_nine_nm(self):
        self.check_circle(58.0, -7.5, 9.0)

    def test_first_and_last_are_identical_objects_or_exact_copies(self):
        points = circle_points({'lat': 50.0, 'lng': -5.0}, 3.0)
        self.assertEqual(points[0], points[-1])
        self.assertIsNot(points[0], points[-1])


if __name__ == '__main__':
    unittest.main()

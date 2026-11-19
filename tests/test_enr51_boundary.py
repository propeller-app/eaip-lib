import collections
import math
import pathlib
import unittest

from eaip.airspace.boundary import BoundaryError, parse_boundary
from eaip.enr51 import (parse_enr51, parse_enr51_boundaries,
                        parse_enr51_boundary)


FIXTURE = pathlib.Path(__file__).parent / 'fixtures' / 'EG-ENR-5.1.html'


def area_sq_nm(points):
    """
    Equirectangular shoelace area in square nautical miles.
    """
    lat0 = points[0]['lat']
    lng0 = points[0]['lng']
    coords = [
        ((point['lng'] - lng0) * math.cos(math.radians(lat0)) * 60.0,
         (point['lat'] - lat0) * 60.0)
        for point in points
    ]
    area = 0.0
    for (x1, y1), (x2, y2) in zip(coords, coords[1:]):
        area += x1 * y2 - x2 * y1
    return abs(area) / 2.0


class TestParseEnr51Boundary(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.records = parse_enr51(FIXTURE.read_text(encoding='utf-8'))
        cls.by_ident = {record['ident']: record for record in cls.records}
        cls.boundaries, cls.failures = parse_enr51_boundaries(cls.records)

    def boundary(self, ident):
        return self.boundaries[ident]

    def test_whole_fixture(self):
        self.assertEqual(len(self.records), 1307)
        self.assertEqual(self.failures, [])
        self.assertEqual(len(self.boundaries), 1307)
        self.assertEqual(list(self.boundaries), [r['ident'] for r in self.records])
        shapes = collections.Counter(b['shape'] for b in self.boundaries.values())
        self.assertEqual(shapes, {'polygon': 1096, 'circle': 211})
        for ident, boundary in self.boundaries.items():
            self.assertEqual(boundary['ident'], ident)
            self.assertEqual(boundary['name'], self.by_ident[ident]['name'])

    def test_direct_parse_regression(self):
        checked = 0
        for record in self.records:
            try:
                direct = parse_boundary(record['boundary_text'])
            except BoundaryError:
                continue
            checked += 1
            self.assertEqual(self.boundaries[record['ident']]['points'], direct,
                             record['ident'])
        self.assertEqual(checked, 1089)

    def test_all_closed_and_polygons_positive_area(self):
        for ident, boundary in self.boundaries.items():
            points = boundary['points']
            self.assertEqual(points[0], points[-1], ident)
            if boundary['shape'] == 'polygon':
                self.assertGreater(area_sq_nm(points), 0.0, ident)

    def test_circle_specifics(self):
        cases = {
            'EGD005A': ('3', 'NM', 3.0),
            'EGD015': ('500', 'M', 500 / 1852),
            'EGD061': ('926', 'M', 0.5),
            'EGD402C': ('3000', 'FT', 914.4 / 1852),
            'EGD803Z1': ('5.00', 'NM', 5.0),
        }
        for ident, (printed_radius, printed_unit, radius_nm) in cases.items():
            circle = self.boundary(ident)['circle']
            self.assertEqual(circle['printed_radius'], printed_radius, ident)
            self.assertEqual(circle['printed_unit'], printed_unit, ident)
            self.assertLess(abs(circle['radius_nm'] - radius_nm), 1e-9, ident)
        self.assertLess(abs(self.boundary('EGD061')['circle']['radius_nm'] - 0.5),
                        1e-9)

    def test_circle_rings(self):
        for ident, boundary in self.boundaries.items():
            if boundary['shape'] != 'circle':
                continue
            points = boundary['points']
            self.assertEqual(len(points), 121, ident)
            self.assertEqual(points[0], points[-1], ident)
            expected = math.pi * boundary['circle']['radius_nm'] ** 2
            self.assertLess(abs(area_sq_nm(points) - expected) / expected, 0.01,
                            ident)

    def test_approximations(self):
        expected = {
            'EGD012': ['then along the coastline to'],
            'EGD031': ['then along the coastline in an easterly direction to'],
            'EGD138D': ['then along the north coast of Foulness Island to'],
            'EGD401': ['then along the river to'],
            'EGD710': [
                'then along the east coast of Raasay and Rona in an northerly direction to',
                'then along the west coast of the Applecross peninsula in an southerly direction to',
            ],
            'EGD802': ['then along the coastline to'],
        }
        approximated = {ident: boundary['approximations']
                        for ident, boundary in self.boundaries.items()
                        if boundary['approximate']}
        self.assertEqual(approximated, expected)
        self.assertEqual(sum(len(phrases) for phrases in approximated.values()), 7)
        for ident, boundary in self.boundaries.items():
            if ident in expected:
                continue
            self.assertEqual(boundary['approximations'], [], ident)
            self.assertFalse(boundary['approximate'], ident)
        self.assertEqual(self.boundary('EGD012')['points'][0],
                         self.boundary('EGD012')['points'][-1])

    def test_egr160_exclusion(self):
        expected = ('so much of the bed of the River Thames as lies within that '
                    'area between the ordinary high water marks on each of its banks')
        boundary = self.boundary('EGR160')
        self.assertEqual(boundary['exclusions'], [expected])
        self.assertEqual(len(boundary['points']), 10)
        self.assertEqual(boundary['points'][0], boundary['points'][-1])
        for ident, other in self.boundaries.items():
            if ident != 'EGR160':
                self.assertEqual(other['exclusions'], [], ident)

    def test_arc_records(self):
        for ident in ('EGR157', 'EGD005B'):
            boundary = self.boundary(ident)
            self.assertEqual(boundary['shape'], 'polygon', ident)
            self.assertEqual(boundary['points'][0], boundary['points'][-1], ident)
        self.assertEqual(
            self.by_ident['EGR157']['boundary_text'].count(
                'by the arc of a circle radius'), 5)

    def test_strictness(self):
        broken = [
            'A circle, 3 NM radius, centred on 500007N 0051354W',
            'A circle, 3 KM radius, centred at 500007N 0051354W',
            'A circle, 3 NM radius, centred at 500007N 0051354W extra',
            ('500000N 0050000W - then along the coast 501000N 0050000W - '
             '500000N 0050000W'),
            ('500000N 0050000W Excluding foo. - 501000N 0050000W - '
             '500000N 0050000W'),
        ]
        for text in broken:
            with self.assertRaises(BoundaryError, msg=text):
                parse_enr51_boundary(text)


if __name__ == '__main__':
    unittest.main()

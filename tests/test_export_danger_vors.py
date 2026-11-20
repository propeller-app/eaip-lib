import json
import pathlib
import re
import tempfile
import unittest

from eaip.enr41 import parse_enr41
from eaip.enr51 import parse_enr51, parse_enr51_boundaries
from eaip.export import (export_danger, export_vors,
                         write_danger_vors_files)


ENR51 = pathlib.Path(__file__).parent / 'fixtures' / 'EG-ENR-5.1.html'
ENR41 = pathlib.Path(__file__).parent / 'fixtures' / 'EG-ENR-4.1.html'

DANGER_KEYS = {
    'name', 'upper_limit', 'lower_limit', 'ident', 'boundary',
    'section', 'approximate', 'exclusions', 'source',
}
UPPER_RE = re.compile(r'^(FL\d+|\d+ FT (ALT|AGL))$')
VORS_KEYS = {
    'id', 'location', 'frequency', 'dme', 'rotation', 'name', 'type',
    'source', 'rotation_source',
}


def _synthetic_vor(ident='XXX', declination=None, magnetic_variation=None):
    return {
        'id': ident,
        'name': 'TEST',
        'type': 'VOR',
        'components': ['VOR'],
        'frequency': {'text': '123.450', 'value': 123.45, 'unit': 'MHz'},
        'dme': None,
        'location': {'text': '510000.00N 0010000.00W',
                     'lat': 51.0, 'lng': -1.0},
        'elevation': None,
        'magnetic_variation': magnetic_variation,
        'declination': declination,
    }


def _synthetic_danger(upper='1000 FT ALT', lower='SFC'):
    return {
        'ident': 'EGX001',
        'name': 'TEST',
        'section': 'Danger Area',
        'limits': {
            'upper': {'text': upper, 'value': None, 'uom': None,
                      'code': None, 'annotation': None},
            'lower': None if lower is None else {
                'text': lower, 'value': None, 'uom': None,
                'code': None, 'annotation': None},
        },
    }


class TestExportDanger(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.enr51_html = ENR51.read_text(encoding='utf-8')
        cls.records = parse_enr51(cls.enr51_html)
        cls.boundaries, cls.failed = parse_enr51_boundaries(cls.records)
        cls.exported = export_danger(cls.records, cls.boundaries)

    def test_counts(self):
        # 1307 records = 1035 with a digit in the upper limit + 272 without.
        # Exported upper forms: AGL 661 + ALT 315 + FL 59 = 1035.
        # Skipped reasons: "As Per AUP / UUP" 227 + "UNL" 45 = 272.
        self.assertEqual(len(self.records), 1307)
        self.assertEqual(self.failed, [])
        self.assertEqual(len(self.exported['danger']), 1035)
        self.assertEqual(len(self.exported['skipped']), 272)
        self.assertEqual(
            {reason: sum(1 for entry in self.exported['skipped']
                         if entry['reason'] == reason)
             for reason in ('As Per AUP / UUP', 'UNL')},
            {'As Per AUP / UUP': 227, 'UNL': 45})

    def test_entry_shape(self):
        for entry in self.exported['danger']:
            self.assertEqual(set(entry), DANGER_KEYS)
            self.assertIsInstance(entry['name'], str)
            self.assertTrue(entry['name'])
            self.assertIsInstance(entry['ident'], str)
            self.assertTrue(entry['ident'])
            self.assertIsInstance(entry['upper_limit'], str)
            self.assertIsInstance(entry['lower_limit'], str)
            self.assertIn(entry['section'],
                          {'Danger Area', 'Prohibited Area',
                           'Restricted Area'})
            self.assertIsInstance(entry['approximate'], bool)
            self.assertIsInstance(entry['exclusions'], list)
            self.assertEqual(entry['source'], 'ENR-5.1')
            self.assertTrue(entry['boundary'])
            for point in entry['boundary']:
                self.assertEqual(set(point), {'lat', 'lng'})
                self.assertIsInstance(point['lat'], float)
                self.assertIsInstance(point['lng'], float)
            self.assertEqual(entry['boundary'][0], entry['boundary'][-1])
        idents = [entry['ident'] for entry in self.exported['danger']]
        self.assertEqual(len(idents), len(set(idents)))

    def test_every_exported_upper_has_a_digit_for_the_renderer(self):
        # georeference.py:884 does re.findall(r'(\d+)', upper_limit)[0].
        for entry in self.exported['danger']:
            self.assertTrue(re.findall(r'(\d+)', entry['upper_limit']),
                            entry['upper_limit'])
            self.assertRegex(entry['upper_limit'], UPPER_RE)

    def test_approximate_records_are_flagged(self):
        flagged = [entry['ident'] for entry in self.exported['danger']
                   if entry['approximate']]
        # The 6 approximate ENR-5.1 records; all fall in the exported set.
        self.assertEqual(flagged, ['EGD012', 'EGD031', 'EGD138D',
                                   'EGD401', 'EGD710', 'EGD802'])

    def test_named_records(self):
        by_ident = {entry['ident']: entry
                    for entry in self.exported['danger']}
        # EGD001: fixture upper "1000 FT ALT", lower "SFC".
        self.assertEqual(by_ident['EGD001']['name'], 'TREVOSE HEAD')
        self.assertEqual(by_ident['EGD001']['upper_limit'], '1000 FT ALT')
        self.assertEqual(by_ident['EGD001']['lower_limit'], 'SFC')
        # EGR1U001A: fixture upper "2000 FT AGL".
        self.assertEqual(by_ident['EGR1U001A']['upper_limit'],
                         '2000 FT AGL')
        # EGD064A: fixture upper "FL 660" -> "FL660".
        self.assertEqual(by_ident['EGD064A']['upper_limit'], 'FL660')
        # EGD005A is a strict circle: 121-point closed ring.
        self.assertEqual(len(by_ident['EGD005A']['boundary']), 121)
        # EGR160's upper limit is UNL, so the fixed rule skips it; its River
        # Thames exclusion is therefore checked on the parsed boundary, not in
        # danger.json. No exported record has an exclusion.
        self.assertNotIn('EGR160', by_ident)
        self.assertIn('EGR160',
                      [entry['ident'] for entry in self.exported['skipped']])
        self.assertTrue(any('River Thames' in phrase
                            for phrase in self.boundaries['EGR160']['exclusions']))
        for entry in self.exported['danger']:
            self.assertEqual(entry['exclusions'], [])


class TestExportVors(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.enr41_html = ENR41.read_text(encoding='utf-8')
        cls.records = parse_enr41(cls.enr41_html)
        cls.exported = export_vors(cls.records)

    def test_counts(self):
        # 54 rows = 21 with a VOR component (20 VOR/DME + 1 VOR-only PTH).
        # Skipped = 31 DME-only + 2 NDB = 33.
        self.assertEqual(len(self.records), 54)
        self.assertEqual(len(self.exported['vors']), 21)
        self.assertEqual(len(self.exported['skipped']), 33)
        self.assertEqual(
            {kind: sum(1 for entry in self.exported['skipped']
                       if entry['type'] == kind)
             for kind in ('DME', 'NDB')},
            {'DME': 31, 'NDB': 2})

    def test_entry_shape(self):
        for entry in self.exported['vors']:
            self.assertEqual(set(entry), VORS_KEYS)
            self.assertIsInstance(entry['id'], str)
            self.assertTrue(entry['id'])
            self.assertIsInstance(entry['frequency'], str)
            self.assertIsInstance(entry['dme'], bool)
            self.assertIsInstance(entry['rotation'], float)
            self.assertIn(entry['rotation_source'],
                          {'declination', 'magnetic_variation'})
            self.assertEqual(entry['source'], 'ENR-4.1')
            self.assertEqual(set(entry['location']), {'lat', 'lng'})
            self.assertIsInstance(entry['location']['lat'], float)
            self.assertIsInstance(entry['location']['lng'], float)
        ids = [entry['id'] for entry in self.exported['vors']]
        self.assertEqual(len(ids), len(set(ids)))

    def test_adn(self):
        entry = next(entry for entry in self.exported['vors']
                     if entry['id'] == 'ADN')
        self.assertEqual(entry['frequency'], '114.3')
        self.assertIs(entry['dme'], True)
        self.assertEqual(entry['rotation'], -0.4)
        self.assertEqual(entry['rotation_source'], 'declination')

    def test_no_exported_vor_lacks_declination(self):
        # Every one of the 21 exported VORs has a declination in the fixture,
        # so no fixture record exercises the magnetic_variation fallback.
        self.assertTrue(all(entry['rotation_source'] == 'declination'
                            for entry in self.exported['vors']))

    def test_pth_is_vor_only(self):
        entry = next(entry for entry in self.exported['vors']
                     if entry['id'] == 'PTH')
        self.assertIs(entry['dme'], False)
        self.assertEqual(entry['frequency'], '110.4')
        # PTH declination 0.5W -> rotation +0.5.
        self.assertEqual(entry['rotation'], 0.5)


class TestDangerVorsStrictness(unittest.TestCase):

    def test_navaid_without_declination_or_variation_raises(self):
        record = _synthetic_vor()
        with self.assertRaisesRegex(ValueError, 'declination'):
            export_vors([record])

    def test_magnetic_variation_fallback(self):
        record = _synthetic_vor(
            magnetic_variation={'text': '1.25°E', 'value': 1.25,
                                'year': 2027})
        result = export_vors([record])
        entry = result['vors'][0]
        self.assertEqual(entry['rotation'], -1.25)
        self.assertEqual(entry['rotation_source'], 'magnetic_variation')

    def test_unknown_danger_limit_raises(self):
        record = _synthetic_danger(upper='1000 FT BANANA')
        with self.assertRaisesRegex(ValueError, 'unknown upper'):
            export_danger([record], {})

    def test_missing_lower_limit_is_empty_string(self):
        record = _synthetic_danger(lower=None)
        boundaries = {'EGX001': {'points': [{'lat': 1.0, 'lng': 2.0}],
                                 'exclusions': [], 'approximate': False}}
        entry = export_danger([record], boundaries)['danger'][0]
        self.assertEqual(entry['lower_limit'], '')


class TestWriteFiles(unittest.TestCase):

    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            result = write_danger_vors_files(
                ENR51.read_text(encoding='utf-8'),
                ENR41.read_text(encoding='utf-8'), directory)
            expected = {
                'danger.json': result['danger']['danger'],
                'danger_skipped.json': result['danger']['skipped'],
                'vors.json': result['vors']['vors'],
                'vors_skipped.json': result['vors']['skipped'],
            }
            self.assertEqual(len(expected['danger.json']), 1035)
            self.assertEqual(len(expected['vors.json']), 21)
            for filename, value in expected.items():
                with open(pathlib.Path(directory) / filename,
                          encoding='utf-8') as handle:
                    self.assertEqual(json.load(handle), value)
            self.assertEqual(
                sorted(path.name for path in pathlib.Path(directory).iterdir()),
                sorted(expected))

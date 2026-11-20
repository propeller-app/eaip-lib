import json
import pathlib
import re
import tempfile
import unittest

from eaip.airspace.boundary import parse_boundaries
from eaip.enr21 import parse_enr21
from eaip.export import export_airspaces, write_airspace_files


FIXTURE = pathlib.Path(__file__).parent / 'fixtures' / 'EG-ENR-2.1.html'
KEYS = {
    'name', 'upper_limit', 'lower_limit', '_class', 'frequency',
    'frequency_annotation', 'frequency_ambiguous', 'squawk', 'boundary',
    'band_index', 'frequencies', 'exclusions', 'source',
}
LIMIT_RE = re.compile(r'^(FL\d+|\d+ FT (ALT|AGL)|SFC|UNL)$')


def _synthetic(name, class_='D', frequency='123.450'):
    record = {
        'name': name,
        'bands': [{'upper': 'FL 195', 'lower': 'SFC',
                   'minimum': None, 'class': class_}],
        'units': [{'frequencies': [frequency]}],
    }
    boundary = {'points': [{'lat': 51.0, 'lng': -1.0},
                           {'lat': 51.0, 'lng': -1.0}],
                'exclusions': []}
    return record, {name: boundary}


class TestExportAirspaces(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.html = FIXTURE.read_text(encoding='utf-8')
        cls.records = parse_enr21(cls.html)
        cls.boundaries, cls.failed = parse_boundaries(cls.records)
        cls.exported = export_airspaces(cls.records, cls.boundaries)

    def entries(self):
        return (self.exported['ctas'] + self.exported['ctrs']
                + self.exported['tma'])

    def test_counts(self):
        # CTA 379 records + 3 second bands (NORTH SEA CTA 1/2/3) = 382.
        # TMA 33 records + 6 second bands (MANCHESTER TMA 1 and
        # SCOTTISH TMA 1-5) = 39. CTR 1 record + 0 = 1.
        # FIR 3 + UIR 2 + OCA 1 = 6 skipped records.
        self.assertEqual(len(self.records), 419)
        self.assertEqual(self.failed, [])
        self.assertEqual(len(self.exported['ctas']), 382)
        self.assertEqual(len(self.exported['ctrs']), 1)
        self.assertEqual(len(self.exported['tma']), 39)
        self.assertEqual(len(self.exported['skipped']), 6)
        self.assertEqual(len(self.entries()), 422)

    def test_skipped_records(self):
        self.assertEqual(
            [entry['name'] for entry in self.exported['skipped']],
            ['LONDON FIR', 'SCOTTISH FIR', 'SHANWICK OCEANIC FIR',
             'LONDON UIR', 'SCOTTISH UIR',
             'SHANWICK OCEANIC CONTROL AREA (OCA)'])
        for entry in self.exported['skipped']:
            self.assertEqual(set(entry), {'name', 'reason'})
            self.assertIsInstance(entry['reason'], str)
            self.assertTrue(entry['reason'])

    def test_every_entry_shape(self):
        for entry in self.entries():
            self.assertEqual(set(entry), KEYS)
            self.assertIsInstance(entry['name'], str)
            self.assertIsInstance(entry['upper_limit'], str)
            self.assertIsInstance(entry['lower_limit'], str)
            self.assertIsInstance(entry['_class'], str)
            self.assertEqual(len(entry['_class']), 1)
            self.assertIn(entry['_class'], 'ABCDEFG')
            self.assertTrue(entry['frequency'] == ''
                            or isinstance(entry['frequency'], float))
            self.assertIsInstance(entry['frequency_annotation'], str)
            self.assertIsInstance(entry['frequency_ambiguous'], bool)
            self.assertEqual(entry['squawk'], '')
            self.assertIsInstance(entry['band_index'], int)
            self.assertIsInstance(entry['frequencies'], list)
            for value in entry['frequencies']:
                self.assertIsInstance(value, float)
            self.assertIsInstance(entry['exclusions'], list)
            self.assertEqual(entry['source'], 'ENR-2.1')
            self.assertTrue(entry['boundary'])
            for point in entry['boundary']:
                self.assertEqual(set(point), {'lat', 'lng'})
                self.assertIsInstance(point['lat'], float)
                self.assertIsInstance(point['lng'], float)
            self.assertEqual(entry['boundary'][0], entry['boundary'][-1])

    def test_limits_are_normalised(self):
        for entry in self.entries():
            for key in ('upper_limit', 'lower_limit'):
                limit = entry[key]
                self.assertIsNone(re.search(r'FL \d', limit), limit)
                self.assertRegex(limit, LIMIT_RE)

    def test_london_gatwick_cta(self):
        # Fixture lines: name 8447, upper 8454, lower 8455, class 8457,
        # frequencies 8474/8485/8492/8499, annotations 8477/8488/8495/8502.
        # 118.950 and 129.025 are instructed, 121.500 is emergency, so E8c
        # picks 126.825.
        entry = next(entry for entry in self.exported['ctas']
                     if entry['name'] == 'LONDON GATWICK CTA')
        self.assertEqual(entry['upper_limit'], '2500 FT ALT')
        self.assertEqual(entry['lower_limit'], '1500 FT ALT')
        self.assertEqual(entry['_class'], 'D')
        self.assertEqual(entry['frequency'], 126.825)
        self.assertEqual(entry['frequency_annotation'],
                         'DOC 45 NM/24,500 FT.')
        self.assertIs(entry['frequency_ambiguous'], False)
        self.assertEqual(entry['frequencies'],
                         [118.95, 121.5, 126.825, 129.025])
        self.assertEqual(entry['squawk'], '')
        self.assertEqual(entry['band_index'], 0)
        self.assertEqual(entry['exclusions'], ['Gatwick CTR'])

    def test_multi_band_north_sea_cta_1(self):
        entries = [entry for entry in self.exported['ctas']
                   if entry['name'] == 'NORTH SEA CTA 1']
        self.assertEqual(len(entries), 2)
        self.assertEqual([entry['band_index'] for entry in entries], [0, 1])
        self.assertEqual(entries[0]['boundary'], entries[1]['boundary'])
        self.assertEqual([(entry['lower_limit'], entry['upper_limit'],
                           entry['_class']) for entry in entries],
                         [('FL175', 'FL195', 'A'),
                          ('FL195', 'FL245', 'C')])

    def test_london_tma_1(self):
        entry = next(entry for entry in self.exported['tma']
                     if entry['name'] == 'LONDON TMA 1')
        self.assertEqual(entry['_class'], 'A')
        self.assertEqual(entry['upper_limit'], 'FL195')
        self.assertEqual(entry['lower_limit'], '2500 FT ALT')

    def test_write_files_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            result = write_airspace_files(self.html, directory)
            self.assertEqual(result, self.exported)
            expected = {'ctas': 'ctas.json', 'ctrs': 'ctrs.json',
                        'tma': 'tma.json', 'skipped': 'skipped_airspaces.json'}
            for key, filename in expected.items():
                with open(pathlib.Path(directory) / filename,
                          encoding='utf-8') as handle:
                    self.assertEqual(json.load(handle), result[key])
            self.assertEqual(
                sorted(path.name for path in pathlib.Path(directory).iterdir()),
                sorted(expected.values()))


class TestExportAirspacesStrictness(unittest.TestCase):

    def test_ambiguous_name_raises(self):
        record, boundaries = _synthetic('TEST CTA CTR')
        with self.assertRaisesRegex(ValueError, 'ambiguous'):
            export_airspaces([record], boundaries)

    def test_unparseable_frequency_raises(self):
        record, boundaries = _synthetic('TEST CTA', frequency='not a freq')
        with self.assertRaisesRegex(ValueError, 'unparseable frequency'):
            export_airspaces([record], boundaries)

    def test_bad_class_raises(self):
        record, boundaries = _synthetic('TEST CTA', class_='DD')
        with self.assertRaisesRegex(ValueError, 'class'):
            export_airspaces([record], boundaries)

    def test_missing_frequency_is_empty_string(self):
        record, boundaries = _synthetic('TEST CTA')
        record['units'] = []
        result = export_airspaces([record], boundaries)
        self.assertEqual(result['ctas'][0]['frequency'], '')
        self.assertEqual(result['ctas'][0]['frequencies'], [])

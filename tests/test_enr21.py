import pathlib
import unittest

from eaip.enr21 import parse_enr21


FIXTURE = pathlib.Path(__file__).parent / 'fixtures' / 'EG-ENR-2.1.html'


def unit(name, callsign, language, hours, frequencies):
    return {
        'name': name,
        'callsign': callsign,
        'language': language,
        'hours': hours,
        'frequencies': frequencies,
    }


class TestParseEnr21(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.records = parse_enr21(FIXTURE.read_text(encoding='utf-8'))
        cls.by_name = {}
        for record in cls.records:
            cls.by_name.setdefault(record['name'], []).append(record)

    def record(self, name):
        matches = self.by_name[name]
        self.assertEqual(len(matches), 1, f'{name} should be one record')
        return matches[0]

    def test_record_count(self):
        self.assertEqual(len(self.records), 419)

    def test_row_ids_unique_among_non_none(self):
        row_ids = [r['row_id'] for r in self.records if r['row_id'] is not None]
        self.assertEqual(len(row_ids), len(set(row_ids)))
        self.assertEqual(len(row_ids), 418)
        self.assertEqual([r['name'] for r in self.records if r['row_id'] is None],
                         ['BRIZE NORTON CTR'])

    def test_berry_head_cta_6(self):
        # name 1490, limits 1494-1497, unit 1500-1514, remarks 1518
        record = self.record('BERRY HEAD CTA 6')
        self.assertEqual(record['row_id'], '2054')
        self.assertTrue(record['boundary_text'].startswith('512238N 0071903W'))
        self.assertEqual(record['bands'], [
            {'upper': 'FL 195', 'lower': 'FL 135', 'minimum': None, 'class': 'A'},
        ])
        self.assertEqual(record['units'], [
            unit('LONDON ACC', 'LONDON CONTROL', 'English', 'H24', ['132.955']),
        ])
        self.assertTrue(record['remarks'].startswith('Part of ATS Routes L37, L38 and N160'))

    def test_cotswold_cta_11_two_units(self):
        # name 4264, limits 4268-4271, LONDON ACC 4274-4291,
        # CARDIFF APP continuation 1020_700 at 4297-4313
        record = self.record('COTSWOLD CTA 11')
        self.assertEqual(record['row_id'], '1020')
        self.assertEqual(record['bands'], [
            {'upper': 'FL 195', 'lower': 'FL 105', 'minimum': None, 'class': 'A'},
        ])
        self.assertEqual(record['units'], [
            unit('LONDON ACC', 'LONDON CONTROL', 'English', 'H24\n(Note 1)', ['134.755']),
            unit('CARDIFF APP', 'CARDIFF RADAR', 'English',
                 '0600-2300 (0500-2200)\n(Note 1)', ['125.855']),
        ])

    def test_london_uir_same_extent_and_missing_fields(self):
        # name 570, "Same extent" 572, limits 573-576, units 579-615
        record = self.record('LONDON UIR')
        self.assertEqual(record['row_id'], '1161')
        self.assertEqual(record['boundary_text'], 'Same extent as LONDON FIR')
        self.assertEqual(record['bands'], [
            {'upper': 'FL 660', 'lower': 'FL 245', 'minimum': None, 'class': 'C'},
        ])
        self.assertEqual(record['units'], [
            unit('LONDON ACC', None, None, 'H24', []),
            unit('SCOTTISH ACC', 'SCOTTISH CONTROL', 'English', 'H24',
                 ['118.780', '133.050', '133.800']),
        ])

    def test_scottish_uir_same_extent(self):
        record = self.record('SCOTTISH UIR')
        self.assertEqual(record['boundary_text'], 'Same extent as SCOTTISH FIR')

    def test_london_fir_two_bands_and_four_units(self):
        # name 20, band 1 limits 24-26, band 2 limits 27-29
        record = self.record('LONDON FIR')
        self.assertEqual(record['bands'], [
            {'upper': 'FL 245', 'lower': 'FL 195', 'minimum': None, 'class': 'C'},
            {'upper': 'FL 195', 'lower': 'SFC', 'minimum': None, 'class': 'G'},
        ])
        self.assertEqual(len(record['units']), 4)

    def test_exactly_twelve_multi_band_records(self):
        expected = {
            'LONDON FIR',
            'SCOTTISH FIR',
            'SHANWICK OCEANIC FIR',
            'NORTH SEA CTA 1',
            'NORTH SEA CTA 2 (GODOS)',
            'NORTH SEA CTA 3 (MOLIX)',
            'MANCHESTER TMA 1',
            'SCOTTISH TMA 1',
            'SCOTTISH TMA 2',
            'SCOTTISH TMA 3',
            'SCOTTISH TMA 4',
            'SCOTTISH TMA 5',
        }
        multi = {r['name'] for r in self.records if len(r['bands']) > 1}
        self.assertEqual(multi, expected)

    def test_pepze_cta_9_missing_callsign(self):
        # callsign cell is "-" (line 11041), frequency 133.600 (line 11044)
        record = self.record('PEPZE CTA 9')
        self.assertEqual(record['row_id'], '10195')
        self.assertEqual(record['units'], [
            unit('LONDON ACC', None, None, None, ['133.600']),
        ])

    def test_brize_norton_ctr_has_no_row_id(self):
        # ENR-2.1.1 table at the end: record row 16815, band 16817,
        # unit rows 16818 and 16823-16827
        record = self.record('BRIZE NORTON CTR')
        self.assertIsNone(record['row_id'])
        self.assertEqual(record['bands'], [
            {'upper': '3500 FT ALT', 'lower': 'SFC', 'minimum': None, 'class': 'D'},
        ])
        self.assertEqual(len(record['units']), 2)
        self.assertEqual(record['units'][0]['name'], 'RAF BRIZE NORTON')
        self.assertEqual(record['units'][0]['callsign'], 'BRIZE ZONE')
        # frequency text stays as printed; E8 normalises it.
        self.assertEqual(record['units'][0]['frequencies'], ['119.005 MHz'])
        self.assertEqual(record['units'][1]['callsign'], 'BRIZE RADAR')
        self.assertEqual(record['units'][1]['frequencies'], ['124.280 MHz'])


if __name__ == '__main__':
    unittest.main()

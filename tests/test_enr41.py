import collections
import pathlib
import unittest

from eaip.enr41 import (_parse_coordinate, _parse_type, _parse_variation,
                        parse_enr41)


FIXTURE = pathlib.Path(__file__).parent / 'fixtures' / 'EG-ENR-4.1.html'


def _synthetic_row(name='NAME', ident='XXX', type_text='DME',
                   coord='510000.00N 0000000.00E', include_id=True):
    id_cell = ''
    if include_id:
        id_cell = (
            f'<span class="SD">{ident}</span>'
            '<span class="sdParams">TDME;CODE_ID;1</span>')
    return (
        '<table><tr id="NAV-DME-XXX"><td>'
        f'<strong><span class="SD">{name}</span>'
        '<span class="sdParams">TDME;TXT_NAME;1</span></strong>'
        f'\n<p class="line">{type_text}</p></td>'
        f'<td>{id_cell}</td><td></td><td></td><td>{coord}</td>'
        '<td></td><td></td><td></td>'
        '</tr></table>')


class TestParseEnr41(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.records = parse_enr41(FIXTURE.read_text(encoding='utf-8'))
        cls.by_ident = {r['id']: r for r in cls.records}

    def record(self, ident):
        return self.by_ident[ident]

    def test_record_count(self):
        self.assertEqual(len(self.records), 54)

    def test_ids_are_unique_and_stripped(self):
        idents = [r['id'] for r in self.records]
        self.assertEqual(len(idents), len(set(idents)))
        for ident in idents:
            self.assertTrue(ident)
            self.assertEqual(ident, ident.strip())

    def test_type_counts(self):
        self.assertEqual(
            collections.Counter(r['type'] for r in self.records),
            {'DME': 31, 'VOR/DME': 20, 'NDB': 2, 'VOR': 1})

    def test_component_counts(self):
        self.assertEqual(
            collections.Counter(tuple(r['components']) for r in self.records),
            {('DME',): 31, ('VOR', 'DME'): 20, ('NDB',): 2, ('VOR',): 1})
        self.assertEqual(
            collections.Counter(c for r in self.records for c in r['components']),
            {'VOR': 21, 'DME': 51, 'NDB': 2})

    def test_optional_field_counts(self):
        self.assertEqual(
            sum(bool(r['hours_annotations']) for r in self.records), 5)
        self.assertEqual(
            sum(r['declination'] is not None for r in self.records), 21)
        self.assertEqual(
            sum(r['magnetic_variation'] is not None for r in self.records), 54)
        self.assertEqual(
            sum(r['dme'] is not None for r in self.records), 51)
        self.assertEqual(
            sum(r['frequency'] is not None for r in self.records), 23)
        self.assertEqual(
            sum(r['paired_frequency'] is not None for r in self.records), 30)
        self.assertEqual(
            sum(r['elevation'] is not None for r in self.records), 51)

    def test_adn_vor_dme(self):
        # ADN: row 8, name 10, type 13, frequency 17, channel 19,
        # hours 22/24, co-ordinates 29/31, elevation 34, FRA 36,
        # remarks 39/42.
        record = self.record('ADN')
        self.assertEqual(record['row_id'], 'NAV-VORDME-ADN')
        self.assertEqual(record['name'], 'ABERDEEN')
        self.assertEqual(record['type'], 'VOR/DME')
        self.assertEqual(record['components'], ['VOR', 'DME'])
        self.assertEqual(record['frequency'], {
            'text': '114.300', 'value': 114.3, 'unit': 'MHz'})
        # VOR/DME rows print no VAL_GHOST_FREQ; only DME-only rows do.
        self.assertIsNone(record['paired_frequency'])
        self.assertEqual(record['dme'], {'channel': '90X'})
        self.assertEqual(record['location']['text'],
                         '571837.62N 0021602.09W')
        # 57 + 18/60 + 37.62/3600 = 57.31045
        self.assertAlmostEqual(record['location']['lat'], 57.31045, delta=1e-6)
        # -(2 + 16/60 + 2.09/3600) = -2.2672472222
        self.assertAlmostEqual(record['location']['lng'], -2.2672472222,
                               delta=1e-6)
        self.assertEqual(record['elevation'], {
            'text': '610', 'value': 610.0, 'unit': 'FT'})
        self.assertEqual(record['magnetic_variation'], {
            'text': '0.04°E', 'value': 0.04, 'year': 2027})
        self.assertEqual(record['declination'], {
            'text': '0.4°E', 'value': 0.4, 'year': 2026})
        self.assertEqual(record['hours'], 'H24')
        self.assertEqual(record['hours_annotations'], [
            'Hours of operation for aerodrome purposes: HO'])
        self.assertEqual(record['fra_relevance'], 'IAD')
        self.assertEqual(
            record['remarks'],
            'FRA (AD): EGPC, EGPE, EGPN, EGPT, EGQL\n\n\n'
            'APCH Aid to Aberdeen/Dyce.\n'
            'VOR/DME DOC: 90 NM/50,000 FT '
            '(200 NM/50,000 FT in Sector R045-135).')

    def test_pth_vor_only(self):
        # PTH: row 1122, type 1128, variation/declination 1129,
        # id 1130, frequency 1133, co-ordinates 1139/1141,
        # FRA 1143, remarks 1146/1149.
        record = self.record('PTH')
        self.assertEqual(record['row_id'], 'NAV-VOR-PTH')
        self.assertEqual(record['name'], 'PERTH')
        self.assertEqual(record['type'], 'VOR')
        self.assertEqual(record['components'], ['VOR'])
        self.assertEqual(record['frequency'], {
            'text': '110.400', 'value': 110.4, 'unit': 'MHz'})
        self.assertIsNone(record['paired_frequency'])
        self.assertIsNone(record['dme'])
        self.assertEqual(record['location']['text'],
                         '562632.63N 0032206.96W')
        # 56 + 26/60 + 32.63/3600 = 56.4423972222
        self.assertAlmostEqual(record['location']['lat'], 56.4423972222,
                               delta=1e-6)
        # -(3 + 22/60 + 6.96/3600) = -3.3686
        self.assertAlmostEqual(record['location']['lng'], -3.3686, delta=1e-6)
        self.assertIsNone(record['elevation'])
        self.assertEqual(record['magnetic_variation'], {
            'text': '0.30°W', 'value': -0.3, 'year': 2027})
        self.assertEqual(record['declination'], {
            'text': '0.5°W', 'value': -0.5, 'year': 2023})
        self.assertEqual(record['hours'], 'H24')
        self.assertEqual(record['hours_annotations'], [])
        self.assertEqual(record['fra_relevance'], 'IAD')
        self.assertIn('No associated DME.', record['remarks'])

    def test_lon_dme_channel_only(self):
        # LON: row 830, name 832, variation 834, id 835, channel 838,
        # hours 842, co-ordinates 845/847, elevation 850, FRA 852.
        record = self.record('LON')
        self.assertEqual(record['row_id'], 'NAV-DME-LON')
        self.assertEqual(record['name'], 'LONDON')
        self.assertEqual(record['type'], 'DME')
        self.assertEqual(record['components'], ['DME'])
        self.assertIsNone(record['frequency'])
        self.assertIsNone(record['paired_frequency'])
        self.assertEqual(record['dme'], {'channel': '83X'})
        self.assertEqual(record['location']['text'],
                         '512914.09N 0002759.54W')
        # 51 + 29/60 + 14.09/3600 = 51.4872472222
        self.assertAlmostEqual(record['location']['lat'], 51.4872472222,
                               delta=1e-6)
        # -(0 + 27/60 + 59.54/3600) = -0.4665388889
        self.assertAlmostEqual(record['location']['lng'], -0.4665388889,
                               delta=1e-6)
        # The fixture prints 113 FT for LON; the task note said None.
        self.assertEqual(record['elevation'], {
            'text': '113', 'value': 113.0, 'unit': 'FT'})
        self.assertEqual(record['magnetic_variation'], {
            'text': '1.22°E', 'value': 1.22, 'year': 2027})
        self.assertIsNone(record['declination'])
        self.assertEqual(record['hours'], 'H24')
        self.assertEqual(record['hours_annotations'], [])
        self.assertEqual(record['fra_relevance'], '-')
        self.assertIn('No associated En-route VOR.', record['remarks'])
        self.assertIn('DME DOC: 40 NM/50,000 FT', record['remarks'])

    def test_hen_ndb(self):
        # HEN: row 649, name 651, variation 653, id 654, frequency 657,
        # co-ordinates 663/665, FRA 667, remarks 670/673.
        record = self.record('HEN')
        self.assertEqual(record['row_id'], 'NAV-NDB-HEN')
        self.assertEqual(record['name'], 'HENTON')
        self.assertEqual(record['type'], 'NDB')
        self.assertEqual(record['components'], ['NDB'])
        self.assertEqual(record['frequency'], {
            'text': '433.500', 'value': 433.5, 'unit': 'kHz'})
        self.assertIsNone(record['paired_frequency'])
        self.assertIsNone(record['dme'])
        self.assertEqual(record['location']['text'],
                         '514535.07N 0004725.05W')
        # 51 + 45/60 + 35.07/3600 = 51.7597416667
        self.assertAlmostEqual(record['location']['lat'], 51.7597416667,
                               delta=1e-6)
        # -(0 + 47/60 + 25.05/3600) = -0.7902916667
        self.assertAlmostEqual(record['location']['lng'], -0.7902916667,
                               delta=1e-6)
        self.assertIsNone(record['elevation'])
        self.assertEqual(record['magnetic_variation'], {
            'text': '1.10°E', 'value': 1.1, 'year': 2027})
        self.assertIsNone(record['declination'])
        self.assertEqual(record['hours'], 'H24')
        self.assertEqual(record['hours_annotations'], [])
        self.assertEqual(record['fra_relevance'], '-')
        self.assertEqual(
            record['remarks'],
            'No associated En-route navigational dependency.\n\n\n'
            'Range 30 NM.')

    def test_ben_dme_with_hours_annotation(self):
        # BEN: row 103, name 105, variation 107, id 108, channel 111,
        # paired frequency 114, hours 117/120, co-ordinates 123/125,
        # elevation 128, FRA 130, remarks 132.
        record = self.record('BEN')
        self.assertEqual(record['row_id'], 'NAV-DME-BEN')
        self.assertEqual(record['name'], 'BENBECULA')
        self.assertEqual(record['type'], 'DME')
        self.assertEqual(record['components'], ['DME'])
        self.assertIsNone(record['frequency'])
        self.assertEqual(record['paired_frequency'], {
            'text': '113.950', 'value': 113.95, 'unit': 'MHz'})
        self.assertEqual(record['dme'], {'channel': '86Y'})
        self.assertEqual(record['location']['text'],
                         '572840.57N 0072155.08W')
        # 57 + 28/60 + 40.57/3600 = 57.4779361111
        self.assertAlmostEqual(record['location']['lat'], 57.4779361111,
                               delta=1e-6)
        # -(7 + 21/60 + 55.08/3600) = -7.3653
        self.assertAlmostEqual(record['location']['lng'], -7.3653, delta=1e-6)
        self.assertEqual(record['elevation'], {
            'text': '46', 'value': 46.0, 'unit': 'FT'})
        self.assertEqual(record['magnetic_variation'], {
            'text': '2.11°W', 'value': -2.11, 'year': 2027})
        self.assertIsNone(record['declination'])
        self.assertEqual(record['hours'], 'H24')
        self.assertEqual(record['hours_annotations'], [
            'Hours of operation for aerodrome purposes: Mon-Fri 0800-1630 '
            '(0700-1530); Sat 0800-0915 (0700-0815), 1030-1245 '
            '(0930-1145); Sun 1600-1800 (1500-1700) and by arrangement '
            'with AD operator (HIAL).'])
        self.assertEqual(record['fra_relevance'], '-')
        self.assertEqual(
            record['remarks'],
            'No associated En-route VOR.\nAPCH Aid to Benbecula.\n'
            'On Benbecula AD.\nDME DOC: 150 NM/50,000 FT '
            '(200 NM/50,000 FT in Sector R197-002).')


class TestEnr41Strictness(unittest.TestCase):

    def test_bad_coordinate_raises(self):
        with self.assertRaises(ValueError):
            _parse_coordinate('999999.99N 0000000.00E')
        with self.assertRaises(ValueError):
            _parse_coordinate('516000.00N 0000000.00E')
        with self.assertRaises(ValueError):
            _parse_coordinate('510000.00N 0006000.00E')
        with self.assertRaises(ValueError):
            _parse_coordinate('not a coordinate')

    def test_unknown_type_raises(self):
        with self.assertRaisesRegex(ValueError, 'unknown type'):
            parse_enr41(_synthetic_row(type_text='TACAN'))

    def test_missing_id_raises(self):
        with self.assertRaisesRegex(ValueError, 'missing id'):
            parse_enr41(_synthetic_row(include_id=False))

    def test_variation_parser(self):
        self.assertEqual(_parse_variation('0.04°E'), 0.04)
        self.assertEqual(_parse_variation('2.11°W'), -2.11)
        self.assertEqual(_parse_variation('0°'), 0.0)
        with self.assertRaises(ValueError):
            _parse_variation('1.00')
        with self.assertRaises(ValueError):
            _parse_variation('1.00°N')

    def test_type_parser(self):
        self.assertEqual(_parse_type('ABERDEEN\n\nVOR/DME', 'NAV-VORDME-ADN'),
                         'VOR/DME')
        with self.assertRaisesRegex(ValueError, 'unknown type'):
            _parse_type('ABERDEEN\n\nTACAN', 'NAV-TACAN-XXX')

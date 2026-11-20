import pathlib
import re
import unittest

from eaip.enr21 import parse_enr21


FIXTURE = pathlib.Path(__file__).parent / 'fixtures' / 'EG-ENR-2.1.html'


def _synthetic_html(frequency_rows, annotations):
    """
    One-record, one-unit ENR-2.1 table. ``frequency_rows`` are (value, id)
    pairs; ``annotations`` are (text, id) pairs placed in the same cell.
    """
    frequencies = '\n'.join(
        f'<p><span class="SD">{value}</span>'
        f'<span class="sdParams">TFREQUENCY;VAL_FREQ_TRANS;{ident}</span></p>'
        for value, ident in frequency_rows)
    notes = '\n'.join(
        f'<p><span class="SD">{text}</span>'
        f'<span class="sdParams">TFREQUENCY;ANNOTATION:1.eng;{ident}</span></p>'
        for text, ident in annotations)
    return f'''<table><tr>
<td>
  <p><span class="SD">TEST CTA</span>
     <span class="sdParams">TAIRSPACE;TXT_NAME;1</span></p>
  <p>Upper limit: <span class="SD">1000</span>
     <span class="sdParams">TAIRSPACE_VOLUME;VAL_DIST_VER_UPPER;1</span>
     <span class="SD">FT ALT</span>
     <span class="sdParams">TAIRSPACE_VOLUME;UOM_DIST_VER_UPPER;1</span></p>
  <p>Lower limit: <span class="SD">SFC</span>
     <span class="sdParams">TAIRSPACE_VOLUME;VAL_DIST_VER_LOWER;1</span></p>
</td>
<td>
  <p><span class="SD">TEST APP</span>
     <span class="sdParams">TUNIT;TXT_NAME;2</span></p>
</td>
<td>
  {frequencies}
  {notes}
</td>
</tr></table>'''


class TestFrequencyAnnotations(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.records = parse_enr21(FIXTURE.read_text(encoding='utf-8'))

    def test_annotations_align_with_frequencies(self):
        for record in self.records:
            for index, unit in enumerate(record['units']):
                self.assertEqual(
                    len(unit['frequency_annotations']), len(unit['frequencies']),
                    f'{record["name"]} unit {index}')

    def test_fixture_totals(self):
        frequencies = sum(len(unit['frequencies']) for record in self.records
                          for unit in record['units'])
        annotated = sum(1 for record in self.records for unit in record['units']
                        for annotation in unit['frequency_annotations']
                        if annotation is not None)
        self.assertEqual(frequencies, 849)
        self.assertEqual(annotated, 302)

    def test_london_gatwick_cta_annotations(self):
        # Frequencies at 8474, 8485, 8492, 8499; annotations at 8477, 8488,
        # 8495, 8502.
        record = next(record for record in self.records
                      if record['name'] == 'LONDON GATWICK CTA')
        self.assertEqual(record['units'][0]['frequencies'],
                         ['118.950', '121.500', '126.825', '129.025'])
        self.assertEqual(record['units'][0]['frequency_annotations'], [
            'When instructed by ATC. DOC 25 NM/10,000 FT.',
            'Emergency frequency O/R.',
            'DOC 45 NM/24,500 FT.',
            'When instructed by ATC. DOC 45 NM/24,500 FT.',
        ])

    def test_annotation_ids_shared_by_a_frequency_are_the_same_text(self):
        # The eAIP reuses one frequency id across records; the annotations
        # matched to it must agree. A conflicting duplicate raises.
        html = _synthetic_html(
            [('123.450', '7')],
            [('First text.', '7'), ('Different text.', '7')])
        with self.assertRaisesRegex(ValueError, 'more than one annotation'):
            parse_enr21(html)

    def test_annotation_without_a_frequency_raises(self):
        html = _synthetic_html([('123.450', '7')], [('Orphan text.', '8')])
        with self.assertRaisesRegex(ValueError, 'no matching frequency'):
            parse_enr21(html)


if __name__ == '__main__':
    unittest.main()


# ---------------------------------------------------------------------------
# Part B: frequency selection and export keys.
# ---------------------------------------------------------------------------

import math
import re

from eaip.airspace.boundary import parse_boundaries
from eaip.enr41 import parse_enr41
from eaip.enr51 import parse_enr51, parse_enr51_boundaries
from eaip.export import (export_airspaces, export_danger, export_vors,
                         select_frequency)


ENR41 = pathlib.Path(__file__).parent / 'fixtures' / 'EG-ENR-4.1.html'
ENR51 = pathlib.Path(__file__).parent / 'fixtures' / 'EG-ENR-5.1.html'
FREQUENCY_RE = re.compile(r'^(\d+(?:\.\d+)?)\s*(?:MHz)?$')


def _value(text):
    return float(FREQUENCY_RE.match(text.strip()).group(1))


def _secondary(annotation):
    text = (annotation or '').lower()
    return 'instructed by atc' in text or 'emergency' in text


def _non_secondary_values(record):
    values = []
    for unit in record['units']:
        for text, note in zip(unit['frequencies'],
                              unit['frequency_annotations']):
            value = _value(text)
            if not _secondary(note) and value not in values:
                values.append(value)
    return values


class TestAirspaceFrequencyExport(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        html = FIXTURE.read_text(encoding='utf-8')
        cls.records = parse_enr21(html)
        boundaries, cls.failed = parse_boundaries(cls.records)
        cls.exported = export_airspaces(cls.records, boundaries)
        cls.entries = (cls.exported['ctas'] + cls.exported['ctrs']
                       + cls.exported['tma'])

    def entry(self, collection, name):
        return next(entry for entry in self.exported[collection]
                    if entry['name'] == name)

    def test_london_gatwick_cta_frequency(self):
        # Frequencies 8474/8485/8492/8499, annotations 8477/8488/8495/8502:
        # 118.950 instructed, 121.500 emergency, 126.825 plain DOC.
        entry = self.entry('ctas', 'LONDON GATWICK CTA')
        self.assertEqual(entry['frequency'], 126.825)
        self.assertEqual(entry['frequency_annotation'], 'DOC 45 NM/24,500 FT.')
        self.assertIs(entry['frequency_ambiguous'], False)

    def test_north_sea_cta_1_frequency(self):
        # 128.130 with "(Note 1)".
        entry = self.entry('ctas', 'NORTH SEA CTA 1')
        self.assertEqual(entry['frequency'], 128.13)
        self.assertEqual(entry['frequency_annotation'], '(Note 1)')
        self.assertIs(entry['frequency_ambiguous'], False)

    def test_brize_norton_ctr_frequency(self):
        # ZONE 119.005 (line 16821) and RADAR 124.280 (line 16827), no
        # annotations, two non-secondary values.
        entry = self.entry('ctrs', 'BRIZE NORTON CTR')
        self.assertEqual(entry['frequency'], 119.005)
        self.assertEqual(entry['frequency_annotation'], '')
        self.assertIs(entry['frequency_ambiguous'], True)

    def test_select_frequency_edge_cases(self):
        by_name = {record['name']: record for record in self.records}
        # LONDON UIR units: LONDON ACC has no frequencies, SCOTTISH ACC has
        # 118.780/133.050/133.800 (unit 578-615).
        self.assertEqual(select_frequency(by_name['LONDON UIR']),
                         ('118.780', '', True))
        oca = by_name['SHANWICK OCEANIC CONTROL AREA (OCA)']
        self.assertEqual(select_frequency(oca), ('', '', False))
        synthetic = {
            'name': 'SYNTHETIC CTA',
            'units': [{'frequencies': ['121.500', '118.950'],
                       'frequency_annotations': [
                           'Emergency frequency.', 'When instructed by ATC.']}],
        }
        self.assertEqual(select_frequency(synthetic),
                         ('121.500', 'Emergency frequency.', False))

    def test_ambiguous_flags_match_an_independent_count(self):
        for entry in self.entries:
            self.assertIsInstance(entry['frequency_ambiguous'], bool)
        by_name = {record['name']: record for record in self.records}
        expected_true = {
            name for name in {entry['name'] for entry in self.entries}
            if len(_non_secondary_values(by_name[name])) > 1}
        actual_true = {entry['name'] for entry in self.entries
                       if entry['frequency_ambiguous']}
        self.assertEqual(actual_true, expected_true)

    def test_only_gatwick_differs_from_the_old_pick(self):
        by_name = {record['name']: record for record in self.records}
        differing = set()
        for entry in self.entries:
            units = by_name[entry['name']]['units']
            old = _value(units[0]['frequencies'][0])
            if entry['frequency'] != old:
                differing.add(entry['name'])
        self.assertEqual(differing, {'LONDON GATWICK CTA'})
        gatwick = self.entry('ctas', 'LONDON GATWICK CTA')
        self.assertEqual(gatwick['frequency'], 126.825)
        self.assertNotEqual(gatwick['frequency'], 118.950)


class TestDangerIdentExport(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        html = ENR51.read_text(encoding='utf-8')
        cls.records = parse_enr51(html)
        boundaries, cls.failed = parse_enr51_boundaries(cls.records)
        cls.exported = export_danger(cls.records, boundaries)

    def test_ident_is_stripped_and_eaip_ident_kept(self):
        # EGD044 is printed at fixture line 1018, EGR1U001A at 6580.
        by_eaip = {entry['eaip_ident']: entry
                   for entry in self.exported['danger']}
        self.assertEqual(by_eaip['EGD044']['ident'], 'D044')
        self.assertEqual(by_eaip['EGR1U001A']['ident'], 'R1U001A')
        for entry in self.exported['danger']:
            self.assertTrue(entry['eaip_ident'].startswith('EG'))
            self.assertEqual(entry['ident'], entry['eaip_ident'][2:])
        idents = [entry['ident'] for entry in self.exported['danger']]
        self.assertEqual(len(idents), len(set(idents)))

    def test_section_prefix_agreement_over_all_records(self):
        expected = {'EGD': 'Danger Area', 'EGR': 'Restricted Area',
                    'EGP': 'Prohibited Area'}
        for record in self.records:
            self.assertEqual(record['section'],
                             expected[record['ident'][:3]],
                             record['ident'])

    def test_bad_and_colliding_idents_raise(self):
        boundary = {'points': [{'lat': 1.0, 'lng': 2.0}],
                    'exclusions': [], 'approximate': False}

        def record(ident):
            return {'ident': ident, 'name': 'TEST',
                    'section': 'Danger Area',
                    'limits': {'upper': {'text': '1000 FT ALT'},
                               'lower': {'text': 'SFC'}}}

        with self.assertRaisesRegex(ValueError, 'EG'):
            export_danger([record('XYZ001')], {'XYZ001': boundary})
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            export_danger([record('EGD005A'), record('EGD005A')],
                          {'EGD005A': boundary})


class TestVorRotationZero(unittest.TestCase):

    def test_exported_rotations_are_never_negative_zero(self):
        records = parse_enr41(ENR41.read_text(encoding='utf-8'))
        exported = export_vors(records)
        for entry in exported['vors']:
            if entry['rotation'] == 0:
                self.assertGreater(math.copysign(1, entry['rotation']), 0,
                                   entry['id'])

    def test_declination_zero_gives_positive_zero(self):
        record = {'id': 'ZZZ', 'name': 'TEST', 'type': 'VOR',
                  'components': ['VOR'],
                  'frequency': {'text': '123.450', 'value': 123.45},
                  'location': {'lat': 1.0, 'lng': 2.0},
                  'declination': {'text': '0.0°E', 'value': 0.0},
                  'magnetic_variation': None}
        entry = export_vors([record])['vors'][0]
        self.assertEqual(entry['rotation'], 0.0)
        self.assertGreater(math.copysign(1, entry['rotation']), 0)


class TestFrequencyCheckScript(unittest.TestCase):

    def test_report_lists_ambiguous_entries_only(self):
        from scripts.frequency_check import frequency_report
        text = frequency_report(FIXTURE.read_text(encoding='utf-8'))
        self.assertTrue(text)
        self.assertIn('BRIZE NORTON CTR', text)
        self.assertNotIn('LONDON GATWICK CTA', text)


if __name__ == '__main__':
    unittest.main()

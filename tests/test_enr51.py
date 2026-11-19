import collections
import pathlib
import re
import unittest

from eaip.enr51 import parse_enr51


FIXTURE = pathlib.Path(__file__).parent / 'fixtures' / 'EG-ENR-5.1.html'


def limit(value, uom, code, annotation, text):
    return {
        'value': value,
        'uom': uom,
        'code': code,
        'annotation': annotation,
        'text': text,
    }


class TestParseEnr51(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.records = parse_enr51(FIXTURE.read_text(encoding='utf-8'))
        cls.by_ident = {r['ident']: r for r in cls.records}

    def record(self, ident):
        return self.by_ident[ident]

    def test_record_count(self):
        self.assertEqual(len(self.records), 1307)

    def test_idents_are_unique_and_stripped(self):
        idents = [r['ident'] for r in self.records]
        self.assertEqual(len(idents), len(set(idents)))
        for ident in idents:
            self.assertTrue(ident)
            self.assertEqual(ident, ident.strip())

    def test_section_counts(self):
        # Dividers: Danger Area line 29, Prohibited Area line 5983,
        # Restricted Area line 6018.
        counts = collections.Counter(r['section'] for r in self.records)
        self.assertEqual(counts, {
            'Danger Area': 446,
            'Prohibited Area': 2,
            'Restricted Area': 859,
        })
        self.assertNotIn(None, counts)

    def test_egd001(self):
        # ident 33, limits 37-38, remarks 41
        record = self.record('EGD001')
        self.assertEqual(record['row_id'], '959')
        self.assertEqual(record['name'], 'TREVOSE HEAD')
        self.assertEqual(record['section'], 'Danger Area')
        self.assertEqual(
            record['boundary_text'],
            '501918N 0053042W - 502400N 0053900W - 503200N 0053400W - '
            '503930N 0052400W - 504300N 0051230W - 503830N 0050430W - '
            '501918N 0053042W')
        self.assertEqual(record['limits'], {
            'upper': limit('1000', 'FT', 'ALT', None, '1000 FT ALT'),
            'lower': limit('SFC', None, None, None, 'SFC'),
        })
        self.assertEqual(record['activation'], ['Activated by NOTAM.'])
        self.assertEqual(
            record['remarks'],
            'Activity: Ordnance, Munitions and Explosives.\n\n'
            'Service: SUACS: Culdrose APP on 134.055 when open; at other '
            'times SUAAIS: London Information on 124.750 MHz.\n\n'
            'Contact: Pre-flight information / Booking: Culdrose Operations, '
            'Tel: 01326-552415.\n\n'
            'SUA Authority: DAATM (HQ Navy).\n\n\n'
            'Hours: Activated by NOTAM.')

    def test_egd005b_arc(self):
        # ident 136, boundary 138, limits 140-141, remarks 144, activation 147
        record = self.record('EGD005B')
        self.assertEqual(record['row_id'], '4314')
        self.assertEqual(record['name'], 'PREDANNACK CORRIDOR')
        self.assertEqual(record['section'], 'Danger Area')
        self.assertEqual(
            record['boundary_text'],
            '500208N 0051722W - 495818N 0052242W - 495124N 0051200W - '
            '495629N 0050728W - 495809N 0051024W thence clockwise by the arc '
            'of a circle radius 3 NM centred on 500007N 0051354W to '
            '500208N 0051722W')
        self.assertEqual(record['boundary_text'].count(
            'by the arc of a circle radius'), 1)
        self.assertEqual(record['limits'], {
            'upper': limit('8000', 'FT', 'ALT', None, '8000 FT ALT'),
            'lower': limit('SFC', None, None, None, 'SFC'),
        })
        self.assertEqual(record['activation'], ['Activated by NOTAM.'])
        self.assertEqual(
            record['remarks'],
            'Activity: Unmanned Aircraft System (UAS).\n\n'
            'Service: SUACS: Culdrose APP on 134.055 when open; at other '
            'times SUAAIS: Swanwick Mil via London Information on 124.750 '
            'MHz.\n\n'
            'Contact: Pre-flight information / Booking: Culdrose Operations, '
            'Tel: 01326-552201.\n\n'
            'SUA Authority: DAATM (HQ Navy).\n\n\n'
            'Hours: Activated by NOTAM.')

    def test_egd005a_circle(self):
        # ident 123, circle 124, limits 126-127, remarks 130
        record = self.record('EGD005A')
        self.assertEqual(record['row_id'], '4315')
        self.assertEqual(record['name'], 'PREDANNACK')
        self.assertEqual(record['section'], 'Danger Area')
        self.assertEqual(
            record['boundary_text'],
            'A circle, 3 NM radius, centred at 500007N 0051354W')
        self.assertTrue(record['boundary_text'].startswith('A circle,'))
        self.assertEqual(record['limits'], {
            'upper': limit('8000', 'FT', 'ALT', None, '8000 FT ALT'),
            'lower': limit('SFC', None, None, None, 'SFC'),
        })
        self.assertEqual(record['activation'], ['Activated by NOTAM.'])
        self.assertEqual(
            record['remarks'],
            'Activity: Unmanned Aircraft System (UAS).\n\n'
            'Service: SUACS: Culdrose APP on 134.055 when open; at other '
            'times SUAAIS: Swanwick Mil via London Information on 124.750 '
            'MHz.\n\n'
            'Contact: Pre-flight information / Booking: Culdrose Operations, '
            'Tel: 01326-552201.\n\n'
            'SUA Authority: DAATM (HQ Navy).\n\n\n'
            'Hours: Activated by NOTAM.')

    def test_egd003z1_annotation_limits(self):
        # ident 61, limits 65-66 (annotation only), remarks 69
        record = self.record('EGD003Z1')
        self.assertEqual(record['row_id'], '9854')
        self.assertEqual(record['name'], 'PLYMOUTH FBZ')
        self.assertEqual(record['section'], 'Danger Area')
        self.assertEqual(
            record['boundary_text'],
            '501038N 0034857W - 501055N 0034824W - 501102N 0034743W - '
            '501057N 0034701W - 500414N 0033308W - 500335N 0033252W - '
            '494125N 0034719W - 493658N 0041132W - 501038N 0034857W')
        annotation = limit(None, None, None, 'As Per AUP / UUP',
                           'As Per AUP / UUP')
        self.assertEqual(record['limits'], {
            'upper': annotation,
            'lower': annotation,
        })
        self.assertEqual(record['activation'], [])
        self.assertEqual(record['remarks'],
                         'For IFR flight planning purposes only. 1 NM FPL Buffer.')

    def test_egd714bz1_annotation_upper_sfc_lower(self):
        # ident 5519, upper annotation 5523, lower SFC 5524, remarks 5527
        record = self.record('EGD714BZ1')
        self.assertEqual(record['row_id'], '16947')
        self.assertEqual(record['name'], 'SPACEPORT ONE')
        self.assertEqual(record['section'], 'Danger Area')
        self.assertEqual(
            record['boundary_text'],
            '575033N 0071508W - 575011N 0071338W - 574926N 0071256W - '
            '574842N 0071329W - 573952N 0072040W - 573545N 0072016W - '
            '573517N 0072047W - 573208N 0072936W - 573203N 0073037W - '
            '573217N 0073133W - 573237N 0073201W - 574105N 0073848W - '
            '574129N 0073857W - 574205N 0073842W - 575033N 0071508W')
        self.assertEqual(record['limits'], {
            'upper': limit(None, None, None, 'As Per AUP / UUP',
                           'As Per AUP / UUP'),
            'lower': limit('SFC', None, None, None, 'SFC'),
        })
        self.assertEqual(record['activation'], [])
        self.assertEqual(record['remarks'],
                         'For IFR flight planning purposes only.')

    def test_egr157_five_arcs(self):
        # ident 6155, boundary 6157 (all five arcs), limits 6159-6160, remarks 6163
        record = self.record('EGR157')
        self.assertEqual(record['row_id'], '1245')
        self.assertEqual(record['name'], 'HYDE PARK')
        self.assertEqual(record['section'], 'Restricted Area')
        self.assertEqual(record['boundary_text'].count(
            'by the arc of a circle radius'), 5)
        self.assertTrue(record['boundary_text'].startswith('513212N 0000911W'))
        self.assertTrue(record['boundary_text'].endswith(
            '513151N 0000952W to 513212N 0000911W'))
        self.assertEqual(record['limits'], {
            'upper': limit('1400', 'FT', 'ALT', None, '1400 FT ALT'),
            'lower': limit('SFC', None, None, None, 'SFC'),
        })
        self.assertEqual(record['activation'], [])
        self.assertEqual(
            record['remarks'],
            'Flight permitted by:\n'
            'any aircraft in the service of the Chief Officer of Police for '
            'the Metropolitan Police District;\n'
            'any aircraft flying in accordance with a Special Flight '
            'Notification issued by the appropriate ATC unit;\n'
            'any helicopter flying on Helicopter Route H4;\n'
            'any aircraft flying in accordance with an Enhanced '
            'Non-Standard Flight clearance issued by the appropriate ATC '
            'unit.\n\n'
            'See also ENR 1.1, paragraph 4.1.6.\n\n'
            'SI 1300/2017\n\n'
            'Contact: www.nats.co.uk/nsf')

    def test_upper_limit_agl(self):
        # EGR1U001A ident 6580, upper limit 6583
        record = self.record('EGR1U001A')
        self.assertEqual(record['limits']['upper'],
                         limit('2000', 'FT', 'AGL', None, '2000 FT AGL'))
        self.assertEqual(record['limits']['upper']['code'], 'AGL')

    def test_circle_and_latitude_counts(self):
        self.assertEqual(sum(r['boundary_text'].startswith('A circle,')
                             for r in self.records), 211)
        non_nm = re.compile(r'A circle, \d+(?:\.\d+)? (?:M|FT) radius')
        self.assertEqual(sum(bool(non_nm.search(r['boundary_text']))
                             for r in self.records), 7)
        self.assertEqual(sum('following the line of latitude' in r['boundary_text']
                             for r in self.records), 147)

    def test_egd012_keeps_coastline_phrase(self):
        # ident 583, boundary 585
        record = self.record('EGD012')
        self.assertIn('then along the coastline to', record['boundary_text'])
        self.assertTrue(record['boundary_text'].endswith(
            'then along the coastline to 504220N 0024500W'))

    def test_egr160_keeps_thames_exclusion(self):
        # ident 6191, "Excluding ..." sentence 6195
        record = self.record('EGR160')
        thames = ('Excluding so much of the bed of the River Thames as lies '
                  'within that area between the ordinary high water marks on '
                  'each of its banks.')
        self.assertTrue(record['boundary_text'].endswith(thames))


if __name__ == '__main__':
    unittest.main()

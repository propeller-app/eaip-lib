import datetime
import pathlib
import unittest

import eaip


FIXTURE = pathlib.Path(__file__).parent / 'fixtures' / 'EG-AD-2.EGKR.html'
EAIP_DATE = datetime.datetime(2026, 1, 22)


class TestAirfieldFromRawHtml(unittest.TestCase):
    """
    Parses a saved AD-2 page for EGKR (Redhill).

    Offline only: ``get_airfield_from_raw_html`` never opens a client.
    """

    @classmethod
    def setUpClass(cls):
        html = FIXTURE.read_text(encoding='utf-8')
        cls.airfield = eaip.get_airfield_from_raw_html(html, EAIP_DATE)

    def test_icao(self):
        self.assertEqual(self.airfield.icao, 'EGKR')

    def test_name(self):
        self.assertEqual(self.airfield.name, 'Redhill')

    def test_geog(self):
        # WGS84 decimal degrees; 511249N 0000819W in the fixture.
        latitude, longitude = self.airfield.geog
        self.assertAlmostEqual(latitude, 51.213611, delta=0.01)
        self.assertAlmostEqual(longitude, -0.138611, delta=0.01)

    def test_runways(self):
        self.assertGreaterEqual(len(self.airfield.runways), 1)

    def test_radios(self):
        self.assertGreaterEqual(len(self.airfield.radios), 1)


if __name__ == '__main__':
    unittest.main()

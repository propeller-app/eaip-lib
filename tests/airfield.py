import unittest
import asyncio
import eaip


class TestAirfield(unittest.TestCase):

    def test_airfield_icao(self):
        a = asyncio.run(eaip.get_airfield('EGKR'))
        self.assertEqual(a.icao, 'EGKR')


if __name__ == '__main__':
    unittest.main()

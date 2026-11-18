import datetime
import unittest

import eaip


# Known 2026 AIRAC effective dates (Thursdays, 28-day cycles).
AIRAC_SEQUENCE_2026 = [
    datetime.date(2026, 1, 22),
    datetime.date(2026, 2, 19),
    datetime.date(2026, 3, 19),
    datetime.date(2026, 4, 16),
    datetime.date(2026, 5, 14),
    datetime.date(2026, 6, 11),
    datetime.date(2026, 7, 9),
    datetime.date(2026, 8, 6),
    datetime.date(2026, 9, 3),
    datetime.date(2026, 10, 1),
    datetime.date(2026, 10, 29),
    datetime.date(2026, 11, 26),
    datetime.date(2026, 12, 24),
]

EPOCH = datetime.date(2026, 10, 29)


def at_midnight(*args) -> datetime.datetime:
    return datetime.datetime(*args)


class TestAiracEffectiveDate(unittest.TestCase):

    def test_epoch_is_effective(self):
        self.assertEqual(eaip.airac_effective_date(EPOCH), at_midnight(2026, 10, 29))

    def test_epoch_next(self):
        self.assertEqual(eaip.next_airac_date(EPOCH), at_midnight(2026, 11, 26))

    def test_day_before_cycle_start(self):
        self.assertEqual(eaip.airac_effective_date(datetime.date(2026, 10, 28)),
                         at_midnight(2026, 10, 1))

    def test_day_after_cycle_start(self):
        self.assertEqual(eaip.airac_effective_date(datetime.date(2026, 10, 30)),
                         at_midnight(2026, 10, 29))

    def test_2026_sequence_effective(self):
        for day in AIRAC_SEQUENCE_2026:
            with self.subTest(day=day):
                self.assertEqual(eaip.airac_effective_date(day),
                                 at_midnight(day.year, day.month, day.day))

    def test_2026_sequence_next(self):
        for day, following in zip(AIRAC_SEQUENCE_2026, AIRAC_SEQUENCE_2026[1:]):
            with self.subTest(day=day):
                self.assertEqual(eaip.next_airac_date(day),
                                 at_midnight(following.year, following.month, following.day))

    def test_across_year_boundary(self):
        self.assertEqual(eaip.next_airac_date(datetime.date(2026, 12, 24)),
                         at_midnight(2027, 1, 21))
        self.assertEqual(eaip.airac_effective_date(datetime.date(2027, 1, 20)),
                         at_midnight(2026, 12, 24))

    def test_before_epoch(self):
        # 2026-01-22 is itself an AIRAC date, ten cycles before the epoch.
        self.assertEqual(eaip.airac_effective_date(datetime.date(2026, 1, 22)),
                         at_midnight(2026, 1, 22))
        self.assertEqual(eaip.next_airac_date(datetime.date(2026, 1, 22)),
                         at_midnight(2026, 2, 19))
        # Day before that: the previous cycle, still before the epoch.
        self.assertEqual(eaip.airac_effective_date(datetime.date(2026, 1, 21)),
                         at_midnight(2025, 12, 25))
        self.assertEqual(eaip.next_airac_date(datetime.date(2026, 1, 21)),
                         at_midnight(2026, 1, 22))

    def test_date_and_datetime_inputs_agree(self):
        for day in AIRAC_SEQUENCE_2026:
            as_datetime = at_midnight(day.year, day.month, day.day)
            with self.subTest(day=day):
                self.assertEqual(eaip.airac_effective_date(day),
                                 eaip.airac_effective_date(as_datetime))
                self.assertEqual(eaip.next_airac_date(day),
                                 eaip.next_airac_date(as_datetime))

    def test_returns_naive_midnight_datetime(self):
        for func in (eaip.airac_effective_date, eaip.next_airac_date):
            with self.subTest(func=func.__name__):
                result = func(datetime.date(2026, 10, 30))
                self.assertIsInstance(result, datetime.datetime)
                self.assertIsNone(result.tzinfo)
                self.assertEqual(result.time(), datetime.time(0, 0))


if __name__ == '__main__':
    unittest.main()

import unittest
from datetime import date

from media_digest.workday import is_china_workday, main


class WorkdayTest(unittest.TestCase):
    def test_regular_weekday_is_workday(self):
        self.assertTrue(is_china_workday(date(2026, 7, 2)))

    def test_national_day_holiday_is_not_workday(self):
        self.assertFalse(is_china_workday(date(2026, 10, 2)))

    def test_adjusted_sunday_is_workday(self):
        self.assertTrue(is_china_workday(date(2026, 9, 20)))

    def test_non_workday_returns_skip_status(self):
        self.assertEqual(main(["--date", "2026-10-02"]), 3)

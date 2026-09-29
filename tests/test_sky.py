# SPDX-License-Identifier: GPL-3.0-or-later
"""Android's SkyGeometryTest, case for case (model/sky.py)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))

from meshsat.model import sky  # noqa: E402


def a_pass(aos: int, los: int, peak: float) -> dict:
    return {"satellite": "IRIDIUM 122", "aos": aos, "los": los, "peak_elev_deg": peak}


class SkyGeometryTest(unittest.TestCase):
    def test_an_80_degree_pass_peaks_at_80_degrees(self):
        x1, mid, x2, peak_y = sky.triangle(a_pass(1000, 1600, 80.0), 0, 3600, left=0, width=3600, bottom=900, height=900)
        self.assertAlmostEqual(peak_y, 900 - 800, places=3)
        self.assertAlmostEqual(mid, 1300, places=3)

    def test_a_pass_off_the_chart_is_clipped_then_centred(self):
        x1, mid, x2, _ = sky.triangle(a_pass(-300, 300, 45.0), 0, 3600, left=10, width=3600, bottom=90, height=90)
        self.assertEqual((round(x1, 3), round(x2, 3), round(mid, 3)), (10, 310, 160))

    def test_signal_colours_follow_the_bridge(self):
        self.assertEqual([sky.signal_colour(b) for b in (5, 3, 2, 1, 0)], ["#10B981", "#10B981", "#F59E0B", "#F59E0B", "#EF4444"])
        self.assertEqual(sky.signal_colour(2.5), "#10B981")  # Kotlin's round(2.5) is 3

    def test_bars_and_degrees_share_the_plot(self):
        self.assertAlmostEqual(sky.bars_y(0, 100, 50), 100)
        self.assertAlmostEqual(sky.bars_y(5, 100, 50), 50)
        self.assertAlmostEqual(sky.elev_y(90.0, 100, 50), 50)

    def test_labels_fall_on_whole_hours(self):
        self.assertEqual(sky.ticks(1800, 9000, 3600), [3600, 7200])

    def test_only_passes_that_touch_the_window(self):
        self.assertTrue(sky.overlaps(a_pass(900, 1500, 30.0), 1000, 2000))
        self.assertFalse(sky.overlaps(a_pass(100, 900, 30.0), 1000, 2000))
        self.assertFalse(sky.overlaps(a_pass(2000, 2600, 30.0), 1000, 2000))

    def test_readings_are_averaged_to_what_the_width_can_show(self):
        raw = [{"at": i * 60, "bars": 0 if i % 2 == 0 else 5} for i in range(720)]
        step = sky.step_for(12 * 3600, width=900, min_gap=9)
        self.assertEqual(step, 432)
        avg = sky.averaged(raw, step)
        self.assertTrue(90 <= len(avg) <= 110, len(avg))
        self.assertTrue(all(2 <= v <= 3 for _, v in avg))

    def test_at_a_minute_a_step_nothing_is_averaged(self):
        self.assertEqual(sky.averaged([{"at": 120, "bars": 3}, {"at": 60, "bars": 1}], 60), [(60, 1.0), (120, 3.0)])

    def test_the_home_card_shows_with_something_to_draw(self):
        now = 100_000
        self.assertFalse(sky.card_shown([], [], now))
        self.assertTrue(sky.card_shown([], [{"at": now - 3 * 3600 + 5, "bars": 2}], now))
        self.assertFalse(sky.card_shown([a_pass(now + 4 * 3600, now + 4 * 3600 + 600, 50)], [{"at": now - 4 * 3600, "bars": 2}], now))
        self.assertTrue(sky.card_shown([a_pass(now + 2 * 3600, now + 2 * 3600 + 600, 50)], [], now))


if __name__ == "__main__":
    unittest.main()

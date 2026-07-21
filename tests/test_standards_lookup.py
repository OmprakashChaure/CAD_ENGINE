import unittest
from utils.standards_lookup import StandardsLookup


class TestStandardsLookup(unittest.TestCase):
    def setUp(self):
        self.lookup = StandardsLookup()

    def test_metric_coarse_pitch(self):
        # M12 Coarse is 1.75
        self.assertEqual(self.lookup.get_metric_coarse_pitch(12.0), 1.75)
        # M10 Coarse is 1.5
        self.assertEqual(self.lookup.get_metric_coarse_pitch(10.0), 1.5)
        # M8 Coarse is 1.25
        self.assertEqual(self.lookup.get_metric_coarse_pitch(8.0), 1.25)
        # Invalid Metric Size
        self.assertIsNone(self.lookup.get_metric_coarse_pitch(999.0))

    def test_metric_fine_pitch(self):
        # M10 Fine is 1.25
        self.assertEqual(self.lookup.get_metric_fine_pitch(10.0), 1.25)
        # M24 Fine is 2.0
        self.assertEqual(self.lookup.get_metric_fine_pitch(24.0), 2.0)
        # Invalid Fine Size
        self.assertIsNone(self.lookup.get_metric_fine_pitch(999.0))

    def test_unified_unc_tpi(self):
        self.assertEqual(self.lookup.get_unc_tpi("1/2"), 13)
        self.assertEqual(self.lookup.get_unc_tpi("1/4"), 20)
        self.assertIsNone(self.lookup.get_unc_tpi("99/99"))

    def test_unified_unf_tpi(self):
        self.assertEqual(self.lookup.get_unf_tpi("1/2"), 20)
        self.assertEqual(self.lookup.get_unf_tpi("1/4"), 28)
        self.assertIsNone(self.lookup.get_unf_tpi("99/99"))

    def test_bsp_parallel_g(self):
        g_1_4 = self.lookup.get_bsp_parallel_g("1/4")
        self.assertIsNotNone(g_1_4)
        self.assertEqual(g_1_4["major_diameter"], 13.157)
        self.assertEqual(g_1_4["pitch_tpi"], 19)
        self.assertIsNone(self.lookup.get_bsp_parallel_g("99/99"))

    def test_npt_taper(self):
        npt_1_2 = self.lookup.get_npt_taper("1/2")
        self.assertIsNotNone(npt_1_2)
        self.assertEqual(npt_1_2["major_diameter"], 21.336)
        self.assertEqual(npt_1_2["pitch_tpi"], 14)
        self.assertEqual(npt_1_2["taper"], 0.0625)
        self.assertIsNone(self.lookup.get_npt_taper("99/99"))

    def test_fit_deviation(self):
        # 50 H7 -> upper = +25 microns (0.025 mm), lower = 0 mm
        dev_50_h7 = self.lookup.get_fit_deviation("H7", 50.0)
        self.assertIsNotNone(dev_50_h7)
        self.assertAlmostEqual(dev_50_h7[0], 0.0, places=6)
        self.assertAlmostEqual(dev_50_h7[1], 0.025, places=6)

        # 50 h7 -> upper = 0 mm, lower = -25 microns (-0.025 mm)
        dev_50_h7_shaft = self.lookup.get_fit_deviation("h7", 50.0)
        self.assertIsNotNone(dev_50_h7_shaft)
        self.assertAlmostEqual(dev_50_h7_shaft[0], -0.025, places=6)
        self.assertAlmostEqual(dev_50_h7_shaft[1], 0.0, places=6)

        # 50 G6 -> upper = -9 microns (-0.009 mm), lower = -25 microns (-0.025 mm)
        dev_50_g6 = self.lookup.get_fit_deviation("G6", 50.0)
        self.assertIsNotNone(dev_50_g6)
        self.assertAlmostEqual(dev_50_g6[0], -0.025, places=6)
        self.assertAlmostEqual(dev_50_g6[1], -0.009, places=6)

        # Invalid fit class
        self.assertIsNone(self.lookup.get_fit_deviation("INVALID_CLASS", 50.0))


if __name__ == "__main__":
    unittest.main()

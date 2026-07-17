import unittest

from pipeline.split_policy import TEST_RATIO, TRAIN_RATIO, VAL_RATIO


class TestSplitPolicy(unittest.TestCase):
    def test_frozen_split_ratios_sum_to_one(self):
        self.assertEqual(TRAIN_RATIO, 0.70)
        self.assertEqual(VAL_RATIO, 0.15)
        self.assertEqual(TEST_RATIO, 0.15)
        self.assertEqual(TRAIN_RATIO + VAL_RATIO + TEST_RATIO, 1.0)


if __name__ == "__main__":
    unittest.main()

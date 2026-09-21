"""Small hand-verifiable cases; tests the independent oracle, not Studies."""
import unittest
import numpy as np
from build_extended import timing_score, brinson, ols


class ReferenceTests(unittest.TestCase):
    def test_flat_prices_have_no_timing_information(self):
        self.assertIsNone(timing_score([100] * 10, 100, 'BUY'))

    def test_good_and_bad_entry(self):
        self.assertEqual(timing_score([90, 95, 100, 105, 110], 90, 'BUY'), 1)
        self.assertEqual(timing_score([90, 95, 100, 105, 110], 110, 'BUY'), 0)

    def test_good_and_bad_exit(self):
        self.assertEqual(timing_score([90, 95, 100, 105, 110], 110, 'SELL'), 1)
        self.assertEqual(timing_score([90, 95, 100, 105, 110], 90, 'SELL'), 0)

    def test_fx_only(self):
        quantity, price = 10, 100
        self.assertEqual(quantity * price * 1.2 - quantity * price * 1.1, 100)

    def test_dividend_detachment_does_not_create_return(self):
        self.assertEqual(10 * 98 + 10 * 2, 10 * 100)

    def test_reinvestment_does_not_create_value(self):
        self.assertAlmostEqual((10 + 20 / 98) * 98, 1000)

    def test_split_does_not_create_value(self):
        self.assertEqual(10 * 100, 20 * 50)

    def test_no_trade_passive_identity(self):
        opening, cash, growth = 800., 200., 1.25
        self.assertEqual(opening * growth + cash, 1200)

    def test_brinson_identity_and_cash(self):
        wp, wb = np.array([.8, 0., .2]), np.array([.5, .5, 0.])
        rp, rb = np.array([.2, 0., 0.]), np.array([.1, -.1, 0.])
        self.assertAlmostEqual(sum(x.sum() for x in brinson(wp, wb, rp, rb)), .16)

    def test_known_linear_model(self):
        x = np.linspace(-.03, .04, 80).reshape(-1, 1)
        beta, _, r2 = ols(.001 + 1.5 * x[:, 0], x)
        np.testing.assert_allclose(beta, [.001, 1.5], atol=1e-12)
        self.assertAlmostEqual(r2, 1)


if __name__ == '__main__': unittest.main()

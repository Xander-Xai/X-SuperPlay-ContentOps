"""Regression tests for the reproducible CPU-only causal masking lesson."""
import unittest

from causal_attention import attention


class CausalAttentionTests(unittest.TestCase):
    def test_first_output_equals_first_value_in_causal_mode(self):
        self.assertEqual(attention([1.0, 2.0, 3.0], causal=True)[0], 1.0)

    def test_future_token_does_not_change_prefix(self):
        base = attention([1.0, 2.0, 3.0], causal=True)
        altered = attention([1.0, 2.0, 30.0], causal=True)
        self.assertEqual(base[:2], altered[:2])

    def test_unmasked_attention_has_future_leakage(self):
        base = attention([1.0, 2.0, 3.0], causal=False)
        altered = attention([1.0, 2.0, 30.0], causal=False)
        self.assertGreater(abs(base[0] - altered[0]), 1.0)

    def test_empty_input_rejected(self):
        with self.assertRaisesRegex(ValueError, "must not be empty"):
            attention([], causal=True)

    def test_nonnumeric_rejected(self):
        with self.assertRaisesRegex(TypeError, "must contain numbers"):
            attention([1, "bad"], causal=False)


if __name__ == "__main__":
    unittest.main()

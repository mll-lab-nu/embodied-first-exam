"""Tests for the gateway's structured token-budget stop record (gateway.tally, totals.json "budget_stop"; issue #229).

    python3 scripts/usage_gateway/tests/test_budget_stop.py     # stdlib only
"""
from __future__ import annotations

import pathlib
import sys
import types
import unittest

HERE = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import gateway  # noqa: E402


class BudgetStop(unittest.TestCase):
    def setUp(self):
        self.saved = getattr(gateway, "ARGS", None)
        gateway.ARGS = types.SimpleNamespace(budget_input=100, budget_output=10)

    def tearDown(self):
        gateway.ARGS = self.saved

    def test_first_refusal_writes_the_stop_record(self):
        tot = {"requests": 0, "input": 120, "cached": 110, "output": 3, "no_usage": 0}
        gateway.tally(tot, {"ts": 5.0, "refused": "over_token_budget"})
        gateway.tally(tot, {"ts": 7.0, "refused": "over_token_budget"})
        bs = tot["budget_stop"]
        self.assertEqual(bs["limit"], "input")
        self.assertEqual((bs["first_refused_at"], bs["last_refused_at"], bs["refused"]), (5.0, 7.0, 2))
        self.assertEqual((bs["input"], bs["cached"], bs["output"]), (120, 110, 3))
        self.assertEqual(tot["refused"], 2)              # the old counter still counts budget refusals

    def test_output_limit(self):
        tot = {"requests": 0, "input": 50, "cached": 0, "output": 11, "no_usage": 0}
        gateway.tally(tot, {"ts": 1.0, "refused": "over_token_budget"})
        self.assertEqual(tot["budget_stop"]["limit"], "output")

    def test_other_refusals_write_no_stop_record(self):
        tot = {"requests": 0, "input": 0, "cached": 0, "output": 0, "no_usage": 0}
        gateway.tally(tot, {"ts": 1.0, "refused": "path_not_allowed"})
        self.assertNotIn("budget_stop", tot)


if __name__ == "__main__":
    unittest.main()

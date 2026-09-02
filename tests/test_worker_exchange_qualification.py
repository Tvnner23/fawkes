import unittest

from src.runtime.worker_exchange_qualification import run_generated_campaign


class WorkerExchangeGeneratedQualificationTests(unittest.TestCase):
    def test_fixed_generated_campaign_passes_every_hard_case_deterministically(self):
        result=run_generated_campaign(128)
        self.assertTrue(result["passed"])
        self.assertEqual(result["hard_failures"],0)
        self.assertEqual(result["case_count"],128)
        self.assertEqual(result["hard_assertion_count"],896)
        self.assertTrue(result["deterministic_reproduction"])
        self.assertFalse(result["manual_transfer_retirement_eligible"])


if __name__ == "__main__": unittest.main()

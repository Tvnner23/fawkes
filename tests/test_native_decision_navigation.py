"""Focused display navigation regression; no live permission or model trial."""
from pathlib import Path
import subprocess
import unittest

class NativeDecisionNavigationTests(unittest.TestCase):
    def test_real_frontend_navigation_contract(self):
        root=Path(__file__).resolve().parents[1]
        result=subprocess.run(['node','tests/js/native_decision_navigation_harness.js'],cwd=root,text=True,capture_output=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('native-decision-navigation-ok',result.stdout)

    def test_attention_launcher_emits_explicit_reveal_after_navigation(self):
        root=Path(__file__).resolve().parents[1]
        result=subprocess.run(['node','tests/js/pi_attention_harness.js'],cwd=root,text=True,capture_output=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('native-launcher-reveal-ok',result.stdout)

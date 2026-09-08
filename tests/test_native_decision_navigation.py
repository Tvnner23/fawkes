"""Focused display navigation regression; no live permission or model trial."""
from pathlib import Path
import subprocess
import unittest
from html.parser import HTMLParser

class NativeDecisionNavigationTests(unittest.TestCase):
    def test_modal_initial_focus_contains_actual_console_keyboard_navigation(self):
        root=Path(__file__).resolve().parents[1]
        result=subprocess.run(['node','tests/js/native_decision_navigation_harness.js','--keyboard'],cwd=root,text=True,capture_output=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('native-dialog-keyboard-owner-ok',result.stdout)

    def test_single_modal_owner_remains_inside_touch_guard(self):
        class Elements(HTMLParser):
            def __init__(self):
                super().__init__(); self.stack=[]; self.paths={}
            def handle_starttag(self,tag,attrs):
                attrs=dict(attrs); identity=attrs.get('id')
                if identity:
                    self.paths.setdefault(identity,[]).append(tuple(self.stack))
                if tag not in {'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}:
                    self.stack.append(identity or tag)
            def handle_endtag(self,tag):
                if self.stack:self.stack.pop()
        root=Path(__file__).resolve().parents[1]
        parsed=Elements();parsed.feed((root/'src/app/static/dev-console/index.html').read_text())
        for name in ('worker-native-cards','worker-native-status','worker-native-result','worker-native-history-items'):
            self.assertEqual(len(parsed.paths[name]),1,name)
            self.assertIn('worker-native-dialog',parsed.paths[name][0])
            self.assertNotIn('worker-reading',parsed.paths[name][0])
            self.assertIn('dev-console',parsed.paths[name][0])
        self.assertIn('worker-native-close',parsed.paths)
        self.assertIn('worker-native-open',parsed.paths)

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

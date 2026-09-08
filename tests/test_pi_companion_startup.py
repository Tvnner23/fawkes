"""Exact companion expressions; no Pi, credentials, browser owner or provider."""
import ast
import json
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'deploy/pi_console_supervisor.py'
CONTEXT = 'ACCEPTED:candidate-snapshot-' + 'f' * 64


def expressions(source=SOURCE, origin='http://127.0.0.1:8791', context=CONTEXT):
    names = {'CONSOLE_READY', 'SUMMARY_CONTROL', 'SUMMARY',
             'CONTROLS_READY', 'RESTORE_CONTROLS'}
    tree = ast.parse(source.read_text())
    assignments = [n for n in tree.body if isinstance(n, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id in names for t in n.targets)]
    scope = {'json': json, 'ORIGIN_JS': json.dumps(origin),
             'accepted_context': lambda: context}
    exec(compile(ast.Module(body=assignments, type_ignores=[]),
                 str(source), 'exec'), scope)
    return {k: scope[k] for k in names if k in scope}


class CompanionStartupTests(unittest.TestCase):
    def run_case(self, case):
        data = {'expressions': expressions(), 'case': case, 'context': CONTEXT}
        run = subprocess.run(['node', 'tests/js/pi_companion_startup_harness.js'],
                             cwd=ROOT, input=json.dumps(data), text=True,
                             capture_output=True, timeout=10)
        self.assertEqual(run.returncode, 0, run.stderr)
        return json.loads(run.stdout)

    def test_nested_briefing_label_reproduces_old_lookup_failure(self):
        r = self.run_case('decorated')
        self.assertFalse(r['old_text_found'])
        self.assertTrue(r['startup'])
        self.assertEqual((r['page'], r['clicks']), ('0', 1))

    def test_legacy_simple_summary_still_works(self):
        r = self.run_case('legacy')
        self.assertTrue(r['old_text_found'])
        self.assertTrue(r['startup'])

    def test_label_can_change_without_changing_page_identity(self):
        self.assertTrue(self.run_case('translated')['startup'])

    def test_missing_page0_control_is_rejected(self):
        self.assertFalse(self.run_case('missing_control')['startup'])

    def test_duplicate_page0_control_is_rejected(self):
        self.assertFalse(self.run_case('duplicate_control')['startup'])

    def test_missing_or_duplicate_summary_section_is_rejected(self):
        for case in ('missing_page', 'duplicate_page'):
            with self.subTest(case=case):
                self.assertFalse(self.run_case(case)['startup'])

    def test_disabled_control_is_rejected(self):
        r = self.run_case('disabled')
        self.assertFalse(r['startup'])
        self.assertEqual(r['clicks'], 0)

    def test_aria_disabled_control_is_rejected(self):
        self.assertFalse(self.run_case('aria_disabled')['startup'])

    def test_wrong_origin_or_path_is_rejected(self):
        for case in ('wrong_origin', 'wrong_path'):
            with self.subTest(case=case):
                r = self.run_case(case)
                self.assertFalse(r['startup'])
                self.assertEqual(r['clicks'], 0)

    def test_wrong_accepted_binding_is_rejected(self):
        self.assertFalse(self.run_case('wrong_context')['startup'])

    def test_missing_live_projection_is_rejected(self):
        self.assertFalse(self.run_case('not_live')['startup'])

    def test_click_without_visible_summary_is_not_ready(self):
        for case in ('navigation_noop', 'hidden_page', 'wrong_aria'):
            with self.subTest(case=case):
                r = self.run_case(case)
                self.assertFalse(r['startup'])
                self.assertIsNone(r['config'])

    def test_restore_keeps_worker_page_focus_and_scroll(self):
        r = self.run_case('restore')
        self.assertTrue(r['restored'])
        self.assertEqual((r['page'], r['clicks'], r['focus'], r['scroll']),
                         ('4', 0, 'reply-composer', 173))

    def test_restoration_rejects_missing_or_ambiguous_controls(self):
        for case in ('restore_missing', 'restore_duplicate', 'restore_wrong_origin'):
            with self.subTest(case=case):
                r = self.run_case(case)
                self.assertFalse(r['restored'])
                self.assertEqual(r['clicks'], 0)

    def test_same_selector_preserves_matrix_contract(self):
        r = self.run_case('decorated')
        self.assertEqual(r['config'], {'idleMs': 120000,
                         'emulatedPointerScroll': True,
                         'summarySelector': '#dev-console button[data-page-target="0"]'})

    def test_controls_ready_requires_existing_matrix_and_scroll_configuration(self):
        r = self.run_case('decorated')
        self.assertFalse(r['controls_before_matrix'])
        self.assertTrue(r['controls_after_matrix'])


if __name__ == '__main__':
    unittest.main()

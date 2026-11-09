"""The policy verifier: which files it takes, what only the submission file may be, and how the intake's three outcomes become the result `./forshor check` reads.
The intake itself (Lean, the mirror, ForShor) is stubbed: it is tested in evaluation/export_v2/pytests/test_intake_v2.py and was run for real on both boards."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).parent))
import policy_verifier as pv  # noqa: E402

PP = "import ForShor.X\nnamespace PolicySubmission\ndef policy := 1\nend PolicySubmission\n"
PTP = "import ForShor.X\nnamespace PTPPolicySubmission\ndef policy := 1\nend PTPPolicySubmission\n"
OLD = "import TableGeneration.Policy\nnamespace TableGeneration.Submission.Policy\ndef implementation := 1\nend TableGeneration.Submission.Policy\n"


def stub(tmp: Path, outcome: dict) -> list:
    """A command that stands in for evaluation/intake_v2.py: writes `outcome` where --out says and a verification where --verification-out says."""
    script = tmp / "stub_intake.py"
    script.write_text("import json, sys\n"
                      "a = sys.argv\n"
                      f"o = {outcome!r}\n"
                      "open(a[a.index('--out') + 1], 'w').write(json.dumps(o))\n"
                      "if o.get('verified'):\n"
                      "    open(a[a.index('--verification-out') + 1], 'w').write('{}')\n"
                      "open('args.json', 'w').write(json.dumps(a))\n"
                      "sys.exit(0 if o.get('verified') else 1)\n")
    return [sys.executable, str(script)]


class PolicyVerifier(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.tmp = Path(self.t.name)
        self.repo = self.tmp / "repo"
        (self.repo / "TableGeneration/Submission").mkdir(parents=True)
        self.out = self.tmp / "out"
        (self.tmp / "forshor").mkdir()

    def tearDown(self):
        self.t.cleanup()

    def write(self, text):
        (self.repo / pv.SUBMISSION).write_text(text)

    def run_pv(self, outcome=None, files=None, ok=True, env=None, preflight=False):
        changed = lambda repo: (ok, [pv.SUBMISSION] if files is None else files, "Compared base...head.")
        env = {"FORSHOR_TREE": str(self.tmp / "forshor")} if env is None else env
        code = pv.run(self.repo, self.out, get_changed_files=changed, env=env, intake=stub(self.tmp, outcome or {"verified": True, "policy": {"digest": "a" * 64, "mode": "PhaseProduct", "bands": 1, "forshorPolicy": True}}), preflight=preflight)
        return code, json.loads((self.out / "table-generation-submission-result.json").read_text())

    def test_the_two_policy_namespaces_are_this_verifiers_and_the_older_file_is_not(self):
        for text, expected in ((PP, True), (PTP, True), (OLD, False), ("def x := 1\n", False)):
            self.write(text)
            self.assertEqual(pv.applies(self.repo), expected, text[:40])
        self.assertFalse(pv.applies(self.tmp / "nowhere"))

    def test_a_verified_policy_is_a_successful_full_result_with_its_verification(self):
        self.write(PP)
        code, result = self.run_pv()
        self.assertEqual((code, result["status"], result["phase"], result["kind"]), (0, "success", "full", "policy"))
        self.assertEqual(result["verification"], "verification.json")
        self.assertTrue((self.out / "verification.json").exists() and (self.out / "table-generation-summary.md").exists())
        args = json.loads((self.tmp / "repo" / "args.json").read_text())
        self.assertIn("--no-publish", args)
        self.assertEqual(args[args.index("--lean-policy") + 1], str(self.repo.resolve() / pv.SUBMISSION))
        self.assertEqual(args[args.index("--tree") + 1], str(self.repo.resolve()), "the STO tree defaults to the repository")
        self.assertNotIn("--publisher-url", args, "the verifier never publishes and needs no publisher")

    def test_a_refusal_names_its_stage_and_a_failed_run_is_not_called_a_verdict(self):
        self.write(PP)
        code, result = self.run_pv({"refused": True, "stage": "lexical", "reason": "ForShor's lexical gate refused the file"})
        self.assertEqual((code, result["status"]), (1, "failure"))
        self.assertEqual(result["checks"][-1]["name"], "lexical")
        self.assertIsNone(result["verification"])
        code, result = self.run_pv({"failed": True, "error": "OSError: no space left"})
        self.assertEqual(code, 1)
        self.assertIn("not a verdict", result["checks"][-1]["details"])

    def test_only_the_submission_file_may_change(self):
        self.write(PP)
        for extra in ("TableGeneration/Submission/Policy/Helper.lean", "lakefile.lean", "README.md"):
            code, result = self.run_pv(files=[pv.SUBMISSION, extra])
            self.assertEqual(code, 1, extra)
            self.assertIn(extra, result["checks"][0]["details"])
        code, _ = self.run_pv(files=[])
        self.assertEqual(code, 0, "no file list (a local run with no base) is the comparison skipped, said so, not a failure here")
        code, result = self.run_pv(ok=False)
        self.assertEqual(code, 1)
        self.assertEqual(result["checks"][0]["status"], "failure")

    def test_the_trusted_environment_must_be_prepared(self):
        self.write(PP)
        code, result = self.run_pv(env={})
        self.assertEqual(code, 1)
        self.assertEqual(result["checks"][-1]["name"], "trees")

    def test_result_is_bound_to_the_pr_head_and_exact_hosted_attempt(self):
        self.write(PP)
        env = {"FORSHOR_TREE": str(self.tmp / "forshor"), "GITHUB_REPOSITORY": "zapatacomputing/forshor-submissions",
               "GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "2", "TABLE_GEN_PR_NUMBER": "12", "TABLE_GEN_HEAD_SHA": "a" * 40}
        code, result = self.run_pv(env=env)
        self.assertEqual(code, 0)
        self.assertEqual(result["metadata"]["head_sha"], "a" * 40)
        self.assertEqual(result["metadata"]["run_id"], "123")
        self.assertEqual(result["metadata"]["run_attempt"], "2")
        self.assertEqual(result["metadata"]["pr_number"], "12")

    def test_the_older_syntax_gate_steps_aside_for_a_policy_file_and_only_for_that(self):
        """CI runs the older syntax-gate script before the verifier, in the submission's directory; it must not fail a policy submission."""
        import subprocess
        script = Path(__file__).parent / "test_submission_syntax_gate.py"
        self.write(PP)
        done = subprocess.run([sys.executable, str(script)], cwd=self.repo, capture_output=True, text=True, timeout=120)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("not applicable to a policy submission", done.stdout)

    def test_the_preflight_checks_the_files_and_runs_no_lean(self):
        self.write(PP)
        code, result = self.run_pv(env={}, preflight=True)
        self.assertEqual((code, result["phase"]), (0, "preflight"))
        self.assertFalse((self.tmp / "repo" / "args.json").exists(), "nothing was run")
        code, _ = self.run_pv(files=[pv.SUBMISSION, "x"], env={}, preflight=True)
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()

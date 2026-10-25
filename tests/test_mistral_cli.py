"""Subprocess contracts for Mistral STT; no SDK, credentials or network."""
import os
from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "STT/mistral_stt.py"
RUNNER = Path(__file__).with_name("_mistral_cli_runner.py")


class MistralCliTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.source = self.work / "한글 음성.mp3"
        self.source.write_bytes(b"sample-audio")
        self.output = self.work / "한글 음성_mistral.txt"

    def run_cli(self, scenario="success", args=None, key="test-placeholder"):
        env = {"PATH": os.defpath, "PYTHONIOENCODING": "utf-8"}
        if "SYSTEMROOT" in os.environ:
            env["SYSTEMROOT"] = os.environ["SYSTEMROOT"]
        if key is not None:
            env["MISTRAL_API_KEY"] = key
        return subprocess.run(
            [sys.executable, "-S", str(RUNNER), scenario, str(SCRIPT),
             *(args if args is not None else [str(self.source)])],
            env=env, cwd=self.work, stdin=subprocess.DEVNULL,
            capture_output=True, text=True, encoding="utf-8", timeout=15,
        )

    def assert_failed(self, result):
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("전사 완료!", result.stdout)

    def test_help_without_key_or_sdk(self):
        for flag in ("--help", "-h"):
            with self.subTest(flag=flag):
                result = self.run_cli("missing_sdk", [flag], key=None)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("usage:", result.stdout)
                self.assertIn("--lang", result.stdout)
                self.assertIn("--no-diarize", result.stdout)

    def test_missing_or_empty_key_is_failure(self):
        for key in (None, "", "   "):
            with self.subTest(key=key):
                self.assert_failed(self.run_cli(key=key))
        self.assertFalse((self.work / "client-created").exists())

    def test_missing_sdk_is_failure(self):
        self.assert_failed(self.run_cli("missing_sdk"))

    def test_invalid_input_is_rejected_before_client(self):
        directory = self.work / "directory.mp3"
        directory.mkdir()
        for args in ([""], ["--unknown"], ["missing.mp3"], ["unsupported.txt"],
                     [str(directory)], [str(self.source), "extra.mp3"]):
            with self.subTest(args=args):
                self.assert_failed(self.run_cli(args=args))
                self.assertFalse((self.work / "client-created").exists())

    def test_no_discovered_input_is_failure(self):
        self.source.unlink()
        self.assert_failed(self.run_cli(args=[]))
        self.assertFalse((self.work / "client-created").exists())

    def test_oversize_is_rejected_before_client(self):
        self.assert_failed(self.run_cli("oversize"))
        self.assertFalse((self.work / "client-created").exists())

    def test_empty_input_is_rejected_before_client(self):
        self.source.write_bytes(b"")
        self.assert_failed(self.run_cli())
        self.assertFalse((self.work / "client-created").exists())

    def test_empty_results_and_api_errors_preserve_old_output(self):
        self.output.write_text("이전 결과", encoding="utf-8")
        before = self.output.read_bytes()
        for scenario in ("empty", "whitespace", "authentication", "rate_limit", "api_error"):
            with self.subTest(scenario=scenario):
                self.assert_failed(self.run_cli(scenario))
                self.assertEqual(self.output.read_bytes(), before)

    def test_success_preserves_name_utf8_speakers_and_request_options(self):
        self.output.write_text("이전 결과", encoding="utf-8")
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.output.read_text(encoding="utf-8"),
                         "[화자 1]\n안녕하세요. 반갑습니다.\n\n[화자 2]\n네, 반갑습니다.")
        request = json.loads((self.work / "request.json").read_text(encoding="utf-8"))
        self.assertEqual(request, {"model": "voxtral-mini-latest", "file_name": self.source.name,
                                  "content": "sample-audio", "diarize": True,
                                  "timestamp_granularities": ["segment"]})

    def test_plain_text_fallback(self):
        result = self.run_cli("plain")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.output.read_text(encoding="utf-8"), "한국어 전체 전사")

    def test_language_requires_explicit_plain_mode_before_sdk_or_input(self):
        self.output.write_text("이전 결과", encoding="utf-8")
        before = self.output.read_bytes(), self.output.stat().st_mtime_ns
        result = self.run_cli("missing_sdk", ["--lang", "ko"], key=None)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("--no-diarize", result.stderr)
        self.assertFalse((self.work / "client-created").exists())
        self.assertEqual((self.output.read_bytes(), self.output.stat().st_mtime_ns), before)

    def test_invalid_language_is_rejected_before_client(self):
        for language in ("", " ", "ko-KR", "kor", "k", "ko,en", "한국", "12", "éa", "KO"):
            with self.subTest(language=language):
                result = self.run_cli(args=[str(self.source), "--no-diarize", "--lang", language])
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertFalse((self.work / "client-created").exists())

    def test_language_plain_request_omits_timestamps_and_normalizes_case(self):
        result = self.run_cli("plain", [str(self.source), "--lang", "KO", "--no-diarize"])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        request = json.loads((self.work / "request.json").read_text(encoding="utf-8"))
        self.assertEqual(request, {"model": "voxtral-mini-latest", "file_name": self.source.name,
                                  "content": "sample-audio", "diarize": False, "language": "ko"})
        self.assertEqual(self.output.read_text(encoding="utf-8"), "한국어 전체 전사")

    def test_plain_mode_uses_full_text_even_if_segments_are_returned(self):
        result = self.run_cli(args=[str(self.source), "--no-diarize"])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        request = json.loads((self.work / "request.json").read_text(encoding="utf-8"))
        self.assertEqual(request, {"model": "voxtral-mini-latest", "file_name": self.source.name,
                                  "content": "sample-audio", "diarize": False})
        self.assertEqual(self.output.read_text(encoding="utf-8"), "fallback")

    def test_language_plain_failures_preserve_previous_output(self):
        self.output.write_text("이전 결과", encoding="utf-8")
        before = self.output.read_bytes(), self.output.stat().st_mtime_ns
        for scenario in ("empty", "whitespace", "authentication", "rate_limit", "api_error",
                         "write_error", "replace_error"):
            with self.subTest(scenario=scenario):
                result = self.run_cli(scenario, [str(self.source), "--lang", "ko", "--no-diarize"])
                self.assert_failed(result)
                self.assertEqual((self.output.read_bytes(), self.output.stat().st_mtime_ns), before)
                self.assertEqual(list(self.work.glob("*.tmp")), [])

    def test_language_plain_mode_keeps_auto_discovery(self):
        result = self.run_cli("plain", ["--lang", "en", "--no-diarize"])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        request = json.loads((self.work / "request.json").read_text(encoding="utf-8"))
        self.assertEqual(request["file_name"], self.source.name)
        self.assertEqual(request["language"], "en")

    def test_auto_discovery_keeps_extension_priority(self):
        (self.work / "first.wav").write_bytes(b"other")
        result = self.run_cli(args=[])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(self.output.exists())
        self.assertFalse((self.work / "first_mistral.txt").exists())

    def test_failed_partial_write_or_replace_preserves_old_output(self):
        for previous in (False, True):
            if previous:
                self.output.write_text("이전 결과", encoding="utf-8")
                before = self.output.read_bytes()
            for scenario in ("write_error", "replace_error"):
                with self.subTest(previous=previous, scenario=scenario):
                    self.assert_failed(self.run_cli(scenario))
                    if previous:
                        self.assertEqual(self.output.read_bytes(), before)
                    else:
                        self.assertFalse(self.output.exists())
                    self.assertEqual(list(self.work.glob("*.tmp")), [])


if __name__ == "__main__":
    unittest.main()

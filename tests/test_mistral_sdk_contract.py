"""Optional installed-SDK multipart contracts; subprocesses deny external networking."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "STT/mistral_stt.py"
RUNNER = Path(__file__).with_name("_mistral_sdk_runner.py")


class MistralSdkContractTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.source = self.work / "한글 음성.mp3"
        self.source.write_bytes(b"sample-audio")
        self.output = self.work / "한글 음성_mistral.txt"

    def run_cli(self, scenario="success", options=()):
        env = {"PATH": os.defpath, "PYTHONIOENCODING": "utf-8",
               "MISTRAL_API_KEY": "test-placeholder"}
        if "SYSTEMROOT" in os.environ:
            env["SYSTEMROOT"] = os.environ["SYSTEMROOT"]
        result = subprocess.run(
            [sys.executable, *(["-S"] if sys.flags.no_site else []),
             str(RUNNER), scenario, str(SCRIPT), str(self.source), *options],
            cwd=self.work, env=env, stdin=subprocess.DEVNULL,
            capture_output=True, text=True, encoding="utf-8", timeout=30,
        )
        if result.returncode == 77:
            self.skipTest("mistralai.client and httpx2 are required for optional SDK contracts")
        requests = json.loads((self.work / "requests.json").read_text(encoding="utf-8"))
        self.assertEqual(len(requests), 1, result.stdout + result.stderr)
        self.assertEqual(requests[0]["model"], ["voxtral-mini-latest"])
        self.assertEqual(requests[0]["file"], ["sample-audio"])
        return result, requests[0]

    def test_default_request_and_speaker_output_remain_unchanged(self):
        result, fields = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(fields["diarize"], ["true"])
        self.assertEqual(fields["timestamp_granularities"], ["segment"])
        self.assertNotIn("language", fields)
        self.assertEqual(self.output.read_text(encoding="utf-8"), "[화자 1]\n한국어 전체 전사")

    def test_language_plain_mode_serializes_without_timestamp_field(self):
        result, fields = self.run_cli(options=("--lang", "KO", "--no-diarize"))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(fields["diarize"], ["false"])
        self.assertEqual(fields["language"], ["ko"])
        self.assertNotIn("timestamp_granularities", fields)
        self.assertEqual(self.output.read_text(encoding="utf-8"), "한국어 전체 전사")

    def test_auto_plain_mode_omits_language_and_timestamps(self):
        result, fields = self.run_cli(options=("--no-diarize",))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(fields["diarize"], ["false"])
        self.assertNotIn("language", fields)
        self.assertNotIn("timestamp_granularities", fields)

    def test_http_error_preserves_previous_output(self):
        self.output.write_text("이전 결과", encoding="utf-8")
        before = self.output.read_bytes(), self.output.stat().st_mtime_ns
        result, _ = self.run_cli("error", ("--lang", "ko", "--no-diarize"))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertNotIn("전사 완료!", result.stdout)
        self.assertEqual((self.output.read_bytes(), self.output.stat().st_mtime_ns), before)
        self.assertEqual(list(self.work.glob("*.tmp")), [])

    def test_empty_plain_text_preserves_previous_output(self):
        self.output.write_text("이전 결과", encoding="utf-8")
        before = self.output.read_bytes(), self.output.stat().st_mtime_ns
        result, _ = self.run_cli("empty", ("--lang", "ko", "--no-diarize"))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual((self.output.read_bytes(), self.output.stat().st_mtime_ns), before)


if __name__ == "__main__":
    unittest.main()

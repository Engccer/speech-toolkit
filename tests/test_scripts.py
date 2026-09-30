"""스크립트 규약 시험. 네트워크·API 키·SDK 없이 돈다.

실행: python3 -m unittest discover -s tests
"""

import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load(rel_path):
    name = os.path.splitext(os.path.basename(rel_path))[0]
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel_path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class HelpWithoutKeyTest(unittest.TestCase):
    """--help는 API 키 없이 동작해야 한다(CLAUDE.md 공통 규약)."""

    def run_help(self, rel_path):
        with tempfile.TemporaryDirectory() as home:
            # 밀폐: 셸 환경을 물려받지 않는다(키·사용자 site-packages 모두 끊김)
            env = {"PATH": os.defpath, "HOME": home, "PYTHONIOENCODING": "utf-8"}
            if os.name == "nt" and "SYSTEMROOT" in os.environ:
                env["SYSTEMROOT"] = os.environ["SYSTEMROOT"]
            return subprocess.run(
                [sys.executable, "-S", os.path.join(ROOT, rel_path), "--help"],
                env=env, cwd=home, capture_output=True, text=True, encoding="utf-8", timeout=30,
                stdin=subprocess.DEVNULL,
            )

    def test_deepgram_help_without_key_or_sdk(self):
        result = self.run_help("STT/deepgram_stt.py")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("usage:", result.stdout)

    def test_long_tts_help_without_key_or_sdk(self):
        result = self.run_help("TTS/long_tts.py")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("usage:", result.stdout)


class LongTtsTest(unittest.TestCase):
    def setUp(self):
        self.mod = load("TTS/long_tts.py")

    def test_default_models_have_measured_rates(self):
        for provider, model in self.mod.DEFAULT_MODEL.items():
            self.assertIn((provider, model), self.mod.MODELS)

    def test_v3_rate_scales_with_speed(self):
        cps, chunk = self.mod.resolve_rate("elevenlabs", "eleven_v3", 1.2)
        self.assertAlmostEqual(cps, 4.35 * 1.2)
        self.assertEqual(chunk, 300)

    def test_v4_rate_ignores_speed_and_stays_under_seam(self):
        cps, chunk = self.mod.resolve_rate("elevenlabs", "eleven_v4", 1.2)
        self.assertAlmostEqual(cps, 7.1)
        self.assertLess(chunk, 290)

    def test_unknown_model_requires_rate(self):
        with self.assertRaises(SystemExit):
            self.mod.resolve_rate("elevenlabs", "eleven_multilingual_v2", 1.0)
        cps, chunk = self.mod.resolve_rate("elevenlabs", "eleven_multilingual_v2", 1.1, 5.0)
        self.assertAlmostEqual(cps, 5.5)
        self.assertEqual(chunk, self.mod.FALLBACK_CHUNK_SECONDS)

    def test_chunks_respect_limit_and_keep_all_text(self):
        text = "첫 문단입니다.\n" + "긴 문장입니다. " * 40 + "\n마지막 문단입니다."
        chunks = self.mod.split_into_chunks(text, 100)
        self.assertTrue(all(len(c) <= 100 for c in chunks))
        squash = lambda s: "".join(s.split())
        self.assertEqual(squash("".join(chunks)), squash(text))

    def test_short_tail_is_not_truncation(self):
        self.assertFalse(self.mod.is_truncated(5.0, 3.0))
        self.assertTrue(self.mod.is_truncated(300.0, 200.0))
        self.assertFalse(self.mod.is_truncated(300.0, 270.0))


class OpenAIOutputNameTest(unittest.TestCase):
    def setUp(self):
        self.mod = load("TTS/openai_tts.py")

    def test_pcm_is_not_saved_as_wav(self):
        # 헤더 없는 원시 PCM을 .wav로 저장하면 재생할 수 없는 파일이 된다
        out = self.mod.get_output_filename(os.path.join("d", "report.txt"), "pcm")
        self.assertTrue(out.endswith("report_openai.pcm"), out)

    def test_pcm_is_safe_to_concat_but_wav_flac_are_not(self):
        self.assertIn("pcm", self.mod.SAFE_CONCAT_FORMATS)
        self.assertNotIn("wav", self.mod.SAFE_CONCAT_FORMATS)
        self.assertNotIn("flac", self.mod.SAFE_CONCAT_FORMATS)

    def test_other_formats_keep_extension(self):
        for fmt in ("mp3", "wav", "flac"):
            out = self.mod.get_output_filename("report.txt", fmt)
            self.assertTrue(out.endswith(f"report_openai.{fmt}"), out)


class ElevenLabsVoiceMappingTest(unittest.TestCase):
    def setUp(self):
        self.mod = load("TTS/elevenlabs_tts.py")

    def test_auto_assign_skips_voice_taken_by_alias(self):
        mapping = self.mod.build_voice_mapping(["화자1", "철수"])
        self.assertNotEqual(mapping["화자1"], mapping["철수"])

    def test_auto_assign_skips_voice_taken_by_voice_map(self):
        mapping = self.mod.build_voice_mapping(["지영", "현우"], "현우=Yuna")
        self.assertNotEqual(mapping["지영"], mapping["현우"])

    def test_voice_map_entry_absent_from_script_takes_no_voice(self):
        mapping = self.mod.build_voice_mapping(["지영", "현우"], "영희=Yuna")
        self.assertEqual(mapping["지영"], self.mod.find_voice_by_name("Yuna")["id"])

    def test_distinct_until_presets_run_out(self):
        presets = self.mod.VOICE_PRESETS
        speakers = [f"사람{i}" for i in range(len(presets))]
        mapping = self.mod.build_voice_mapping(speakers)
        self.assertEqual(len(set(mapping.values())), len(presets))

    def test_cycles_after_presets_run_out(self):
        presets = self.mod.VOICE_PRESETS
        speakers = [f"사람{i}" for i in range(len(presets) + 2)]
        mapping = self.mod.build_voice_mapping(speakers)
        self.assertEqual(mapping[speakers[len(presets)]], presets[0]["id"])
        self.assertEqual(mapping[speakers[len(presets) + 1]], presets[1]["id"])


if __name__ == "__main__":
    unittest.main()

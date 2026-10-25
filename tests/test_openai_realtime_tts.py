"""Realtime 파일 합성 계약. 합성 네트워크와 실제 키를 사용하지 않는다."""

import base64
import contextlib
import copy
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock
import wave


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "TTS/openai_tts.py"
MODEL = "gpt-realtime-2.1-mini"
PCM = b"\x01\x00\x02\x00"


def response_events(text="Hello.", number=1, pcm=PCM):
    rid, item = f"resp_{number}", f"msg_{number}"
    identity = {"response_id": rid, "item_id": item,
                "output_index": 0, "content_index": 0}
    return [
        {"type": "response.created", "response": {"id": rid}},
        {"type": "response.output_audio.delta", **identity,
         "delta": base64.b64encode(pcm).decode()},
        {"type": "response.output_audio_transcript.delta", **identity, "delta": text},
        {"type": "response.output_audio.done", **identity},
        {"type": "response.output_audio_transcript.done", **identity, "transcript": text},
        {"type": "response.done", "response": {
            "object": "realtime.response", "id": rid, "status": "completed", "status_details": None,
            "conversation_id": None, "output_modalities": ["audio"], "max_output_tokens": 4096,
            "metadata": None, "output": [{
                "id": item, "type": "message", "role": "assistant", "status": "completed",
                "content": [{"type": "output_audio", "transcript": text}],
            }], "usage": {"input_tokens": 10, "output_tokens": 10}}},
    ]


class FakeConnection:
    def __init__(self, batches=None):
        self.queue = [{"type": "session.created", "session": {"id": "sess_test"}}]
        self.batches = batches or [response_events()]
        self.sent = []
        self.timeouts = []
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        self.closed = True

    def send(self, raw):
        event = json.loads(raw)
        self.sent.append(event)
        if event["type"] == "session.update":
            self.queue.append({"type": "session.updated", "session": event["session"]})
        elif event["type"] == "response.create":
            self.queue.extend(copy.deepcopy(self.batches.pop(0)))

    def recv(self, timeout=None):
        self.timeouts.append(timeout)
        if not self.queue:
            raise TimeoutError("no more events")
        event = self.queue.pop(0)
        if isinstance(event, BaseException):
            raise event
        if isinstance(event, str):
            return event
        event.setdefault("event_id", f"event_{len(self.timeouts)}")
        return json.dumps(event)


class RealtimeTest(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location("openai_tts_test", SCRIPT)
        self.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.mod)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.source = self.work / "notice.txt"
        self.source.write_text("Hello.", encoding="utf-8")
        self.output = self.work / "notice_openai.pcm"
        self.output.write_bytes(b"previous output")
        self.old_stat = self.output.stat().st_mtime_ns
        self.enterContext(mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test-placeholder"}, clear=True))
        for name in ("connect", "connect_ex"):
            self.enterContext(mock.patch.object(socket.socket, name, side_effect=AssertionError("network disabled")))
        self.enterContext(mock.patch.object(socket, "getaddrinfo", side_effect=AssertionError("network disabled")))
        self.original_synthesize = self.mod.synthesize_chunk
        self.legacy = self.enterContext(mock.patch.object(
            self.mod, "synthesize_chunk", side_effect=RuntimeError("REST called unexpectedly")))

    def run_cli(self, extra=(), connection=None, source=None, no_input=False):
        connection = connection or FakeConnection()
        connector = mock.Mock(return_value=connection)
        with mock.patch.object(self.mod, "load_realtime_connector", return_value=connector, create=True), \
                mock.patch.object(sys, "argv", [str(SCRIPT), *([] if no_input else [str(self.source if source is None else source)]),
                                               "--model", MODEL, "--format", "pcm", *extra]), \
                contextlib.redirect_stdout(io.StringIO()) as out:
            code = self.mod.main()
        self.log = out.getvalue()
        self.connector = connector
        return code, connection

    def assert_preserved(self):
        self.assertEqual(self.output.read_bytes(), b"previous output")
        self.assertEqual(self.output.stat().st_mtime_ns, self.old_stat)
        self.assertEqual(sorted(p.name for p in self.work.iterdir()),
                         ["notice.txt", "notice_openai.pcm"])

    def test_invalid_realtime_options_never_reach_network(self):
        for options in (("--voice", "fable"), ("--voice", "nova"), ("--voice", "onyx"),
                        ("--speed", "1.6"), ("--speed", "nan"), ("--speed", "0.1"),
                        ("--chunk-size", "0"), ("--chunk-size", "-1"), ("--chunk-size", "4097")):
            with self.subTest(options=options):
                code, _ = self.run_cli(options)
                self.assertEqual(code, 1)
                self.connector.assert_not_called()
                self.legacy.assert_not_called()
                self.assert_preserved()

    def test_success_request_is_isolated_and_preserves_filename(self):
        code, connection = self.run_cli(("--voice", "CEDAR", "--speed", "1.25", "--instructions", "Calm"))
        self.assertEqual(code, 0)
        self.assertEqual(self.output.read_bytes(), PCM)
        self.assertTrue(connection.closed)
        self.assertFalse(any(t.name.startswith("openai-deadline") for t in threading.enumerate()))
        self.legacy.assert_not_called()
        session, request = connection.sent
        self.assertEqual(session["session"]["audio"]["output"], {
            "format": {"type": "audio/pcm", "rate": 24000}, "voice": "cedar", "speed": 1.25})
        self.assertIsNone(session["session"]["audio"]["input"]["turn_detection"])
        self.assertIn("Calm", session["session"]["instructions"])
        self.assertEqual(request["response"]["conversation"], "none")
        self.assertEqual(request["response"]["input"], [{"type": "message", "role": "user",
            "content": [{"type": "input_text", "text": "Hello."}]}])
        self.assertEqual(request["response"]["output_modalities"], ["audio"])
        self.assertEqual(request["response"]["max_output_tokens"], 4096)
        self.assertTrue(all(t is not None and 0 < t <= 180 for t in connection.timeouts))
        self.assertIn("입력 토큰: 10", self.log)

    def test_splitter_loss_falls_back_before_requests(self):
        self.source.write_text("abc, def", encoding="utf-8")
        connection = FakeConnection([response_events("abc,", 1), response_events(" def", 2)])
        code, connection = self.run_cli(("--chunk-size", "4"), connection)
        self.assertEqual(code, 0)
        texts = [e["response"]["input"][0]["content"][0]["text"] for e in connection.sent
                 if e["type"] == "response.create"]
        self.assertEqual(texts, ["abc,", " def"])
        self.assertEqual(self.output.read_bytes(), PCM + PCM)
        self.assertEqual(self.mod.split_text_into_chunks("abc, def", 4), ["abc", "def"])

    def test_nfc_and_whitespace_are_the_only_transcript_relaxation(self):
        self.source.write_text("가 나.", encoding="utf-8")
        code, _ = self.run_cli(connection=FakeConnection([response_events("가\n나.")]))
        self.assertEqual(code, 0)
        self.assertEqual(self.output.read_bytes(), PCM)

    def test_transcript_addition_omission_or_punctuation_change_fails(self):
        for text in ("Hello. Extra.", "Hell.", "Hello", "", "A summary."):
            with self.subTest(text=text):
                code, _ = self.run_cli(connection=FakeConnection([response_events(text)]))
                self.assertEqual(code, 1)
                self.assert_preserved()

    def test_final_output_must_match_collected_identity_and_content(self):
        mutations = [
            lambda r: r.update(status="incomplete"),
            lambda r: r.update(status="cancelled"),
            lambda r: r.update(status="failed"),
            lambda r: r.update(id="resp_other"),
            lambda r: r["output"].append(copy.deepcopy(r["output"][0])),
            lambda r: r["output"][0].update(id="msg_other"),
            lambda r: r["output"][0]["content"].append({"type": "text", "text": "extra"}),
            lambda r: r["output"][0]["content"][0].update(transcript="Extra."),
            lambda r: r["output"][0]["content"][0].update(type="text"),
            lambda r: r["output"][0]["content"][0].update(type="audio"),
        ]
        for mutate in mutations:
            events = response_events()
            mutate(events[-1]["response"])
            with self.subTest(events=events[-1]):
                code, _ = self.run_cli(connection=FakeConnection([events]))
                self.assertEqual(code, 1)
                self.assert_preserved()

    def test_invalid_or_missing_stream_events_fail_without_partial_output(self):
        cases = []
        for index in (3, 4, 5):
            events = response_events()
            del events[index]
            cases.append(events)
        for pcm in (b"", b"x"):
            cases.append(response_events(pcm=pcm))
        for field, value in (("delta", "not base64!"), ("response_id", "other"),
                             ("item_id", "other"), ("output_index", 1), ("content_index", 1)):
            events = response_events()
            events[1][field] = value
            cases.append(events)
        cases.extend([["invalid json"], [{"type": "error", "error": {"message": "PRIVATE BODY"}}]])
        for events in cases:
            with self.subTest(events=events):
                code, _ = self.run_cli(connection=FakeConnection([events]))
                self.assertEqual(code, 1)
                self.assertNotIn("PRIVATE BODY", self.log)
                self.assert_preserved()

    def test_duplicate_event_is_not_duplicate_audio(self):
        events = response_events()
        events[1]["event_id"] = "duplicate"
        events.insert(2, copy.deepcopy(events[1]))
        code, _ = self.run_cli(connection=FakeConnection([events]))
        self.assertEqual(code, 0)
        self.assertEqual(self.output.read_bytes(), PCM)

    def test_timeout_and_interrupt_cancel_active_response_and_close(self):
        for error in (TimeoutError(), KeyboardInterrupt()):
            with self.subTest(error=type(error).__name__):
                events = response_events()[:2] + [error]
                code, connection = self.run_cli(connection=FakeConnection([events]))
                self.assertEqual(code, 1)
                self.assertEqual(connection.sent[-1], {"type": "response.cancel", "response_id": "resp_1"})
                self.assertTrue(connection.closed)
                self.assertIn("확인되지", self.log)
                self.assert_preserved()

    def test_session_created_and_updated_waits_are_bounded(self):
        for phase in ("created", "updated", "wrong_configuration"):
            connection = FakeConnection()
            if phase == "created":
                connection.queue = []
            elif phase == "updated":
                original = connection.send
                def send(raw):
                    original(raw)
                    connection.queue.clear()
                connection.send = send
            else:
                original = connection.send
                def send(raw):
                    original(raw)
                    connection.queue[-1]["session"]["audio"]["output"]["voice"] = "ash"
                connection.send = send
            with self.subTest(phase=phase):
                code, connection = self.run_cli(connection=connection)
                self.assertEqual(code, 1)
                self.assertTrue(all(0 < t <= 20 for t in connection.timeouts))
                self.assertFalse(any(e["type"] == "response.create" for e in connection.sent))
                self.assert_preserved()

    def test_session_acknowledgement_must_confirm_script_and_disabled_vad(self):
        for field in ("instructions", "turn_detection", "type"):
            connection = FakeConnection()
            original = connection.send
            def send(raw):
                original(raw)
                session = connection.queue[-1]["session"]
                if field == "turn_detection":
                    del session["audio"]["input"]["turn_detection"]
                else:
                    session[field] = "unexpected"
            connection.send = send
            with self.subTest(field=field):
                code, _ = self.run_cli(connection=connection)
                self.assertEqual(code, 1)
                self.assertFalse(any(e["type"] == "response.create" for e in connection.sent))
                self.assert_preserved()

    def test_second_chunk_failure_preserves_old_output(self):
        self.source.write_text("Hello. Again.", encoding="utf-8")
        events = response_events("Again.", 2)
        events[-1]["response"]["status"] = "incomplete"
        code, _ = self.run_cli(("--chunk-size", "6"), FakeConnection([response_events(), events]))
        self.assertEqual(code, 1)
        self.assert_preserved()

    def test_replace_failure_preserves_old_file(self):
        with mock.patch.object(self.mod.os, "replace", side_effect=OSError("disk error")):
            code, _ = self.run_cli()
        self.assertEqual(code, 1)
        self.assert_preserved()

    def test_unwritable_destination_is_detected_before_connection(self):
        import tempfile as tempmodule
        with mock.patch.object(tempmodule, "mkstemp", side_effect=PermissionError("denied")):
            code, _ = self.run_cli()
        self.assertEqual(code, 1)
        self.connector.assert_not_called()
        self.assert_preserved()

    def test_post_replace_print_failure_does_not_turn_success_into_failure(self):
        def printing(*args, **kwargs):
            if args and "저장 완료" in str(args[0]):
                raise BrokenPipeError()
        with mock.patch("builtins.print", side_effect=printing):
            code, _ = self.run_cli()
        self.assertEqual(code, 0)
        self.assertEqual(self.output.read_bytes(), PCM)

    def test_empty_source_and_missing_key_never_connect(self):
        self.source.write_text(" ", encoding="utf-8")
        code, _ = self.run_cli()
        self.assertEqual(code, 1)
        self.connector.assert_not_called()
        self.source.write_text("Hello.", encoding="utf-8")
        os.environ.clear()
        code, _ = self.run_cli()
        self.assertEqual(code, 1)
        self.connector.assert_not_called()
        self.assert_preserved()

    def test_automatic_file_selection_prefers_txt(self):
        (self.work / "other.md").write_text("Other.", encoding="utf-8")
        with contextlib.chdir(self.work):
            code, _ = self.run_cli(no_input=True)
        self.assertEqual(code, 0)
        self.assertEqual(self.output.read_bytes(), PCM)
        self.assertFalse((self.work / "other_openai.pcm").exists())

    def test_direct_text_uses_output_stem(self):
        with contextlib.chdir(self.work):
            code, _ = self.run_cli(source="Hello.")
        self.assertEqual(code, 0)
        self.assertEqual((self.work / "output_openai.pcm").read_bytes(), PCM)

    def test_missing_input_and_unsupported_file_fail_without_connecting(self):
        with contextlib.chdir(self.work), mock.patch.object(self.mod, "find_input_file", return_value=None):
            code, _ = self.run_cli(no_input=True)
        self.assertEqual(code, 1)
        self.connector.assert_not_called()
        bad = self.work / "source.csv"
        bad.write_text("Hello.", encoding="utf-8")
        code, _ = self.run_cli(source=bad)
        self.assertEqual(code, 1)
        self.connector.assert_not_called()

    def test_encoder_unavailability_and_timeout_precede_network(self):
        with mock.patch.object(shutil, "which", return_value=None):
            code, _ = self.run_cli(("--format", "mp3"))
        self.assertEqual(code, 1)
        self.connector.assert_not_called()
        for result in (subprocess.CompletedProcess([], 0, b"", b""),
                       subprocess.TimeoutExpired("ffmpeg", 20)):
            with mock.patch.object(shutil, "which", return_value="ffmpeg"), \
                    mock.patch.object(subprocess, "run") as run:
                if isinstance(result, BaseException):
                    run.side_effect = result
                else:
                    run.return_value = result
                code, _ = self.run_cli(("--format", "mp3"))
            self.assertEqual(code, 1)
            self.connector.assert_not_called()
            self.assert_preserved()

    def test_partial_write_failure_cleans_temporary_and_preserves_old_file(self):
        original = open
        class BrokenWriter:
            def __init__(self, stream):
                self.stream = stream
            def __enter__(self):
                return self
            def __exit__(self, *args):
                self.stream.close()
            def write(self, value):
                self.stream.write(value[:2])
                raise OSError("partial write")
        def broken_open(filename, mode="r", *args, **kwargs):
            stream = original(filename, mode, *args, **kwargs)
            return BrokenWriter(stream) if mode == "wb" and Path(filename).name.startswith(".openai-") else stream
        with mock.patch("builtins.open", side_effect=broken_open):
            code, _ = self.run_cli()
        self.assertEqual(code, 1)
        self.assert_preserved()

    def test_encoding_failure_and_decode_timeout_preserve_old_file(self):
        output = self.work / "notice_openai.mp3"
        output.write_bytes(b"old compressed output")
        old_mtime = output.stat().st_mtime_ns
        for phase in ("encode", "decode"):
            def run(command, **kwargs):
                self.assertGreater(kwargs["timeout"], 0)
                self.assertLessEqual(kwargs["timeout"], 180)
                if command[-1] == "-":
                    raise subprocess.TimeoutExpired("ffmpeg", 180)
                if phase == "encode":
                    return subprocess.CompletedProcess(command, 1, b"", b"private error")
                Path(command[-1]).write_bytes(b"encoded")
                return subprocess.CompletedProcess(command, 0, b"", b"")
            with self.subTest(phase=phase), mock.patch.object(self.mod, "preflight_encoder", return_value="ffmpeg"), \
                    mock.patch.object(subprocess, "run", side_effect=run):
                code, _ = self.run_cli(("--format", "mp3"))
            self.assertEqual(code, 1)
            self.assertEqual(output.read_bytes(), b"old compressed output")
            self.assertEqual(output.stat().st_mtime_ns, old_mtime)
            self.assertFalse(list(self.work.glob(".openai-*")))

    def test_cancel_send_failure_still_closes_connection(self):
        connection = FakeConnection([response_events()[:2] + [TimeoutError()]])
        original = connection.send
        def send(raw):
            if json.loads(raw)["type"] == "response.cancel":
                raise OSError("disconnected")
            original(raw)
        connection.send = send
        code, _ = self.run_cli(connection=connection)
        self.assertEqual(code, 1)
        self.assertTrue(connection.closed)
        self.assertIn("확인되지", self.log)
        self.assert_preserved()

    def test_whole_job_deadline_stops_before_next_paid_response(self):
        self.source.write_text("Hello. Again.", encoding="utf-8")
        connection = FakeConnection([response_events(), response_events("Again.", 2)])
        now = [0]
        original = connection.recv
        def recv(**kwargs):
            event = original(**kwargs)
            if json.loads(event)["type"] == "response.done":
                now[0] = 3301
            return event
        connection.recv = recv
        with mock.patch.object(self.mod.time, "monotonic", side_effect=lambda: now[0]):
            code, _ = self.run_cli(("--chunk-size", "6"), connection)
        self.assertEqual(code, 1)
        self.assertEqual(sum(e["type"] == "response.create" for e in connection.sent), 1)
        self.assert_preserved()

    def test_post_replace_interrupt_is_also_success(self):
        def printing(*args, **kwargs):
            if args and "저장 완료" in str(args[0]):
                raise KeyboardInterrupt()
        with mock.patch("builtins.print", side_effect=printing):
            code, _ = self.run_cli()
        self.assertEqual(code, 0)
        self.assertEqual(self.output.read_bytes(), PCM)

    def test_legacy_rest_payload_and_http_failure_contract_remain(self):
        from types import SimpleNamespace
        self.legacy.side_effect = self.original_synthesize
        for options, model, voice, speed in (([], "gpt-4o-mini-tts", "marin", 1.0),
                    (["--model", "tts-1", "--voice", "nova", "--speed", "4.0"], "tts-1", "nova", 4.0)):
            post = mock.Mock(return_value=SimpleNamespace(status_code=200, content=b"rest-audio"))
            with mock.patch.dict(sys.modules, {"requests": SimpleNamespace(post=post)}), \
                    mock.patch.object(sys, "argv", [str(SCRIPT), str(self.source), "--format", "pcm",
                                                   "--instructions", "Calm", *options]), \
                    contextlib.redirect_stdout(io.StringIO()):
                code = self.mod.main()
            self.assertIsNone(code)
            payload = {"model": model, "voice": voice, "input": "Hello.", "response_format": "pcm", "speed": speed}
            if model == "gpt-4o-mini-tts":
                payload["instructions"] = "Calm"
            self.assertEqual(post.call_args.kwargs["json"], payload)
            self.assertEqual(post.call_args.kwargs["timeout"], 180)
            self.assertEqual(self.output.read_bytes(), b"rest-audio")
        post = mock.Mock(return_value=SimpleNamespace(status_code=500, text="offline", json=lambda: {"error": {"message": "offline"}}))
        with mock.patch.dict(sys.modules, {"requests": SimpleNamespace(post=post)}), \
                mock.patch.object(sys, "argv", [str(SCRIPT), str(self.source), "--format", "pcm"]), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertIsNone(self.mod.main())
        self.assertEqual(self.output.read_bytes(), b"rest-audio")

    def test_stalled_sends_and_close_are_shutdown_within_finite_limits(self):
        class BlockingSocket:
            def __init__(self):
                self.stopped = threading.Event()
                self.shutdown_calls = []
                self.closed = False

            def sendall(self, data):
                # Safety fuse keeps a missing watchdog from hanging the test runner.
                if not self.stopped.wait(1):
                    raise OSError("fixture safety fuse: sendall stayed blocked")
                raise OSError("socket shutdown interrupted sendall")

            def shutdown(self, how):
                self.shutdown_calls.append(how)
                self.stopped.set()

            def close(self):
                self.closed = True
                self.stopped.set()

            def settimeout(self, value):
                raise AssertionError("must not change the receiver's socket timeout")

        class StalledConnection(FakeConnection):
            def __init__(self, phase):
                batches = [response_events()[:2] + [TimeoutError()]] if phase == "response.cancel" else None
                super().__init__(batches)
                self.phase = phase
                self.socket = BlockingSocket()
                self.protocol_mutex = threading.Lock()
                self.close_started = False

            def send(self, raw):
                if json.loads(raw)["type"] == self.phase:
                    self.sent.append(json.loads(raw))
                    with self.protocol_mutex:
                        self.socket.sendall(raw.encode())
                else:
                    super().send(raw)

            def close(self):
                self.close_started = True
                try:
                    if self.phase in ("close", "close_silent"):
                        with self.protocol_mutex:
                            try:
                                self.socket.sendall(b"close frame")
                            except OSError:
                                if self.phase != "close_silent":
                                    raise
                finally:
                    self.socket.close()
                    super().close()

        original_remaining = self.mod.remaining
        for phase in ("session.update", "response.create", "response.cancel", "close", "close_silent"):
            connection = StalledConnection(phase)
            timers_before = {t.ident for t in threading.enumerate() if t.name.startswith("openai-deadline")}
            start = time.monotonic()
            with self.subTest(phase=phase), mock.patch.object(
                    self.mod, "remaining", side_effect=lambda deadline, maximum: min(
                        original_remaining(deadline, maximum), 0.05)), \
                    mock.patch.object(self.mod, "REALTIME_CLEANUP_TIMEOUT", 0.05, create=True):
                code, _ = self.run_cli(connection=connection)
                elapsed = time.monotonic() - start
                self.assertEqual(code, 1)
                self.assertTrue(connection.socket.shutdown_calls)
                self.assertTrue(all(how == socket.SHUT_RDWR for how in connection.socket.shutdown_calls))
                self.assertTrue(connection.close_started)
                self.assertTrue(connection.closed)
                self.assertTrue(connection.socket.closed)
                self.assertLess(elapsed, 0.75)
                self.assert_preserved()
                self.assertEqual({t.ident for t in threading.enumerate() if t.name.startswith("openai-deadline")},
                                 timers_before)
                if phase == "response.cancel":
                    self.assertEqual(connection.sent[-1], {"type": "response.cancel", "response_id": "resp_1"})
                print(f"stalled-io {phase}: elapsed={elapsed:.3f}s, shutdown={len(connection.socket.shutdown_calls)}")


class OfflineProcessTest(unittest.TestCase):
    def run_script(self, folder, args):
        # -S blocks installed SDKs; the audit hook blocks even accidental network calls.
        runner = ("import sys,runpy; "
                  "sys.addaudithook(lambda event,args: (_ for _ in ()).throw(AssertionError('network disabled')) "
                  "if event in ('socket.connect','socket.getaddrinfo') else None); "
                  "sys.argv=sys.argv[1:]; runpy.run_path(sys.argv[0],run_name='__main__')")
        env = {"PATH": os.defpath, "PYTHONIOENCODING": "utf-8", "OPENAI_API_KEY": "test-placeholder"}
        if "SYSTEMROOT" in os.environ:
            env["SYSTEMROOT"] = os.environ["SYSTEMROOT"]
        return subprocess.run([sys.executable, "-S", "-B", "-c", runner, str(SCRIPT), *args],
                              cwd=folder, env=env, text=True, encoding="utf-8", capture_output=True,
                              timeout=30, stdin=subprocess.DEVNULL)

    def test_help_and_lists_without_dependencies(self):
        with tempfile.TemporaryDirectory() as folder:
            for option in ("--help", "--list-voices", "--list-models"):
                with self.subTest(option=option):
                    result = self.run_script(folder, [option])
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn("gpt-realtime-2.1-mini", result.stdout)

    def test_missing_websockets_is_failure_without_request_or_new_file(self):
        with tempfile.TemporaryDirectory() as folder:
            result = self.run_script(folder, ["Hello.", "--model", MODEL, "--format", "pcm"])
            self.assertEqual(result.returncode, 1)
            self.assertIn("websockets", result.stdout)
            self.assertEqual(list(Path(folder).iterdir()), [])


class LocalFormatTest(unittest.TestCase):
    def test_synthetic_pcm_converts_and_decodes_all_six_formats(self):
        ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
        if not ffmpeg or not ffprobe:
            self.skipTest("local format integration needs ffmpeg and ffprobe")
        spec = importlib.util.spec_from_file_location("openai_tts_formats", SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        pcm = b"".join(struct.pack("<h", int(10000 * math.sin(2 * math.pi * 440 * i / 24000)))
                       for i in range(24000))
        env = {"PATH": os.pathsep.join({str(Path(ffmpeg).parent), str(Path(ffprobe).parent), os.defpath})}
        if "SYSTEMROOT" in os.environ:
            env["SYSTEMROOT"] = os.environ["SYSTEMROOT"]
        with tempfile.TemporaryDirectory() as folder, mock.patch.dict(os.environ, env, clear=True):
            for fmt in ("pcm", "wav", "mp3", "opus", "aac", "flac"):
                with self.subTest(fmt=fmt):
                    destination = str(Path(folder) / ("audio." + fmt))
                    deadline = mod.time.monotonic() + 180
                    encoder = mod.preflight_encoder(fmt, deadline)
                    mod.write_realtime_audio(pcm, destination, fmt, encoder, deadline)
                    raw_options = ["-f", "s16le", "-sample_rate", "24000", "-ch_layout", "mono"] if fmt == "pcm" else []
                    probe = subprocess.run([ffprobe, "-v", "error", *raw_options, "-show_format",
                                            "-show_streams", "-of", "json", destination],
                                           capture_output=True, timeout=20, check=True, stdin=subprocess.DEVNULL)
                    metadata = json.loads(probe.stdout)
                    duration = float(metadata["format"]["duration"])
                    self.assertTrue(0.9 <= duration <= 1.2, metadata)
                    decoded = subprocess.run([ffmpeg, "-nostdin", "-v", "error", *raw_options, "-i",
                                              destination, "-ar", "24000", "-ac", "1", "-f", "s16le", "-"],
                                             capture_output=True, timeout=20, check=True, stdin=subprocess.DEVNULL)
                    self.assertEqual(decoded.stderr, b"")
                    self.assertTrue(43200 <= len(decoded.stdout) <= 57600)
                    if fmt in ("pcm", "wav", "flac"):
                        self.assertEqual(decoded.stdout, pcm)
                    print(f"local-format {fmt}: bytes={Path(destination).stat().st_size}, duration={duration}, decode=0")


if __name__ == "__main__":
    unittest.main()

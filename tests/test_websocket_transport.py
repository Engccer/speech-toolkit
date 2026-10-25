"""설치된 WebSocket SDK의 실제 루프백 통신. 외부 API·실제 키를 사용하지 않는다."""
import importlib.util
import json
from pathlib import Path
import threading
import time
import unittest

from test_openai_realtime_tts import PCM, response_events

try:
    from websockets.sync.server import serve
except ImportError:
    serve = None


@unittest.skipIf(serve is None, "websockets SDK 미설치")
class WebSocketTransportTest(unittest.TestCase):
    def test_real_transport_preserves_headers_timeout_and_chunk_order(self):
        script = Path(__file__).resolve().parents[1] / "TTS" / "openai_tts.py"
        spec = importlib.util.spec_from_file_location("tts_transport_test", script)
        tts = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tts)
        chunks = ["첫 문장입니다.", "Second sentence."]
        received = []
        failures = []
        finished = threading.Event()

        def handler(connection):
            try:
                self.assertEqual(connection.request.headers["Authorization"], "Bearer local-test")
                with self.assertRaises(TimeoutError):
                    connection.recv(timeout=0.01)
                connection.send(json.dumps({"type": "session.created", "session": {}}))
                settings = json.loads(connection.recv(timeout=5))
                connection.send(json.dumps({"type": "session.updated", "session": settings["session"]}))
                for number, text in enumerate(chunks, 1):
                    request = json.loads(connection.recv(timeout=5))
                    received.append(request["response"]["input"][0]["content"][0]["text"])
                    for index, event in enumerate(response_events(text, number, PCM * number)):
                        event["event_id"] = f"{number}-{index}"
                        connection.send(json.dumps(event))
            except BaseException as error:
                failures.append(error)
            finally:
                finished.set()

        with serve(handler, "127.0.0.1", 0) as server:
            worker = threading.Thread(target=server.serve_forever, name="tts-test-server")
            worker.start()
            actual_connect = tts.load_realtime_connector()
            connections = []

            def local_connect(uri, **kwargs):
                connection = actual_connect(f"ws://127.0.0.1:{server.socket.getsockname()[1]}",
                                            proxy=None, **kwargs)
                connections.append(connection)
                return connection

            try:
                audio, usage = tts.synthesize_realtime(local_connect, "local-test", chunks,
                                                       "marin", 1.0, None, time.monotonic() + 10)
                self.assertTrue(finished.wait(5))
                self.assertFalse(failures, failures)
                self.assertEqual(received, chunks)
                self.assertEqual(audio, PCM * 3)
                self.assertEqual(len(usage), 2)
                self.assertEqual(connections[0].socket.fileno(), -1)
            finally:
                server.shutdown()
                worker.join(timeout=5)
            self.assertFalse(worker.is_alive())
        self.assertFalse(any(t.name.startswith("openai-deadline") for t in threading.enumerate()))


if __name__ == "__main__":
    unittest.main()

"""Isolated CLI harness: SDK substitute and external network denial."""
import json
import os
from pathlib import Path
import runpy
import sys
from types import SimpleNamespace


def forbid_network(event, args):
    if event == "socket.connect" and args[1][0] in ("127.0.0.1", "::1"):
        return  # Windows asyncio's internal socketpair.
    if event in ("socket.connect", "socket.getaddrinfo"):
        raise AssertionError("External network is disabled in CLI tests")


sys.addaudithook(forbid_network)
scenario, script, *arguments = sys.argv[1:]


def complete(**kwargs):
    Path("request.json").write_text(json.dumps({
        "model": kwargs["model"],
        "file_name": kwargs["file"]["file_name"],
        "content": kwargs["file"]["content"].read().decode("ascii"),
        "diarize": kwargs["diarize"],
        "timestamp_granularities": kwargs["timestamp_granularities"],
    }), encoding="utf-8")
    if scenario in ("authentication", "rate_limit", "api_error"):
        raise RuntimeError({"authentication": "Unauthorized", "rate_limit": "Rate limit", "api_error": "Service unavailable"}[scenario])
    if scenario in ("empty", "whitespace"):
        return SimpleNamespace(text="" if scenario == "empty" else " \n\t", segments=[])
    if scenario == "plain":
        return SimpleNamespace(text="한국어 전체 전사", segments=[])
    return SimpleNamespace(text="fallback", segments=[
        SimpleNamespace(speaker_id="speaker_1", text="안녕하세요."),
        SimpleNamespace(speaker_id="speaker_1", text="반갑습니다."),
        SimpleNamespace(speaker_id="speaker_2", text="네, 반갑습니다."),
    ])


class Mistral:
    def __init__(self, **kwargs):
        Path("client-created").touch()
        self.audio = SimpleNamespace(transcriptions=SimpleNamespace(complete=complete))

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def close(self):
        pass


if scenario != "missing_sdk":
    sys.modules["mistralai"] = SimpleNamespace(Mistral=Mistral)
    sys.modules["mistralai.client"] = SimpleNamespace(Mistral=Mistral)

if scenario == "oversize":
    os.path.getsize = lambda path: 1024 ** 3 + 1
if scenario == "replace_error":
    def replace_error(*args):
        raise PermissionError("destination locked")
    os.replace = replace_error
if scenario == "write_error":
    import tempfile
    original = tempfile.NamedTemporaryFile

    class BrokenWrite:
        def __init__(self, *args, **kwargs):
            self.stream = original(*args, **kwargs)
            self.name = self.stream.name

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.stream.close()

        def write(self, value):
            self.stream.write(value[:2])
            raise OSError("disk full after partial write")

    tempfile.NamedTemporaryFile = BrokenWrite

sys.argv = [script, *arguments]
runpy.run_path(script, run_name="__main__")

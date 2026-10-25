"""Exercise the installed Mistral SDK with a local HTTP transport substitute."""
from email import policy
from email.parser import BytesParser
import importlib.util
import io
import json
from pathlib import Path
import runpy
import sys
from unittest import mock


def forbid_network(event, args):
    if event == "socket.connect" and args[1][0] in ("127.0.0.1", "::1"):
        return  # Windows asyncio's internal socketpair.
    if event in ("socket.connect", "socket.getaddrinfo"):
        raise AssertionError("External network is disabled in SDK tests")


sys.addaudithook(forbid_network)
if any(importlib.util.find_spec(name) is None for name in ("httpx2", "mistralai")):
    sys.exit(77)
import httpx2
import mistralai
import mistralai.client

scenario, script, *arguments = sys.argv[1:]
requests = []


def handle(request):
    assert request.method == "POST"
    assert request.url.path == "/v1/audio/transcriptions"
    message = BytesParser(policy=policy.default).parsebytes(
        b"Content-Type: " + request.headers["content-type"].encode("ascii")
        + b"\r\nMIME-Version: 1.0\r\n\r\n" + request.read())
    fields = {}
    for part in message.iter_parts():
        name = part.get_param("name", header="content-disposition")
        fields.setdefault(name, []).append(part.get_payload(decode=True).decode("utf-8"))
    requests.append(fields)
    if scenario == "error":
        return httpx2.Response(422, json={"message": "Invalid request"})
    text = " \n\t" if scenario == "empty" else "한국어 전체 전사"
    return httpx2.Response(200, json={
        "model": "voxtral-mini-latest", "language": "ko", "usage": {}, "text": text,
        "segments": [{"start": 0, "end": 1, "speaker_id": "speaker_1", "text": text}],
    })


with httpx2.Client(transport=httpx2.MockTransport(handle)) as transport:
    client = mistralai.client.Mistral(api_key="test-placeholder", client=transport, retry_config=None)
    with client, mock.patch.object(mistralai.client, "Mistral", return_value=client), \
         mock.patch.object(mistralai, "Mistral", return_value=client, create=True), \
         mock.patch.object(sys, "argv", [script, *arguments]), \
         mock.patch.object(sys, "stdin", io.StringIO()):
        try:
            runpy.run_path(script, run_name="__main__")
        except SystemExit as exc:
            code = exc.code
        else:
            code = 0
Path("requests.json").write_text(json.dumps(requests, ensure_ascii=False), encoding="utf-8")
sys.exit(code)

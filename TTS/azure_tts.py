#!/usr/bin/env python3
"""Azure AI Speech TTS - 텍스트를 음성으로 변환 (기본: ko-KR-SunHiNeural).

gemini_tts.py / elevenlabs_tts.py와 같은 CLI 계약을 따른다.
  python azure_tts.py <입력파일> [--voice ...] [--language-code ...] [--tempo ...]
출력: 입력파일과 같은 폴더의 "<stem>_azure_tts.wav"

표준 라이브러리만 사용한다(추가 pip 패키지 불필요). Azure Speech REST API를 직접 호출하고,
속도는 SSML <prosody rate>로 합성 단계에서 적용하므로 이 스크립트에는 ffmpeg가 필요 없다
(Azure 상한 2배를 넘는 속도는 provider 스크립트가 ffmpeg로 보탠다).

환경 변수:
  AZURE_SPEECH_KEY     (필수) Speech 리소스 키
  AZURE_SPEECH_REGION  (필수) 리전 예: koreacentral, eastus
  AZURE_SPEECH_ENDPOINT (선택) 전체 엔드포인트를 직접 지정할 때
Windows에서 프로세스 환경에 키가 없으면 사용자 환경 변수(레지스트리)에서 읽는다.
키를 등록하기 전에 띄운 셸·Git Bash는 새 사용자 환경 변수를 물려받지 못하기 때문이다.

한 요청이 만들 수 있는 오디오는 10분까지다(공식 한도). 긴 대본은 speech-toolkit의
long_tts.py --provider azure처럼 나눠 부른다. 429(요청 과다, F0는 60초에 20건)는
--retries N을 주면 Retry-After를 따라(회당 최대 30초) N번까지 다시 시도한다. 기본은 0이라
턴 요약 훅처럼 시간 제한이 짧은 호출자는 곧바로 실패해 폴백으로 넘어간다.
"""

import argparse
import glob
import os
import ssl
import sys
import time
import urllib.error
import urllib.request
from xml.sax.saxutils import escape

DEFAULT_VOICE = "ko-KR-SunHiNeural"
DEFAULT_LANGUAGE = "ko-KR"
# WAV(PCM)로 직접 받으므로 변환 단계가 없다.
DEFAULT_FORMAT = "riff-24khz-16bit-mono-pcm"
TIMEOUT = 60
MAX_RETRY_WAIT = 30.0


def _fail(message):
    print(f"[ERROR] {message}", file=sys.stderr)
    sys.exit(1)


def _env(name):
    value = os.environ.get(name, "").strip()
    if value or os.name != "nt":
        return value
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            return str(winreg.QueryValueEx(key, name)[0]).strip()
    except OSError:
        return ""


def _credentials():
    key = _env("AZURE_SPEECH_KEY")
    region = _env("AZURE_SPEECH_REGION")
    if not key:
        _fail("AZURE_SPEECH_KEY 환경 변수가 없습니다.")
    if not region and not _env("AZURE_SPEECH_ENDPOINT"):
        _fail("AZURE_SPEECH_REGION 환경 변수가 없습니다.")
    return key, region


def _synth_endpoint(region):
    override = _env("AZURE_SPEECH_ENDPOINT")
    if override:
        return override.rstrip("/")
    return f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1"


def _voices_endpoint(region):
    override = _env("AZURE_SPEECH_ENDPOINT")
    if override:
        return override.rstrip("/").rsplit("/", 1)[0] + "/voices/list"
    return f"https://{region}.tts.speech.microsoft.com/cognitiveservices/voices/list"


def _ssl_context():
    """TLS 검사 장비(교내망 프록시 등) 뒤에서도 동작하도록 OS 신뢰 저장소를 우선 사용한다.

    OpenSSL 3는 Authority Key Identifier가 없는 사설 CA를 거부하는데, 그런 CA도
    Windows/macOS 신뢰 저장소에는 등록돼 있는 경우가 많다. truststore가 있으면
    검증을 OS에 위임하고, 없으면 기본 컨텍스트로 돌아간다(설치 필수 아님).
    """
    try:
        import truststore

        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except ImportError:
        bundle = os.environ.get("REQUESTS_CA_BUNDLE", "").strip()
        if bundle and os.path.isfile(bundle):
            return ssl.create_default_context(cafile=bundle)
        return ssl.create_default_context()


def _request(url, key, data=None, headers=None, method="GET", retries=0):
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Ocp-Apim-Subscription-Key", key)
    req.add_header("User-Agent", "azure_tts.py")
    for name, value in (headers or {}).items():
        req.add_header(name, value)
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT, context=_ssl_context()) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt < retries:
                time.sleep(_retry_after(exc.headers.get("Retry-After"), attempt))
                continue
            detail = ""
            try:
                detail = exc.read().decode("utf-8", "replace").strip()[:400]
            except Exception:
                pass
            # 키 값은 절대 출력하지 않는다.
            _fail(f"HTTP {exc.code} {exc.reason}. {detail}")
        except urllib.error.URLError as exc:
            _fail(f"네트워크 오류: {exc.reason}")
        except (TimeoutError, ConnectionError) as exc:
            _fail(f"네트워크 오류: {exc}")


def _retry_after(header, attempt):
    """Retry-After 초를 따르고, 없거나 이상하면 5·10·20초로 늘린다. 30초를 넘기지 않는다."""
    try:
        wait = float(header)
    except (TypeError, ValueError):
        wait = 5.0 * (2 ** attempt)
    return min(max(wait, 1.0), MAX_RETRY_WAIT)


def build_ssml(text, voice, language, rate, pitch=None, style=None):
    """SSML을 만든다. rate는 '+50%' 같은 상대값이나 'default'."""
    inner = escape(text)
    prosody_attrs = []
    if rate and rate != "default":
        prosody_attrs.append(f'rate="{escape(rate, {chr(34): "&quot;"})}"')
    if pitch:
        prosody_attrs.append(f'pitch="{escape(pitch, {chr(34): "&quot;"})}"')
    if prosody_attrs:
        inner = f"<prosody {' '.join(prosody_attrs)}>{inner}</prosody>"
    if style:
        inner = (
            f'<mstts:express-as style="{escape(style, {chr(34): "&quot;"})}">'
            f"{inner}</mstts:express-as>"
        )
    return (
        '<speak version="1.0" '
        'xmlns="http://www.w3.org/2001/10/synthesis" '
        'xmlns:mstts="http://www.w3.org/2001/mstts" '
        f'xml:lang="{escape(language)}">'
        f'<voice name="{escape(voice)}">{inner}</voice>'
        "</speak>"
    )


def tempo_to_rate(tempo):
    """배율(1.0 = 보통)을 SSML rate 퍼센트 문자열로 바꾼다.

    Azure의 prosody rate는 0.5~2배만 받으므로 그 범위로 자른다.
    """
    try:
        value = min(max(float(tempo), 0.5), 2.0)
    except (TypeError, ValueError):
        return "default"
    if abs(value - 1.0) < 0.01:
        return "default"
    percent = (value - 1.0) * 100.0
    return f"{percent:+.0f}%"


def list_voices(key, region, language):
    raw = _request(_voices_endpoint(region), key)
    import json

    voices = json.loads(raw.decode("utf-8"))
    rows = [v for v in voices if not language or v.get("Locale", "").lower() == language.lower()]
    rows.sort(key=lambda v: v.get("ShortName", ""))
    for v in rows:
        print(f"{v.get('ShortName'):<32} {v.get('Gender','?'):<8} {v.get('LocalName','')}")
    print(f"\n{len(rows)} voice(s)" + (f" for {language}" if language else ""))


def main():
    parser = argparse.ArgumentParser(
        description="Azure AI Speech TTS - 텍스트를 음성으로 변환 (기본: ko-KR-SunHiNeural)"
    )
    parser.add_argument("file", nargs="?", help="입력 파일 경로 (.txt, .md)")
    parser.add_argument("--voice", default=DEFAULT_VOICE, help=f"음성 (기본: {DEFAULT_VOICE})")
    parser.add_argument(
        "--language-code", dest="language_code", default=DEFAULT_LANGUAGE,
        help=f"언어 코드 (기본: {DEFAULT_LANGUAGE})",
    )
    parser.add_argument("--rate", default=None, help="SSML rate 예: +50%%, -20%%, default")
    parser.add_argument("--tempo", default=None, help="배율(1.0=보통). --rate 미지정 시 변환해 사용")
    parser.add_argument("--pitch", default=None, help="SSML pitch 예: +2st")
    parser.add_argument("--style", default=None, help="말하기 스타일 예: cheerful")
    parser.add_argument("--output-format", dest="output_format", default=DEFAULT_FORMAT)
    parser.add_argument("--output", default=None, help="출력 WAV 경로 직접 지정")
    parser.add_argument("--retries", type=int, default=0,
                        help="429(요청 과다) 때 다시 시도할 횟수. 기본 0(바로 실패)")
    parser.add_argument("--list-voices", action="store_true", help="음성 목록 출력")
    args = parser.parse_args()

    key, region = _credentials()

    if args.list_voices:
        list_voices(key, region, args.language_code)
        return

    if not args.file:
        args.file = next((f for ext in (".txt", ".md") for f in sorted(glob.glob(f"*{ext}"))), None)
        if not args.file:
            parser.error("입력 파일이 필요하다 (또는 --list-voices)")
        print(f"[INFO] 입력 파일 자동 선택: {args.file}")
    if not os.path.isfile(args.file):
        _fail(f"입력 파일이 없습니다: {args.file}")

    with open(args.file, "r", encoding="utf-8") as fh:
        text = fh.read().strip()
    if not text:
        _fail("입력 파일이 비어 있습니다.")

    rate = args.rate if args.rate else tempo_to_rate(args.tempo)
    ssml = build_ssml(text, args.voice, args.language_code, rate, args.pitch, args.style)

    audio = _request(
        _synth_endpoint(region),
        key,
        data=ssml.encode("utf-8"),
        headers={
            "Content-Type": "application/ssml+xml",
            "X-Microsoft-OutputFormat": args.output_format,
        },
        method="POST",
        retries=max(args.retries, 0),
    )
    if not audio:
        _fail("빈 오디오가 돌아왔습니다.")

    if args.output:
        out_path = args.output
    else:
        stem = os.path.splitext(args.file)[0]
        out_path = f"{stem}_azure_tts.wav"

    with open(out_path, "wb") as fh:
        fh.write(audio)

    print(f"[OK] Saved to: {out_path}")
    print(f"[VOICE] {args.voice} ({args.language_code}, rate={rate}, {len(audio)} bytes)")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3.12
"""
OpenAI TTS (Text-to-Speech) 스크립트
OpenAI Audio API(/v1/audio/speech)로 텍스트를 자연스러운 음성으로 변환합니다.

기본 모델: gpt-4o-mini-tts (current snapshot: gpt-4o-mini-tts-2025-12-15)
  - 13개 빌트인 음성 (alloy/ash/ballad/coral/echo/fable/nova/onyx/sage/shimmer/verse/marin/cedar)
  - 자연어 `instructions` 파라미터로 톤·악센트·감정·속도·속삭임 스티어링
  - 한도: 입력 4,096자 / 2,000 토큰(초과 시 자동 청크 분할)
  - 한국어 본문도 지원 (음성은 영어 최적화)

사용법:
    python openai_tts.py [파일경로 또는 "텍스트"] [옵션]

옵션:
    --voice NAME            음성 선택 (기본: marin). marin/cedar 권장.
    --model NAME            모델 override (기본: gpt-4o-mini-tts)
    --format FMT            출력 포맷: mp3|opus|aac|flac|wav|pcm (기본: mp3)
    --speed FLOAT           재생 속도 0.25-4.0 (기본: 1.0)
    --instructions TEXT     자연어 톤 지시 (gpt-4o-mini-tts 전용)
    --chunk-size N          청크당 최대 글자 수 (기본: 3000, max 4096)
    --list-voices           음성 목록 출력
    --list-models           모델 목록 출력

환경 변수:
    OPENAI_API_KEY          OpenAI API 키 (gpt_realtime.py와 공용)

입력: .txt, .md 파일 또는 명령줄 텍스트 인자
출력: [파일명]_openai.mp3 (포맷 변경 시 확장자 자동 반영)

스티어링 예시 (--instructions):
    "Speak in a cheerful and positive tone."
    "British accent, slow pace, like teaching a child."
    "Whisper softly, intimate and warm."
    "Calm, professional narrator voice for an audiobook."

주의:
    - tts-1 / tts-1-hd는 --instructions 미지원 (gpt-4o-mini-tts 전용 기능)
    - 4,096자 초과 시 문장 경계로 자동 분할 후 MP3 바이트 concat (mp3/opus/aac만 안전)
    - 사용 정책상 합성 음성임을 최종 사용자에게 명시 의무

참고:
    https://developers.openai.com/api/docs/guides/text-to-speech
    https://platform.openai.com/playground/tts  (음성 미리듣기)
"""

import argparse
import glob
import os
import re
import sys


DEFAULT_MODEL = "gpt-4o-mini-tts"
DEFAULT_VOICE = "marin"
DEFAULT_FORMAT = "mp3"
DEFAULT_SPEED = 1.0
DEFAULT_CHUNK_SIZE = 3000  # 4,096자 한도 안전 마진, ~750 토큰 (2,000 한도 안전)
HARD_CHAR_LIMIT = 4096

API_URL = "https://api.openai.com/v1/audio/speech"

# 13개 빌트인 음성. gpt-4o-mini-tts 전체 지원, tts-1/hd는 9개만 (verse/marin/cedar 제외)
AVAILABLE_VOICES = [
    ("alloy",   "중성적이고 차분한 톤"),
    ("ash",     "에너지 있고 명확한 남성 톤"),
    ("ballad",  "부드럽고 서정적인 톤"),
    ("coral",   "따뜻하고 친근한 톤 (공식 가이드 예시)"),
    ("echo",    "낮고 차분한 남성 톤"),
    ("fable",   "이야기꾼 스타일, 영국식 억양"),
    ("nova",    "젊고 밝은 여성 톤"),
    ("onyx",    "깊고 권위 있는 남성 톤"),
    ("sage",    "지적이고 신중한 톤"),
    ("shimmer", "밝고 표현력 있는 여성 톤"),
    ("verse",   "다재다능한 표현형 톤 (gpt-4o-mini-tts 전용)"),
    ("marin",   "OpenAI 공식 권장. 자연스럽고 균형 잡힌 톤 (기본값)"),
    ("cedar",   "OpenAI 공식 권장. 무게감 있는 톤"),
]

LEGACY_ONLY_VOICES = {"alloy", "ash", "coral", "echo", "fable", "onyx", "nova", "sage", "shimmer"}

KNOWN_MODELS = [
    ("gpt-4o-mini-tts",            "최신 권장. instructions 스티어링·13개 음성·SSE 스트리밍 (기본값)"),
    ("gpt-4o-mini-tts-2025-12-15", "최신 dated 스냅샷. 재현성 보장용 고정 버전"),
    ("gpt-4o-mini-tts-2025-03-20", "이전 dated 스냅샷"),
    ("tts-1-hd",                   "구형 고품질. instructions 미지원, 9개 음성"),
    ("tts-1",                      "구형 저지연. instructions 미지원, 9개 음성"),
]

SUPPORTED_FORMATS = ["mp3", "opus", "aac", "flac", "wav", "pcm"]
SAFE_CONCAT_FORMATS = {"mp3", "opus", "aac"}  # 바이트 concat 가능한 스트림 포맷

SUPPORTED_EXTENSIONS = [".txt", ".md"]

# 문장 경계 정규식: 한국어 종결어미·문장부호 + 영어 문장부호
SENTENCE_BOUNDARY = re.compile(
    r"(?<=[.!?])\s+|(?<=[다요죠까네음군지])\.\s+|(?<=[다요죠까네음군지])(?=[\s\n])",
    re.UNICODE,
)


def find_input_file():
    """현재 디렉토리에서 지원되는 텍스트 파일 자동 탐색"""
    for ext in SUPPORTED_EXTENSIONS:
        files = glob.glob(f"*{ext}")
        if files:
            return files[0]
    return None


def get_output_filename(input_file, fmt):
    ext = "wav" if fmt == "pcm" else fmt
    dir_path = os.path.dirname(os.path.abspath(input_file))
    base = os.path.splitext(os.path.basename(input_file))[0]
    return os.path.join(dir_path, f"{base}_openai.{ext}")


def list_voices():
    print("\n사용 가능한 OpenAI TTS 음성 (13개):")
    print("-" * 70)
    for name, desc in AVAILABLE_VOICES:
        legacy_mark = "  (tts-1/hd 공통)" if name in LEGACY_ONLY_VOICES else "  (gpt-4o-mini-tts 전용)"
        print(f"  {name:<10}{legacy_mark}")
        print(f"  {'':<10}  {desc}")
    print("-" * 70)
    print("\n공식 권장: marin, cedar")
    print("미리듣기: https://platform.openai.com/playground/tts 또는 https://openai.fm")
    print("\n사용 예:")
    print("  python openai_tts.py input.txt --voice marin")
    print('  python openai_tts.py input.txt --voice coral --instructions "Cheerful and friendly"')


def list_models():
    print("\n사용 가능한 OpenAI TTS 모델:")
    print("-" * 70)
    for name, desc in KNOWN_MODELS:
        print(f"  {name}")
        print(f"    {desc}")
    print("-" * 70)


def validate_voice(name):
    for v, _ in AVAILABLE_VOICES:
        if v.lower() == name.lower():
            return v
    return None


def split_text_into_chunks(text, max_chars):
    """문장 경계로 분할 → 청크당 max_chars 이하가 되도록 묶음.

    1) 문장 경계로 분할.
    2) 문장이 단독으로 max_chars를 초과하면 콤마·공백으로 추가 분할.
    3) 그래도 초과하면 글자 단위로 hard cut.
    """
    if len(text) <= max_chars:
        return [text]

    sentences = [s.strip() for s in SENTENCE_BOUNDARY.split(text) if s and s.strip()]
    if not sentences:
        sentences = [text]

    chunks = []
    buf = ""
    for sent in sentences:
        if len(sent) > max_chars:
            if buf:
                chunks.append(buf)
                buf = ""
            for sub in _hard_split(sent, max_chars):
                chunks.append(sub)
            continue

        candidate = (buf + " " + sent).strip() if buf else sent
        if len(candidate) <= max_chars:
            buf = candidate
        else:
            chunks.append(buf)
            buf = sent
    if buf:
        chunks.append(buf)
    return chunks


def _hard_split(text, max_chars):
    """과대 문장을 콤마 → 공백 → 글자 순으로 잘라 max_chars 이하 조각으로 변환."""
    for delim in [", ", " "]:
        if delim in text:
            parts = text.split(delim)
            out, buf = [], ""
            for p in parts:
                candidate = (buf + delim + p) if buf else p
                if len(candidate) <= max_chars:
                    buf = candidate
                else:
                    if buf:
                        out.append(buf)
                    buf = p
            if buf:
                out.append(buf)
            if all(len(s) <= max_chars for s in out):
                return out
    return [text[i:i + max_chars] for i in range(0, len(text), max_chars)]


def synthesize_chunk(api_key, model, voice, text, fmt, speed, instructions):
    """단일 청크를 합성하여 오디오 바이트 반환"""
    try:
        import requests
    except ImportError:
        print(f"오류: requests 패키지가 필요합니다. (Python: {sys.executable})")
        print(f'설치: "{sys.executable}" -m pip install requests')
        sys.exit(1)

    payload = {
        "model": model,
        "voice": voice,
        "input": text,
        "response_format": fmt,
        "speed": speed,
    }
    if instructions and model.startswith("gpt-4o-mini-tts"):
        payload["instructions"] = instructions
    elif instructions:
        print(f"경고: {model}은 --instructions 미지원입니다. 무시됨.")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    resp = requests.post(API_URL, headers=headers, json=payload, timeout=180)
    if resp.status_code != 200:
        try:
            err = resp.json().get("error", {})
            msg = err.get("message", resp.text)
        except Exception:
            msg = resp.text
        raise RuntimeError(f"API 오류 (HTTP {resp.status_code}): {msg}")
    return resp.content


def main():
    parser = argparse.ArgumentParser(
        description="OpenAI TTS - 텍스트를 음성으로 변환 (기본: gpt-4o-mini-tts)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  기본 변환:
    python openai_tts.py input.txt
    python openai_tts.py "안녕하세요. 오늘 날씨가 참 좋네요."

  스티어링 (gpt-4o-mini-tts 전용):
    python openai_tts.py input.txt --instructions "Speak cheerfully and warmly"
    python openai_tts.py input.txt --voice cedar --instructions "Calm narrator voice"

  음성·포맷·속도 변경:
    python openai_tts.py input.txt --voice coral --format wav --speed 1.2

  긴 문서 (자동 청크 분할):
    python openai_tts.py long_article.md            # 4096자 초과 시 자동 분할 + concat

  목록 조회:
    python openai_tts.py --list-voices
    python openai_tts.py --list-models
        """,
    )
    parser.add_argument("input", nargs="?",
                        help="입력 파일 경로 또는 직접 텍스트")
    parser.add_argument("--voice", default=DEFAULT_VOICE,
                        help=f"음성 (기본: {DEFAULT_VOICE}). --list-voices로 확인")
    parser.add_argument("--model", default=DEFAULT_MODEL,
                        help=f"모델 (기본: {DEFAULT_MODEL})")
    parser.add_argument("--format", dest="fmt", default=DEFAULT_FORMAT,
                        choices=SUPPORTED_FORMATS,
                        help=f"출력 포맷 (기본: {DEFAULT_FORMAT})")
    parser.add_argument("--speed", type=float, default=DEFAULT_SPEED,
                        help=f"속도 0.25-4.0 (기본: {DEFAULT_SPEED})")
    parser.add_argument("--instructions",
                        help="자연어 스티어링 (gpt-4o-mini-tts 전용)")
    parser.add_argument("--chunk-size", dest="chunk_size", type=int,
                        default=DEFAULT_CHUNK_SIZE,
                        help=f"청크당 최대 글자 (기본: {DEFAULT_CHUNK_SIZE}, max {HARD_CHAR_LIMIT})")
    parser.add_argument("--list-voices", action="store_true", help="음성 목록 출력")
    parser.add_argument("--list-models", action="store_true", help="모델 목록 출력")

    args = parser.parse_args()

    if args.list_voices:
        list_voices()
        return
    if args.list_models:
        list_models()
        return

    # 유효성 검증
    if not (0.25 <= args.speed <= 4.0):
        print(f"오류: --speed는 0.25-4.0 범위여야 합니다. (입력값: {args.speed})")
        return

    if args.chunk_size > HARD_CHAR_LIMIT:
        print(f"오류: --chunk-size는 {HARD_CHAR_LIMIT} 이하여야 합니다.")
        return

    voice = validate_voice(args.voice)
    if not voice:
        print(f"오류: 알 수 없는 음성: {args.voice}")
        print("--list-voices 옵션으로 사용 가능한 음성을 확인하세요.")
        return

    if voice not in LEGACY_ONLY_VOICES and args.model in ("tts-1", "tts-1-hd"):
        print(f"오류: '{voice}' 음성은 {args.model}에서 지원하지 않습니다.")
        print(f"가능한 음성: {', '.join(sorted(LEGACY_ONLY_VOICES))}")
        return

    if args.fmt not in SAFE_CONCAT_FORMATS:
        # 청크 분할이 필요한지 미리 알 수 없으므로, 위험만 알린다
        pass

    try:
        api_key = os.environ["OPENAI_API_KEY"]
    except KeyError:
        print("오류: OPENAI_API_KEY 환경 변수가 설정되지 않았습니다.")
        print('설정: setx OPENAI_API_KEY "your-key"  (Windows)')
        print('      export OPENAI_API_KEY="your-key"  (macOS/Linux)')
        return

    # 입력 텍스트 결정: 파일 경로 vs 직접 텍스트 vs 자동 탐색
    if args.input and os.path.exists(args.input):
        input_file = args.input
        ext = os.path.splitext(input_file)[1].lower()
        if ext not in SUPPORTED_EXTENSIONS:
            print(f"오류: 지원하지 않는 파일 형식: {ext}")
            print(f"지원: {', '.join(SUPPORTED_EXTENSIONS)}")
            return
        with open(input_file, "r", encoding="utf-8") as f:
            text = f.read().strip()
        output_file = get_output_filename(input_file, args.fmt)
    elif args.input:
        # 파일이 아니면 직접 텍스트로 간주
        text = args.input.strip()
        output_file = get_output_filename("output.txt", args.fmt)
    else:
        input_file = find_input_file()
        if not input_file:
            print("오류: 입력 파일을 찾을 수 없습니다.")
            print('사용법: python openai_tts.py <파일경로 또는 "텍스트">')
            print(f"지원 형식: {', '.join(SUPPORTED_EXTENSIONS)}")
            return
        with open(input_file, "r", encoding="utf-8") as f:
            text = f.read().strip()
        output_file = get_output_filename(input_file, args.fmt)

    if not text:
        print("오류: 입력 텍스트가 비어있습니다.")
        return

    # 청크 분할
    chunks = split_text_into_chunks(text, args.chunk_size)

    print(f"텍스트 길이: {len(text)}자")
    print(f"모델: {args.model} / 음성: {voice} / 포맷: {args.fmt} / 속도: {args.speed}")
    if args.instructions:
        print(f"스티어링: {args.instructions[:60]}{'...' if len(args.instructions) > 60 else ''}")
    if len(chunks) > 1:
        print(f"청크 {len(chunks)}개로 분할 ({args.chunk_size}자 단위)")
        if args.fmt not in SAFE_CONCAT_FORMATS:
            print(f"  ⚠ {args.fmt} 포맷은 단순 concat이 안전하지 않을 수 있음. mp3/opus/aac 권장.")

    # 청크별 합성
    audio_parts = []
    for i, chunk in enumerate(chunks, 1):
        if len(chunks) > 1:
            print(f"  [{i}/{len(chunks)}] {len(chunk)}자 합성 중...")
        else:
            print("음성 변환 중...")
        try:
            audio_bytes = synthesize_chunk(
                api_key, args.model, voice, chunk,
                args.fmt, args.speed, args.instructions,
            )
        except RuntimeError as e:
            print(f"오류: {e}")
            return
        audio_parts.append(audio_bytes)

    # 결합 및 저장
    combined = b"".join(audio_parts)
    with open(output_file, "wb") as f:
        f.write(combined)

    size_kb = len(combined) / 1024
    print(f"\n저장 완료: {output_file} ({size_kb:.1f} KB)")
    print("ℹ 사용 정책: AI 합성 음성임을 최종 사용자에게 명시할 의무가 있습니다.")


if __name__ == "__main__":
    main()

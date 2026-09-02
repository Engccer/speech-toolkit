"""
Meta Muse Voice Transcribe STT 스크립트
음성/영상 파일을 텍스트로 전사하며, 화자 구분(diarization)을 지원합니다.

사용법:
    python muse_stt.py [입력파일] [--lang ko] [--timestamps] [--no-diarize]

    입력파일을 지정하지 않으면 현재 디렉토리에서 지원 확장자 파일을 자동 탐색합니다.

출력:
    [파일명]_muse.txt (입력 파일과 같은 디렉토리에 저장)
    --timestamps 지정 시 [파일명]_muse_ts.txt 추가 저장

환경변수:
    META_API_KEY: Meta Model API 키 (https://dev.meta.ai/ 에서 발급)
                  Meta 공식 문서 예제가 쓰는 MODEL_API_KEY도 대체로 읽습니다.

모델:
    muse-voice-transcribe-1.0 ($0.18/오디오 시간, 초 단위 과금)

언어 (선택):
    --lang <이름|코드>  languageBias 힌트 (기본 ko). 쉼표로 여러 개 지정 가능.
                        예: --lang ko / --lang ko,en / --lang Korean,English
                        코드 스위칭을 강제하지 않는 힌트이며, --lang none 으로 끌 수 있습니다.

화자 분리:
    기본 DIARIZATION 모드로 화자 라벨(A, B, ...)을 받습니다.
    --no-diarize 를 주면 ENDPOINTING 모드로 발화 경계만 나눕니다.

    주의: 화자 라벨은 세션 범위입니다. 10분을 넘겨 자동 분할되면 조각마다 라벨이
    새로 시작하므로 조각 간 화자 A가 동일 인물이라는 보장이 없습니다.
    출력 파일 머리말에 이 경고가 함께 기록됩니다.

키워드 프롬프팅 (선택):
    입력 파일과 같은 디렉토리에 keyterms.txt가 있으면 자동 로드해 keywords로 전달합니다.
    - 한 줄에 한 키워드, '#'으로 시작하는 줄과 빈 줄은 무시
    - 고유명사·기관명·약어 인식률을 올리지만 표기를 보장하지는 않습니다.

API 제약 (파일 전사 엔드포인트):
    - 입력은 mono 16-bit PCM WAV(16kHz 또는 24kHz)만 허용 → ffmpeg로 자동 변환
    - 요청당 오디오 10분 / 본문 32MB 상한 → 9분 단위로 자동 분할
    - 단어 단위 타임스탬프·감정·음향 이벤트는 제공하지 않습니다(턴 단위 시각만).

필요 패키지:
    pip install requests
    ffmpeg/ffprobe가 PATH에 있어야 합니다(입력 변환·분할에 사용).
"""

import argparse
import glob
import os
import shutil
import subprocess
import sys
import tempfile
import time
import traceback

API_URL = "https://api.meta.ai/v1/asr/transcribe"
MODEL = "muse-voice-transcribe-1.0"

# API 상한은 10분/32MB. 24kHz mono 16-bit는 초당 48KB이므로
# 9분 조각 = 약 25.9MB로 두 상한 모두 안전하게 밑돈다.
CHUNK_SECONDS = 540
SAMPLE_RATE = 24000

SUPPORTED_EXTENSIONS = [
    ".mp3", ".m4a", ".wav", ".flac", ".aac", ".ogg", ".aiff",
    ".mp4", ".mov", ".avi", ".webm", ".mkv",
]

# languageBias는 언어 이름 문자열을 받는다. 흔한 코드를 이름으로 옮긴다.
LANGUAGE_NAMES = {
    "ar": "Arabic", "bn": "Bengali", "nl": "Dutch", "en": "English",
    "fr": "French", "de": "German", "he": "Hebrew", "hi": "Hindi",
    "id": "Indonesian", "it": "Italian", "ja": "Japanese", "kn": "Kannada",
    "ko": "Korean", "ms": "Malay", "zh": "Mandarin Chinese", "mr": "Marathi",
    "pl": "Polish", "pt": "Portuguese", "es": "Spanish", "tl": "Tagalog",
    "ta": "Tamil", "te": "Telugu", "th": "Thai", "tr": "Turkish",
    "vi": "Vietnamese",
}


def get_output_filename(input_file):
    """입력 파일 경로를 기반으로 출력 파일 경로 생성"""
    dir_path = os.path.dirname(os.path.abspath(input_file))
    base_name = os.path.splitext(os.path.basename(input_file))[0]
    return os.path.join(dir_path, f"{base_name}_muse.txt")


def find_input_file():
    """현재 디렉토리에서 입력 파일을 찾습니다."""
    for ext in SUPPORTED_EXTENSIONS:
        files = glob.glob(f"*{ext}")
        if files:
            return files[0]
    return None


def load_keywords(input_file):
    """입력 파일과 같은 디렉토리에서 keyterms.txt를 찾아 키워드 목록 반환."""
    path = os.path.join(os.path.dirname(os.path.abspath(input_file)), "keyterms.txt")
    if not os.path.exists(path):
        return []
    keywords = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            term = line.strip()
            if term and not term.startswith("#"):
                keywords.append(term)
    return keywords


def parse_language_bias(value):
    """--lang 값을 languageBias 배열로 변환합니다. 'none'이면 빈 목록."""
    if not value or value.strip().lower() == "none":
        return []
    names = []
    for token in value.split(","):
        token = token.strip()
        if not token:
            continue
        names.append(LANGUAGE_NAMES.get(token.lower(), token))
    return names


def probe_duration(path):
    """ffprobe로 재생 길이(초)를 구합니다. 실패하면 None."""
    if not shutil.which("ffprobe"):
        return None
    try:
        out = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                path,
            ],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        return float(out)
    except (subprocess.CalledProcessError, ValueError):
        return None


def convert_to_wav(path, workdir, chunk_seconds=None):
    """입력을 API가 받는 mono 16-bit PCM WAV로 변환합니다.

    chunk_seconds가 주어지면 그 길이 단위로 분할해 여러 파일을 만듭니다.
    변환된 WAV 경로 목록을 순서대로 반환합니다.
    """
    common = [
        "ffmpeg", "-v", "error", "-y", "-i", path,
        "-vn", "-ac", "1", "-ar", str(SAMPLE_RATE), "-c:a", "pcm_s16le",
        "-map_metadata", "-1",
    ]
    if chunk_seconds:
        pattern = os.path.join(workdir, "chunk_%03d.wav")
        subprocess.run(
            common + ["-f", "segment", "-segment_time", str(chunk_seconds), pattern],
            check=True,
        )
        return sorted(glob.glob(os.path.join(workdir, "chunk_*.wav")))

    out = os.path.join(workdir, "audio.wav")
    subprocess.run(common + [out], check=True)
    return [out]


def format_timestamp(seconds):
    """초를 HH:MM:SS 형식으로 변환합니다."""
    total = int(seconds)
    return f"{total // 3600:02d}:{(total % 3600) // 60:02d}:{total % 60:02d}"


def transcribe_chunk(requests, api_key, wav_path, request_settings, session_id):
    """WAV 한 조각을 전사해 응답 JSON을 반환합니다."""
    import json

    last_error = None
    for attempt in range(3):
        with open(wav_path, "rb") as audio:
            response = requests.post(
                API_URL,
                params={"sessionId": session_id},
                headers={"Authorization": f"Bearer {api_key}"},
                files={
                    "request": (None, json.dumps(request_settings), "application/json"),
                    "audio": (os.path.basename(wav_path), audio, "audio/wav"),
                },
                timeout=600,
            )

        if response.status_code == 200:
            return response.json()

        # 동시 스트림 8개·시간당 1000개 제한이 있어 429는 재시도 가치가 있다.
        if response.status_code == 429 or response.status_code >= 500:
            last_error = f"HTTP {response.status_code}: {response.text[:300]}"
            wait = 2 ** attempt * 5
            print(f"  재시도 대기 {wait}초 ({last_error})")
            time.sleep(wait)
            continue

        raise RuntimeError(f"API 오류 HTTP {response.status_code}: {response.text[:500]}")

    raise RuntimeError(f"재시도 후에도 실패했습니다. {last_error}")


def collect_turns(result, time_offset, chunk_label=None):
    """응답의 turns를 (시작초, 화자, 텍스트) 목록으로 정규화합니다."""
    turns = []
    for turn in result.get("turns") or []:
        text = (turn.get("transcript") or "").strip()
        if not text:
            continue
        start = turn.get("startMs")
        start_sec = (start / 1000.0 + time_offset) if isinstance(start, (int, float)) else time_offset
        speaker = turn.get("speaker")
        if speaker and chunk_label:
            speaker = f"{chunk_label}-{speaker}"
        turns.append((start_sec, speaker, text))
    return turns


def render_grouped(turns):
    """같은 화자의 연속 발화를 묶어 본문을 만듭니다."""
    if not any(speaker for _, speaker, _ in turns):
        return " ".join(text for _, _, text in turns)

    lines = []
    current = None
    buffer = []
    for _, speaker, text in turns:
        if speaker != current:
            if buffer:
                lines.append(" ".join(buffer))
                lines.append("")
            lines.append(f"[화자 {speaker}]" if speaker else "[화자 미상]")
            current = speaker
            buffer = [text]
        else:
            buffer.append(text)
    if buffer:
        lines.append(" ".join(buffer))
    return "\n".join(lines)


def render_timestamped(turns):
    """발화마다 [HH:MM:SS]와 화자를 붙인 판을 만듭니다."""
    lines = []
    for start, speaker, text in turns:
        prefix = f"[{format_timestamp(start)}]"
        if speaker:
            prefix += f" [화자 {speaker}]"
        lines.append(f"{prefix} {text}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Meta Muse Voice Transcribe STT")
    parser.add_argument("input_file", nargs="?", help="입력 오디오/비디오 파일 경로")
    parser.add_argument(
        "--lang", default="ko",
        help="languageBias 힌트 (기본 ko). 쉼표로 여러 개, 'none'이면 미지정.",
    )
    parser.add_argument(
        "--no-diarize", action="store_true",
        help="화자 분리를 끄고 ENDPOINTING 모드로 발화 경계만 나눕니다.",
    )
    parser.add_argument(
        "--timestamps", action="store_true",
        help="[파일명]_muse_ts.txt에 발화별 [HH:MM:SS]·화자를 붙인 판을 함께 저장.",
    )
    args = parser.parse_args()

    try:
        import requests
    except ImportError as e:
        print("오류: requests 패키지를 찾을 수 없습니다.")
        print("설치 명령: pip install requests")
        print(f"상세: {e}")
        return

    api_key = os.environ.get("META_API_KEY") or os.environ.get("MODEL_API_KEY")
    if not api_key:
        print("오류: META_API_KEY 환경 변수가 설정되지 않았습니다.")
        print('설정 명령: export META_API_KEY="your-api-key"  (Windows: setx META_API_KEY "your-api-key")')
        print("키 발급: https://dev.meta.ai/")
        return

    if not shutil.which("ffmpeg"):
        print("오류: ffmpeg를 찾을 수 없습니다.")
        print("Muse 파일 전사 API는 mono 16-bit PCM WAV만 받으므로 변환에 ffmpeg가 필요합니다.")
        return

    if args.input_file:
        input_file = args.input_file
        print(f"입력 경로: {input_file}")
        ext = os.path.splitext(input_file)[1].lower()
        if ext not in SUPPORTED_EXTENSIONS:
            print(f"오류: 지원하지 않는 파일 형식입니다: {ext}")
            print(f"지원 형식: {', '.join(SUPPORTED_EXTENSIONS)}")
            return
        if not os.path.exists(input_file):
            print(f"오류: 파일을 찾을 수 없습니다: {input_file}")
            return
    else:
        input_file = find_input_file()
        if not input_file:
            print("오류: 입력 파일을 찾을 수 없습니다.")
            print(f"지원 형식: {', '.join(SUPPORTED_EXTENSIONS)}")
            return

    mode = "ENDPOINTING" if args.no_diarize else "DIARIZATION"
    language_bias = parse_language_bias(args.lang)
    keywords = load_keywords(input_file)

    print(f"입력 파일: {input_file}")
    print(f"모드: {mode}")
    print(f"언어 힌트: {', '.join(language_bias) if language_bias else '없음'}")
    if keywords:
        preview = ", ".join(keywords[:5])
        print(f"키워드 {len(keywords)}개 적용: {preview}{' ...' if len(keywords) > 5 else ''}")

    request_settings = {
        "model": MODEL,
        "mode": mode,
        "audioEncoding": "WAV",
    }
    if language_bias:
        request_settings["languageBias"] = language_bias
    if keywords:
        request_settings["keywords"] = keywords

    duration = probe_duration(input_file)
    if duration:
        print(f"재생 길이: {format_timestamp(duration)}")
    needs_split = duration is None or duration > CHUNK_SECONDS

    session_base = f"muse-{os.getpid()}"
    all_turns = []
    split_note = None

    with tempfile.TemporaryDirectory(prefix="muse_stt_") as workdir:
        print("오디오 변환 중 (mono 16-bit PCM WAV 24kHz)...")
        try:
            wavs = convert_to_wav(
                input_file, workdir,
                chunk_seconds=CHUNK_SECONDS if needs_split else None,
            )
        except subprocess.CalledProcessError as e:
            print(f"오류: ffmpeg 변환에 실패했습니다. {e}")
            return

        if len(wavs) > 1:
            print(f"분할 완료: {len(wavs)}개 조각 (요청당 10분 상한)")
            if mode == "DIARIZATION":
                split_note = (
                    f"# 주의: 입력이 {len(wavs)}개 조각으로 분할 전사되었습니다. "
                    "화자 라벨은 조각(세션)마다 새로 매겨지므로 조각 번호를 앞에 붙였습니다. "
                    "서로 다른 조각의 같은 알파벳이 동일 인물이라는 보장은 없습니다."
                )
            else:
                split_note = f"# 주의: 입력이 {len(wavs)}개 조각으로 분할 전사되었습니다."

        offset = 0.0
        for index, wav in enumerate(wavs):
            if len(wavs) > 1:
                print(f"전사 중... ({index + 1}/{len(wavs)}, 시작 {format_timestamp(offset)})")
            else:
                print("전사 중...")

            try:
                result = transcribe_chunk(
                    requests, api_key, wav, request_settings,
                    f"{session_base}-{index:03d}",
                )
            except RuntimeError as e:
                print(f"오류: {e}")
                return

            chunk_label = f"{index + 1}" if len(wavs) > 1 else None
            all_turns.extend(collect_turns(result, offset, chunk_label))

            chunk_duration = probe_duration(wav)
            offset += chunk_duration if chunk_duration else CHUNK_SECONDS

    if not all_turns:
        print("오류: 전사 결과가 비어있습니다.")
        return

    body = render_grouped(all_turns)
    transcript = f"{split_note}\n\n{body}" if split_note else body

    output_file = get_output_filename(input_file)
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(transcript)

    print(f"\n전사 완료! {len(transcript)}글자가 저장되었습니다.")
    print(f"출력 파일: {output_file}")

    if args.timestamps:
        ts_file = output_file.replace("_muse.txt", "_muse_ts.txt")
        ts_body = render_timestamped(all_turns)
        with open(ts_file, "w", encoding="utf-8") as f:
            f.write(f"{split_note}\n\n{ts_body}" if split_note else ts_body)
        print(f"타임스탬프 판: {ts_file}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n오류 발생: {e}")
        print("\n상세 정보:")
        traceback.print_exc()

    try:
        if sys.stdin.isatty():
            input("\nEnter를 눌러 종료...")
    except EOFError:
        pass

"""
Gemini 3.5 Transcribe STT 스크립트
전용 음성인식 모델(gemini-3.5-transcribe)로 음성/영상 파일을 텍스트로 전사합니다.
화자 분리, 단어 단위 타임스탬프, 커스텀 어휘 바이어싱을 API 정식 파라미터로 지원합니다.

사용법:
    python gemini_transcribe_stt.py [입력파일] [--mode smart|verbatim] [--lang ko-KR]
                                    [--no-diarize] [--word-timestamps] [--vocab FILE]

    입력파일을 지정하지 않으면 현재 디렉토리에서 지원 확장자 파일을 자동 탐색합니다.

출력:
    [파일명]_gemini_transcribe.txt (입력 파일과 같은 디렉토리에 저장)

환경변수:
    GEMINI_API_KEY: Gemini API 키

전사 모드:
    --mode verbatim  (기본) 축어 전사. 화자 분리·타임스탬프를 켤 수 있음
    --mode smart     간투사 제거, 자기수정 반영, 자동 문단·목록 구조화
                     주의: smart 모드는 화자 분리·타임스탬프와 병용 불가(API 제약)

화자 분리:
    기본 활성(최대 8명, 3명 이상은 API 문서상 experimental). --no-diarize로 해제.

길이 상한 (API 제약, 초과분은 ffmpeg로 자동 분할):
    화자 분리 또는 단어 타임스탬프 사용 시  30분/요청
    둘 다 끈 경우                           60분/요청

커스텀 어휘 (선택):
    입력 파일과 같은 디렉토리에 keyterms.txt가 있으면 자동 로드하여 custom_vocabulary로 전달.
    - 한 줄에 한 용어, 샵(#)으로 시작하는 줄과 빈 줄은 무시
    - API 상한 1000개, 문서 권장은 100개 이하
    - --vocab <파일>로 다른 경로 지정, --no-keyterms로 자동 로드 해제

필요 패키지:
    pip install google-genai   (2.19.0에서 client.interactions 확인)
분할 기능에는 ffmpeg/ffprobe가 PATH에 있어야 합니다.
"""

import os
import sys
import glob
import shutil
import subprocess
import tempfile
import traceback

MODEL = "gemini-3.5-transcribe"

MIME_TYPES = {
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".wav": "audio/wav",
    ".flac": "audio/flac",
    ".aac": "audio/aac",
    ".ogg": "audio/ogg",
    ".aiff": "audio/aiff",
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".avi": "video/x-msvideo",
    ".webm": "video/webm",
}


def get_output_filename(input_file):
    """입력 파일 경로를 기반으로 출력 파일 경로 생성"""
    dir_path = os.path.dirname(os.path.abspath(input_file))
    base_name = os.path.splitext(os.path.basename(input_file))[0]
    return os.path.join(dir_path, f"{base_name}_gemini_transcribe.txt")


def find_input_file():
    """현재 디렉토리에서 입력 파일을 찾습니다."""
    for ext in MIME_TYPES:
        files = glob.glob(f"*{ext}")
        if files:
            return files[0]
    return None


def load_vocabulary(path):
    """어휘 파일에서 용어 목록을 읽습니다. 주석 줄과 빈 줄은 무시."""
    terms = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                terms.append(line)
    return terms


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


def split_audio(path, chunk_seconds, workdir):
    """ffmpeg로 오디오를 chunk_seconds 단위 mp3로 분할합니다. 분할 파일 경로 목록 반환."""
    pattern = os.path.join(workdir, "chunk_%03d.mp3")
    subprocess.run(
        [
            "ffmpeg", "-v", "error", "-y", "-i", path,
            "-vn", "-ac", "1", "-ar", "16000", "-b:a", "64k",
            "-f", "segment", "-segment_time", str(chunk_seconds),
            pattern,
        ],
        check=True,
    )
    return sorted(glob.glob(os.path.join(workdir, "chunk_*.mp3")))


def parse_offset(value):
    """오프셋 문자열(예: 1.234s)을 초(float)로 변환합니다. 파싱 불가면 None."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if text.endswith("s"):
        text = text[:-1]
    try:
        return float(text)
    except ValueError:
        return None


def format_timestamp(seconds):
    """초를 H:MM:SS 형식으로 변환합니다."""
    total = int(seconds)
    return f"{total // 3600}:{(total % 3600) // 60:02d}:{total % 60:02d}"


def extract_word_annotations(interaction):
    """응답에서 word_info 주석을 순서대로 수집합니다."""
    words = []
    for step in getattr(interaction, "steps", None) or []:
        for content in getattr(step, "content", None) or []:
            for annotation in getattr(content, "annotations", None) or []:
                if getattr(annotation, "type", None) == "word_info":
                    words.append(annotation)
    return words


def build_turns(words, time_offset=0.0):
    """단어 주석을 화자 단위 발화로 묶습니다. (화자, 시작, 끝, 텍스트) 튜플 목록 반환."""
    turns = []
    for w in words:
        speaker = getattr(w, "speaker", None)
        text = getattr(w, "text", "") or ""
        start = parse_offset(getattr(w, "start_offset", None))
        end = parse_offset(getattr(w, "end_offset", None))
        if start is not None:
            start += time_offset
        if end is not None:
            end += time_offset

        if turns and turns[-1][0] == speaker:
            prev = turns[-1]
            turns[-1] = (
                prev[0],
                prev[1] if prev[1] is not None else start,
                end if end is not None else prev[2],
                f"{prev[3]} {text}".strip(),
            )
        else:
            turns.append((speaker, start, end, text))
    return turns


def render_turns(turns):
    """화자 발화 목록을 출력 텍스트로 렌더링합니다."""
    lines = []
    for speaker, start, end, text in turns:
        prefix = f"[{speaker}] " if speaker else ""
        if start is not None and end is not None:
            prefix += f"({format_timestamp(start)} - {format_timestamp(end)}) "
        lines.append(f"{prefix}{text}")
    return "\n".join(lines)


def upload_file(client, path, mime_type):
    """Files API로 업로드하고 ACTIVE 상태가 될 때까지 대기합니다."""
    import time

    # 비ASCII 파일명은 업로드에서 문제가 되므로 임시 ASCII 경로로 복사
    ext = os.path.splitext(path)[1]
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp_path = tmp.name
    try:
        shutil.copy2(path, tmp_path)
        uploaded = client.files.upload(file=tmp_path, config={"mime_type": mime_type})
        while uploaded.state.name == "PROCESSING":
            time.sleep(2)
            uploaded = client.files.get(name=uploaded.name)
        if uploaded.state.name != "ACTIVE":
            raise RuntimeError(f"파일 처리 실패: {uploaded.state.name}")
        return uploaded
    finally:
        os.unlink(tmp_path)


def transcribe(client, path, mime_type, generation_config):
    """단일 파일을 전사합니다. (본문 텍스트, 단어 주석) 반환."""
    uploaded = upload_file(client, path, mime_type)
    interaction = client.interactions.create(
        model=MODEL,
        input=[{"type": "audio", "uri": uploaded.uri, "mime_type": uploaded.mime_type}],
        generation_config=generation_config,
    )
    return interaction.output_text, extract_word_annotations(interaction)


def main():
    try:
        import google.genai  # noqa: F401
    except ImportError as e:
        print("오류: google-genai 패키지를 찾을 수 없습니다.")
        print("설치 명령: pip install google-genai")
        print(f"상세: {e}")
        return

    import argparse

    parser = argparse.ArgumentParser(
        description="Gemini 3.5 Transcribe: 음성/영상 파일을 전사합니다 (화자 분리·타임스탬프·커스텀 어휘 지원).",
    )
    parser.add_argument("input_file", nargs="?", help="입력 오디오/비디오 파일 경로 (생략 시 현재 폴더에서 자동 탐색)")
    parser.add_argument("--mode", choices=["verbatim", "smart"], default="verbatim",
                        help="전사 모드 (기본 verbatim). smart는 화자 분리·타임스탬프와 병용 불가")
    parser.add_argument("--lang", action="append", metavar="BCP47",
                        help="언어 코드 지정 (예: --lang ko-KR). 반복 지정 가능. 생략 시 자동 감지")
    parser.add_argument("--diarize", dest="diarize", action="store_true", default=None,
                        help="화자 분리 사용 (기본값)")
    parser.add_argument("--no-diarize", dest="diarize", action="store_false",
                        help="화자 분리 해제 (요청당 길이 상한이 60분으로 늘어남)")
    parser.add_argument("--word-timestamps", action="store_true",
                        help="단어 단위 타임스탬프 요청 (API 문서상 전사 정확도가 다소 낮아질 수 있음)")
    parser.add_argument("--vocab", metavar="FILE", help="커스텀 어휘 파일 경로 (기본: 입력 파일 옆 keyterms.txt)")
    parser.add_argument("--no-keyterms", action="store_true", help="keyterms.txt 자동 로드 해제")
    args = parser.parse_args()

    diarize_explicit = args.diarize is not None
    diarize = True if args.diarize is None else args.diarize

    if args.mode == "smart":
        if diarize_explicit and diarize:
            print("오류: --mode smart는 화자 분리와 함께 쓸 수 없습니다. --no-diarize를 쓰거나 --mode verbatim으로 바꾸세요.")
            return
        if args.word_timestamps:
            print("오류: --mode smart는 --word-timestamps와 함께 쓸 수 없습니다. --mode verbatim으로 바꾸세요.")
            return
        diarize = False

    try:
        api_key = os.environ["GEMINI_API_KEY"]
    except KeyError:
        print("오류: GEMINI_API_KEY 환경 변수가 설정되지 않았습니다.")
        print('설정 명령: export GEMINI_API_KEY="your-api-key"  (Windows: setx GEMINI_API_KEY "your-api-key")')
        return

    # 입력 파일 결정
    input_file = args.input_file or find_input_file()
    if not input_file:
        print("오류: 오디오 파일을 찾을 수 없습니다.")
        print(f"지원 형식: {', '.join(MIME_TYPES)}")
        return

    ext = os.path.splitext(input_file)[1].lower()
    if ext not in MIME_TYPES:
        print(f"오류: 지원하지 않는 파일 형식입니다: {ext}")
        print(f"지원 형식: {', '.join(MIME_TYPES)}")
        return
    if not os.path.exists(input_file):
        print(f"오류: 파일을 찾을 수 없습니다: {input_file}")
        return

    mime_type = MIME_TYPES[ext]
    print(f"입력 파일: {input_file} ({mime_type})")
    print(f"파일 크기: {os.path.getsize(input_file) / (1024 * 1024):.1f} MB")

    # 커스텀 어휘 로드
    vocabulary = []
    vocab_path = args.vocab
    if vocab_path is None and not args.no_keyterms:
        candidate = os.path.join(os.path.dirname(os.path.abspath(input_file)), "keyterms.txt")
        if os.path.exists(candidate):
            vocab_path = candidate
    if vocab_path:
        if not os.path.exists(vocab_path):
            print(f"오류: 어휘 파일을 찾을 수 없습니다: {vocab_path}")
            return
        vocabulary = load_vocabulary(vocab_path)
        if len(vocabulary) > 1000:
            print(f"경고: 어휘 {len(vocabulary)}개 중 상한인 1000개까지만 전달합니다.")
            vocabulary = vocabulary[:1000]
        elif len(vocabulary) > 100:
            print(f"경고: 어휘 {len(vocabulary)}개. API 문서 권장치는 100개 이하입니다.")
        print(f"커스텀 어휘: {len(vocabulary)}개 ({vocab_path})")

    # 전사 설정 구성
    transcription_config = {}
    if args.lang:
        transcription_config["language_codes"] = args.lang
    if vocabulary:
        transcription_config["custom_vocabulary"] = vocabulary

    if args.mode == "smart":
        transcription_config["mode"] = {"type": "smart"}
    else:
        mode = {"type": "verbatim"}
        if diarize:
            mode["diarization_mode"] = "speaker"
        if args.word_timestamps:
            mode["timestamp_granularities"] = ["word"]
        transcription_config["mode"] = mode

    generation_config = {"transcription_config": transcription_config}

    annotated = args.mode == "verbatim" and (diarize or args.word_timestamps)
    limit_seconds = (30 if annotated else 60) * 60
    print(f"모드: {args.mode}, 화자 분리: {'사용' if diarize else '해제'}, "
          f"단어 타임스탬프: {'사용' if args.word_timestamps else '해제'}, "
          f"요청당 상한: {limit_seconds // 60}분")

    duration = probe_duration(input_file)
    if duration is None:
        print("경고: ffprobe로 길이를 확인하지 못했습니다. 분할 없이 한 번에 요청합니다.")
    else:
        print(f"재생 길이: {format_timestamp(duration)}")

    from google import genai
    client = genai.Client(api_key=api_key)

    texts = []
    turns = []
    chunk_note = None

    if duration is not None and duration > limit_seconds:
        if not shutil.which("ffmpeg"):
            print(f"오류: 길이 {format_timestamp(duration)}가 상한 {limit_seconds // 60}분을 초과하는데 "
                  "ffmpeg가 없어 분할할 수 없습니다.")
            print("ffmpeg를 설치하거나, --no-diarize로 상한을 60분으로 늘리거나, 파일을 직접 나눠 주세요.")
            return

        workdir = tempfile.mkdtemp(prefix="gemini_transcribe_")
        try:
            print(f"길이가 상한을 초과하여 {limit_seconds // 60}분 단위로 분할합니다...")
            chunks = split_audio(input_file, limit_seconds, workdir)
            print(f"분할 완료: {len(chunks)}개 조각")
            for i, chunk in enumerate(chunks):
                offset = i * limit_seconds
                print(f"전사 중... ({i + 1}/{len(chunks)}, 시작 {format_timestamp(offset)})")
                text, words = transcribe(client, chunk, "audio/mpeg", generation_config)
                if text:
                    texts.append(text)
                turns.extend(build_turns(words, time_offset=offset))
            if diarize:
                chunk_note = (
                    f"# 주의: 입력이 {len(chunks)}개 조각으로 분할 전사되었습니다. "
                    "화자 라벨(spk_N)은 조각별로 독립 부여되므로 조각 간 동일 인물이 아닐 수 있습니다."
                )
        finally:
            shutil.rmtree(workdir, ignore_errors=True)
    else:
        print("전사 중...")
        text, words = transcribe(client, input_file, mime_type, generation_config)
        if text:
            texts.append(text)
        turns.extend(build_turns(words))

    # 결과 렌더링: 주석이 있으면 화자·시간 단위로, 없으면 본문 텍스트 그대로
    body = render_turns(turns) if turns else "\n\n".join(texts)
    if not body.strip():
        print("경고: 전사 결과가 비어 있습니다.")
    transcript = f"{chunk_note}\n\n{body}" if chunk_note else body

    output_file = get_output_filename(input_file)
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(transcript)

    print(f"\n전사 완료! {len(transcript)}글자가 저장되었습니다.")
    print(f"출력 파일: {output_file}")


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

"""
ElevenLabs TTS 통합 스크립트 (단일 화자 + 다중 화자 대화)

ElevenLabs v3 모델로 텍스트/대화를 자연스러운 음성으로 변환합니다.
입력 형식을 감지해 자동으로 단일/다중 모드를 전환하며, 플래그로 강제 가능합니다.

사용법:
    python elevenlabs_tts.py [파일경로] [옵션]

모드:
    단일 화자 — 일반 텍스트. --voice, --speed, --stability로 제어.
    다중 화자 — '화자: 대사' 또는 '[화자] 대사' 형식. --voice-map으로 음성 지정.
    자동 감지 — 2개 이상의 엔트리 + 2명 이상의 유니크 화자가 있으면 다중 모드로 전환.

예시:
    python elevenlabs_tts.py input.txt                                  # 자동 감지
    python elevenlabs_tts.py input.txt --voice Yuna --speed 1.2         # 단일 (CLI)
    python elevenlabs_tts.py dialogue.txt                               # 다중 (자동)
    python elevenlabs_tts.py dialogue.txt --voice-map "화자1=Yuna,화자2=Seojin"
    python elevenlabs_tts.py input.txt --multi-speaker                  # 강제 다중
    python elevenlabs_tts.py input.txt --single                         # 강제 단일
    python elevenlabs_tts.py --list-voices | --list-tags

입력: .txt, .md 파일
출력: [파일명]_elevenlabs.mp3 (단일/다중 모드 공통)

API 키:
    환경변수 ELEVENLABS_API_KEY 사용

주의:
    - text_to_dialogue API는 voice_settings(속도·안정성 등) 미지원 → 단일 모드에서만 적용.
    - 감정 태그(예: [excited], [thoughtfully])는 두 모드 모두 지원.
"""

import os
import sys
import argparse
import traceback
import re


# ============================================================
# 설정
# ============================================================

DEFAULT_MODEL_ID = "eleven_v3"

# 음성 프리셋 (단일 모드 선택지 + 다중 모드 자동 할당 로테이션 순서)
VOICE_PRESETS = [
    {"id": "xi3rF0t7dg7uN2M0WUhr", "name": "Yuna",    "desc": "한국어 여성 — 부드럽고 밝은 목소리"},
    {"id": "FQ3MuLxZh0jHcZmA5vW1", "name": "DoHyeon", "desc": "한국어 남성 — 자연스러운 대화 톤"},
    {"id": "BaW4Cx7nYOh1XNVQBrK2", "name": "Seojin",  "desc": "한국어 남성 — 신뢰감 있는 중저음"},
    {"id": "EkK5I93UQWFDigLMpZcX", "name": "James",   "desc": "영어 남성 — 명확하고 전문적"},
    {"id": "IEUDyekKvUpLhkH6PS1k", "name": "Kiki",    "desc": "영어 여성 — 따뜻하고 차분한 내레이터"},
]

SPEED_PRESETS = [
    {"value": 0.8, "label": "느리게 (0.8)"},
    {"value": 1.0, "label": "보통 (1.0)"},
    {"value": 1.2, "label": "빠르게 (1.2)"},
]

STABILITY_PRESETS = [
    {"value": 0.2, "label": "Creative (0.2) — 감정 표현 풍부"},
    {"value": 0.5, "label": "Natural (0.5) — 균형 잡힌 톤"},
    {"value": 0.8, "label": "Robust (0.8) — 안정적이고 일관됨"},
]

# 단일 모드 기본값
DEFAULT_VOICE_NAME = "Yuna"
DEFAULT_STABILITY = 0.5
DEFAULT_SIMILARITY_BOOST = 0.75
DEFAULT_STYLE = 0.0
DEFAULT_SPEED = 1.2
DEFAULT_USE_SPEAKER_BOOST = True

# 다중 모드 화자 이름 별칭 → VOICE_PRESETS의 name
# 여기에 없는 이름은 VOICE_PRESETS 순서로 자동 할당됨
DIALOGUE_VOICE_ALIASES = {
    "유나": "Yuna",       "yuna": "Yuna",
    "도현": "DoHyeon",    "dohyeon": "DoHyeon",
    "서진": "Seojin",     "seojin": "Seojin",
    "제임스": "James",    "james": "James",
    "키키": "Kiki",       "kiki": "Kiki",
    "화자1": "Yuna",      "speaker1": "Yuna",
    "화자2": "DoHyeon",   "speaker2": "DoHyeon",
}

# ElevenLabs v3 감정/스타일 태그 레퍼런스 (단일/다중 모두 지원)
EMOTION_TAGS = {
    "긍정적/밝은 감정": [
        "[cheerfully]", "[excited]", "[confidently]", "[laughing]",
    ],
    "부정적/침울한 감정": [
        "[sadly]", "[angrily]", "[concerned]", "[nervously]", "[sighing]",
    ],
    "표현/톤 수정자": [
        "[whispering]", "[thoughtfully]", "[sarcastically]",
        "[stuttering]", "[interrupting]",
    ],
}

SUPPORTED_EXTENSIONS = ['.txt', '.md']


# ============================================================
# 유틸리티
# ============================================================

def find_input_file():
    """현재 디렉토리에서 지원되는 텍스트 파일 자동 탐색"""
    import glob
    for ext in SUPPORTED_EXTENSIONS:
        files = glob.glob(f"*{ext}")
        if files:
            return files[0]
    return None


def get_output_filename(input_file):
    """입력 파일 경로 → 출력 파일 경로 (모드 무관 통일)"""
    dir_path = os.path.dirname(os.path.abspath(input_file))
    base_name = os.path.splitext(os.path.basename(input_file))[0]
    return os.path.join(dir_path, f"{base_name}_elevenlabs.mp3")


def find_voice_by_name(name):
    """VOICE_PRESETS에서 이름(case-insensitive) 매칭"""
    for v in VOICE_PRESETS:
        if v['name'].lower() == name.lower():
            return v
    return None


def interactive_select(prompt, options, default_idx=0):
    """대화형 선택 메뉴. Enter → default_idx."""
    print(f"\n{prompt}")
    for i, opt in enumerate(options):
        marker = " *" if i == default_idx else ""
        print(f"  {i + 1}. {opt}{marker}")
    while True:
        choice = input(f"  선택 [Enter={default_idx + 1}]: ").strip()
        if choice == "":
            return default_idx
        if choice.isdigit() and 1 <= int(choice) <= len(options):
            return int(choice) - 1
        print(f"  1~{len(options)} 사이 숫자를 입력하세요.")


def list_voices():
    print("\n사용 가능한 음성 프리셋:")
    print("-" * 72)
    for v in VOICE_PRESETS:
        print(f"  {v['name']:<10} — {v['desc']}")
        print(f"  {'':<10}   ID: {v['id']}")
    print("-" * 72)
    print("\n사용 예:")
    print('  python elevenlabs_tts.py input.txt --voice Yuna')
    print('  python elevenlabs_tts.py dialogue.txt --voice-map "화자1=Yuna,화자2=Seojin"')


def list_tags():
    print("\nElevenLabs v3 감정/스타일 태그 (단일/다중 화자 모두 지원)")
    print("=" * 72)
    print("태그는 본문 또는 대사 앞에 대괄호로 삽입합니다. 영어 태그만 인식됩니다.\n")
    for category, tags in EMOTION_TAGS.items():
        print(f"[{category}]")
        for i in range(0, len(tags), 3):
            row = tags[i:i + 3]
            print("  " + "  ".join(f"{t:<22}" for t in row))
        print()
    print("=" * 72)
    print("사용 예시:")
    print('  단일:  [excited] 오늘 정말 재미있었어요!')
    print('  다중:  유나: [cheerfully] 안녕하세요!')
    print('         도현: [thoughtfully] 음... 그건 좀 복잡한 얘기네요.')


# ============================================================
# 대화 파싱
# ============================================================

_PATTERN_COLON = re.compile(r'^([^:\[\]]+):\s*(.+)$')
_PATTERN_BRACKET = re.compile(r'^\[([^\]]+)\]\s*(.+)$')


def parse_dialogue(content):
    """
    대화 스크립트 파싱 → [{'speaker': ..., 'text': ...}, ...].

    지원 형식:
        화자이름: 대사
        화자이름: [감정태그] 대사
        [화자이름] 대사
        [화자이름] [감정태그] 대사

    빈 줄과 '#' 주석은 무시. 패턴에 맞지 않는 줄은 직전 엔트리에 이어붙임.
    """
    entries = []
    for line in content.strip().split('\n'):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        match = _PATTERN_COLON.match(line) or _PATTERN_BRACKET.match(line)
        if match:
            entries.append({
                "speaker": match.group(1).strip(),
                "text": match.group(2).strip(),
            })
        elif entries:
            entries[-1]["text"] += " " + line
    return entries


def looks_like_dialogue(content):
    """
    자동 감지. False positive를 줄이기 위해 콜론 패턴(`화자: 대사`)만 사용한다.
    `[화자] 대사` 브라켓 형식은 감정 태그(`[excited]`)와 구분이 모호해
    자동 감지에서는 제외 — 명시적 --multi-speaker 시에는 parse_dialogue가 계속 지원.

    판정: 콜론 패턴 매칭이 2+개 AND 유니크 화자가 2+명.
    """
    colon_entries = []
    for line in content.strip().split('\n'):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        m = _PATTERN_COLON.match(line)
        if m:
            colon_entries.append({
                "speaker": m.group(1).strip(),
                "text": m.group(2).strip(),
            })

    if len(colon_entries) < 2 or len({e['speaker'] for e in colon_entries}) < 2:
        return False, parse_dialogue(content)
    # 본격 파싱은 parse_dialogue(브라켓 + 콜론 + 이어붙이기)로 재실행
    return True, parse_dialogue(content)


def build_voice_mapping(speakers, custom_map_arg=None):
    """
    화자 이름 → voice_id 매핑.

    우선순위:
      1. --voice-map CLI 인자 (예: "화자1=Yuna,화자2=Seojin")
      2. DIALOGUE_VOICE_ALIASES 기본 별칭 (case-insensitive)
      3. VOICE_PRESETS 순서로 자동 순환 할당
    """
    mapping = {}

    if custom_map_arg:
        for pair in custom_map_arg.split(','):
            if '=' not in pair:
                continue
            speaker, voice_name = (x.strip() for x in pair.split('=', 1))
            preset = find_voice_by_name(voice_name)
            if preset:
                mapping[speaker] = preset['id']
            else:
                print(f"경고: 알 수 없는 음성 '{voice_name}' (화자 '{speaker}') — 무시")

    for speaker in speakers:
        if speaker in mapping:
            continue
        key = speaker.lower() if speaker.lower() in DIALOGUE_VOICE_ALIASES else speaker
        if key in DIALOGUE_VOICE_ALIASES:
            preset = find_voice_by_name(DIALOGUE_VOICE_ALIASES[key])
            if preset:
                mapping[speaker] = preset['id']

    auto_idx = 0
    for speaker in speakers:
        if speaker in mapping:
            continue
        preset = VOICE_PRESETS[auto_idx % len(VOICE_PRESETS)]
        mapping[speaker] = preset['id']
        print(f"  {speaker} → {preset['name']} (자동 할당)")
        auto_idx += 1

    return mapping


# ============================================================
# TTS 실행
# ============================================================

def single_speaker_tts(client, voice_settings_cls, text, voice, speed, stability, model_id):
    char_count = len(text)
    print(f"\n음성 변환 중... (모드: 단일, 음성: {voice['name']}, "
          f"속도: {speed}, 안정성: {stability}, 문자: {char_count})")

    audio_gen = client.text_to_speech.convert(
        voice_id=voice['id'],
        model_id=model_id,
        text=text,
        voice_settings=voice_settings_cls(
            stability=stability,
            similarity_boost=DEFAULT_SIMILARITY_BOOST,
            style=DEFAULT_STYLE,
            use_speaker_boost=DEFAULT_USE_SPEAKER_BOOST,
            speed=speed,
        ),
    )
    return b''.join(audio_gen), char_count


def multi_speaker_tts(client, entries, voice_mapping, model_id):
    inputs = [
        {"text": e["text"], "voice_id": voice_mapping[e["speaker"]]}
        for e in entries
    ]
    total_chars = sum(len(e["text"]) for e in entries)
    print(f"\n음성 변환 중... (모드: 다중, 엔트리: {len(entries)}개, "
          f"모델: {model_id}, 문자: {total_chars})")

    # text_to_dialogue는 voice_settings 미지원 (ElevenLabs API 한계)
    audio_gen = client.text_to_dialogue.convert(inputs=inputs)
    return b''.join(audio_gen), total_chars


# ============================================================
# 메인
# ============================================================

def build_parser():
    parser = argparse.ArgumentParser(
        description='ElevenLabs TTS - 단일/다중 화자 통합 변환 (eleven_v3)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  자동 감지 (기본):
    python elevenlabs_tts.py input.txt

  단일 화자 — CLI 인자 지정:
    python elevenlabs_tts.py input.txt --voice Yuna --speed 1.2 --stability 0.5

  단일 화자 — 대화형 (CLI 인자 미지정 + TTY):
    python elevenlabs_tts.py input.txt

  다중 화자 — 파일에 '화자: 대사' 있으면 자동 전환:
    # dialogue.txt:
    #   유나: 안녕하세요!
    #   도현: [thoughtfully] 오랜만이네요.
    python elevenlabs_tts.py dialogue.txt

  다중 화자 — 음성 커스터마이징:
    python elevenlabs_tts.py dialogue.txt --voice-map "화자1=Yuna,화자2=Seojin"

  모드 강제:
    python elevenlabs_tts.py input.txt --multi-speaker
    python elevenlabs_tts.py input.txt --single

  참조:
    python elevenlabs_tts.py --list-voices
    python elevenlabs_tts.py --list-tags
        """,
    )
    parser.add_argument('file', nargs='?', help='입력 파일 경로 (.txt, .md)')

    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument('--multi-speaker', action='store_true',
                            help='다중 화자 모드 강제')
    mode_group.add_argument('--single', action='store_true',
                            help='단일 화자 모드 강제 (자동 감지 비활성화)')

    parser.add_argument('--voice', default=None,
                        help=f'단일 모드 음성 이름 (기본: {DEFAULT_VOICE_NAME})')
    parser.add_argument('--speed', type=float, default=None,
                        help='단일 모드 속도 0.7-1.2')
    parser.add_argument('--stability', type=float, default=None,
                        help='단일 모드 안정성 0.0-1.0')

    parser.add_argument('--voice-map', dest='voice_map', default=None,
                        help='다중 모드 화자=음성 매핑 (예: "화자1=Yuna,화자2=Seojin")')

    parser.add_argument('--model', default=DEFAULT_MODEL_ID,
                        help=f'모델 ID (기본: {DEFAULT_MODEL_ID})')
    parser.add_argument('--list-voices', action='store_true', help='음성 프리셋 출력')
    parser.add_argument('--list-tags', action='store_true', help='감정 태그 레퍼런스 출력')

    return parser


def resolve_input_file(arg_file):
    input_file = arg_file or find_input_file()
    if not input_file:
        print("오류: 입력 파일을 찾을 수 없습니다.")
        print(f"지원 형식: {', '.join(SUPPORTED_EXTENSIONS)}")
        return None
    if not os.path.exists(input_file):
        print(f"오류: 파일을 찾을 수 없습니다: {input_file}")
        return None
    ext = os.path.splitext(input_file)[1].lower()
    if ext not in SUPPORTED_EXTENSIONS:
        print(f"오류: 지원하지 않는 파일 형식입니다: {ext}")
        print(f"지원 형식: {', '.join(SUPPORTED_EXTENSIONS)}")
        return None
    return input_file


def resolve_single_settings(args):
    """단일 모드 음성/속도/안정성 결정. 대화형 or CLI."""
    interactive = (
        args.voice is None
        and args.speed is None
        and args.stability is None
        and sys.stdin.isatty()
    )

    if interactive:
        idx = interactive_select(
            "음성 선택:",
            [f"{v['name']} — {v['desc']}" for v in VOICE_PRESETS],
            default_idx=0,
        )
        voice = VOICE_PRESETS[idx]

        idx = interactive_select(
            "속도 선택:",
            [s["label"] for s in SPEED_PRESETS],
            default_idx=2,
        )
        speed = SPEED_PRESETS[idx]["value"]

        idx = interactive_select(
            "안정성 선택:",
            [s["label"] for s in STABILITY_PRESETS],
            default_idx=1,
        )
        stability = STABILITY_PRESETS[idx]["value"]
    else:
        voice_name = args.voice or DEFAULT_VOICE_NAME
        voice = find_voice_by_name(voice_name)
        if voice is None:
            print(f"오류: 알 수 없는 음성: {voice_name}")
            print("--list-voices 옵션으로 목록을 확인하세요.")
            return None
        speed = args.speed if args.speed is not None else DEFAULT_SPEED
        stability = args.stability if args.stability is not None else DEFAULT_STABILITY

    return voice, speed, stability


def determine_mode(args, content):
    """(mode, entries) 결정. mode is 'single' or 'dialogue'."""
    if args.multi_speaker:
        entries = parse_dialogue(content)
        if len(entries) < 2 or len({e['speaker'] for e in entries}) < 2:
            print("오류: --multi-speaker가 지정됐지만 유효한 다중 화자 패턴을 찾지 못했습니다.")
            print("형식: '화자: 대사' 또는 '[화자] 대사'")
            return None, None
        return 'dialogue', entries

    if args.single:
        return 'single', None

    is_dialogue, entries = looks_like_dialogue(content)
    if is_dialogue:
        print("다중 화자 패턴 감지 → dialogue 모드 (단일 강제: --single)")
        return 'dialogue', entries
    return 'single', None


def main():
    args = build_parser().parse_args()

    if args.list_voices:
        list_voices()
        return
    if args.list_tags:
        list_tags()
        return

    try:
        from elevenlabs import ElevenLabs, VoiceSettings
    except ImportError as e:
        print("오류: elevenlabs 패키지를 찾을 수 없습니다.")
        print("설치 명령: pip install elevenlabs")
        print(f"상세: {e}")
        return

    # ElevenLabs API 키: 환경변수 ELEVENLABS_API_KEY 사용
    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        print("오류: 환경변수 ELEVENLABS_API_KEY가 설정되어 있지 않습니다.")
        sys.exit(1)

    if args.speed is not None and not (0.7 <= args.speed <= 1.2):
        print(f"오류: speed는 0.7-1.2 범위여야 합니다. (입력값: {args.speed})")
        return
    if args.stability is not None and not (0.0 <= args.stability <= 1.0):
        print(f"오류: stability는 0.0-1.0 범위여야 합니다. (입력값: {args.stability})")
        return

    input_file = resolve_input_file(args.file)
    if not input_file:
        return

    print(f"입력 파일: {input_file}")
    with open(input_file, "r", encoding="utf-8") as f:
        content = f.read().strip()
    if not content:
        print("오류: 파일이 비어있습니다.")
        return

    mode, entries = determine_mode(args, content)
    if mode is None:
        return

    client = ElevenLabs(api_key=api_key)

    try:
        if mode == 'dialogue':
            speakers = []
            seen = set()
            for e in entries:
                if e['speaker'] not in seen:
                    speakers.append(e['speaker'])
                    seen.add(e['speaker'])
            print(f"대화 엔트리: {len(entries)}개 / 화자: {', '.join(speakers)}")

            voice_mapping = build_voice_mapping(speakers, args.voice_map)
            audio_data, char_count = multi_speaker_tts(client, entries, voice_mapping, args.model)
        else:
            resolved = resolve_single_settings(args)
            if resolved is None:
                return
            voice, speed, stability = resolved
            audio_data, char_count = single_speaker_tts(
                client, VoiceSettings, content, voice, speed, stability, args.model,
            )

        if not audio_data:
            print("오류: 음성 변환 결과가 비어있습니다.")
            return

        output_file = get_output_filename(input_file)
        with open(output_file, "wb") as f:
            f.write(audio_data)

        file_size_kb = len(audio_data) / 1024
        print(f"\n변환 완료! 파일 크기: {file_size_kb:.1f} KB")
        print(f"출력 파일: {output_file}")
        print(f"사용 문자: {char_count}자")

    except Exception as e:
        error_msg = str(e).lower()
        if "api_key" in error_msg or "authentication" in error_msg:
            print("오류: API 키가 유효하지 않습니다.")
        elif "rate" in error_msg and "limit" in error_msg:
            print("오류: API 요청 한도를 초과했습니다. 잠시 후 다시 시도해주세요.")
        else:
            raise


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

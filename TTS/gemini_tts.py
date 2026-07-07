"""
Gemini TTS (Text-to-Speech) 스크립트
Google Gemini API의 네이티브 TTS 기능을 사용하여 텍스트를 음성으로 변환합니다.

기본 모델: gemini-3.1-flash-tts-preview (Preview, 2026-04 업데이트)
  - 70+ 언어 지원
  - 200+ 오디오 태그로 감정/페이싱/스타일 세밀 제어
  - 30개 프리셋 음성
  - 무료 티어 제공 (유료: 입력 $1/1M tok, 출력 $20/1M tok, 오디오=25tok/초)

사용법:
    python gemini_tts.py [파일경로] [옵션]

옵션:
    --voice NAME            음성 선택 (기본: Puck)
    --multi-speaker         다중 화자 모드 활성화
    --voice1 NAME           다중 화자 모드에서 화자1 음성 (기본: Kore)
    --voice2 NAME           다중 화자 모드에서 화자2 음성 (기본: Puck)
    --style TEXT            음성 스타일 지시 (프롬프트 프리픽스, 예: "천천히, 따뜻하게")
    --temperature FLOAT     음성 변동성 (0.0-2.0, 기본 1.0, 높을수록 풍부한 표현)
    --language-code CODE    언어 코드 (예: ko-KR, en-US, en-IN, ja-JP)
    --model NAME            모델 override (기본: gemini-3.1-flash-tts-preview)
    --list-voices           사용 가능한 음성 목록 출력
    --list-tags             오디오 태그 레퍼런스 출력

환경 변수:
    GEMINI_API_KEY          Google Gemini API 키

입력: .txt, .md 파일
출력: [파일명]_gemini_tts.wav

오디오 태그 (영어 태그만 인식되나, 비영어 본문과 혼용 가능):

  1. 비언어 사운드: 태그 자체가 소리로 대체됨
     [sigh], [laughing], [uhm], [cough], [gasp], [giggles]

  2. 스타일 수정자: 뒤따르는 구절의 전달 방식 변경
     [whispering], [shouting], [robotic], [sarcasm], [excited], [bored],
     [curious], [scared], [tired], [mischievously], [panicked], [serious]

  3. 페이싱/속도
     [short pause] ~250ms, [medium pause] ~500ms, [long pause] ~1000ms+
     [very fast], [very slow], [extremely fast]

예시 (한국어 + 영어 태그 혼합):
  [excited] 오늘은 정말 멋진 하루였어요. [long pause] 믿을 수 없을 정도로.
  [whispering] 이건 비밀인데, [gasp] 사실 나도 몰랐어.

주의:
  - --style 프리픽스는 긴 텍스트(~2000토큰+)에서 INVALID_ARGUMENT 유발 위험. 인라인 태그로 대체 권장.
  - 입력 8,192 토큰 / 출력 16,384 토큰 (~655초 ≈ 11분) 제한. 긴 텍스트는 분할 필요.
  - Preview 모델이므로 스펙 변경 가능.
"""

import os
import sys
import argparse
import traceback
import re
import wave

# 기본 모델: Gemini 3.1 Flash TTS Preview (2026-04)
DEFAULT_MODEL = "gemini-3.1-flash-tts-preview"

# 지원하는 30개 프리셋 음성
AVAILABLE_VOICES = [
    "Zephyr", "Puck", "Charon", "Kore", "Fenrir", "Leda", "Orus", "Aoede",
    "Callirrhoe", "Autonoe", "Enceladus", "Iapetus", "Umbriel", "Algieba",
    "Despina", "Erinome", "Algenib", "Rasalgethi", "Laomedeia", "Achernar",
    "Alnilam", "Schedar", "Gacrux", "Pulcherrima", "Achird", "Zubenelgenubi",
    "Vindemiatrix", "Sadachbia", "Sadaltager", "Sulafat"
]

# 자주 쓰는 언어 코드 (참고용, 전체 70+ 언어 지원)
COMMON_LANGUAGE_CODES = [
    ("ko-KR", "한국어"),
    ("en-US", "영어 (미국)"),
    ("en-GB", "영어 (영국)"),
    ("en-IN", "영어 (인도)"),
    ("ja-JP", "일본어"),
    ("zh-CN", "중국어 (간체)"),
    ("es-ES", "스페인어"),
    ("fr-FR", "프랑스어"),
    ("de-DE", "독일어"),
    ("it-IT", "이탈리아어"),
    ("pt-BR", "포르투갈어 (브라질)"),
    ("ru-RU", "러시아어"),
]

# 오디오 태그 레퍼런스 (--list-tags 출력용)
AUDIO_TAGS_REFERENCE = {
    "비언어 사운드 (태그 자체가 소리로 대체됨)": [
        "[sigh]", "[laughing]", "[giggles]", "[uhm]", "[cough]", "[gasp]",
    ],
    "감정/스타일 수정자 (뒤따르는 구절의 전달 방식 변경)": [
        "[excited]", "[bored]", "[curious]", "[scared]", "[tired]",
        "[whispering]", "[shouting]", "[robotic]", "[sarcasm]",
        "[mischievously]", "[panicked]", "[serious]", "[trembling]",
        "[amazed]", "[crying]", "[reluctantly]",
    ],
    "페이싱/속도": [
        "[short pause]", "[medium pause]", "[long pause]",
        "[very fast]", "[very slow]", "[extremely fast]",
    ],
    "창의적 페르소나 (실험적)": [
        "[like a cartoon dog]", "[like dracula]",
        "[sarcastically, one painfully slow word at a time]",
    ],
}

# 지원하는 입력 파일 확장자
SUPPORTED_EXTENSIONS = ['.txt', '.md']

# Gemini TTS 오디오 설정 (API 반환 형식: audio/L16;codec=pcm;rate=24000)
SAMPLE_RATE = 24000
SAMPLE_WIDTH = 2  # 16bit = 2 bytes
CHANNELS = 1  # mono

# 입력 토큰 제한 (8,192) 근처 경고 임계값 (글자수 기준 ~4글자/토큰)
TOKEN_WARNING_THRESHOLD = 7500
CHARS_PER_TOKEN_ESTIMATE = 4


def save_wav(pcm_data, output_file):
    """Raw PCM 데이터를 WAV 파일로 저장"""
    with wave.open(output_file, 'wb') as wav_file:
        wav_file.setnchannels(CHANNELS)
        wav_file.setsampwidth(SAMPLE_WIDTH)
        wav_file.setframerate(SAMPLE_RATE)
        wav_file.writeframes(pcm_data)


def get_output_filename(input_file):
    """입력 파일 경로에서 출력 파일 경로 생성"""
    dir_path = os.path.dirname(input_file)
    base_name = os.path.splitext(os.path.basename(input_file))[0]
    output_name = f"{base_name}_gemini_tts.wav"
    if dir_path:
        return os.path.join(dir_path, output_name)
    return output_name


def find_input_file():
    """현재 디렉토리에서 지원되는 텍스트 파일 자동 탐색"""
    import glob
    for ext in SUPPORTED_EXTENSIONS:
        files = glob.glob(f"*{ext}")
        if files:
            return files[0]
    return None


def list_voices():
    """사용 가능한 음성 목록 출력"""
    print("\n사용 가능한 음성 목록 (30개):")
    print("-" * 50)
    for i, voice in enumerate(AVAILABLE_VOICES, 1):
        print(f"  {i:2}. {voice}")
    print("-" * 50)
    print("\n사용 예: python gemini_tts.py input.txt --voice Kore")


def list_tags():
    """오디오 태그 레퍼런스 출력"""
    print("\nGemini 3.1 Flash TTS 오디오 태그 레퍼런스")
    print("=" * 60)
    print("태그는 본문에 인라인으로 삽입하며, 영어 태그만 인식됩니다.")
    print("비영어 본문과 혼합 사용 가능합니다.\n")

    for category, tags in AUDIO_TAGS_REFERENCE.items():
        print(f"[{category}]")
        # 한 줄에 3개씩 출력
        for i in range(0, len(tags), 3):
            row = tags[i:i + 3]
            print("  " + "  ".join(f"{t:<28}" for t in row))
        print()

    print("=" * 60)
    print("사용 예시:")
    print('  [excited] 오늘은 정말 멋진 하루였어요. [long pause] 믿을 수 없을 정도로.')
    print('  [whispering] 이건 비밀인데, [gasp] 사실 나도 몰랐어.')
    print('  [robotic] 시스템 점검을 시작합니다. [short pause] 준비 완료.')
    print("\n전체 목록: https://ai.google.dev/gemini-api/docs/speech-generation#transcript-tags")


def validate_voice(voice_name):
    """음성 이름 유효성 검사"""
    for voice in AVAILABLE_VOICES:
        if voice.lower() == voice_name.lower():
            return voice
    return None


def parse_multi_speaker_text(text):
    """
    다중 화자 텍스트 파싱
    [화자1] 또는 [Speaker1] 형식의 태그를 인식
    """
    pattern = r'\[(화자1|화자2|Speaker1|Speaker2|1|2)\]\s*'

    segments = []
    current_speaker = 1

    parts = re.split(pattern, text, flags=re.IGNORECASE)

    for part in parts:
        part = part.strip()
        if not part:
            continue

        lower_part = part.lower()
        if lower_part in ['화자1', 'speaker1', '1']:
            current_speaker = 1
        elif lower_part in ['화자2', 'speaker2', '2']:
            current_speaker = 2
        else:
            if part:
                segments.append({
                    'speaker': current_speaker,
                    'text': part
                })

    return segments


def _build_speech_config(types, voice_name=None, language_code=None, multi_speaker=None):
    """SpeechConfig 생성 공통 헬퍼. language_code가 있으면 포함."""
    kwargs = {}
    if language_code:
        kwargs['language_code'] = language_code
    if multi_speaker is not None:
        kwargs['multi_speaker_voice_config'] = multi_speaker
    elif voice_name:
        kwargs['voice_config'] = types.VoiceConfig(
            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice_name)
        )
    return types.SpeechConfig(**kwargs)


def _build_generate_config(types, speech_config, temperature=None):
    """GenerateContentConfig 생성 공통 헬퍼. temperature가 있으면 포함."""
    kwargs = {
        'response_modalities': ["AUDIO"],
        'speech_config': speech_config,
    }
    if temperature is not None:
        kwargs['temperature'] = temperature
    return types.GenerateContentConfig(**kwargs)


def single_speaker_tts(client, types, text, voice_name, model,
                       style=None, temperature=None, language_code=None):
    """단일 화자 TTS 수행"""
    content = f"{style}: {text}" if style else text

    info_parts = [f"음성: {voice_name}", f"모델: {model}"]
    if temperature is not None:
        info_parts.append(f"temperature: {temperature}")
    if language_code:
        info_parts.append(f"언어: {language_code}")
    print(f"음성 변환 중... ({', '.join(info_parts)})")

    speech_config = _build_speech_config(types, voice_name=voice_name, language_code=language_code)
    config = _build_generate_config(types, speech_config, temperature=temperature)

    response = client.models.generate_content(
        model=model,
        contents=content,
        config=config,
    )

    if response.usage_metadata:
        m = response.usage_metadata
        print(f"  토큰 사용: 입력 {m.prompt_token_count} + 출력 {m.candidates_token_count} = 합계 {m.total_token_count}")

    return response.candidates[0].content.parts[0].inline_data.data


def multi_speaker_tts(client, types, text, voice1, voice2, model,
                      style=None, temperature=None, language_code=None):
    """다중 화자 TTS 수행"""
    segments = parse_multi_speaker_text(text)

    if not segments:
        print("경고: 화자 태그를 찾을 수 없습니다. 단일 화자로 처리합니다.")
        return single_speaker_tts(
            client, types, text, voice1, model,
            style=style, temperature=temperature, language_code=language_code,
        )

    print(f"다중 화자 모드: {len(segments)}개 세그먼트 감지")
    print(f"  화자1: {voice1} / 화자2: {voice2} / 모델: {model}")
    if temperature is not None:
        print(f"  temperature: {temperature}")
    if language_code:
        print(f"  언어: {language_code}")

    speaker_voices = {1: voice1, 2: voice2}
    prompt_parts = [f"[{speaker_voices[seg['speaker']]}]: {seg['text']}" for seg in segments]
    combined_prompt = "\n".join(prompt_parts)
    if style:
        combined_prompt = f"{style}\n\n{combined_prompt}"

    print("음성 변환 중...")

    multi_speaker_config = types.MultiSpeakerVoiceConfig(
        speaker_voice_configs=[
            types.SpeakerVoiceConfig(
                speaker=voice_name,
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice_name)
                ),
            )
            for voice_name in (voice1, voice2)
        ]
    )

    speech_config = _build_speech_config(
        types, language_code=language_code, multi_speaker=multi_speaker_config
    )
    config = _build_generate_config(types, speech_config, temperature=temperature)

    response = client.models.generate_content(
        model=model,
        contents=combined_prompt,
        config=config,
    )

    if response.usage_metadata:
        m = response.usage_metadata
        print(f"  토큰 사용: 입력 {m.prompt_token_count} + 출력 {m.candidates_token_count} = 합계 {m.total_token_count}")

    return response.candidates[0].content.parts[0].inline_data.data


def main():
    parser = argparse.ArgumentParser(
        description='Gemini TTS - 텍스트를 음성으로 변환 (기본: gemini-3.1-flash-tts-preview)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  기본 변환:
    python gemini_tts.py input.txt
    python gemini_tts.py input.txt --voice Puck

  오디오 태그 (본문에 인라인 삽입):
    # input.txt 내용: "[excited] 오늘은 멋진 날! [long pause] 정말로요."
    python gemini_tts.py input.txt --voice Aoede

  언어 명시 + 변동성 제어:
    python gemini_tts.py input.txt --language-code ko-KR --temperature 1.5

  스타일 프리픽스 (짧은 텍스트 권장):
    python gemini_tts.py input.txt --style "천천히, 따뜻한 목소리로"

  다중 화자:
    python gemini_tts.py dialogue.txt --multi-speaker --voice1 Kore --voice2 Puck

  모델 override (예: 2.5로 폴백):
    python gemini_tts.py input.txt --model gemini-2.5-flash-preview-tts

  참조:
    python gemini_tts.py --list-voices
    python gemini_tts.py --list-tags
        """
    )
    parser.add_argument('file', nargs='?', help='입력 파일 경로 (.txt, .md)')
    parser.add_argument('--voice', default='Puck', help='음성 선택 (기본: Puck)')
    parser.add_argument('--multi-speaker', action='store_true', help='다중 화자 모드')
    parser.add_argument('--voice1', default='Kore', help='다중 화자 화자1 음성')
    parser.add_argument('--voice2', default='Puck', help='다중 화자 화자2 음성')
    parser.add_argument('--style', help='스타일 프리픽스 (예: "천천히, 따뜻하게")')
    parser.add_argument('--temperature', type=float, default=None,
                        help='음성 변동성 (0.0-2.0, 기본: 모델 기본값)')
    parser.add_argument('--language-code', dest='language_code', default=None,
                        help='언어 코드 (예: ko-KR, en-US, ja-JP)')
    parser.add_argument('--model', default=DEFAULT_MODEL,
                        help=f'모델명 override (기본: {DEFAULT_MODEL})')
    parser.add_argument('--list-voices', action='store_true', help='음성 목록 출력')
    parser.add_argument('--list-tags', action='store_true', help='오디오 태그 레퍼런스 출력')

    args = parser.parse_args()

    if args.list_voices:
        list_voices()
        return
    if args.list_tags:
        list_tags()
        return

    try:
        from google import genai
        from google.genai import types
    except ImportError:
        print("오류: google-genai 패키지를 찾을 수 없습니다.")
        print("설치 명령: pip install google-genai")
        return

    try:
        api_key = os.environ["GEMINI_API_KEY"]
    except KeyError:
        print("오류: GEMINI_API_KEY 환경 변수가 설정되지 않았습니다.")
        print('설정: export GEMINI_API_KEY="your-key"  (Windows: setx GEMINI_API_KEY "your-key")')
        return

    # Temperature 유효성
    if args.temperature is not None and not (0.0 <= args.temperature <= 2.0):
        print(f"오류: temperature는 0.0-2.0 범위여야 합니다. (입력값: {args.temperature})")
        return

    # 입력 파일
    if args.file:
        input_file = args.file
    else:
        input_file = find_input_file()
        if not input_file:
            print("오류: 입력 파일을 찾을 수 없습니다.")
            print("사용법: python gemini_tts.py <파일경로>")
            print(f"지원 형식: {', '.join(SUPPORTED_EXTENSIONS)}")
            return

    if not os.path.exists(input_file):
        print(f"오류: 파일을 찾을 수 없습니다: {input_file}")
        return

    ext = os.path.splitext(input_file)[1].lower()
    if ext not in SUPPORTED_EXTENSIONS:
        print(f"오류: 지원하지 않는 파일 형식입니다: {ext}")
        print(f"지원 형식: {', '.join(SUPPORTED_EXTENSIONS)}")
        return

    # 음성 유효성
    if args.multi_speaker:
        voice1 = validate_voice(args.voice1)
        voice2 = validate_voice(args.voice2)
        if not voice1:
            print(f"오류: 알 수 없는 음성입니다: {args.voice1}")
            print("--list-voices 옵션으로 사용 가능한 음성을 확인하세요.")
            return
        if not voice2:
            print(f"오류: 알 수 없는 음성입니다: {args.voice2}")
            print("--list-voices 옵션으로 사용 가능한 음성을 확인하세요.")
            return
    else:
        voice = validate_voice(args.voice)
        if not voice:
            print(f"오류: 알 수 없는 음성입니다: {args.voice}")
            print("--list-voices 옵션으로 사용 가능한 음성을 확인하세요.")
            return

    # 파일 읽기
    print(f"파일 읽는 중: {input_file}")
    with open(input_file, 'r', encoding='utf-8') as f:
        text = f.read().strip()

    if not text:
        print("오류: 파일이 비어있습니다.")
        return

    estimated_tokens = len(text) // CHARS_PER_TOKEN_ESTIMATE
    if estimated_tokens > TOKEN_WARNING_THRESHOLD:
        print(f"경고: 텍스트가 너무 깁니다. (추정 {estimated_tokens} 토큰)")
        print("Gemini TTS 입력 한도: 8,192 토큰. 텍스트를 분할해 주세요.")
        return

    print(f"텍스트 길이: {len(text)}자 (추정 {estimated_tokens} 토큰)")

    client = genai.Client(api_key=api_key)

    if args.multi_speaker:
        audio_data = multi_speaker_tts(
            client, types, text, voice1, voice2, args.model,
            style=args.style, temperature=args.temperature,
            language_code=args.language_code,
        )
    else:
        audio_data = single_speaker_tts(
            client, types, text, voice, args.model,
            style=args.style, temperature=args.temperature,
            language_code=args.language_code,
        )

    output_file = get_output_filename(input_file)
    save_wav(audio_data, output_file)

    file_size = os.path.getsize(output_file)
    if file_size >= 1024 * 1024:
        size_str = f"{file_size / (1024 * 1024):.2f} MB"
    else:
        size_str = f"{file_size / 1024:.2f} KB"

    print(f"\n변환 완료!")
    print(f"출력 파일: {output_file}")
    print(f"파일 크기: {size_str}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n오류 발생: {e}")
        traceback.print_exc()

    try:
        if sys.stdin.isatty() and sys.stdout.isatty():
            input("\nEnter를 눌러 종료...")
    except EOFError:
        pass

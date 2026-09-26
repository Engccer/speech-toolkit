"""
Gemini TTS (Text-to-Speech) 스크립트
Google Gemini API의 네이티브 TTS 기능을 사용하여 텍스트를 음성으로 변환합니다.

기본 모델: gemini-3.8-flash-tts (정식판, 2026-09)
  - 130+ 언어 자동 감지 (--language-code 불필요)
  - 30개 프리셋 음성 + 확장 음성 라이브러리·보이스 디자인 ID(voice_...) 사용 가능
  - 2026-12-31까지 무료 (이후 입력 $1/1M tok, 출력 $18/1M tok)
  - 저비용 대량용: gemini-3.8-flash-lite-tts (출력 $12/1M tok)

모델별 호출 경로:
  - 3.8 이후: Interactions API REST 직접 호출 (SDK 불필요). 입력은 낭독 대본으로만
    취급되므로 --style은 대본이 아니라 speech_metadata.style로 전달한다.
  - 2.5·3.1 (레거시): google-genai SDK generate_content. --style은 본문 앞에 붙는다.

사용법:
    python gemini_tts.py [파일경로] [옵션]

옵션:
    --voice NAME            음성 선택 (기본: Puck)
    --multi-speaker         다중 화자 모드 활성화
    --voice1 NAME           다중 화자 모드에서 화자1 음성 (기본: Kore)
    --voice2 NAME           다중 화자 모드에서 화자2 음성 (기본: Puck)
    --style TEXT            음성 스타일 지시 (예: "천천히, 따뜻하게")
    --temperature FLOAT     음성 변동성 (0.0-2.0, 기본 1.0, 높을수록 풍부한 표현)
    --language-code CODE    언어 코드 (레거시 모델 전용, 예: ko-KR, en-US, ja-JP)
    --model NAME            모델 override (기본: gemini-3.8-flash-tts)
    --list-voices           사용 가능한 음성 목록 출력
    --list-tags             오디오 태그 레퍼런스 출력

환경 변수:
    GEMINI_API_KEY          Google Gemini API 키

입력: .txt, .md 파일
출력: [파일명]_gemini_tts.wav

오디오 태그 (--list-tags로 모델별 목록 확인):
  - 3.8: 꺾쇠 태그. 예) 이건 비밀인데 <whispers> 사실 나도 몰랐어. <laugh>
  - 3.1: 대괄호 태그. 예) [whispering] 이건 비밀인데, [gasp] 사실 나도 몰랐어.

주의:
  - 레거시 모델에서 --style 프리픽스는 긴 텍스트(~2000토큰+)에서 INVALID_ARGUMENT 유발 위험.
  - 입력 8,192 토큰 제한 기준으로 경고한다. 긴 텍스트는 분할 필요.
"""

import os
import sys

# Windows 콘솔 기본 인코딩(cp949)에서 비-cp949 문자(ℹ, ⚠, ≈ 등)를 출력하면
# UnicodeEncodeError로 스크립트가 죽는다. 출력물은 이미 저장된 뒤라 실질 피해는
# 없지만 종료 코드가 1이 되어 호출부가 실패로 오인한다. (2026-09-07)
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
import argparse
import base64
import json
import traceback
import re
import urllib.error
import urllib.request
import wave

# 기본 모델: Gemini 3.8 Flash TTS (2026-09 정식판)
DEFAULT_MODEL = "gemini-3.8-flash-tts"

# generate_content 경로를 쓰는 레거시 모델. 그 밖의 모델은 Interactions API로 호출한다.
LEGACY_MODEL_PREFIXES = ("gemini-2.5-", "gemini-3.1-")

INTERACTIONS_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"

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

# 3.8 인라인 보컬 태그 (--list-tags 출력용)
AUDIO_TAGS_REFERENCE = {
    "비언어 사운드": [
        "<laugh>", "<chuckle>", "<giggle>", "<snicker>", "<cackle>", "<cheer>",
        "<sigh>", "<breath>", "<heavy breath>", "<exhales>", "<gasp>", "<pant>",
        "<cough>", "<sneeze>", "<yawn>", "<throat-clearing>", "<tsk>", "<pff>",
        "<cry>", "<sob>", "<whimper>", "<groan>", "<moan>", "<argh>",
        "<growl>", "<grunt>", "<grr>", "<hiss>", "<snort>",
        "<scream>", "<shout>", "<shriek>", "<whispers>",
    ],
    "페이싱": [
        "<short pause>", "<long pause>",
    ],
}

# 레거시(3.1) 오디오 태그 레퍼런스
LEGACY_AUDIO_TAGS_REFERENCE = {
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

# 레거시 raw PCM 응답을 WAV로 감쌀 때의 설정 (audio/L16;codec=pcm;rate=24000)
SAMPLE_RATE = 24000
SAMPLE_WIDTH = 2  # 16bit = 2 bytes
CHANNELS = 1  # mono

# 입력 토큰 제한 (8,192) 근처 경고 임계값 (글자수 기준 ~4글자/토큰)
TOKEN_WARNING_THRESHOLD = 7500
CHARS_PER_TOKEN_ESTIMATE = 4


def save_wav(audio_data, output_file):
    """오디오를 WAV 파일로 저장. 이미 WAV(3.8 응답)면 그대로 쓰고, raw PCM(레거시)이면 헤더를 붙인다."""
    if audio_data[:4] == b"RIFF":
        with open(output_file, 'wb') as f:
            f.write(audio_data)
        return
    pcm_data = audio_data
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


def is_legacy_model(model):
    """generate_content 경로를 쓰는 레거시 모델(2.5·3.1)인지 판정"""
    return model.startswith(LEGACY_MODEL_PREFIXES)


def list_tags(model):
    """모델에 맞는 오디오 태그 레퍼런스 출력"""
    if is_legacy_model(model):
        list_legacy_tags()
        return

    print(f"\n{model} 인라인 보컬 태그 레퍼런스")
    print("=" * 60)
    print("태그는 본문에 꺾쇠로 삽입합니다. 비영어 본문과 혼합 사용 가능합니다.")
    print("말투·감정처럼 문장 전체에 걸리는 지시는 태그 대신 --style을 쓰세요.\n")

    for category, tags in AUDIO_TAGS_REFERENCE.items():
        print(f"[{category}]")
        for i in range(0, len(tags), 4):
            print("  " + "  ".join(f"{t:<20}" for t in tags[i:i + 4]))
        print()

    print("=" * 60)
    print("사용 예시:")
    print('  이건 비밀인데 <whispers> 사실 나도 몰랐어. <laugh>')
    print('  잠깐만요. <long pause> 이제 시작합니다.')
    print("\n전체 목록: https://ai.google.dev/gemini-api/docs/speech-generation")


def list_legacy_tags():
    """레거시(3.1) 오디오 태그 레퍼런스 출력"""
    print("\nGemini 3.1 Flash TTS 오디오 태그 레퍼런스")
    print("=" * 60)
    print("태그는 본문에 인라인으로 삽입하며, 영어 태그만 인식됩니다.")
    print("비영어 본문과 혼합 사용 가능합니다.\n")

    for category, tags in LEGACY_AUDIO_TAGS_REFERENCE.items():
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


def validate_voice(voice_name, model):
    """음성 이름 유효성 검사. 3.8 이후는 프리셋 밖의 라이브러리 음성·voice_ ID도 그대로 넘긴다."""
    for voice in AVAILABLE_VOICES:
        if voice.lower() == voice_name.lower():
            return voice
    if not is_legacy_model(model):
        return voice_name
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


def legacy_single_speaker_tts(client, types, text, voice_name, model,
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


def legacy_multi_speaker_tts(client, types, text, voice1, voice2, model,
                      style=None, temperature=None, language_code=None):
    """다중 화자 TTS 수행"""
    segments = parse_multi_speaker_text(text)

    if not segments:
        print("경고: 화자 태그를 찾을 수 없습니다. 단일 화자로 처리합니다.")
        return legacy_single_speaker_tts(
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


def interactions_tts(api_key, turns, speakers, model, style=None, temperature=None):
    """
    Interactions API(3.8 이후)로 TTS 수행.
    turns: [(speaker 이름 또는 None, 대사)], speakers: [(speaker 이름, 음성)].
    단일 화자는 speakers를 [(None, 음성)]로 넘긴다.
    """
    content = []
    for speaker, text in turns:
        metadata = {"type": "speech_metadata"}
        if speaker:
            metadata["speaker"] = speaker
        if style:
            metadata["style"] = style
        item = {"type": "text", "text": text}
        if len(metadata) > 1:
            item["annotations"] = [metadata]
        content.append(item)

    if len(speakers) == 1:
        speech_config = [{"voice": speakers[0][1]}]
    else:
        speech_config = {
            "mode": "conversational",
            "speakers": [{"speaker": name, "voice": voice} for name, voice in speakers],
        }

    generation_config = {"speech_config": speech_config}
    if temperature is not None:
        generation_config["temperature"] = temperature

    body = {
        "model": model,
        "input": [{"type": "user_input", "content": content}],
        "response_format": {"type": "audio"},
        "generation_config": generation_config,
    }
    request = urllib.request.Request(
        INTERACTIONS_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
    )
    try:
        # 출력 한도(~655초 분량)를 넘는 여유를 둔다
        with urllib.request.urlopen(request, timeout=900) as response:
            result = json.load(response)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')}") from None
    except urllib.error.URLError as e:
        raise RuntimeError(f"요청 실패({e.reason}). 시간 초과라면 텍스트를 분할해 보세요.") from None

    usage = result.get("usage") or {}
    if usage:
        print(f"  토큰 사용: 입력 {usage.get('total_input_tokens')} + 출력 {usage.get('total_output_tokens')}"
              f" = 합계 {usage.get('total_tokens')}")

    for step in reversed(result.get("steps", [])):
        for block in reversed(step.get("content", [])):
            if block.get("type") == "audio":
                return base64.b64decode(block["data"])
    raise RuntimeError(f"응답에 오디오가 없습니다: {json.dumps(result, ensure_ascii=False)[:500]}")


def single_speaker_tts(api_key, text, voice, model, style=None, temperature=None):
    """단일 화자 TTS (3.8 이후)"""
    info_parts = [f"음성: {voice}", f"모델: {model}"]
    if temperature is not None:
        info_parts.append(f"temperature: {temperature}")
    print(f"음성 변환 중... ({', '.join(info_parts)})")
    return interactions_tts(api_key, [(None, text)], [(None, voice)], model,
                            style=style, temperature=temperature)


def multi_speaker_tts(api_key, text, voice1, voice2, model, style=None, temperature=None):
    """다중 화자 TTS (3.8 이후). 대사마다 speech_metadata.speaker를 붙인다."""
    segments = parse_multi_speaker_text(text)
    if not segments:
        print("경고: 화자 태그를 찾을 수 없습니다. 단일 화자로 처리합니다.")
        return single_speaker_tts(api_key, text, voice1, model, style=style, temperature=temperature)

    print(f"다중 화자 모드: {len(segments)}개 세그먼트 감지")
    print(f"  화자1: {voice1} / 화자2: {voice2} / 모델: {model}")
    if temperature is not None:
        print(f"  temperature: {temperature}")
    print("음성 변환 중...")

    turns = [(f"Speaker{seg['speaker']}", seg['text']) for seg in segments]
    speakers = [("Speaker1", voice1), ("Speaker2", voice2)]
    return interactions_tts(api_key, turns, speakers, model, style=style, temperature=temperature)


def main():
    parser = argparse.ArgumentParser(
        description=f'Gemini TTS - 텍스트를 음성으로 변환 (기본: {DEFAULT_MODEL})',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  기본 변환:
    python gemini_tts.py input.txt
    python gemini_tts.py input.txt --voice Puck

  오디오 태그 (본문에 인라인 삽입):
    # input.txt 내용: "이건 비밀인데 <whispers> 사실 나도 몰랐어. <laugh>"
    python gemini_tts.py input.txt --voice Aoede

  스타일 지시 + 변동성 제어:
    python gemini_tts.py input.txt --style "천천히, 따뜻한 목소리로" --temperature 1.5

  다중 화자 (본문에 [화자1] / [화자2] 태그):
    python gemini_tts.py dialogue.txt --multi-speaker --voice1 Kore --voice2 Puck

  저비용 대량 생성:
    python gemini_tts.py input.txt --model gemini-3.8-flash-lite-tts

  레거시 모델로 폴백 (--language-code는 레거시 전용):
    python gemini_tts.py input.txt --model gemini-3.1-flash-tts-preview --language-code ko-KR

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
    parser.add_argument('--style', help='스타일 지시 (예: "천천히, 따뜻하게")')
    parser.add_argument('--temperature', type=float, default=None,
                        help='음성 변동성 (0.0-2.0, 기본: 모델 기본값)')
    parser.add_argument('--language-code', dest='language_code', default=None,
                        help='언어 코드, 레거시 모델 전용 (예: ko-KR, en-US, ja-JP)')
    parser.add_argument('--model', default=DEFAULT_MODEL,
                        help=f'모델명 override (기본: {DEFAULT_MODEL})')
    parser.add_argument('--list-voices', action='store_true', help='음성 목록 출력')
    parser.add_argument('--list-tags', action='store_true', help='오디오 태그 레퍼런스 출력')

    args = parser.parse_args()

    if args.list_voices:
        list_voices()
        return
    if args.list_tags:
        list_tags(args.model)
        return

    legacy = is_legacy_model(args.model)
    if legacy:
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
        voice1 = validate_voice(args.voice1, args.model)
        voice2 = validate_voice(args.voice2, args.model)
        if not voice1:
            print(f"오류: 알 수 없는 음성입니다: {args.voice1}")
            print("--list-voices 옵션으로 사용 가능한 음성을 확인하세요.")
            return
        if not voice2:
            print(f"오류: 알 수 없는 음성입니다: {args.voice2}")
            print("--list-voices 옵션으로 사용 가능한 음성을 확인하세요.")
            return
    else:
        voice = validate_voice(args.voice, args.model)
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

    if not legacy:
        if args.language_code:
            print(f"참고: {args.model} 모델은 언어를 자동 감지하므로 --language-code를 무시합니다.")
        if args.multi_speaker:
            audio_data = multi_speaker_tts(
                api_key, text, voice1, voice2, args.model,
                style=args.style, temperature=args.temperature,
            )
        else:
            audio_data = single_speaker_tts(
                api_key, text, voice, args.model,
                style=args.style, temperature=args.temperature,
            )
    else:
        client = genai.Client(api_key=api_key)
        if args.multi_speaker:
            audio_data = legacy_multi_speaker_tts(
                client, types, text, voice1, voice2, args.model,
                style=args.style, temperature=args.temperature,
                language_code=args.language_code,
            )
        else:
            audio_data = legacy_single_speaker_tts(
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

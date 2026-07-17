# TTS (텍스트 → 음성)

| 도구 | 출력 | 환경변수 | 비고 |
|------|------|---------|------|
| `TTS/gemini_tts.py` | WAV (`_gemini_tts.wav`) | `GEMINI_API_KEY` | 단일/다중 화자, 30개 프리셋, 200+ 오디오 태그 |
| `TTS/elevenlabs_tts.py` | MP3 (`_elevenlabs.mp3`) | `ELEVENLABS_API_KEY` | v3, 단일+다중 통합 (자동 감지) |
| `TTS/openai_tts.py` | MP3 (`_openai.mp3`) | `OPENAI_API_KEY` | gpt-4o-mini-tts, 13개 음성, `--instructions` 자연어 스티어링, 자동 청크 분할 |
| `TTS/speechify_tts.py` | MP3 (`_speechify.mp3`) | `SPEECHIFY_API_KEY` | simba-3.2, SSML 변환(속도·피치·볼륨·감정·정지) |

## Gemini TTS

기본 모델: **gemini-3.1-flash-tts-preview** (2026-04 업데이트). 영어 태그 + 한국어 본문 혼합 OK.

```bash
python TTS/gemini_tts.py "안녕하세요"
python TTS/gemini_tts.py --list-voices              # 30개 프리셋
python TTS/gemini_tts.py --list-tags                # 200+ 오디오 태그 목록
python TTS/gemini_tts.py input.txt --temperature 0.7 --language-code ko-KR
python TTS/gemini_tts.py input.txt --model gemini-3.1-flash-tts-preview
```

옵션: `--list-voices` / `--list-tags` / `--temperature 0.0-2.0` / `--language-code ko-KR` / `--model <override>`.

200+ 인라인 오디오 태그로 감정·페이싱 제어:
- `[excited]`, `[whispering]`, `[long pause]`, `[laughing]` 등
- 본문 안에 직접 삽입: `"여기서 [whispering] 비밀이야 [long pause] 그것은..."`

### Gemini TTS 한도 (중요)

| 항목 | 한도 |
|------|------|
| 입력 토큰 | 8,192 |
| 입력 바이트 | 8,000 (Vertex AI) |
| 출력 토큰 | 16,384 (~655초 ≈ **11분**) |

**출력 한도 근접 시 후반부 내용이 무한 반복됨**: 긴 텍스트는 반드시 청크 분할 후 결합.

`--style` 프리픽스는 긴 텍스트(~2000토큰+)에서 `INVALID_ARGUMENT` 오류를 유발하므로 **인라인 오디오 태그로 대체** 권장.

출처: ai.google.dev/gemini-api/docs/models/gemini-3.1-flash-tts-preview

## ElevenLabs TTS

단일/다중 화자 통합 스크립트. **자동 감지**: 파일에 `화자: 대사` 콜론 패턴이 **2개 이상** 있으면 자동으로 dialogue 모드 전환.

```bash
# 단일 화자
python TTS/elevenlabs_tts.py "한 화자가 말하는 텍스트"
python TTS/elevenlabs_tts.py input.txt --voice Yuna --speed 1.1 --stability 0.5

# 다중 화자 (콜론 패턴 자동 감지)
python TTS/elevenlabs_tts.py dialogue.txt
# 강제 다중: --multi-speaker
# 강제 단일 (콜론 패턴 무시): --single

# 화자 매핑
python TTS/elevenlabs_tts.py dialogue.txt --voice-map "지영=Yuna,현우=Seojin"

# 목록
python TTS/elevenlabs_tts.py --list-voices
python TTS/elevenlabs_tts.py --list-tags
```

옵션: `--voice <name>` / `--speed 0.7-1.2` / `--stability 0.0-1.0` / `--voice-map "화자=Voice,..."` / `--multi-speaker` / `--single` / `--list-voices` / `--list-tags`.

감정 태그(`[excited]`, `[thoughtfully]` 등)는 두 모드 모두 지원.

**API 제약**: `text_to_dialogue` API는 `voice_settings`(속도·안정성)를 미지원 → `--speed`, `--stability`는 단일 모드에서만 적용됨.

전체 음성 목록: `python TTS/elevenlabs_tts.py --list-voices`.

## OpenAI TTS

기본 모델: **gpt-4o-mini-tts** (snapshot `gpt-4o-mini-tts-2025-12-15`). 13개 빌트인 음성, 공식 권장은 **marin / cedar**.

```bash
python TTS/openai_tts.py input.txt
python TTS/openai_tts.py "안녕하세요. 오늘 날씨가 참 좋네요."        # 직접 텍스트
python TTS/openai_tts.py input.txt --voice cedar --speed 1.1
python TTS/openai_tts.py input.txt --instructions "Cheerful and warm"
python TTS/openai_tts.py input.txt --format wav
python TTS/openai_tts.py --list-voices                              # 13개
python TTS/openai_tts.py --list-models                              # 5종 모델
```

옵션: `--voice <name>` / `--model gpt-4o-mini-tts|tts-1-hd|tts-1` / `--format mp3|opus|aac|flac|wav|pcm` / `--speed 0.25-4.0` / `--instructions "<자연어 톤 지시>"` / `--chunk-size 3000`.

### OpenAI TTS 차별점: `--instructions` 자연어 스티어링

`gpt-4o-mini-tts` 계열만 지원 (`tts-1` / `tts-1-hd`는 미지원). 톤·악센트·감정·속도·속삭임을 자연어 한 줄로 지시:

```bash
python TTS/openai_tts.py input.txt --instructions "Speak in a British accent, slowly, like teaching a child"
python TTS/openai_tts.py input.txt --instructions "Calm, professional narrator for an audiobook"
python TTS/openai_tts.py input.txt --instructions "Whisper softly, intimate and warm"
```

### OpenAI TTS 한도 (중요)

| 항목 | 한도 |
|------|------|
| `input` 글자 | 4,096 chars |
| 입력 토큰 (gpt-4o-mini-tts) | 2,000 |

**한도 초과 시 자동 청크 분할 + 바이트 concat**. `mp3`/`opus`/`aac` 포맷은 안전, `wav`/`flac`/`pcm`은 청크 분할이 발생하면 헤더 중복으로 손상될 수 있으니 `--chunk-size 4000` 이하로 짧은 입력에만 사용 권장.

한국어 본문도 지원하지만 음성 자체는 영어 최적화다. 한국어 발음 자연스러움은 ElevenLabs Yuna/DoHyeon이 더 우수. OpenAI는 영어 + `--instructions` 스티어링 워크플로우가 강점.

**사용 정책**: AI 합성 음성임을 최종 사용자에게 명시할 의무 (스크립트 종료 시 안내 출력).

출처: developers.openai.com/api/docs/guides/text-to-speech | 미리듣기 https://openai.fm

# TTS (텍스트 → 음성)

## 목차

- [Gemini TTS](#gemini-tts)
- [ElevenLabs TTS](#elevenlabs-tts)
- [OpenAI TTS](#openai-tts)
- [Speechify TTS](#speechify-tts)
- [긴 텍스트 분할](#긴-텍스트-분할)

| 도구 | 출력 | 환경변수 | 비고 |
|------|------|---------|------|
| `TTS/gemini_tts.py` | WAV (`_gemini_tts.wav`) | `GEMINI_API_KEY` | 3.8 기본(Lite 선택), 단일/다중 화자, 30개 프리셋 + 확장 음성, 인라인 보컬 태그 |
| `TTS/elevenlabs_tts.py` | MP3 (`_elevenlabs.mp3`) | `ELEVENLABS_API_KEY` | 단일 화자 기본 v4(다중 화자는 서버 기본 모델), 단일+다중 통합 (자동 감지) |
| `TTS/openai_tts.py` | MP3 (`_openai.mp3`) | `OPENAI_API_KEY` | gpt-4o-mini-tts, 13개 음성, `--instructions` 자연어 스티어링, 자동 청크 분할 |
| `TTS/speechify_tts.py` | MP3 (`_speechify.mp3`) | `SPEECHIFY_API_KEY` | simba-3.0(기본, 한국어 포함), SSML 변환(속도·피치·볼륨·감정·정지) |

입력은 모두 `.txt`·`.md` 파일이다. 텍스트를 인자로 직접 받는 것은 `openai_tts.py`뿐이다.

## Gemini TTS

기본 모델: **gemini-3.8-flash-tts** (2026-09 정식판). 언어는 자동 감지한다. 저비용 대량 생성은 **gemini-3.8-flash-lite-tts**.

```bash
python TTS/gemini_tts.py input.txt
python TTS/gemini_tts.py --list-voices              # 30개 프리셋
python TTS/gemini_tts.py --list-tags                # 3.8 꺾쇠 태그 목록 (--model 레거시면 3.1 태그)
python TTS/gemini_tts.py input.txt --style "천천히, 따뜻하게" --temperature 0.7
python TTS/gemini_tts.py dialogue.txt --multi-speaker --voice1 Kore --voice2 Puck
python TTS/gemini_tts.py input.txt --model gemini-3.8-flash-lite-tts
python TTS/gemini_tts.py input.txt --model gemini-3.1-flash-tts-preview --language-code ko-KR
```

옵션: `--voice`(기본 Puck) / `--multi-speaker --voice1 --voice2` / `--style` / `--temperature 0.0-2.0`(생략하면 모델 기본값) / `--model <override>` / `--language-code`(레거시 전용) / `--list-voices` / `--list-tags`.

**다중 화자**(`--multi-speaker`를 줄 때만, 자동 감지 없음): 대본의 `[화자1]`/`[화자2]`(또는 `[Speaker1]`/`[Speaker2]`, `[1]`/`[2]`) 태그로 대사를 나눈다. 두 명까지이며 다른 태그는 본문으로 읽힌다. 모든 모델에 같다.

| 모델 | 출력 요금 (1M tok) | 비고 |
|------|------|------|
| gemini-3.8-flash-tts | $18 (2026-12-31까지 무료) | 기본값. 표현력 우선 |
| gemini-3.8-flash-lite-tts | $12 (2026-12-31까지 무료) | 대량·저비용 |
| gemini-3.1-flash-tts-preview | $20 | 레거시 |

### 3.8과 레거시(2.5·3.1)의 차이

- **호출 경로**: 3.8 이후는 Interactions API를 REST로 직접 호출한다(SDK 불필요). 모델명이 `gemini-2.5-`·`gemini-3.1-`로 시작하면 기존 `generate_content` 경로를 쓴다.
- **입력은 낭독 대본으로만 취급된다**: 본문 앞에 지시문을 붙이면 그대로 읽는다. 그래서 `--style`은 대사마다 `speech_metadata.style`로 전달된다.
- **다중 화자**: 3.8은 대사마다 화자 이름을 붙여 보낸다(스크립트가 태그에서 채운다).
- **태그 표기**: 3.8은 꺾쇠(`<laugh>`, `<whispers>`, `<long pause>`), 3.1은 대괄호(`[whispering]`, `[long pause]`).
- **언어 코드**: 3.8은 `language_code`를 거부한다(자동 감지). 넘기면 안내 후 무시한다.
- **응답 형식**: 3.8은 완성된 WAV, 레거시는 헤더 없는 PCM이다. 저장 시 자동 판별한다.
- **음성**: 3.8은 프리셋 밖의 확장 라이브러리 음성·보이스 디자인 ID(`voice_...`)도 `--voice`에 그대로 넘길 수 있다.

### Gemini TTS 한도 (중요)

| 항목 | 한도 |
|------|------|
| 입력 토큰 | 8,192 |
| 입력 바이트 | 8,000 (Vertex AI) |
| 출력 토큰 | 16,384 (~655초 ≈ **11분**) |

3.8·3.1 모두 같다. **출력 한도 근접 시 후반부 내용이 무한 반복된다.** 한도를 넘는 텍스트는 [긴 텍스트 분할](#긴-텍스트-분할)대로 나눠 부른다.

스크립트는 글자 수 ÷ 4로 입력 토큰을 어림해 7,500을 넘으면 호출하지 않고 멈춘다. 영어 기준 어림이라 한국어는 이 가드를 통과해도 한도를 넘을 수 있다.

레거시 모델에서 `--style` 프리픽스는 긴 텍스트(~2000토큰+)에서 `INVALID_ARGUMENT` 오류를 유발하므로 인라인 오디오 태그로 대체 권장.

출처: ai.google.dev/gemini-api/docs/speech-generation, ai.google.dev/gemini-api/docs/pricing

## ElevenLabs TTS

단일/다중 화자 통합 스크립트. **자동 감지**: `화자: 대사` 콜론 줄이 **2개 이상**이고 서로 다른 화자가 **2명 이상**이면 dialogue 모드로 전환한다. dialogue 모드는 `text_to_dialogue` API로 대화를 한 요청에 보내므로, 화자별로 나눠 부르는 방식과 달리 모델이 대화 흐름을 함께 본다.

```bash
# 단일 화자
python TTS/elevenlabs_tts.py input.txt
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

옵션: `--voice <name>` / `--speed 0.7-1.2`(기본 1.2) / `--stability 0.0-1.0` / `--model`(기본 `eleven_v4`, 단일 모드만) / `--voice-map "화자=Voice,..."` / `--multi-speaker` / `--single` / `--list-voices` / `--list-tags`.

감정 태그(`[excited]`, `[thoughtfully]` 등)는 두 모드 모두 지원.

**API 제약**: `text_to_dialogue` API는 `voice_settings`(속도·안정성)를 미지원 → `--speed`, `--stability`는 단일 모드에서만 적용된다. `--model`도 단일 모드에서만 API에 전달된다.

한국어 프리셋 7종(Yuna·Kelee 여성, DoHyeon·Seojin·Jason·Hyunsu·Min 남성) + 영어 2종(James·Kiki). 다중 화자에서 `--voice-map`이 없으면 별칭(유나·도현 등 프리셋 이름, `화자1`=Yuna·`화자2`=DoHyeon)으로 먼저 배정하고, 나머지 화자는 아직 배정되지 않은 프리셋을 순서대로 받는다. 한국어 7종 다음은 영어 음성이므로 화자가 8명 이상이거나 특정 음성을 원하면 `--voice-map`으로 지정한다.

전체 음성 목록: `python TTS/elevenlabs_tts.py --list-voices`.

### text_to_dialogue 입력 길이

한 요청의 총 입력이 길면 실패하거나 뒷부분이 잘린다. 엔트리 총합 **2,000자 내외**로 [긴 텍스트 분할](#긴-텍스트-분할)대로 나눠 부른다. 청크 경계는 화자 전환 지점에 두어야 문장이 끊기지 않고, 조각마다 두 화자 이상이 있어야 dialogue 모드로 감지된다.

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

**입력이 `--chunk-size`(기본 3,000자, 최대 4,096)를 넘으면 문장 경계로 자동 분할해 바이트로 잇는다.** `mp3`/`opus`/`aac`/`pcm`은 안전하고, `wav`/`flac`은 조각마다 헤더가 붙어 손상될 수 있으니 입력을 chunk-size 이하로 유지한다. `pcm`은 헤더 없는 원시 PCM이라 `.pcm` 파일로 저장된다.

한국어 본문도 지원하지만 음성 자체는 영어 최적화다. 한국어 발음 자연스러움은 ElevenLabs Yuna/DoHyeon이 더 우수. OpenAI는 영어 + `--instructions` 스티어링 워크플로우가 강점.

**사용 정책**: AI 합성 음성임을 최종 사용자에게 명시할 의무 (스크립트 종료 시 안내 출력).

출처: developers.openai.com/api/docs/guides/text-to-speech | 미리듣기 https://openai.fm

## Speechify TTS

기본 모델 **simba-3.0**은 카탈로그 음성 전부와 한국어 음성을 받는다. **simba-3.2**는 영어 전용이라 `_32` 접미사 음성과 함께 지정할 때만 쓴다(`--model simba-3.2 --voice harper_32`). 기본 음성 `george`는 한국어 음성이 아니므로 한국어 글은 `--voice`에 한국어 voice_id를 준다. 스크립트에 음성 목록 옵션은 없다.

옵션: `--voice` / `--model` / `-o <출력 경로>` / `--no-ssml` / `--rate 0%` / `--pitch +3%` / `--volume medium` / `--break-time 300ms` / `--emotion` / `--cadence` (값은 기본값).

## 긴 텍스트 분할

스크립트가 알아서 나누는 것은 OpenAI TTS뿐이다. Gemini TTS와 ElevenLabs 다중 화자 모드는 입력을 한 번에 보내므로, 한도를 넘는 입력은 에이전트가 문단·화자 전환 경계에서 나눠 조각마다 부르고 ffmpeg로 잇는다(`ffmpeg -f concat -safe 0 -i list.txt -c copy <출력>`).

조각마다 같은 `--voice`·`--style`·`--temperature`를 준다. ElevenLabs 다중 화자는 자동 배정이 조각마다 등장 순서로 다시 정해져 음성이 뒤바뀔 수 있으므로 모든 조각에 같은 `--voice-map`을 준다.

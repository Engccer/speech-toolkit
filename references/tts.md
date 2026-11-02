# TTS (텍스트 → 음성)

## 목차

- [Gemini TTS](#gemini-tts)
- [ElevenLabs TTS](#elevenlabs-tts)
- [OpenAI TTS](#openai-tts)
- [Speechify TTS](#speechify-tts)
- [Azure TTS](#azure-tts)
- [긴 텍스트 분할](#긴-텍스트-분할)

| 도구 | 출력 | 환경변수 | 비고 |
|------|------|---------|------|
| `TTS/gemini_tts.py` | WAV (`_gemini_tts.wav`) | `GEMINI_API_KEY` | 3.8 기본(Lite 선택), 단일/다중 화자, 30개 프리셋 + 확장 음성, 인라인 보컬 태그 |
| `TTS/elevenlabs_tts.py` | MP3 (`_elevenlabs.mp3`) | `ELEVENLABS_API_KEY` | 단일 화자 기본 v4(다중 화자는 서버 기본 모델), 단일+다중 통합 (자동 감지) |
| `TTS/openai_tts.py` | MP3 (`_openai.mp3`) | `OPENAI_API_KEY` | gpt-realtime-2.1-mini 기본, 10개 음성·원문 전사 대조·PCM 결합 |
| `TTS/speechify_tts.py` | MP3 (`_speechify.mp3`) | `SPEECHIFY_API_KEY` | simba-3.5(기본, 한국어 포함 48개 언어), SSML 변환(속도·피치·볼륨·정지) |
| `TTS/azure_tts.py` | WAV (`_azure_tts.wav`) | `AZURE_SPEECH_KEY`·`AZURE_SPEECH_REGION` | Azure AI Speech REST, 표준 라이브러리만, SSML 배속 0.5~2.0 |
| `TTS/long_tts.py` | ElevenLabs MP3 / Gemini·Azure WAV | 제공자의 키 | 긴 단일 화자 대본을 나눠 합성·병합하고 길이로 절단 검증. [긴 텍스트 분할](#긴-텍스트-분할) |

입력은 모두 `.txt`·`.md` 파일이다. 텍스트를 인자로 직접 받는 것은 `openai_tts.py`뿐이다.

## Gemini TTS

기본 모델: **gemini-3.8-flash-tts** (2026-09 정식판). 언어는 자동 감지한다. 저비용 대량 생성은 **gemini-3.8-flash-lite-tts**.

```bash
python TTS/gemini_tts.py input.txt
python TTS/gemini_tts.py --list-voices              # 30개 프리셋
python TTS/gemini_tts.py --list-tags                # 3.8 꺾쇠 태그 목록 (--model 레거시면 3.1 태그)
python TTS/gemini_tts.py input.txt --style "천천히, 따뜻하게"
python TTS/gemini_tts.py dialogue.txt --multi-speaker --voice1 Kore --voice2 Puck
python TTS/gemini_tts.py input.txt --model gemini-3.8-flash-lite-tts
python TTS/gemini_tts.py input.txt --model gemini-3.1-flash-tts-preview --language-code ko-KR
```

옵션: `--voice`(기본 Puck) / `--multi-speaker --voice1 --voice2` / `--style` / `--model <override>` / `--language-code`(레거시 전용) / `--list-voices` / `--list-tags`.

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

**eleven_v4 실측**(한국어, Yuna): 요청당 상한 10,000자. 초당 약 7.1자로 v3(초당 4.35자 @1.0)보다 빠르고, `--speed`를 1.2로 올려도 빨라지지 않았다. 한 요청이 약 293초를 넘으면 문장 중간 100~150자를 에러 없이 건너뛰었다(약 293초·620초 지점). 긴 대본은 `long_tts.py`로 나눈다.

**API 제약**: `text_to_dialogue` API는 `voice_settings`(속도·안정성)를 미지원 → `--speed`, `--stability`는 단일 모드에서만 적용된다. `--model`도 단일 모드에서만 API에 전달된다.

한국어 프리셋 7종(Yuna·Kelee 여성, DoHyeon·Seojin·Jason·Hyunsu·Min 남성) + 영어 2종(James·Kiki). 다중 화자에서 `--voice-map`이 없으면 별칭(유나·도현 등 프리셋 이름, `화자1`=Yuna·`화자2`=DoHyeon)으로 먼저 배정하고, 나머지 화자는 아직 배정되지 않은 프리셋을 순서대로 받는다. 한국어 7종 다음은 영어 음성이므로 화자가 8명 이상이거나 특정 음성을 원하면 `--voice-map`으로 지정한다.

전체 음성 목록: `python TTS/elevenlabs_tts.py --list-voices`.

### text_to_dialogue 입력 길이

한 요청의 총 입력이 길면 실패하거나 뒷부분이 잘린다. 엔트리 총합 **2,000자 내외**로 [긴 텍스트 분할](#긴-텍스트-분할)대로 나눠 부른다. 청크 경계는 화자 전환 지점에 두어야 문장이 끊기지 않고, 조각마다 두 화자 이상이 있어야 dialogue 모드로 감지된다.

## OpenAI TTS

기본·유일 지원 모델은 **gpt-realtime-2.1-mini**다. 기본 음성은 **marin**이며 **cedar**도 선택할 수 있다. Realtime API로 청크를 합성하고 PCM을 결합해 음성 파일 하나로 저장한다.

```bash
python TTS/openai_tts.py input.txt
python TTS/openai_tts.py "안녕하세요. 오늘 날씨가 참 좋네요."        # 직접 텍스트
python TTS/openai_tts.py input.txt --voice cedar --speed 1.1
python TTS/openai_tts.py input.txt --instructions "Cheerful and warm"
python TTS/openai_tts.py input.txt --format wav
python TTS/openai_tts.py --list-voices                              # 10개
python TTS/openai_tts.py --list-models
```

옵션: `--voice <name>` / `--model gpt-realtime-2.1-mini` / `--format mp3|opus|aac|flac|wav|pcm` / `--speed 0.25~1.5` / `--instructions "<자연어 톤 지시>"` / `--chunk-size 3000`.

무인자 실행은 현재 폴더의 `.txt` 우선, 다음 `.md` 중 첫 파일 하나를 고른다. 기존 파일은 UTF-8로 읽고, 존재하지 않는 경로는 직접 텍스트로 취급한다. 출력은 입력 파일 옆 `<stem>_openai.<format>`이며 직접 텍스트는 현재 폴더 `output_openai.<format>`이다.

### 자연어 톤 지시

`--instructions`로 톤·악센트·감정·속도·속삭임을 요청한다.

```bash
python TTS/openai_tts.py input.txt --instructions "Speak in a British accent, slowly, like teaching a child"
python TTS/openai_tts.py input.txt --instructions "Calm, professional narrator for an audiobook"
python TTS/openai_tts.py input.txt --instructions "Whisper softly, intimate and warm"
```

### 처리와 검증

Realtime은 응답을 생성하는 API여서 원문 낭독 지시 준수가 보장되지 않는다. 청크마다 모델 전사와 원문을 대조하며, 실제 음성은 별도 청취로 확인한다. [Realtime 계약](https://developers.openai.com/api/reference/resources/realtime/client-events)

| 항목 | 동작 |
|---|---|
| 모델 | `gpt-realtime-2.1-mini`가 기본값이며 유일한 지원 모델. 다른 모델 값은 호출 전에 거부. 자동 재시도·폴백 없음 |
| 음성 | `alloy`, `ash`, `ballad`, `coral`, `echo`, `sage`, `shimmer`, `verse`, `marin`, `cedar`. `fable`·`nova`·`onyx`는 호출 전에 거부, 대체 없음 |
| 속도·청크 | `--speed 0.25~1.5`, `--chunk-size 1~4096`. 기본값은 각각 1.0·3000. 문자 분할 기준은 토큰·발화 완결성 보장이 아님 |
| 스타일 | `--instructions`를 낭독 지시와 분리된 스타일 값으로 전달 |
| 원문 보존 | 네트워크 전에 원문과 청크 재결합을 NFC·공백 제거 기준으로 비교. 분할 손실이 있으면 문자 슬라이스로 재분할 |
| 전사 대조 | 청크마다 완료된 오디오 전사와 원문을 NFC·공백 제거 기준으로 비교. 숫자·문장부호·단어 차이도 실패. 정상 발화도 표기 차이로 거부될 수 있음 |
| 완료 판정 | 최종 completed 상태·응답/item/content 식별자·단일 output_audio·빈 오디오 여부를 확인. 전사 일치는 실제 발화 정확성 보장이 아니므로 중요 자료는 전체 청취 필요 |
| 파일 | PCM 24kHz·16bit·mono로 청크를 결합. PCM은 그대로, WAV는 헤더 하나, MP3·Opus·AAC·FLAC은 전체 PCM을 한 번 인코딩 |
| 의존성 | websockets>=15.0.1. 압축 출력에는 libmp3lame·libopus·aac·flac 중 해당 ffmpeg 인코더 필요. 자동 설치 없음 |
| 실패·저장 | 유료 요청 전 목적지 임시 파일 생성. 검증 뒤 `os.replace` 성공이 완료 시점. 그 전 실패·중단은 exit 1과 이전 출력 보존. 그 뒤 안내 출력 실패는 성공을 바꾸지 않음 |
| 대기 한도 | 연결·세션 대기 20초, 세션 설정 송신·확인 합계 20초, 청크의 생성 요청 송신·수신 합계 180초. 인코더 확인 20초, 변환·디코드 각각 180초, 전체 55분. 오래 걸리면 더 작은 chunk-size를 명시해 다시 실행 |
| 중단 | 활성 response_id로 취소를 최선 노력 요청하고 연결 종료. 취소 송신과 연결 종료에는 각각 5초 watchdog을 적용. 송신·종료가 정체되면 소켓 shutdown으로 깨우며, watchdog 발동은 실패로 처리. 취소 확인 없이 비용 중단을 보장하지 않음. 재실행은 다시 과금될 수 있음 |

강제 종료·전원 차단에서는 임시 파일이 남을 수 있다. 합성·입력·키·의존성 오류는 exit 1이다. 지원하지 않는 모델 등 argparse 사용 오류는 exit 2다. help·목록은 exit 0이며 키·SDK가 없어도 동작한다.

Mac의 짧은 영어·한국어 표본은 실합성과 사용자 청취에서 큰 문제가 없었다. Windows도 한국어 1응답·영어 2청크의 실합성·전사·PCM 결합과 여섯 포맷 변환을 확인했다. 긴 자료·다른 음성·극단 배속·Windows 청취·2청크 연결의 실제 청취는 이 결과로 확정하지 않는다.

**사용 정책**: AI 합성 음성임을 최종 사용자에게 명시할 의무 (스크립트 종료 시 안내 출력).

출처: [Realtime API](https://developers.openai.com/api/docs/guides/realtime)

## Speechify TTS

기본 모델 **simba-3.5**는 한국어 포함 48개 언어를 지원하며 모든 카탈로그 음성을 받는다. **simba-3.2**는 영어 음성 전용이다(`--model simba-3.2 --voice george`). 언어를 지정하지 않으면 음성의 locale을 따르므로, 한국어 글은 `--voice ah-reum`처럼 한국어 voice_id를 준다. 기본 음성은 `george`다. **simba-3.0**은 영어·독일어·스페인어·프랑스어·이탈리아어·포르투갈어를 공식 지원한다.

옵션: `--voice` / `--model` / `-o <출력 경로>` / `--no-ssml` / `--rate 0%` / `--pitch +3%` / `--volume medium` / `--break-time 300ms` / `--emotion` / `--cadence` (값은 기본값).

Simba 3.x는 감정 스타일 태그를 수락하지만 음성에 적용하지 않는다. `--emotion`과 그 안의 `--cadence`는 이 제약을 따른다. 모델·음성별 현재 지원 범위는 [Speechify 모델 문서](https://docs.speechify.ai/build/guides/concepts/models)와 API 모델·음성 목록을 확인한다.

## Azure TTS

Azure AI Speech REST API를 표준 라이브러리로 부른다. 기본 음성은 `ko-KR-SunHiNeural`이고 `--list-voices --language-code ko-KR`로 목록을 본다. 출력은 24kHz 16bit 모노 WAV라 변환 단계가 없다.

옵션: `--voice` / `--language-code ko-KR` / `--tempo`(배율) 또는 `--rate +50%` / `--pitch +2st` / `--style cheerful` / `--output-format` / `--output <경로>` / `--retries 0`.

`long_tts.py`의 Azure 발화 속도(7.15자/초)는 한국어 값이다. `ko-`로 시작하지 않는 음성은 `--chars-per-sec`를 주지 않으면 호출 전에 멈춘다.

다른 제공자와 다른 점:

- **배속이 합성 단계에서 바뀐다.** `--tempo`는 SSML `prosody rate`로 들어가 음성 자체가 빨라진다(ffmpeg `atempo` 후처리가 아님). 발화 속도는 배속에 정비례한다. `ko-KR-HyunsuNeural` 한국어 1,464자가 1.0·1.5·2.0배속에서 각각 204.7·136.4·102.3초였다. 범위는 0.5~2.0이고 밖의 값은 말없이 잘린다. 2배보다 빠르게 들으려면 합성 후 `atempo`를 더한다.
- **한도는 문자 수가 아니라 오디오 길이다.** 요청당 생성 오디오가 10분까지다(공식 한도). 2배속이면 같은 10분에 글자가 두 배 들어간다. 긴 대본은 `long_tts.py --provider azure`로 나눈다.
- **F0(무료) 등급은 60초에 요청 20건, 월 50만 자다.** 조각을 잘게 쪼개면 요청 수 한도에 먼저 닿는다. `--retries N`을 주면 429 응답 때 `Retry-After`를 따라(회당 최대 30초) N번까지 다시 시도한다. 기본은 0이고 `long_tts.py`는 3을 준다. 4만 자짜리 오디오북 하나가 월 무료량의 8%를 쓴다.
- **Windows에서 키를 등록하기 전에 띄운 셸은 새 사용자 환경 변수를 물려받지 못한다.** 프로세스 환경에 키가 없으면 사용자 환경 변수(레지스트리)에서 읽는다.

출처: [Azure Speech 한도](https://learn.microsoft.com/azure/ai-services/speech-service/speech-services-quotas-and-limits)

## 긴 텍스트 분할

TTS API는 요청당 문자 상한 안에서도 긴 입력을 에러 없이 망가뜨린다(HTTP 200). eleven_v3는 약 550초에서 뒷부분이 잘리고, eleven_v4는 약 293초를 넘으면 중간을 건너뛰며, Gemini는 약 655초(출력 16,384토큰)에서 잘린다. 한국어는 1자가 1음절이라 영어 기준의 "5,000자 ≈ 5분" 안내보다 훨씬 빨리 이 길이에 닿는다.

**단일 화자 대본은 `long_tts.py`에 맡긴다.** 모델별 발화 속도로 예상 길이를 계산해 문단·문장 경계에서 나누고(v4 240초, v3·Gemini·Azure 300초), 조각마다 합성해 무손실로 잇고, 실제 길이가 예상의 85% 미만이면서 10초 넘게 부족하면 실패로 끝낸다.

```bash
python TTS/long_tts.py script.txt                              # ElevenLabs eleven_v4, Yuna
python TTS/long_tts.py script.txt --model eleven_v3 --speed 1.2
python TTS/long_tts.py script.txt --provider gemini            # gemini-3.8-flash-tts, Puck
python TTS/long_tts.py script.txt --provider azure --speed 2.0  # ko-KR-HyunsuNeural, 2배속
python TTS/long_tts.py script.txt --compact-copy               # + 1.5배속 사본(_compact.mp3, 목표 1.8MB)
```

옵션: `--provider elevenlabs|gemini|azure` / `--model` / `--voice` / `--speed`(ElevenLabs 0.7~1.2·기본 1.2, Azure 0.5~2.0·기본 1.0) / `--chars-per-sec`(speed 1.0 기준 자/초) / `--chunk-seconds` / `--compact-copy` / `--tempo 1.5` / `--target-mb 1.8`. ffmpeg·ffprobe가 필요하다.

발화 속도 상수는 **한국어 대본으로 잰 값**이다. 다른 언어나 스크립트 표에 없는 모델은 `--chars-per-sec`를 준다(표에 없는 모델은 이 값이 없으면 멈춘다). 값이 실제보다 크면 멀쩡한 오디오를 절단으로 오판하고, 작으면 조각이 길어져 상한에 닿는다. 길이 검증은 끝부분 절단을 잡지만 몇 초짜리 중간 누락은 잡지 못하므로, 완결성이 중요하면 결과를 STT로 전사해 대본과 대조한다.

Gemini 다중 화자와 ElevenLabs 다중 화자 모드는 입력을 한 번에 보내므로, 한도를 넘는 입력은 에이전트가 화자 전환 경계에서 나눠 조각마다 부르고 ffmpeg로 잇는다. MP3는 `ffmpeg -f concat -safe 0 -i list.txt -c copy <출력>`, WAV는 조각마다 헤더가 있어 `-c copy` 대신 `-c:a pcm_s16le`로 잇는다.

조각마다 같은 `--voice`·`--style`을 준다. ElevenLabs 다중 화자는 자동 배정이 조각마다 등장 순서로 다시 정해져 음성이 뒤바뀔 수 있으므로 모든 조각에 같은 `--voice-map`을 준다.

# STT (음성 → 텍스트)

## 목차

- [입력 포맷](#입력-포맷)
- [사용 예와 출력 형식](#사용-예와-출력-형식)
- [키텀 파일](#키텀-파일)
- [선택 가이드](#선택-가이드)
- [Deepgram 옵션](#deepgram-옵션)
- [Gemini 3.5 Transcribe 옵션](#gemini-35-transcribe-옵션)
- [Meta Muse Voice Transcribe 옵션](#meta-muse-voice-transcribe-옵션)
- [Daglo ngrok 설정](#daglo-ngrok-설정)

7개 엔진 모두 화자 분리(diarization)를 한다. 파일 크기·길이·정확도·언어로 선택.

| 도구 | 모델 | 화자 분리 | 최대 | 환경변수 | 특이사항 |
|------|------|----------|------|----------|---------|
| `STT/elevenlabs_stt.py` | Scribe v2 | O | 2 GB | `ELEVENLABS_API_KEY` | 가장 큰 파일. 비디오 컨테이너 17종 지원 |
| `STT/gemini_stt.py` | Gemini 3.7 Flash | O(프롬프트) | 9.5 시간 | `GEMINI_API_KEY` | 가장 긴 음성. 20MB+ Files API 자동 사용 |
| `STT/gemini_transcribe_stt.py` | Gemini 3.5 Transcribe | O(최대 8명) | 30분/요청 (화자 분리·단어 타임스탬프를 모두 끄면 60분) | `GEMINI_API_KEY` | 전용 ASR. WER 2.6%. 키텀 파일(custom_vocabulary)·단어 타임스탬프 정식 파라미터. 상한 초과분은 ffmpeg 자동 분할. **public preview** |
| `STT/deepgram_stt.py` | Nova-3 | O | 제한없음 | `DEEPGRAM_API_KEY` | 한국어 기본 설정. 스마트 포맷팅, 단락 구분 |
| `STT/mistral_stt.py` | Voxtral Mini Transcribe v2 | O | 1 GB / 3시간 | `MISTRAL_API_KEY` | 13개 언어. **$0.003/분** |
| `STT/daglo_stt.py` | Daglo (비동기) | O | 제한없음 | `DAGLO_API_KEY` | **ngrok 터널 필요** (로컬 파일 호스팅용) |
| `STT/muse_stt.py` | Muse Voice Transcribe 1.0 | O(20명+) | 10분/요청 (초과분 자동 분할) | `META_API_KEY` | Meta Model API. **$0.003/분**. 스트리밍 WER 3.1%. 언어·키텀 바이어싱, 코드 스위칭. ffmpeg 필수 |

## 입력 포맷

| 도구 | 지원 확장자 |
|------|------------|
| ElevenLabs | MP3, M4A, WAV, FLAC, AAC, OGG, AIFF, WEBM, MP4, AVI, MKV, MOV, WMV, FLV, MPEG, 3GP |
| Gemini | MP3, M4A, WAV, FLAC, AAC, OGG, AIFF, MP4, MOV, AVI, WEBM |
| Gemini 3.5 Transcribe | MP3, M4A, WAV, FLAC, AAC, OGG, AIFF, MP4, MOV, AVI, WEBM |
| Deepgram | MP3, M4A, WAV, FLAC, AAC, OGG, AIFF, MP4, MOV, AVI, WEBM |
| Muse | MP3, M4A, WAV, FLAC, AAC, OGG, AIFF, MP4, MOV, AVI, WEBM, MKV (모두 ffmpeg로 PCM WAV 변환 후 전송) |
| Mistral | MP3, M4A, WAV, FLAC, OGG |
| Daglo | MP3, M4A, WAV, FLAC, AAC, OGG, MP4, MOV, AVI |

## 사용 예와 출력 형식

```bash
python STT/gemini_stt.py meeting.m4a              # 9.5시간까지, Files API 자동
python STT/gemini_transcribe_stt.py meeting.m4a --lang ko-KR   # 전용 ASR, 화자 분리 기본
python STT/elevenlabs_stt.py interview.mp3        # 2GB까지
python STT/deepgram_stt.py podcast.wav            # 한국어 기본, 빠름
python STT/muse_stt.py meeting.m4a --lang ko,en   # 한·영 코드 스위칭, 화자 분리 기본
python STT/mistral_stt.py lecture.flac            # 1GB/3시간, $0.003/분
python STT/daglo_stt.py recording.m4a             # ngrok 사전 설정 필요
```

출력: `[입력파일명]_[서비스명].txt`. 화자 표기는 엔진마다 다르다.

| 엔진 | 화자 표기 |
|------|----------|
| Deepgram·ElevenLabs·Mistral·Daglo | 화자가 바뀔 때 `[화자 N]` 한 줄, 다음 줄에 그 화자의 발화 |
| Deepgram `--timestamps` | `_deepgram_ts.txt`에 한 줄씩 `[HH:MM:SS] [화자 N] 발화` |
| Muse | `[화자 A]`, 분할되면 `[화자 1-A]`(조각 번호-라벨) |
| Gemini 3.5 Transcribe | `[spk_1] (0:00:01 - 0:00:12) 발화` (화자 분리·타임스탬프를 쓸 때) |
| Gemini | 프롬프트가 `[화자 N]`을 요청할 뿐 모델 출력이라 형식이 보장되지 않는다 |

## 키텀 파일

입력 파일과 같은 폴더의 `keyterms.txt`(한 줄에 한 용어, `#` 주석·빈 줄 무시)를 세 엔진이 자동으로 읽는다. 인명·기관명·전문용어 인식률을 올릴 뿐 표기를 보장하지는 않는다.

| 엔진 | API 필드 | 한도 |
|------|---------|------|
| Deepgram | `keyterm` | 요청당 500토큰(약 100단어) |
| Gemini 3.5 Transcribe | `custom_vocabulary` | 상한 1000개, 권장 100개 이하. `--vocab FILE`로 다른 파일, `--no-keyterms`로 해제 |
| Muse | `keywords` | |

나머지 엔진(Gemini·ElevenLabs·Mistral·Daglo)은 읽지 않는다.

## 선택 가이드

- **한국어 위주, 정확도 최우선** → Daglo > Gemini > ElevenLabs (Gemini 3.5 Transcribe는 한국어 성능 미검증)
- **단어 타임스탬프·도메인 용어가 중요한 30분 이하 녹음** → Gemini 3.5 Transcribe
- **9시간 넘는 녹음** → 길이 제한 없는 Deepgram·Daglo, 또는 상한 9.5시간인 Gemini(`gemini_stt.py`). Transcribe·Muse도 자동 분할하지만 조각 사이 화자 번호가 이어지지 않는다
- **파일 1~2GB** → ElevenLabs (2GB)
- **영어 위주, 빠른 처리** → Deepgram `--lang en`(기본값이 `ko`라 꼭 붙인다)
- **다국어(13개), 저비용** → Mistral ($0.003/분, Muse와 같은 단가)
- **한 녹음에 화자가 여럿(10명 이상)** → Muse (인식 모델 안에서 화자 귀속, 20명 이상 표방)
- **한·영이 한 문장 안에서 섞이는 녹음** → Muse(네이티브 코드 스위칭) 또는 Deepgram `--multi`
- **20MB+ 파일을 Gemini로** → Files API 자동 전환되니 추가 설정 불필요
- **Daglo 사용 전** → ngrok 인증 토큰 등록 필수

## Deepgram 옵션

`--lang <코드>`(기본 `ko`) / `--multi`(language=multi, 한·영 코드 스위칭 녹음용, `--lang`보다 우선) / `--timestamps`(`_deepgram_ts.txt` 추가 저장). 키텀 파일을 자동으로 읽는다.

## Gemini 3.5 Transcribe 옵션

`gemini_stt.py`(범용 Gemini 모델에 프롬프트로 전사 지시)와 달리 전용 ASR 모델 `gemini-3.5-transcribe`를 Interactions API로 호출한다. 둘은 강점이 갈리므로 교체가 아니라 병용한다.

```bash
python STT/gemini_transcribe_stt.py rec.m4a --lang ko-KR          # 화자 분리 기본 사용
python STT/gemini_transcribe_stt.py rec.m4a --mode smart          # 간투사 제거·자동 구조화
python STT/gemini_transcribe_stt.py rec.m4a --word-timestamps     # 단어 단위 시간 오프셋
python STT/gemini_transcribe_stt.py rec.m4a --no-diarize          # 상한 60분 (단어 타임스탬프도 끈 경우)
python STT/gemini_transcribe_stt.py rec.m4a --vocab terms.txt     # 키텀 파일 경로 지정
```

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `--mode verbatim\|smart` | `verbatim` | `smart`는 간투사 제거·자기수정 반영·자동 문단화. **화자 분리·타임스탬프와 병용 불가**(API 제약) |
| `--lang <BCP47>` | 자동 감지 | 반복 지정 가능. 한국어는 `ko-KR`. 아는 경우 지정하면 정확도가 올라간다 |
| `--diarize` / `--no-diarize` | 사용 | 최대 8명. 3명 이상 귀속은 API 문서상 experimental |
| `--word-timestamps` | 해제 | 단어별 시작·종료 오프셋. API 문서상 전사 정확도가 다소 낮아질 수 있음 |
| `--vocab FILE` / `--no-keyterms` | 옆 `keyterms.txt` 자동 | [키텀 파일](#키텀-파일) 참조 |

**키텀 파일**: `custom_vocabulary` 정식 파라미터로 넘긴다. 프롬프트 주입이 아니라 API 바이어싱이라 인명·기관명·전문용어 인식률에 직접 작용한다.

**길이 상한과 자동 분할**: 화자 분리나 단어 타임스탬프를 쓰면 요청당 30분, 둘 다 끄면 60분이다. 초과분은 ffmpeg로 상한 단위 분할(모노 16kHz 64kbps MP3) 후 순차 전사하며, 타임스탬프에는 조각 시작 오프셋을 더해 전체 기준 시각으로 맞춘다. **화자 라벨(`spk_N`)은 조각별로 독립 부여되므로 조각 사이에서 같은 번호가 같은 인물이라는 보장이 없고**, 분할이 일어나면 출력 첫 줄에 그 경고가 붙는다. ffprobe가 없으면 길이를 몰라 분할 없이 한 번에 보내고, ffprobe는 있는데 ffmpeg가 없고 파일이 상한을 넘으면 오류로 중단한다.

**출력 형식**: 화자 분리나 타임스탬프를 쓰면 `[spk_1] (0:00:01 - 0:00:12) 발화...` 형태로 화자 단위 묶음을 저장하고, 그 외에는 본문 텍스트를 그대로 저장한다.

**가격**: 약 $0.005/분(입력 $2.00/1M 토큰). 무료 티어가 있다. 실시간 스트리밍용 `gemini-3.5-transcribe-live`는 이 스크립트가 다루지 않는다(파일 전사 전용).

## Meta Muse Voice Transcribe 옵션

Meta의 Muse Voice Transcribe 1.0을 파일 전사 엔드포인트(`POST https://api.meta.ai/v1/asr/transcribe`)로 호출한다. 스트리밍 ASR·화자 귀속·발화 종료 판정이 후처리 단계가 아니라 인식 모델 안에서 한 번에 일어난다. → [사례](cases.md#meta-muse-voice-transcribe-옵션-referencessttmd)

```bash
python STT/muse_stt.py rec.m4a                    # 화자 분리(DIARIZATION) 기본
python STT/muse_stt.py rec.m4a --lang ko,en       # 언어 힌트 복수 지정(코드 스위칭)
python STT/muse_stt.py rec.m4a --lang none        # 언어 힌트 없이
python STT/muse_stt.py rec.m4a --no-diarize       # ENDPOINTING(발화 경계만)
python STT/muse_stt.py rec.m4a --timestamps       # _muse_ts.txt 추가 저장
```

- **입력 변환 필수**: API가 mono 16-bit PCM WAV(16/24kHz)만 받으므로 스크립트가 항상 ffmpeg로
  24kHz mono PCM WAV로 변환한 뒤 보낸다. ffmpeg가 PATH에 없으면 실행되지 않는다(ffprobe가 없으면
  길이를 모른 채 9분 단위로 나눈다).
- **10분·32MB 상한**: 요청당 오디오 10분, 본문 32MB가 상한이라 9분(540초) 단위로 자동 분할한다.
  24kHz mono 16-bit는 초당 48KB여서 9분 조각이 약 25MB로 두 상한을 모두 밑돈다.
- **화자 라벨은 세션 범위**: 분할되면 조각마다 라벨(A, B, ...)이 새로 시작한다. 스크립트가
  `[화자 1-A]`처럼 조각 번호를 붙이고 출력 머리말에 경고를 남긴다. 조각을 가로지르는 화자 동일성이
  중요하면 10분 이하로 잘라 쓰거나 Deepgram·Gemini를 쓴다.
- **키텀 파일**: `keywords`로 보낸다([키텀 파일](#키텀-파일)).
- **응답**: DIARIZATION 응답의 `speaker`는 알파벳 대문자(`A`), 턴 시작 시각은 `turns[].startMs`에 담긴다.
- **언어 힌트**: `languageBias`는 강제가 아니라 힌트다. 지원 언어는 25종(아랍어·벵골어·네덜란드어·
  영어·프랑스어·독일어·히브리어·힌디어·인도네시아어·이탈리아어·일본어·칸나다어·한국어·말레이어·
  중국어(북경어)·마라티어·폴란드어·포르투갈어·스페인어·타갈로그어·타밀어·텔루구어·태국어·터키어·
  베트남어). 코드(`ko`)로 주면 이름(`Korean`)으로 자동 변환한다.
- **제공하지 않는 것**: 단어 단위 타임스탬프, 신뢰도 점수, 음향 이벤트·감정 인식, 전사문 재구성.
  턴 단위 시각만 돌아온다. 단어 타임스탬프가 필요하면 Gemini 3.5 Transcribe를 쓴다.
- **실시간 스트리밍**(`wss://api.meta.ai/v1/asr/realtime`)은 이 스크립트가 감싸지 않는다.
  마이크 받아쓰기·라이브 자막이 필요하면 해당 WebSocket 엔드포인트를 직접 쓴다.
- **요금·한도**: $0.18/오디오 시간(초 단위 절사 과금). 테넌트당 동시 스트림 8개, 시간당 1,000개.
  실패·429 요청은 과금되지 않는다.

## Daglo ngrok 설정

Daglo는 비동기 콜백 방식이라 로컬 파일을 외부에서 다운로드 가능하게 노출해야 한다. ngrok으로 임시 터널을 열어 처리.

```bash
ngrok config add-authtoken <your-token>
python STT/daglo_stt.py recording.m4a   # 자동으로 ngrok 터널 시작
```

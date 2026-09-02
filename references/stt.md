# STT (음성 → 텍스트)

7개 엔진 모두 화자 구분(diarization) 지원. 파일 크기·길이·정확도·언어로 선택.

| 도구 | 모델 | 화자 구분 | 최대 | 환경변수 | 특이사항 |
|------|------|----------|------|----------|---------|
| `STT/elevenlabs_stt.py` | Scribe v2 | O | 2 GB | `ELEVENLABS_API_KEY` | 가장 큰 파일. 비디오 컨테이너 17종 지원 |
| `STT/gemini_stt.py` | Gemini 3.7 Flash | O(프롬프트) | 9.5 시간 | `GEMINI_API_KEY` | 가장 긴 음성. 20MB+ Files API 자동 사용 |
| `STT/gemini_transcribe_stt.py` | Gemini 3.5 Transcribe | O(최대 8명) | 30분/요청 (화자분리 해제 시 60분) | `GEMINI_API_KEY` | 전용 ASR. WER 2.6%. custom vocabulary·단어 타임스탬프 정식 파라미터. 상한 초과분은 ffmpeg 자동 분할. **public preview** |
| `STT/deepgram_stt.py` | Nova-3 | O | 제한없음 | `DEEPGRAM_API_KEY` | 한국어 기본 설정. 스마트 포맷팅, 단락 구분 |
| `STT/mistral_stt.py` | Voxtral Mini Transcribe v2 | O | 1 GB / 3시간 | `MISTRAL_API_KEY` | 13개 언어. **$0.003/분**. 세그먼트 타임스탬프 |
| `STT/daglo_stt.py` | Daglo (비동기) | O | 제한없음 | `DAGLO_API_KEY` | **ngrok 터널 필요** (로컬 파일 호스팅용) |
| `STT/muse_stt.py` | Muse Voice Transcribe 1.0 | O(20명+) | 10분/요청 (초과분 자동 분할) | `META_API_KEY` | Meta Model API. **$0.003/분**. 스트리밍 WER 3.1%. 언어·키워드 바이어싱, 코드 스위칭. ffmpeg 필수 |

## 입력 포맷

| 도구 | 지원 확장자 |
|------|------------|
| ElevenLabs | MP3, M4A, WAV, FLAC, AAC, OGG, AIFF, WEBM, MP4, AVI, MKV, MOV, WMV, FLV, MPEG, 3GP |
| Gemini | MP3, M4A, WAV, FLAC, AAC, OGG, AIFF |
| Gemini 3.5 Transcribe | MP3, M4A, WAV, FLAC, AAC, OGG, AIFF, MP4, MOV, AVI, WEBM |
| Deepgram | MP3, M4A, WAV, FLAC, AAC, OGG, AIFF, MP4, MOV, AVI, WEBM |
| Muse | MP3, M4A, WAV, FLAC, AAC, OGG, AIFF, MP4, MOV, AVI, WEBM, MKV (모두 ffmpeg로 PCM WAV 변환 후 전송) |
| Mistral | MP3, M4A, WAV, FLAC, OGG |
| Daglo | MP3, M4A, WAV, FLAC, AAC, OGG, MP4, MOV, AVI |

## 사용 예

```bash
python STT/gemini_stt.py meeting.m4a              # 9.5시간까지, Files API 자동
python STT/gemini_transcribe_stt.py meeting.m4a --lang ko-KR   # 전용 ASR, 화자 분리 기본
python STT/elevenlabs_stt.py interview.mp3        # 2GB까지
python STT/deepgram_stt.py podcast.wav            # 한국어 기본, 빠름
python STT/muse_stt.py meeting.m4a --lang ko,en   # 한·영 코드 스위칭, 화자 분리 기본
python STT/mistral_stt.py lecture.flac            # 1GB/3시간, $0.003/분
python STT/daglo_stt.py recording.m4a             # ngrok 사전 설정 필요
```

출력: `[입력파일명]_[서비스명].txt`. 화자 구분: `Speaker 1: ...`, `Speaker 2: ...`.

## 선택 가이드

- **한국어 위주, 정확도 최우선** → Daglo > Gemini > ElevenLabs (Gemini 3.5 Transcribe는 한국어 실측 전)
- **단어 타임스탬프·도메인 용어가 중요한 30분 이하 녹음** → Gemini 3.5 Transcribe
- **9시간 초과** → Gemini(`gemini_stt.py`)만 가능
- **파일 1~2GB** → ElevenLabs (단독 가능)
- **영어 위주, 빠른 처리** → Deepgram (Nova-3, 스마트 포맷팅)
- **다국어(13개), 비용 최우선** → Mistral ($0.003/분)
- **한 녹음에 화자가 여럿(10명 이상)** → Muse (인식 모델 안에서 화자 귀속, 20명 이상 표방)
- **한·영이 한 문장 안에서 섞이는 녹음** → Muse(네이티브 코드 스위칭) 또는 Deepgram `--multi`
- **20MB+ 파일을 Gemini로** → Files API 자동 전환되니 추가 설정 불필요
- **Daglo 사용 전** → ngrok 인증 토큰 등록 필수

## Gemini 3.5 Transcribe 옵션

`gemini_stt.py`(범용 Gemini 모델에 프롬프트로 전사 지시)와 달리 전용 ASR 모델 `gemini-3.5-transcribe`를 Interactions API로 호출한다. 둘은 강점이 갈리므로 교체가 아니라 병용한다.

```bash
python STT/gemini_transcribe_stt.py rec.m4a --lang ko-KR          # 화자 분리 기본 사용
python STT/gemini_transcribe_stt.py rec.m4a --mode smart          # 간투사 제거·자동 구조화
python STT/gemini_transcribe_stt.py rec.m4a --word-timestamps     # 단어 단위 시간 오프셋
python STT/gemini_transcribe_stt.py rec.m4a --no-diarize          # 상한 60분으로 확대
python STT/gemini_transcribe_stt.py rec.m4a --vocab terms.txt     # 커스텀 어휘 파일 지정
```

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `--mode verbatim\|smart` | `verbatim` | `smart`는 간투사 제거·자기수정 반영·자동 문단화. **화자 분리·타임스탬프와 병용 불가**(API 제약) |
| `--lang <BCP47>` | 자동 감지 | 반복 지정 가능. 한국어는 `ko-KR`. 아는 경우 지정하면 정확도가 올라간다 |
| `--diarize` / `--no-diarize` | 사용 | 최대 8명. 3명 이상 귀속은 API 문서상 experimental |
| `--word-timestamps` | 해제 | 단어별 시작·종료 오프셋. API 문서상 전사 정확도가 다소 낮아질 수 있음 |
| `--vocab FILE` / `--no-keyterms` | 옆 `keyterms.txt` 자동 | `custom_vocabulary`로 전달. 상한 1000개, 권장 100개 이하 |

**커스텀 어휘**: 입력 파일과 같은 디렉터리의 `keyterms.txt`를 자동으로 읽어 `custom_vocabulary` 정식 파라미터로 넘긴다(형식은 Deepgram 키텀과 동일: 한 줄에 한 용어, `#` 주석·빈 줄 무시). 프롬프트 주입이 아니라 API 바이어싱이라 인명·기관명·전문용어 인식률에 직접 작용한다.

**길이 상한과 자동 분할**: 화자 분리나 단어 타임스탬프를 쓰면 요청당 30분, 둘 다 끄면 60분이다. 초과분은 ffmpeg로 상한 단위 분할(모노 16kHz 64kbps MP3) 후 순차 전사하며, 타임스탬프에는 조각 시작 오프셋을 더해 전체 기준 시각으로 맞춘다. **화자 라벨(`spk_N`)은 조각별로 독립 부여되므로 조각 사이에서 같은 번호가 같은 인물이라는 보장이 없고**, 분할이 일어나면 출력 첫 줄에 그 경고가 붙는다. ffmpeg가 없고 파일이 상한을 넘으면 오류로 중단한다.

**출력 형식**: 화자 분리나 타임스탬프를 쓰면 `[spk_1] (0:00:01 - 0:00:12) 발화...` 형태로 화자 단위 묶음을 저장하고, 그 외에는 본문 텍스트를 그대로 저장한다.

**가격**: 약 $0.005/분(입력 $2.00/1M 토큰). 무료 티어가 있다. 실시간 스트리밍용 `gemini-3.5-transcribe-live`는 이 스크립트가 다루지 않는다(파일 전사 전용).

## Meta Muse Voice Transcribe 옵션

Meta Superintelligence Labs가 2026-09-01 공개한 실시간 오디오 인식 모델을 파일 전사 엔드포인트
(`POST https://api.meta.ai/v1/asr/transcribe`)로 호출한다. 스트리밍 ASR·화자 귀속·발화 종료 판정이
후처리 단계가 아니라 인식 모델 안에서 한 번에 일어난다.

```bash
python STT/muse_stt.py rec.m4a                    # 화자 분리(DIARIZATION) 기본
python STT/muse_stt.py rec.m4a --lang ko,en       # 언어 힌트 복수 지정(코드 스위칭)
python STT/muse_stt.py rec.m4a --lang none        # 언어 힌트 없이
python STT/muse_stt.py rec.m4a --no-diarize       # ENDPOINTING(발화 경계만)
python STT/muse_stt.py rec.m4a --timestamps       # _muse_ts.txt 추가 저장
```

- **입력 변환 필수**: API가 mono 16-bit PCM WAV(16/24kHz)만 받으므로 스크립트가 항상 ffmpeg로
  24kHz mono PCM WAV로 변환한 뒤 보낸다. ffmpeg/ffprobe가 PATH에 없으면 실행되지 않는다.
- **10분·32MB 상한**: 요청당 오디오 10분, 본문 32MB가 상한이라 9분(540초) 단위로 자동 분할한다.
  24kHz mono 16-bit는 초당 48KB여서 9분 조각이 약 25MB로 두 상한을 모두 밑돈다.
- **화자 라벨은 세션 범위**: 분할되면 조각마다 라벨(A, B, ...)이 새로 시작한다. 스크립트가
  `[화자 1-A]`처럼 조각 번호를 붙이고 출력 머리말에 경고를 남긴다. 조각을 가로지르는 화자 동일성이
  중요하면 10분 이하로 잘라 쓰거나 Deepgram·Gemini를 쓴다.
- **키워드**: 입력 파일과 같은 디렉토리의 `keyterms.txt`를 자동 로드해 `keywords`로 보낸다
  (Deepgram과 같은 규약). 인식률을 올릴 뿐 표기를 보장하지는 않는다.
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
- **실측(2026-09-03)**: 한국어 11초 음원 1건으로 실호출 확인. 전사 정확도 100%(고유명사 포함),
  DIARIZATION 응답의 `speaker`는 알파벳 대문자(`A`)로 오고, 턴 시작 시각은 `turns[].startMs`에 담긴다.
  Model API 계정을 만들면 `Playground`라는 기본 키가 하나 자동 생성돼 있다.

## Daglo ngrok 설정

Daglo는 비동기 콜백 방식이라 로컬 파일을 외부에서 다운로드 가능하게 노출해야 한다. ngrok으로 임시 터널을 열어 처리.

```bash
ngrok config add-authtoken <your-token>
python STT/daglo_stt.py recording.m4a   # 자동으로 ngrok 터널 시작
```

## 실시간 스트리밍은 이 저장소의 범위가 아니다

여기 있는 STT 스크립트는 모두 **파일 전사(배치)** 전용이다. 마이크 받아쓰기·라이브 자막처럼
오디오를 흘려보내며 결과를 받는 실시간 스트리밍은 다루지 않으며, 앞으로도 넣지 않는다.
입출력 계약이 다르기 때문이다: 입력 파일이 없고, 끝나는 시점이 없고, 중간 가설(partial)과
확정(final)이 따로 흐르며, 마이크 캡처를 위해 PortAudio 같은 네이티브 의존성이 필요하다.
이 저장소의 공통 규약(폴더 자동 탐색, `<입력>_<service>.<확장자>` 출력)이 하나도 성립하지 않는다.

실시간이 필요하면 각 프로바이더의 스트리밍 엔드포인트를 직접 쓴다. 2026-09 기준 실태:

| 프로바이더 | 실시간 엔드포인트 | 실시간 화자 분리 | 세션 상한 |
|---|---|---|---|
| Meta Muse | `wss://api.meta.ai/v1/asr/realtime` | DIARIZATION 모드 | 60분 |
| Deepgram | `wss://api.deepgram.com/v1/listen` | `diarize=true` | 사실상 없음 |
| Gemini 3.5 Transcribe Live | Live API (`gemini-3.5-transcribe-live`) | **미지원** | **10분** |
| ElevenLabs Scribe v2 Realtime | WebSocket (`scribe_v2_realtime`) | **미지원** | 문서 미기재 |

한국어 실측에서 얻은 주의점 두 가지:

- **위 상용 API들의 실시간 화자 분리는 화자 수를 계통적으로 과소 계수한다.** 같은 오디오·같은
  모델에서 스트리밍이 배치보다 적은 화자를 찾는다(한국어 실측). 배치 전제로 만든 화자 분리를
  스트리밍에 얹은 구현으로 보이므로, 이들의 화자 라벨을 신뢰하는 설계를 세우지 말 것.
  다만 **온라인 화자 분리 자체가 불가능한 것은 아니다.** 증분 클러스터링·화자 캐시로 처음부터
  온라인으로 설계된 알고리즘(diart, NVIDIA Streaming Sortformer 등)은 별개이며, 화자 분리가
  꼭 필요하면 배치를 쓰거나 그런 전용 엔진을 따로 붙인다.
- **Muse 실시간은 인증을 핸드셰이크 첫 JSON 프레임으로 받는다.** `Authorization` 헤더는
  무시된다. 오디오는 컨테이너 없는 raw PCM 바이너리 프레임을 실시간 속도로 보내며
  5초 이상 앞질러 보내면 안 된다. `speaker` 이벤트는 그 **앞의** 오디오에 라벨을 붙인다.

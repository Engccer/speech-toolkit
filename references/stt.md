# STT (음성 → 텍스트)

6개 엔진 모두 화자 구분(diarization) 지원. 파일 크기·길이·정확도·언어로 선택.

| 도구 | 모델 | 화자 구분 | 최대 | 환경변수 | 특이사항 |
|------|------|----------|------|----------|---------|
| `STT/elevenlabs_stt.py` | Scribe v2 | O | 2 GB | `ELEVENLABS_API_KEY` | 가장 큰 파일. 비디오 컨테이너 17종 지원 |
| `STT/gemini_stt.py` | Gemini 3.7 Flash | O(프롬프트) | 9.5 시간 | `GEMINI_API_KEY` | 가장 긴 음성. 20MB+ Files API 자동 사용 |
| `STT/gemini_transcribe_stt.py` | Gemini 3.5 Transcribe | O(최대 8명) | 30분/요청 (화자분리 해제 시 60분) | `GEMINI_API_KEY` | 전용 ASR. WER 2.6%. custom vocabulary·단어 타임스탬프 정식 파라미터. 상한 초과분은 ffmpeg 자동 분할. **public preview** |
| `STT/deepgram_stt.py` | Nova-3 | O | 제한없음 | `DEEPGRAM_API_KEY` | 한국어 기본 설정. 스마트 포맷팅, 단락 구분 |
| `STT/mistral_stt.py` | Voxtral Mini Transcribe v2 | O | 1 GB / 3시간 | `MISTRAL_API_KEY` | 13개 언어. **$0.003/분**. 세그먼트 타임스탬프 |
| `STT/daglo_stt.py` | Daglo (비동기) | O | 제한없음 | `DAGLO_API_KEY` | **ngrok 터널 필요** (로컬 파일 호스팅용) |

## 입력 포맷

| 도구 | 지원 확장자 |
|------|------------|
| ElevenLabs | MP3, M4A, WAV, FLAC, AAC, OGG, AIFF, WEBM, MP4, AVI, MKV, MOV, WMV, FLV, MPEG, 3GP |
| Gemini | MP3, M4A, WAV, FLAC, AAC, OGG, AIFF |
| Gemini 3.5 Transcribe | MP3, M4A, WAV, FLAC, AAC, OGG, AIFF, MP4, MOV, AVI, WEBM |
| Deepgram | MP3, M4A, WAV, FLAC, AAC, OGG, AIFF, MP4, MOV, AVI, WEBM |
| Mistral | MP3, M4A, WAV, FLAC, OGG |
| Daglo | MP3, M4A, WAV, FLAC, AAC, OGG, MP4, MOV, AVI |

## 사용 예

```bash
python STT/gemini_stt.py meeting.m4a              # 9.5시간까지, Files API 자동
python STT/gemini_transcribe_stt.py meeting.m4a --lang ko-KR   # 전용 ASR, 화자 분리 기본
python STT/elevenlabs_stt.py interview.mp3        # 2GB까지
python STT/deepgram_stt.py podcast.wav            # 한국어 기본, 빠름
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

## Daglo ngrok 설정

Daglo는 비동기 콜백 방식이라 로컬 파일을 외부에서 다운로드 가능하게 노출해야 한다. ngrok으로 임시 터널을 열어 처리.

```bash
ngrok config add-authtoken <your-token>
python STT/daglo_stt.py recording.m4a   # 자동으로 ngrok 터널 시작
```

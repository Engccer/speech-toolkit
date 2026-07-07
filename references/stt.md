# STT (음성 → 텍스트)

5개 엔진 모두 화자 구분(diarization) 지원. 파일 크기·길이·정확도·언어로 선택.

| 도구 | 모델 | 화자 구분 | 최대 | 환경변수 | 특이사항 |
|------|------|----------|------|----------|---------|
| `STT/elevenlabs_stt.py` | Scribe v2 | O | 2 GB | `ELEVENLABS_API_KEY` | 가장 큰 파일. 비디오 컨테이너 17종 지원 |
| `STT/gemini_stt.py` | Gemini | O | 9.5 시간 | `GEMINI_API_KEY` | 가장 긴 음성. 타임스탬프 포함. 20MB+ Files API 자동 사용 |
| `STT/deepgram_stt.py` | Nova-3 | O | 제한없음 | `DEEPGRAM_API_KEY` | 한국어 기본 설정. 스마트 포맷팅, 단락 구분 |
| `STT/mistral_stt.py` | Voxtral Mini Transcribe v2 | O | 1 GB / 3시간 | `MISTRAL_API_KEY` | 13개 언어. **$0.003/분**. 세그먼트 타임스탬프 |
| `STT/daglo_stt.py` | Daglo (비동기) | O | 제한없음 | `DAGLO_API_KEY` | **ngrok 터널 필요** (로컬 파일 호스팅용) |

## 입력 포맷

| 도구 | 지원 확장자 |
|------|------------|
| ElevenLabs | MP3, M4A, WAV, FLAC, AAC, OGG, AIFF, WEBM, MP4, AVI, MKV, MOV, WMV, FLV, MPEG, 3GP |
| Gemini | MP3, M4A, WAV, FLAC, AAC, OGG, AIFF |
| Deepgram | MP3, M4A, WAV, FLAC, AAC, OGG, AIFF, MP4, MOV, AVI, WEBM |
| Mistral | MP3, M4A, WAV, FLAC, OGG |
| Daglo | MP3, M4A, WAV, FLAC, AAC, OGG, MP4, MOV, AVI |

## 사용 예

```bash
python STT/gemini_stt.py meeting.m4a              # 9.5시간까지, Files API 자동
python STT/elevenlabs_stt.py interview.mp3        # 2GB까지
python STT/deepgram_stt.py podcast.wav            # 한국어 기본, 빠름
python STT/mistral_stt.py lecture.flac            # 1GB/3시간, $0.003/분
python STT/daglo_stt.py recording.m4a             # ngrok 사전 설정 필요
```

출력: `[입력파일명]_[서비스명].txt`. 화자 구분: `Speaker 1: ...`, `Speaker 2: ...`.

## 선택 가이드

- **한국어 위주, 정확도 최우선** → Daglo > Gemini > ElevenLabs
- **9시간 초과** → Gemini만 가능
- **파일 1~2GB** → ElevenLabs (단독 가능)
- **영어 위주, 빠른 처리** → Deepgram (Nova-3, 스마트 포맷팅)
- **다국어(13개), 비용 최우선** → Mistral ($0.003/분)
- **20MB+ 파일을 Gemini로** → Files API 자동 전환되니 추가 설정 불필요
- **Daglo 사용 전** → ngrok 인증 토큰 등록 필수

## Daglo ngrok 설정

Daglo는 비동기 콜백 방식이라 로컬 파일을 외부에서 다운로드 가능하게 노출해야 한다. ngrok으로 임시 터널을 열어 처리.

```bash
ngrok config add-authtoken <your-token>
python STT/daglo_stt.py recording.m4a   # 자동으로 ngrok 터널 시작
```

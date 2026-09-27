---
name: speech-toolkit
description: "텍스트→음성(TTS)과 음성→텍스트(STT) 변환 CLI 스크립트 모음. TTS는 Gemini/ElevenLabs/OpenAI/Speechify 4종, STT는 Daglo/Deepgram/ElevenLabs/Gemini/Gemini 3.5 Transcribe/Meta Muse/Mistral 7종. 다음 요청에 사용: 텍스트를 음성으로 변환, 나레이션·오디오북 음원 생성, 음성·영상 파일 전사, 회의 녹음 텍스트 변환, TTS, STT, transcription. Use for text-to-speech (TTS) and speech-to-text (STT): generate narration audio from text or transcribe audio/video files to text with multiple AI providers."
license: MIT
metadata:
  version: "1.3.0"
---

# speech-toolkit

텍스트↔음성 변환 CLI 스크립트 모음. 각 스크립트는 독립 실행형이며 공통 규약을 따른다:

- 입력 파일을 명시한다. 인자 없이 실행하면 현재 폴더에서 처음 찾은 지원 파일 **하나**만 처리한다(TTS는 `.txt`를 찾으므로 `keyterms.txt`나 이전 전사 결과가 걸릴 수 있다).
- 출력 파일명은 `<입력>_<service>.<ext>` 형식이다(예: `meeting_deepgram.txt`, `report_gemini_tts.wav`).
- API 키는 환경변수로만 받는다(하드코딩 금지).
- 성공은 출력 파일이 새로 생겼거나 갱신됐는지로 판정한다. 여러 스크립트가 키 부재·API 오류에도 종료 코드 0으로 끝난다.
- 의존성은 `pip install -r requirements.txt`. `muse_stt.py`는 ffmpeg가 늘, `gemini_transcribe_stt.py`는 상한을 넘는 파일을 나눌 때 ffmpeg/ffprobe가 필요하다.

## 라우팅

| 작업 | 스크립트 | 필요 환경변수 |
|---|---|---|
| TTS(표현력·다화자 2명·보컬 태그) | `TTS/gemini_tts.py` | `GEMINI_API_KEY` |
| TTS(감정·억양 자연어 지시) | `TTS/openai_tts.py` | `OPENAI_API_KEY` |
| TTS(한국어 음성 프리셋·다화자 대본) | `TTS/elevenlabs_tts.py` | `ELEVENLABS_API_KEY` |
| TTS(SSML 세밀 제어: 속도·피치·감정) | `TTS/speechify_tts.py` | `SPEECHIFY_API_KEY` |
| STT(빠름·길이 제한 없음, 기본 한국어) | `STT/deepgram_stt.py` | `DEEPGRAM_API_KEY` |
| STT(장시간·자연스러운 한국어) | `STT/gemini_stt.py` | `GEMINI_API_KEY` |
| STT(단어 타임스탬프·도메인 용어·30분 이하) | `STT/gemini_transcribe_stt.py` | `GEMINI_API_KEY` |
| STT(한국어 정확도 우선) | `STT/daglo_stt.py` | `DAGLO_API_KEY` (+ngrok) |
| STT(1~2GB 대용량·영상 컨테이너) | `STT/elevenlabs_stt.py` | `ELEVENLABS_API_KEY` |
| STT(화자 10명 이상·한영 혼용) | `STT/muse_stt.py` | `META_API_KEY` |
| STT(저비용·13개 언어) | `STT/mistral_stt.py` | `MISTRAL_API_KEY` |

상세 옵션은 `references/tts.md`·`references/stt.md` 참조(필요할 때만 로드).

STT 스크립트는 모두 **파일 전사 전용**이다. 마이크 받아쓰기·라이브 자막 같은 실시간 스트리밍은 이 저장소의 범위가 아니며, 그런 요청일 때만 `references/realtime.md`를 읽는다.

ElevenLabs는 공식 CLI도 있다. 강제 정렬(자막·타임스탬프), 발음 사전, 더빙처럼 **위 스크립트가 감싸지 않은 기능**이 필요하면 `references/elevenlabs-cli.md`를 참조한다.

## 사용 예

스크립트 경로는 이 스킬 폴더 기준이다.

```bash
python TTS/gemini_tts.py report.md --voice Kore
python STT/deepgram_stt.py meeting.m4a --lang ko
python STT/gemini_transcribe_stt.py meeting.m4a --lang ko-KR
python STT/muse_stt.py meeting.m4a --lang ko,en --timestamps
```

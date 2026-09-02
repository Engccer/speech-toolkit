---
name: speech-toolkit
description: "텍스트→음성(TTS)과 음성→텍스트(STT) 변환 CLI 스크립트 모음. TTS는 Gemini/ElevenLabs/OpenAI/Speechify 4종, STT는 Daglo/Deepgram/ElevenLabs/Gemini/Gemini 3.5 Transcribe/Meta Muse/Mistral 7종. 다음 요청에 사용: 텍스트를 음성으로 변환, 나레이션·오디오북 음원 생성, 음성·영상 파일 전사, 회의 녹음 텍스트 변환, TTS, STT, transcription. Use for text-to-speech (TTS) and speech-to-text (STT): generate narration audio from text or transcribe audio/video files to text with multiple AI providers."
license: MIT
metadata:
  version: "1.2.0"
---

# speech-toolkit

텍스트↔음성 변환 CLI 스크립트 모음. 각 스크립트는 독립 실행형이며 공통 규약을 따른다:

- 인자 없이 실행하면 현재 폴더에서 지원 확장자를 자동 탐색한다.
- 출력 파일명은 `<입력>_<service>.<ext>` 형식이다(예: `meeting_deepgram.txt`, `report_gemini_tts.wav`).
- API 키는 환경변수로만 받는다(하드코딩 금지).

## 라우팅

| 작업 | 스크립트 | 필요 환경변수 |
|---|---|---|
| TTS(HD 음성, 다화자) | `TTS/gemini_tts.py` | `GEMINI_API_KEY` |
| TTS(감정·억양 지시) | `TTS/openai_tts.py` | `OPENAI_API_KEY` |
| TTS(다국어·음성 라이브러리) | `TTS/elevenlabs_tts.py` | `ELEVENLABS_API_KEY` |
| TTS(Speechify) | `TTS/speechify_tts.py` | `SPEECHIFY_API_KEY` |
| STT(빠름·화자 분리) | `STT/deepgram_stt.py` | `DEEPGRAM_API_KEY` |
| STT(장시간·자연스러운 한국어) | `STT/gemini_stt.py` | `GEMINI_API_KEY` |
| STT(정확도 최우선·전용 ASR) | `STT/gemini_transcribe_stt.py` | `GEMINI_API_KEY` |
| STT(한국어 특화) | `STT/daglo_stt.py` | `DAGLO_API_KEY` (+ngrok) |
| STT(ElevenLabs) | `STT/elevenlabs_stt.py` | `ELEVENLABS_API_KEY` |
| STT(실시간급 지연·다화자 20명+) | `STT/muse_stt.py` | `META_API_KEY` |
| STT(Voxtral) | `STT/mistral_stt.py` | `MISTRAL_API_KEY` |

상세 옵션은 `references/tts.md`·`references/stt.md` 참조(필요할 때만 로드).

STT 스크립트는 모두 **파일 전사 전용**이다. 마이크 받아쓰기·라이브 자막 같은 실시간
스트리밍은 이 저장소의 범위가 아니다(입출력 계약이 다름). 프로바이더별 실시간 지원 실태와
함정은 `references/stt.md`의 「실시간 스트리밍은 이 저장소의 범위가 아니다」 절에 정리돼 있다.

ElevenLabs는 공식 CLI도 있다. 강제 정렬(자막·타임스탬프), 발음 사전, 더빙, 다화자 대본처럼 **위 스크립트가 감싸지 않은 기능**이 필요하면 `references/elevenlabs-cli.md`를 참조한다.

## 사용 예

```bash
python TTS/gemini_tts.py report.md --voice Kore
python STT/deepgram_stt.py meeting.m4a --lang ko
python STT/gemini_transcribe_stt.py meeting.m4a --lang ko-KR
python STT/muse_stt.py meeting.m4a --lang ko,en --timestamps
```

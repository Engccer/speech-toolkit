---
name: speech-toolkit
description: 텍스트→음성(TTS)과 음성→텍스트(STT) 변환 CLI 스크립트 모음. TTS는 Gemini/ElevenLabs/OpenAI/Speechify 4종, STT는 Daglo/Deepgram/ElevenLabs/Gemini/Mistral 5종. 다음 요청에 사용: 텍스트를 음성으로 변환, 나레이션·오디오북 음원 생성, 음성·영상 파일 전사, 회의 녹음 텍스트 변환, TTS, STT, transcription. Use for text-to-speech (TTS) and speech-to-text (STT): generate narration audio from text or transcribe audio/video files to text with multiple AI providers.
license: MIT
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
| STT(자연스러운 한국어·화자 구분) | `STT/gemini_stt.py` | `GEMINI_API_KEY` |
| STT(한국어 특화) | `STT/daglo_stt.py` | `DAGLO_API_KEY` (+ngrok) |
| STT(ElevenLabs) | `STT/elevenlabs_stt.py` | `ELEVENLABS_API_KEY` |
| STT(Voxtral) | `STT/mistral_stt.py` | `MISTRAL_API_KEY` |

상세 옵션은 `references/tts.md`·`references/stt.md` 참조(필요할 때만 로드).

## 사용 예

```bash
python TTS/gemini_tts.py report.md --voice Kore
python STT/deepgram_stt.py meeting.m4a --lang ko
```

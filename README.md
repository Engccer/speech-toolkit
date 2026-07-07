# speech-toolkit

AI API 기반 텍스트↔음성 변환 CLI 스크립트 모음(TTS 4종 + STT 5종). 코딩 에이전트(Claude Code, Codex 등)의 스킬로도, 단독 CLI로도 쓸 수 있다.

CLI scripts for text-to-speech (4 providers) and speech-to-text (5 providers). Works standalone or as an agent skill.

## 설치

```bash
npx skills add Engccer/speech-toolkit -g   # 에이전트 스킬로 설치
# 또는
git clone https://github.com/Engccer/speech-toolkit
pip install -r requirements.txt
```

Python 3.12 기준. `STT/daglo_stt.py`만 ngrok 계정(pyngrok)이 추가로 필요하다.

## 스크립트와 필요 API 키

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

모든 키는 환경변수로만 읽는다. 스크립트에 키를 하드코딩하지 말 것.

## 공통 규약

- 인자 없이 실행하면 현재 폴더에서 입력 파일을 자동 탐색한다.
- 출력: `<입력파일명>_<service>.<확장자>`
- 각 스크립트의 전체 옵션: `python <script> --help` 또는 `references/` 문서.

## 관련 프로젝트

시각장애 사용자를 위한 에이전트 스킬 번들 [skills-for-the-blind](https://github.com/Engccer/skills-for-the-blind)의 멤버 스킬이다.

## License

MIT

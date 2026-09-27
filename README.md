# speech-toolkit

AI API 기반 텍스트↔음성 변환 CLI 스크립트 모음(TTS 4종 + STT 7종). 코딩 에이전트(Claude Code, Codex 등)의 스킬로도, 단독 CLI로도 쓸 수 있다.

CLI scripts for text-to-speech (4 providers) and speech-to-text (7 providers). Works standalone or as an agent skill.

## 설치

```bash
npx skills add Engccer/speech-toolkit -g   # 에이전트 스킬로 설치
# 또는
git clone https://github.com/Engccer/speech-toolkit
pip install -r requirements.txt
```

Python 3.12 기준. `STT/daglo_stt.py`만 ngrok 계정(pyngrok)이 추가로 필요하고, `STT/gemini_transcribe_stt.py`는 길이 상한 초과 파일을 자동 분할할 때 ffmpeg/ffprobe를 쓴다. `STT/muse_stt.py`는 API가 PCM WAV만 받으므로 ffmpeg가 항상 필요하다.

## 사용법

스크립트별 용도·필요한 환경변수·공통 규약은 [SKILL.md](SKILL.md), 스크립트별 옵션은 [references/](references/) 문서나 `python <script> --help`로 본다. API 키는 환경변수로만 읽는다.

## 관련 프로젝트

시각장애 사용자를 위한 에이전트 스킬 번들 [skills-for-the-blind](https://github.com/Engccer/skills-for-the-blind)의 멤버 스킬이다.

## License

MIT

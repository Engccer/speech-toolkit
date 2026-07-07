# speech-toolkit

텍스트↔음성 변환 CLI 스크립트 모음이다. TTS 4종(Gemini, ElevenLabs, OpenAI, Speechify)과 STT 5종(Daglo, Deepgram, ElevenLabs, Gemini, Mistral)을 각각 독립 실행형 스크립트로 제공하며, 코딩 에이전트 스킬로도 단독 CLI로도 쓸 수 있다.

이 저장소는 공개 저장소이므로 개인 경로·실키·개인 스킬 결합을 커밋하지 않는다. PR·이슈·커밋 어디에도 로컬 절대경로(`C:\Users\...`, `/Users/...`), 실제 API 키, 다른 저장소의 비공개 스킬 이름을 남기지 말 것.

## 스크립트 추가 시 공통 규약

새 TTS·STT 스크립트를 추가할 때는 기존 9개 스크립트의 규약을 그대로 따른다:

- 인자 없이 실행 시 현재 폴더에서 지원 확장자를 자동 탐색한다.
- 출력 파일명은 `<입력파일명>_<service>.<확장자>` 형식이다.
- API 키는 반드시 환경변수로만 읽는다(`os.environ.get("...")`). 하드코딩 금지.
- 키가 없으면 한국어 오류 메시지를 출력하고 비정상 종료한다.
- `--help`(또는 `--list-voices`류 옵션)는 API 키 없이도 동작해야 한다.

문서 갱신: 스크립트 옵션이 바뀌면 `SKILL.md`의 라우팅 표와 `references/tts.md`·`references/stt.md`의 상세 옵션을 함께 갱신한다.

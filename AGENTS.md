> 🤖 **이 파일은 자동 생성됩니다. 직접 수정하지 마세요.**
> 정본은 `CLAUDE.md` 입니다. 내용을 바꾸려면 `CLAUDE.md` 를 수정한 뒤
> 프로젝트 루트에서 `python sync_agent_docs.py` 를 실행하세요.
> 이 파일을 직접 고치면 다음 동기화 때 경고와 함께 덮어쓰기 대상이 됩니다.

<!-- SYNC-BODY-START: 이 줄 아래 본문은 CLAUDE.md 와 100% 동일하게 자동 생성됨 -->
# speech-toolkit

텍스트↔음성 변환 CLI 스크립트 모음이다. TTS 4종(Gemini, ElevenLabs, OpenAI, Speechify)과 STT 5종(Daglo, Deepgram, ElevenLabs, Gemini, Mistral)을 각각 독립 실행형 스크립트로 제공하며, 코딩 에이전트 스킬로도 단독 CLI로도 쓸 수 있다.

이 저장소는 공개 저장소이므로 개인 경로·실키·개인 스킬 결합을 커밋하지 않는다. PR·이슈·커밋 어디에도 로컬 절대경로(`C:\Users\...`, `/Users/...`), 실제 API 키, 다른 저장소의 비공개 스킬 이름을 남기지 말 것.

## 스크립트 추가 시 공통 규약

새 TTS·STT 스크립트를 추가할 때는 기존 9개 스크립트의 규약을 그대로 따른다:

- 인자 없이 실행 시 현재 폴더에서 지원 확장자를 자동 탐색한다.
- 출력 파일명은 `<입력파일명>_<service>.<확장자>` 형식이다.
- API 키는 반드시 환경변수로만 읽는다(`os.environ.get("...")`). 하드코딩 금지.
- 키가 없으면 한국어 오류 메시지를 출력한다. 종료 방식은 스크립트마다 다르다: elevenlabs_tts·elevenlabs_stt·daglo_stt·speechify_tts는 `sys.exit(1)`로 비정상 종료하고, 나머지 5개는 메시지 출력 후 조용히 반환한다(exit code 0).
- `--help`(또는 `--list-voices`류 옵션)는 API 키 없이도 동작해야 한다.

문서 갱신: 스크립트 옵션이 바뀌면 `SKILL.md`의 라우팅 표와 `references/tts.md`·`references/stt.md`의 상세 옵션을 함께 갱신한다.

사본 동기화: 일부 TTS 스크립트는 자매 스킬 저장소에 자체 완결성 확보 목적으로 동봉돼 있다(각 사본 상단에 출처 주석 있음). 아래 원본을 수정하면 해당 사본도 같은 내용으로 갱신해 함께 커밋·푸시한다.

- `TTS/elevenlabs_tts.py` → abridge( https://github.com/Engccer/abridge )의 `scripts/elevenlabs_tts.py`, agent-cli-tts-summary( https://github.com/Engccer/agent-cli-tts-summary )의 `assets/tts/elevenlabs_tts.py`
- `TTS/gemini_tts.py` → agent-cli-tts-summary의 `assets/tts/gemini_tts.py`

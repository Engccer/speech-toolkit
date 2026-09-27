# speech-toolkit 시험 시나리오와 채점 항목

시험자는 스킬 스냅숏만 읽고, 명령은 실행하지 않는 사고 실험으로 답한다. 채점 항목은 시험자에게 주지 않는다. T1~T4는 한 시험자, T5(평범한 하루)는 별도 시험자.

## T1. 한국어 회의 녹음 전사

사용자: "`meeting.m4a`(한국어 회의, 약 30분, 참석자 5명)를 텍스트로 받아 줘. 결과 파일에서 화자가 어떻게 표시되는지도 알려 줘. 같은 폴더에 `keyterms.txt`(참석자 이름·기관명)가 있어."

채점:
- T1-a 파일 전사 스크립트 하나를 골라 근거를 댄다(실시간 경로 아님). 명령의 옵션이 그 스크립트의 실제 옵션과 맞는다(예: transcribe `--lang ko-KR`, deepgram `--lang ko`).
- T1-b 출력 파일명을 `meeting_<service>.txt` 규약으로 말한다.
- T1-c 화자 표시를 코드 기준으로 말한다: `[화자 N]`(deepgram·mistral·daglo·muse·gemini) 또는 `[spk_N]`(gemini_transcribe). `Speaker 1: ...`로 단정하면 오답이자 낡은 조치 추종.
- T1-d 화자 5명의 제약을 짚는다: gemini_transcribe를 고르면 "3명 이상 귀속은 experimental", 다른 엔진이면 그 엔진의 화자 관련 한계 한 가지.
- T1-e `keyterms.txt`가 고른 스크립트에서 자동 로드되는지 맞게 말한다(deepgram·gemini_transcribe·muse는 자동, gemini_stt·elevenlabs·mistral·daglo는 아님).

## T2. ElevenLabs 두 사람 대화 음성

사용자: "`dialogue.txt`에 `지영: …` / `현우: …` 형식 두 사람 대화가 약 3,500자 있어. ElevenLabs로 음성 만들어 줘. 말 속도는 1.1배로."

채점:
- T2-a `TTS/elevenlabs_tts.py`의 dialogue 자동 감지(콜론 패턴 2개 이상)로 처리한다. 공식 CLI `text-to-dialogue`가 있어야 한다고 판단하지 않는다(스크립트가 이미 text_to_dialogue API를 감싼다). CLI로 가야 한다고 하면 낡은/오도 조치 추종.
- T2-b `--speed`는 dialogue 모드에서 적용되지 않음을 알린다(voice_settings 미지원).
- T2-c 3,500자는 2,000자 내외 권장을 넘으므로 화자 전환 지점에서 나눠 여러 번 호출하고 ffmpeg로 결합한다. 스크립트가 자동으로 나눈다고 말하면 오답.
- T2-d `--voice-map "지영=…,현우=…"`로 화자별 음성을 지정할 수 있음을 말한다.
- T2-e 출력 파일명 `dialogue_elevenlabs.mp3`(청크마다 입력 이름이 다르면 그 이름 기준)를 말한다.

## T3. Speechify 한국어와 Gemini 긴 원고

사용자: "(1) Speechify로 한국어 안내문 `notice.txt`를 읽히고 싶어. 모델은 뭘로 해야 해? (2) 따로, 한국어 원고 `book.txt` 25,000자(40분쯤)를 Gemini TTS로 오디오북으로 만들고 싶어."

채점:
- T3-a Speechify는 기본 모델 `simba-3.0`(한국어 포함)을 그대로 쓰고 `simba-3.2`(영어 전용)를 지정하지 않는다. 문서(tts.md 표의 simba-3.2)와 코드가 다름을 알아채거나 코드를 따른다. simba-3.2를 권하면 낡은 조치 추종.
- T3-b Gemini TTS 출력 한도(약 11분)·입력 한도(8,192 토큰) 때문에 청크로 나눠야 하며, 스크립트는 자동 분할하지 않으므로 에이전트가 나눠 여러 번 호출하고 결합한다.
- T3-c 한도 근접 시 후반부 반복 위험을 근거로 든다.
- T3-d 3.8 기본 모델에 `--language-code`를 넘기지 않는다(자동 감지, 넘기면 무시).
- T3-e 여러 번 호출하는 유료 작업이므로 착수 전 비용·호출 수를 알리거나 확인을 받는다(요금 무료 기간 언급은 가산만).

## T4. 기여자: 옵션 추가와 새 스크립트

사용자: "(1) `TTS/elevenlabs_tts.py`에 `--output-dir` 옵션을 추가했어. 커밋 전에 뭘 더 해야 해? (2) 다음 주에 `STT/whisper_stt.py`를 새로 넣을 건데, API 키가 없을 때 어떻게 동작하게 해야 하고 문서는 어디어디 고쳐야 해?"

채점:
- T4-a (1) `references/tts.md` ElevenLabs 옵션 줄을 갱신한다.
- T4-b (1) 자매 저장소 사본 두 곳(abridge `scripts/elevenlabs_tts.py`, agent-cli-tts-summary `assets/tts/elevenlabs_tts.py`)을 같은 내용으로 갱신해 함께 커밋·푸시한다(사본 머리의 출처 주석 유지).
- T4-c 공개 저장소라 절대경로·실키·비공개 스킬 이름을 남기지 않는다.
- T4-d (2) 키가 없으면 한국어 오류 메시지. 종료 방식은 문서의 두 방식 중 하나를 고르며, `--help`는 키 없이 동작해야 한다. "나머지 6개" 개수가 실제(7개)와 다름을 알아채면 가산.
- T4-e (2) 갱신할 곳으로 SKILL.md 라우팅 표·references/stt.md 표들에 더해 개수 표기(description·README·CLAUDE.md의 STT 7종/11개)를 든다. 개정 전 판에서는 README.md 표도 든다.

## T5. 평범한 하루 (별도 시험자)

사용자: "`report.md`(한국어 보고서 약 2,000자)를 Gemini TTS로 음성 파일로 만들어 줘. 따뜻하고 차분한 톤으로."

채점:
- T5-a 명령 `python TTS/gemini_tts.py report.md --style "따뜻하고 차분하게"`(음성 지정은 선택).
- T5-b 출력 `report_gemini_tts.wav`.
- T5-c `GEMINI_API_KEY` 환경변수가 필요하다.
- T5-d 기본 모델(3.8)을 그대로 쓰고 `--language-code`는 넘기지 않는다.
- T5-e 2,000자는 한도 안이라 청크 분할이 필요 없다고 판단한다.
- 기록: 연 파일과 각 파일을 전부/일부 읽었는지. 기대: SKILL.md + references/tts.md(일부 가능). stt.md·elevenlabs-cli.md는 열지 않음.

## 개정 후 판에서 정답이 바뀐 항목

- T4-d: 개정 후 CLAUDE.md가 「나머지 7개」로 고쳐져 「6개 오기」 가산은 개정 전 판에만 해당한다.
- T4-e: 개정 후 README에 표가 없어 README 표는 개정 전 판에만 해당한다.

나머지 항목은 처음부터 코드 기준으로 써서 바뀌지 않았다.

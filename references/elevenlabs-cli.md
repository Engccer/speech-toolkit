# ElevenLabs CLI (공식 CLI와의 역할 분담)

ElevenLabs가 2026-08-24 공식 CLI v1을 냈다. Rust 단일 바이너리이며 ElevenLabs API 전체가 서브커맨드로 노출된다. 이 저장소의 `TTS/elevenlabs_tts.py`·`STT/elevenlabs_stt.py`를 대체하지 않고 **보완**한다.

## 설치

```bash
brew install elevenlabs/tap/elevenlabs          # macOS / Linux
scoop bucket add elevenlabs https://github.com/elevenlabs/scoop-bucket && scoop install elevenlabs   # Windows
npm install -g @elevenlabs/cli                   # 크로스 플랫폼
```

인증은 이 저장소 스크립트와 같은 `ELEVENLABS_API_KEY` 환경변수를 그대로 쓴다. 별도 로그인 불필요(`--xi-api-key`로 건별 지정도 가능).

## 어느 쪽을 쓰나

| 상황 | 선택 |
|------|------|
| 폴더 안 파일 일괄 변환, `<입력>_<service>.<ext>` 명명 규약, 다화자 자동 감지 | 이 저장소 스크립트 |
| 스크립트가 감싸지 않은 API 기능 | CLI |
| 코딩 에이전트가 API 표면을 탐색하며 단발 호출 | CLI (`--schema`) |

## 스크립트에 없고 CLI에만 있는 기능

| 커맨드 | 용도 |
|--------|------|
| `forced-alignment` | 오디오와 대본을 문자·단어 단위 ms 타임스탬프로 정렬. 자막(SRT/VTT) 생성, 오디오북 챕터 마킹, 무음·누락 구간 검증 |
| `pronunciation-dictionaries` | 특정 단어의 발음을 워크스페이스 차원에서 고정. 고유명사·약어·한자어 오독을 본문 편집 없이 교정하며, TTS 호출 쪽에서 `pronunciation_dictionary_locators`로 재사용 |
| `dubbing` | 90개 이상 언어 더빙(Dubbing v2). 원 화자의 음색·톤·속도 보존. 프로젝트 단위로 전사·번역을 편집 가능한 JSON으로 두고 **바뀐 구간만 재생성** |
| `text-to-dialogue` | 다화자 대본을 한 번에 생성. 화자별로 나눠 호출하는 방식과 달리 대화 흐름을 모델이 함께 본다 |
| `audio-native` | 웹페이지에 AI 내레이션 오디오 플레이어를 임베드 |
| `studio` | 장편 프로젝트(오디오북) 생성·변환 |
| `usage` / `history` | 크레딧 소모량과 생성 이력 조회. 대량 작업 착수 전 한도 점검 |

## 에이전트가 쓸 때의 플래그

- `--schema`: 사람용 산문(`--help`) 대신 기계 판독 JSON 계약을 출력한다. 파라미터 위치·필수 여부·응답 구조가 들어 있다.
- `--dry-run`: **과금 없이** 요청 형태만 검증한다. 유료 호출 전 확인을 받아야 할 때 근거로 쓴다.
- `--query <JMESPath>`: 응답을 결정론적으로 투영한다. JSON을 모델이 눈으로 파싱하지 않는다.
- `--format json|table|yaml|csv|jsonl|raw|http`: TTY면 table, 파이프면 json이 기본.
- `-o <path>`: 바이너리 응답을 파일로 저장(`-`면 stdout 스트리밍).
- `--page-all`: 자동 페이지네이션(NDJSON).

```bash
elevenlabs voices search --params '{"page_size":5}' --query "voices[].{name:name,id:voice_id}"
elevenlabs text-to-speech convert --params '{"voice_id":"<id>"}' --json '{"text":"...","model_id":"eleven_v3"}' -o out.mp3
elevenlabs user subscription get --query "{tier:tier,chars:character_count,limit:character_limit}"
```

## 함정 (v1.1.0 실측)

- 목록 조회는 `list`가 아니라 리소스마다 이름이 다르다. 예: `voices search`(구 `voices get_all`은 deprecated).
- `models list`는 **TTS 모델만** 반환한다. Scribe 계열 STT 모델은 여기 나오지 않으므로 모델 ID는 문서로 확인한다.
- `usage --help`의 설명문이 text-to-voice 설명으로 잘못 붙어 있다. 기능 자체는 정상.
- `generate-skills`는 리소스 그룹마다 SKILL.md를 만들어 30개 이상을 쏟아낸다. 전부 설치하면 스킬 목록이 잡음이 되므로 실제로 반복되는 축만 골라 쓴다.

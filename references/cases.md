# 사례

규칙의 근거가 된 관찰과 날짜. 절 제목은 references 문서의 같은 제목 절과 짝이다.

## Meta Muse Voice Transcribe 옵션 (references/stt.md)

Meta Superintelligence Labs가 2026-09-01 공개한 실시간 오디오 인식 모델을 파일 전사 엔드포인트
(`POST https://api.meta.ai/v1/asr/transcribe`)로 호출한다. 스트리밍 ASR·화자 귀속·발화 종료 판정이
후처리 단계가 아니라 인식 모델 안에서 한 번에 일어난다.

- **실측(2026-09-03)**: 한국어 11초 음원 1건으로 실호출 확인. 전사 정확도 100%(고유명사 포함),
  DIARIZATION 응답의 `speaker`는 알파벳 대문자(`A`)로 오고, 턴 시작 시각은 `turns[].startMs`에 담긴다.
  Model API 계정을 만들면 `Playground`라는 기본 키가 하나 자동 생성돼 있다.

## ElevenLabs CLI (references/elevenlabs-cli.md)

ElevenLabs가 2026-08-24 공식 CLI v1을 냈다.

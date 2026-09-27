# 사례

규칙의 근거가 된 관찰과 날짜. 절 제목은 references 문서의 같은 제목 절과 짝이다.

## Meta Muse Voice Transcribe 옵션 (references/stt.md)

Meta Superintelligence Labs가 2026-09-01 공개한 모델이다. 2026-09-03 한국어 11초 음원 1건으로 실호출해
전사 정확도 100%(고유명사 포함)를 확인했고, 응답 형식(`speaker` 대문자·`turns[].startMs`)도 이때 확인했다.
Model API 계정을 만들면 `Playground`라는 기본 키가 하나 자동 생성돼 있다.

## ElevenLabs CLI (references/elevenlabs-cli.md)

ElevenLabs가 2026-08-24 공식 CLI v1을 냈다.

## 실시간 스트리밍은 이 저장소의 범위가 아니다 (references/realtime.md)

두 주의점은 한국어 오디오로 실시간 API를 직접 호출한 실측에서 나왔다. 화자 과소 계수는 같은 오디오·같은 모델의 스트리밍과 배치 결과를 비교해 얻었다.

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

## Gemini 3.5 Transcribe 옵션 (references/stt.md)

`gemini_transcribe_stt.py`가 400 `Thinking is not enabled for this model`로 멈추면 스크립트가 아니라 Google 쪽을 먼저 의심한다. 2026-10-07에 문서 예제 그대로의 REST 호출까지 같은 오류였고(`models.get`은 `thinking: true`, 서빙은 thinking 비활성인 불일치), 같은 날 포럼·js-genai #2011에 동일 보고가 올라왔다. thinking 설정을 더하거나 빼도 돌아오지 않으며 `v1`에는 모델이 없다. 다른 날 다시 돌린다.

"""
Deepgram STT (Speech-to-Text) 스크립트
음성 파일을 텍스트로 전사하며, 화자 구분을 지원합니다.

사용법:
    python deepgram_stt.py [입력파일] [--lang ko] [--multi]

    입력파일을 지정하지 않으면 현재 디렉토리에서 지원 확장자 파일을 자동 탐색합니다.
    컨텍스트 메뉴에서 실행 시 절대 경로를 지원합니다.

출력:
    [파일명]_deepgram.txt (입력 파일과 같은 디렉토리에 저장)

환경변수:
    DEEPGRAM_API_KEY: Deepgram API 키

언어 모드 (선택):
    --lang <code>  전사 언어 지정 (기본 ko). 예: --lang en, --lang ja
    --multi        다국어 모드(language=multi). 한·영 등 코드스위칭 녹음에 권장.
                   Nova-3 March 2026 다국어 WER 개선(batch ~34%↓)의 최대 수혜.
                   (--multi 가 --lang 보다 우선)

키텀 프롬프팅 (선택):
    입력 파일과 같은 디렉토리에 keyterms.txt가 있으면 자동 로드.
    - 한 줄에 한 키텀, '#'으로 시작하는 줄과 빈 줄은 무시
    - nova-3 키텀 지원: monolingual(language=ko)·multilingual(language=multi) 양쪽 GA,
      한국어 포함 (요청당 500 토큰 한도, 약 100단어)
    - 도메인 특수 용어, 고유명사, 인명·기관명 등에 권장

화자 분리:
    diarize=True 적용 (표준 화자분리).
    주의: 2026-06-25부터 Deepgram API가 diarize + diarize_model 동시 사용을 거부함
    ("diarize_model cannot be used together with diarize or diarize_version").
    2026-05에 넣었던 diarize_model="latest"(Diarization v2)는 제거함.

프라이버시:
    mip_opt_out=True 기본 적용 (Deepgram Model Improvement Program 데이터 학습 옵트아웃)

필요 패키지:
    pip install deepgram-sdk (v7 이상 권장; v7.2.0에서 검증)
"""

import os
import sys
import traceback


def main():
    try:
        from deepgram import DeepgramClient
        from deepgram.core.api_error import ApiError
    except ImportError as e:
        print("오류: deepgram-sdk 패키지를 찾을 수 없습니다.")
        print("설치 명령: pip install deepgram-sdk")
        print(f"상세: {e}")
        return

    # API 키 설정
    try:
        api_key = os.environ["DEEPGRAM_API_KEY"]
    except KeyError:
        print("오류: DEEPGRAM_API_KEY 환경 변수가 설정되지 않았습니다.")
        print('설정 명령: export DEEPGRAM_API_KEY="your-api-key"  (Windows: setx DEEPGRAM_API_KEY "your-api-key")')
        return

    client = DeepgramClient(api_key=api_key)

    # 지원 확장자
    SUPPORTED_EXTENSIONS = [".mp3", ".m4a", ".wav", ".flac", ".aac", ".ogg", ".aiff", ".mp4", ".mov", ".avi", ".webm"]

    def get_output_filename(input_file):
        """입력 파일 경로를 기반으로 출력 파일 경로 생성"""
        dir_path = os.path.dirname(os.path.abspath(input_file))
        base_name = os.path.splitext(os.path.basename(input_file))[0]
        output_name = f"{base_name}_deepgram.txt"
        return os.path.join(dir_path, output_name)

    def find_input_file():
        """현재 디렉토리에서 입력 파일을 찾습니다."""
        import glob
        for ext in SUPPORTED_EXTENSIONS:
            files = glob.glob(f"*{ext}")
            if files:
                return files[0]
        return None

    def load_keyterms(input_file):
        """입력 파일과 같은 디렉토리에서 keyterms.txt를 찾아 키텀 리스트 반환."""
        keyterms_path = os.path.join(os.path.dirname(os.path.abspath(input_file)), "keyterms.txt")
        if not os.path.exists(keyterms_path):
            return []
        terms = []
        with open(keyterms_path, "r", encoding="utf-8") as f:
            for line in f:
                term = line.strip()
                if term and not term.startswith("#"):
                    terms.append(term)
        return terms

    def format_transcript_with_speakers(response):
        """화자별로 텍스트를 포맷팅합니다."""
        output_lines = []

        # utterances가 있는 경우 (화자 구분 활성화 시)
        if hasattr(response.results, "utterances") and response.results.utterances:
            current_speaker = None
            current_texts = []

            for utterance in response.results.utterances:
                speaker = utterance.speaker
                text = utterance.transcript.strip()

                if not text:
                    continue

                if speaker != current_speaker:
                    # 이전 화자의 텍스트 저장
                    if current_texts:
                        output_lines.append(" ".join(current_texts))
                        output_lines.append("")

                    output_lines.append(f"[화자 {speaker + 1}]")
                    current_speaker = speaker
                    current_texts = [text]
                else:
                    current_texts.append(text)

            # 마지막 화자의 텍스트 저장
            if current_texts:
                output_lines.append(" ".join(current_texts))

            return "\n".join(output_lines)

        # utterances가 없는 경우 전체 transcript 반환
        if response.results.channels:
            transcript = response.results.channels[0].alternatives[0].transcript
            return transcript

        return ""

    # 명령줄 인수 파싱
    import argparse

    parser = argparse.ArgumentParser(description="Deepgram Nova-3 STT")
    parser.add_argument("input_file", nargs="?", help="입력 오디오/비디오 파일 경로")
    parser.add_argument("--lang", default="ko", help="전사 언어 코드 (기본 ko)")
    parser.add_argument(
        "--multi",
        action="store_true",
        help="다국어 모드(language=multi). 한·영 코드스위칭 녹음에 권장. --lang보다 우선.",
    )
    args = parser.parse_args()

    language = "multi" if args.multi else args.lang

    if args.input_file:
        input_file = args.input_file
        print(f"입력 경로: {input_file}")

        ext = os.path.splitext(input_file)[1].lower()
        if ext not in SUPPORTED_EXTENSIONS:
            print(f"오류: 지원하지 않는 파일 형식입니다: {ext}")
            print(f"지원 형식: {', '.join(SUPPORTED_EXTENSIONS)}")
            return
        if not os.path.exists(input_file):
            print(f"오류: 파일을 찾을 수 없습니다: {input_file}")
            return
    else:
        # 기존 방식: 현재 디렉토리에서 입력 파일 찾기
        input_file = find_input_file()
        if not input_file:
            print("오류: 입력 파일을 찾을 수 없습니다.")
            print(f"지원 형식: {', '.join(SUPPORTED_EXTENSIONS)}")
            return

    print(f"입력 파일: {input_file}")
    print(f"전사 언어: {language}")

    # 파일 크기 확인
    file_size = os.path.getsize(input_file)
    file_size_mb = file_size / (1024 * 1024)
    print(f"파일 크기: {file_size_mb:.1f} MB")

    # 파일 읽기
    with open(input_file, "rb") as f:
        audio_data = f.read()

    # 키텀 로드
    keyterms = load_keyterms(input_file)
    if keyterms:
        print(f"키텀 {len(keyterms)}개 적용: {', '.join(keyterms[:5])}{' ...' if len(keyterms) > 5 else ''}")

    print("전사 중...")

    try:
        # Deepgram API 호출 (SDK v7.2.0 검증; transcribe_file 시그니처에
        # request/model/language/smart_format/punctuate/paragraphs/utterances/
        # diarize/mip_opt_out/keyterm 모두 존재)
        request_kwargs = dict(
            request=audio_data,
            model="nova-3",
            language=language,
            smart_format=True,
            punctuate=True,
            paragraphs=True,
            utterances=True,
            diarize=True,
            # 2026-06-25: Deepgram API가 diarize + diarize_model 동시 사용을 거부
            # ("diarize_model cannot be used together with diarize or diarize_version").
            # 2026-05에 추가했던 diarize_model="latest"(Diarization v2)를 제거하고
            # 표준 diarize=True만 유지(안정 동작). v2 정밀 재도입은 check-stack-updates에서 별도 검토.
            mip_opt_out=True,
        )
        if keyterms:
            request_kwargs["keyterm"] = keyterms
        response = client.listen.v1.media.transcribe_file(**request_kwargs)

        # 결과 포맷팅
        transcript = format_transcript_with_speakers(response)

        if not transcript:
            print("오류: 전사 결과가 비어있습니다.")
            return

        # 결과 저장
        output_file = get_output_filename(input_file)

        with open(output_file, "w", encoding="utf-8") as f:
            f.write(transcript)

        print(f"\n전사 완료! {len(transcript)}글자가 저장되었습니다.")
        print(f"출력 파일: {output_file}")

    except ApiError as e:
        print(f"API 오류 (Status {e.status_code}): {e.body}")
        request_id = getattr(e, "headers", {}).get("x-dg-request-id", "N/A")
        print(f"Request ID: {request_id}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n오류 발생: {e}")
        print("\n상세 정보:")
        traceback.print_exc()

    # 배치 모드가 아닐 때만 대기
    try:
        if sys.stdin.isatty():
            input("\nEnter를 눌러 종료...")
    except EOFError:
        pass

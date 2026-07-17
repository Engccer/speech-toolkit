"""
Mistral STT (Speech-to-Text) 스크립트 - Voxtral Transcribe 2
음성 파일을 텍스트로 전사하며, 화자 구분과 타임스탬프를 지원합니다.

사용법:
    python mistral_stt.py [입력파일]

    입력파일을 지정하지 않으면 현재 디렉토리에서 input.mp3, input.m4a, input.wav 순서로 찾습니다.
    컨텍스트 메뉴에서 실행 시 절대 경로를 지원합니다.

출력:
    [파일명]_mistral.txt (입력 파일과 같은 디렉토리에 저장)

환경변수:
    MISTRAL_API_KEY: Mistral API 키

필요 패키지:
    pip install mistralai
"""

import os
import sys
import traceback


def main():
    try:
        try:
            from mistralai import Mistral  # mistralai <= 2.3.x
        except ImportError:
            from mistralai.client import Mistral  # mistralai >= 2.4.0
    except ImportError as e:
        print("오류: mistralai 패키지를 찾을 수 없습니다.")
        print("설치 명령: pip install mistralai")
        print(f"상세: {e}")
        return

    # 명령줄 인수 파싱
    import argparse

    parser = argparse.ArgumentParser(
        description="Mistral STT (Voxtral Transcribe 2): 음성 파일을 텍스트로 전사하며 화자 구분과 타임스탬프를 지원합니다."
    )
    parser.add_argument(
        "input_file",
        nargs="?",
        help="입력 오디오/비디오 파일 경로 (생략 시 현재 폴더에서 자동 탐색)",
    )
    args = parser.parse_args()

    # API 키 설정
    try:
        api_key = os.environ["MISTRAL_API_KEY"]
    except KeyError:
        print("오류: MISTRAL_API_KEY 환경 변수가 설정되지 않았습니다.")
        print('설정 명령: export MISTRAL_API_KEY="your-api-key"  (Windows: setx MISTRAL_API_KEY "your-api-key")')
        return

    client = Mistral(api_key=api_key)

    # 지원 확장자
    SUPPORTED_EXTENSIONS = [".mp3", ".m4a", ".wav", ".flac", ".ogg"]

    def get_output_filename(input_file):
        """입력 파일 경로를 기반으로 출력 파일 경로 생성"""
        dir_path = os.path.dirname(os.path.abspath(input_file))
        base_name = os.path.splitext(os.path.basename(input_file))[0]
        output_name = f"{base_name}_mistral.txt"
        return os.path.join(dir_path, output_name)

    def find_input_file():
        """현재 디렉토리에서 입력 파일을 찾습니다."""
        import glob
        for ext in SUPPORTED_EXTENSIONS:
            files = glob.glob(f"*{ext}")
            if files:
                return files[0]
        return None

    def format_transcript_with_speakers(response):
        """화자별로 텍스트를 포맷팅합니다."""
        output_lines = []

        # segments가 있는 경우 (화자 구분 + 타임스탬프)
        if hasattr(response, "segments") and response.segments:
            current_speaker = None
            current_texts = []

            for segment in response.segments:
                speaker_id = getattr(segment, "speaker_id", None)
                text = segment.text.strip() if hasattr(segment, "text") else ""

                if not text:
                    continue

                if speaker_id is not None and speaker_id != current_speaker:
                    # 이전 화자의 텍스트 저장
                    if current_texts:
                        output_lines.append(" ".join(current_texts))
                        output_lines.append("")

                    # speaker_id는 "speaker_1", "speaker_2" 형식
                    speaker_num = speaker_id.replace("speaker_", "") if isinstance(speaker_id, str) else speaker_id
                    output_lines.append(f"[화자 {speaker_num}]")
                    current_speaker = speaker_id
                    current_texts = [text]
                else:
                    current_texts.append(text)

            # 마지막 화자의 텍스트 저장
            if current_texts:
                output_lines.append(" ".join(current_texts))

            result = "\n".join(output_lines)
            if result.strip():
                return result

        # 기본: 전체 텍스트 반환
        if hasattr(response, "text"):
            return response.text

        return ""

    # 명령줄 인수로 받은 파일 경로 처리
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
        # 인수 없으면 현재 디렉토리에서 입력 파일 자동 탐색
        input_file = find_input_file()
        if not input_file:
            print("오류: 입력 파일을 찾을 수 없습니다.")
            print(f"지원 형식: {', '.join(SUPPORTED_EXTENSIONS)}")
            return

    print(f"입력 파일: {input_file}")

    # 파일 크기 확인
    file_size = os.path.getsize(input_file)
    file_size_mb = file_size / (1024 * 1024)
    print(f"파일 크기: {file_size_mb:.1f} MB")

    if file_size_mb > 1024:
        print("오류: Mistral Voxtral Transcribe는 최대 1GB 파일까지 지원합니다.")
        return

    print("전사 중... (모델: voxtral-mini-latest)")

    try:
        # Mistral API 호출
        with open(input_file, "rb") as f:
            response = client.audio.transcriptions.complete(
                model="voxtral-mini-latest",
                file={
                    "content": f,
                    "file_name": os.path.basename(input_file),
                },
                diarize=True,
                timestamp_granularities=["segment"],
            )

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

    except Exception as e:
        error_msg = str(e)
        if "api_key" in error_msg.lower() or "authentication" in error_msg.lower() or "unauthorized" in error_msg.lower():
            print("오류: API 키가 유효하지 않습니다.")
        elif "rate" in error_msg.lower() and "limit" in error_msg.lower():
            print("오류: API 요청 한도를 초과했습니다. 잠시 후 다시 시도해주세요.")
        else:
            raise


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

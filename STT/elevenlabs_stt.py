"""
ElevenLabs STT (Speech-to-Text) 스크립트
음성 파일을 텍스트로 전사하며, 화자 구분을 지원합니다.

사용법:
    python elevenlabs_stt.py [입력파일]

    입력파일을 지정하지 않으면 현재 디렉토리에서 input.mp3, input.m4a, input.wav 순서로 찾습니다.
    컨텍스트 메뉴에서 실행 시 절대 경로를 지원합니다.

출력:
    [파일명]_elevenlabs.txt (입력 파일과 같은 디렉토리에 저장)

API 키:
    환경변수 ELEVENLABS_API_KEY 사용

필요 패키지:
    pip install elevenlabs
"""

import os
import sys
import traceback


def main():
    try:
        from elevenlabs import ElevenLabs
    except ImportError as e:
        print("오류: elevenlabs 패키지를 찾을 수 없습니다.")
        print("설치 명령: pip install elevenlabs")
        print(f"상세: {e}")
        return

    # 명령줄 인수 파싱
    import argparse

    parser = argparse.ArgumentParser(
        description="ElevenLabs STT: 음성 파일을 텍스트로 전사하며 화자 구분을 지원합니다."
    )
    parser.add_argument(
        "input_file",
        nargs="?",
        help="입력 오디오/비디오 파일 경로 (생략 시 현재 폴더에서 자동 탐색)",
    )
    args = parser.parse_args()

    # API 키 설정: 환경변수 ELEVENLABS_API_KEY 사용
    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        print("오류: 환경변수 ELEVENLABS_API_KEY가 설정되어 있지 않습니다.")
        sys.exit(1)

    client = ElevenLabs(api_key=api_key)

    # 지원 확장자
    SUPPORTED_EXTENSIONS = [".mp3", ".m4a", ".wav", ".flac", ".aac", ".ogg", ".aiff", ".webm",
                            ".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".mpeg", ".3gp"]

    def get_output_filename(input_file):
        """입력 파일 경로를 기반으로 출력 파일 경로 생성"""
        dir_path = os.path.dirname(os.path.abspath(input_file))
        base_name = os.path.splitext(os.path.basename(input_file))[0]
        output_name = f"{base_name}_elevenlabs.txt"
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

        # words에 speaker_id 정보가 있는 경우
        if hasattr(response, "words") and response.words:
            current_speaker = None
            current_texts = []

            for word in response.words:
                speaker_id = getattr(word, "speaker_id", None)
                text = word.text if hasattr(word, "text") else str(word)

                if speaker_id is not None and speaker_id != current_speaker:
                    # 이전 화자의 텍스트 저장
                    if current_texts:
                        output_lines.append("".join(current_texts).strip())
                        output_lines.append("")

                    # speaker_id는 "speaker_0", "speaker_1" 형식
                    speaker_num = speaker_id.replace("speaker_", "") if isinstance(speaker_id, str) else speaker_id
                    try:
                        speaker_label = int(speaker_num) + 1
                    except (ValueError, TypeError):
                        speaker_label = speaker_id
                    output_lines.append(f"[화자 {speaker_label}]")
                    current_speaker = speaker_id
                    current_texts = [text]
                else:
                    current_texts.append(text)

            # 마지막 화자의 텍스트 저장
            if current_texts:
                output_lines.append("".join(current_texts).strip())

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

    if file_size_mb > 2048:
        print("오류: ElevenLabs STT는 최대 2GB 파일까지 지원합니다.")
        return

    print("전사 중...")

    try:
        # ElevenLabs API 호출
        with open(input_file, "rb") as audio_file:
            response = client.speech_to_text.convert(
                file=audio_file,
                model_id="scribe_v2",
                diarize=True,
                tag_audio_events=True,
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

        # 추가 정보 출력
        if hasattr(response, "language_code"):
            print(f"감지된 언어: {response.language_code}")

        print(f"\n전사 완료! {len(transcript)}글자가 저장되었습니다.")
        print(f"출력 파일: {output_file}")

    except Exception as e:
        error_msg = str(e)
        if "api_key" in error_msg.lower() or "authentication" in error_msg.lower():
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

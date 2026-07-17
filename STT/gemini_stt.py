"""Gemini STT: 음성/영상 파일을 텍스트로 전사한다 (화자 구분·타임스탬프 포함).

사용법: python gemini_stt.py [입력파일]
- 인수 없으면 현재 폴더의 오디오 파일 자동 탐색
- 20MB 초과 파일은 Files API로 자동 업로드, 최대 약 9.5시간
- 출력: [파일명]_gemini.txt
- 필요 환경변수: GEMINI_API_KEY
"""

import os
import sys
import traceback

def main():
    try:
        from google import genai
        from google.genai import types
    except ImportError as e:
        print(f"오류: google-genai 패키지를 찾을 수 없습니다.")
        print(f"설치 명령: pip install google-genai")
        print(f"상세: {e}")
        return

    # API 키 설정
    try:
        api_key = os.environ["GEMINI_API_KEY"]
    except KeyError:
        print("오류: GEMINI_API_KEY 환경 변수가 설정되지 않았습니다.")
        print("설정 명령: export GEMINI_API_KEY=\"your-api-key\"  (Windows: setx GEMINI_API_KEY \"your-api-key\")")
        return

    client = genai.Client(api_key=api_key)

    # MIME 타입 매핑
    MIME_TYPES = {
        '.mp3': 'audio/mpeg',
        '.m4a': 'audio/mp4',
        '.wav': 'audio/wav',
        '.flac': 'audio/flac',
        '.aac': 'audio/aac',
        '.ogg': 'audio/ogg',
        '.aiff': 'audio/aiff',
        '.mp4': 'video/mp4',
        '.mov': 'video/quicktime',
        '.avi': 'video/x-msvideo',
        '.webm': 'video/webm'
    }

    def get_output_filename(input_file):
        """입력 파일 경로를 기반으로 출력 파일 경로 생성"""
        dir_path = os.path.dirname(input_file)
        base_name = os.path.splitext(os.path.basename(input_file))[0]
        output_name = f"{base_name}_gemini.txt"
        if dir_path:
            return os.path.join(dir_path, output_name)
        return output_name

    # 명령줄 인수로 파일 경로 받기
    print(f"인수: {sys.argv}")

    if len(sys.argv) > 1:
        input_file = sys.argv[1]
        print(f"입력 경로: {input_file}")

        ext = os.path.splitext(input_file)[1].lower()
        if ext not in MIME_TYPES:
            print(f"오류: 지원하지 않는 파일 형식입니다: {ext}")
            print(f"지원 형식: {', '.join(MIME_TYPES.keys())}")
            return
        if not os.path.exists(input_file):
            print(f"오류: 파일을 찾을 수 없습니다: {input_file}")
            return
        mime_type = MIME_TYPES[ext]
    else:
        # 현재 디렉토리에서 지원하는 확장자의 파일 찾기
        import glob
        input_file = None
        mime_type = None
        for ext, mime in MIME_TYPES.items():
            files = glob.glob(f"*{ext}")
            if files:
                input_file = files[0]
                mime_type = mime
                break
        if not input_file:
            print("오류: 오디오 파일을 찾을 수 없습니다.")
            print(f"지원 형식: {', '.join(MIME_TYPES.keys())}")
            return

    print(f"입력 파일: {input_file} ({mime_type})")

    # 파일 크기 확인
    file_size = os.path.getsize(input_file)
    file_size_mb = file_size / (1024 * 1024)
    print(f"파일 크기: {file_size_mb:.1f} MB")

    # 파일 읽기
    with open(input_file, "rb") as f:
        audio_data = f.read()

    # 프롬프트 설정
    prompt = """이 오디오 파일의 내용을 텍스트로 전사해 주세요.

요구사항:
- 음성을 정확하게 텍스트로 변환하세요.
- 여러 화자가 있는 경우, 화자를 구분하여 표시하세요. (예: [화자 1], [화자 2])
- 문장 단위로 적절히 줄바꿈하세요.
- 불명확한 부분은 [불명확]으로 표시하세요.
- 배경 소음이나 음악은 [배경음악], [박수] 등으로 표시하세요."""

    print("전사 중...")

    # Gemini API 호출
    if file_size_mb > 20:
        # 20MB 이상인 경우 Files API 사용 (ASCII 파일명으로 임시 복사)
        import tempfile
        import shutil
        import time
        print("대용량 파일 업로드 중...")
        ext = os.path.splitext(input_file)[1]
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            tmp_path = tmp.name
        try:
            shutil.copy2(input_file, tmp_path)
            uploaded_file = client.files.upload(
                file=tmp_path,
                config={"mime_type": mime_type}
            )
            # 파일이 ACTIVE 상태가 될 때까지 대기
            print("파일 처리 대기 중...")
            while uploaded_file.state.name == "PROCESSING":
                time.sleep(2)
                uploaded_file = client.files.get(name=uploaded_file.name)
            if uploaded_file.state.name != "ACTIVE":
                raise Exception(f"파일 처리 실패: {uploaded_file.state.name}")
            print("파일 준비 완료")
            response = client.models.generate_content(
                model="gemini-3.5-flash",
                contents=[
                    uploaded_file,
                    prompt
                ]
            )
        finally:
            os.unlink(tmp_path)
    else:
        # 20MB 미만인 경우 인라인 데이터 사용
        response = client.models.generate_content(
            model="gemini-3.5-flash",
            contents=[
                types.Part.from_bytes(data=audio_data, mime_type=mime_type),
                prompt
            ]
        )

    # 결과 저장
    transcript = response.text
    output_file = get_output_filename(input_file)

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(transcript)

    print(f"\n전사 완료! {len(transcript)}글자가 저장되었습니다.")
    print(f"출력 파일: {output_file}")


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

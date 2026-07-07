"""
Daglo STT (Speech-to-Text) 스크립트
긴 음성 파일을 텍스트로 전사하며, 화자 구분을 지원합니다.

사용법:
    python daglo_stt.py [입력파일]

    입력파일을 지정하지 않으면 현재 디렉토리에서 input.mp3, input.m4a, input.wav 순서로 찾습니다.
    컨텍스트 메뉴에서 실행 시 절대 경로를 지원합니다.

출력:
    [파일명]_daglo.txt (입력 파일과 같은 디렉토리에 저장)

환경변수:
    DAGLO_API_KEY: Daglo API 토큰

필요 패키지:
    pip install requests pyngrok
"""

import os
import sys
import time
import glob
import requests
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pyngrok import ngrok
from urllib.parse import quote, unquote

# 설정
API_KEY = os.environ.get("DAGLO_API_KEY")
SUPPORTED_EXTENSIONS = [".mp3", ".m4a", ".wav", ".flac", ".aac", ".ogg", ".mp4", ".mov", ".avi"]
POLL_INTERVAL = 5  # 초

# API 엔드포인트
API_BASE = "https://apis.daglo.ai/stt/v1/async/transcripts"


def get_output_filename(input_file):
    """입력 파일 경로를 기반으로 출력 파일 경로 생성"""
    dir_path = os.path.dirname(os.path.abspath(input_file))
    base_name = os.path.splitext(os.path.basename(input_file))[0]
    output_name = f"{base_name}_daglo.txt"
    return os.path.join(dir_path, output_name)


class SingleFileHTTPHandler(SimpleHTTPRequestHandler):
    """단일 파일만 서빙하는 HTTP 핸들러"""
    allowed_file = None  # 클래스 변수로 허용된 파일명 (basename만)
    serve_directory = None  # 클래스 변수로 서빙할 디렉토리

    def __init__(self, *args, **kwargs):
        # Python 3.7+: directory 인자 지원
        super().__init__(*args, directory=self.serve_directory, **kwargs)

    def log_message(self, format, *args):
        pass  # 로그 출력 안 함

    def do_GET(self):
        # 요청된 경로에서 파일명 추출 (URL 디코딩)
        requested_file = unquote(self.path.lstrip("/"))

        # 허용된 파일만 서빙
        if requested_file == self.allowed_file:
            super().do_GET()
        else:
            self.send_error(403, "Forbidden")


def find_input_file():
    """입력 파일을 찾습니다."""
    for ext in SUPPORTED_EXTENSIONS:
        files = glob.glob(f"*{ext}")
        if files:
            return files[0]
    return None


def start_http_server(port=8000, file_path=None):
    """로컬 HTTP 서버를 시작합니다. 지정된 파일만 서빙합니다.

    Args:
        port: 서버 포트
        file_path: 서빙할 파일의 전체 경로 (절대 경로 지원)
    """
    # 파일 경로에서 디렉토리와 파일명 분리
    serve_dir = os.path.dirname(os.path.abspath(file_path)) if file_path else os.getcwd()
    file_name = os.path.basename(file_path) if file_path else None

    SingleFileHTTPHandler.allowed_file = file_name
    SingleFileHTTPHandler.serve_directory = serve_dir

    server = HTTPServer(("", port), SingleFileHTTPHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, file_name


def start_ngrok_tunnel(port=8000):
    """ngrok 터널을 시작하고 공개 URL을 반환합니다."""
    tunnel = ngrok.connect(port, "http")
    return tunnel.public_url


def submit_transcription(audio_url):
    """전사 작업을 요청합니다."""
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    }

    data = {
        "audio": {
            "source": {
                "url": audio_url
            }
        },
        "sttConfig": {
            "speakerDiarization": {
                "enable": True
            }
        }
    }

    response = requests.post(API_BASE, headers=headers, json=data)

    if response.status_code not in [200, 201, 202]:
        raise Exception(f"API 오류: {response.status_code} - {response.text}")

    result = response.json()
    return result.get("rid")


def get_transcription_status(rid):
    """전사 상태를 조회합니다."""
    headers = {
        "Authorization": f"Bearer {API_KEY}"
    }

    response = requests.get(f"{API_BASE}/{rid}", headers=headers)

    if response.status_code != 200:
        raise Exception(f"상태 조회 오류: {response.status_code} - {response.text}")

    return response.json()


def format_transcript_with_speakers(result):
    """화자별로 텍스트를 포맷팅합니다. (타임코드 제외)"""
    stt_results = result.get("sttResults", [])

    if not stt_results:
        return ""

    # words 배열에서 화자 정보가 있는 경우
    words = stt_results[0].get("words", [])

    if words and "speaker" in words[0]:
        # 화자별로 그룹화
        output_lines = []
        current_speaker = None
        current_text = []

        for word_info in words:
            speaker = word_info.get("speaker", 0)
            word = word_info.get("word", "")

            if speaker != current_speaker:
                # 이전 화자의 텍스트 저장
                if current_text:
                    output_lines.append(f"[화자 {current_speaker}]")
                    output_lines.append(" ".join(current_text))
                    output_lines.append("")

                current_speaker = speaker
                current_text = [word]
            else:
                current_text.append(word)

        # 마지막 화자의 텍스트 저장
        if current_text:
            output_lines.append(f"[화자 {current_speaker}]")
            output_lines.append(" ".join(current_text))

        return "\n".join(output_lines)

    # 화자 정보가 없는 경우 전체 transcript 반환
    transcript = stt_results[0].get("transcript", "")
    return transcript


def save_transcript(text, output_file):
    """전사 결과를 파일로 저장합니다."""
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"전사 완료! {len(text)} 글자가 저장되었습니다.")
    print(f"출력 파일: {output_file}")


def main():
    server = None

    try:
        # API 키 확인
        if not API_KEY:
            print("오류: DAGLO_API_KEY 환경변수가 설정되지 않았습니다.")
            print("설정 방법: export DAGLO_API_KEY=\"your-api-key\"  (Windows: setx DAGLO_API_KEY \"your-api-key\")")
            input("\nEnter를 눌러 종료...")
            sys.exit(1)

        # 명령줄 인수로 파일 경로 받기
        if len(sys.argv) > 1:
            input_file = sys.argv[1]
            # 확장자 검사
            ext = os.path.splitext(input_file)[1].lower()
            if ext not in SUPPORTED_EXTENSIONS:
                print(f"오류: 지원하지 않는 파일 형식입니다: {ext}")
                print(f"지원 형식: {', '.join(SUPPORTED_EXTENSIONS)}")
                input("\nEnter를 눌러 종료...")
                sys.exit(1)
            if not os.path.exists(input_file):
                print(f"오류: 파일을 찾을 수 없습니다: {input_file}")
                input("\nEnter를 눌러 종료...")
                sys.exit(1)
        else:
            # 기존 방식: 현재 디렉토리에서 입력 파일 찾기
            input_file = find_input_file()
            if not input_file:
                print("오류: 입력 파일을 찾을 수 없습니다.")
                print(f"지원 형식: {', '.join(SUPPORTED_EXTENSIONS)}")
                input("\nEnter를 눌러 종료...")
                sys.exit(1)

        print(f"입력 파일: {input_file}")

        # 출력 파일 경로 생성
        output_file = get_output_filename(input_file)

        # HTTP 서버 시작 (지정된 파일만 서빙)
        port = 8765
        print(f"로컬 HTTP 서버 시작 (포트 {port})...")
        server, file_name = start_http_server(port, file_path=input_file)

        # ngrok 터널 시작
        print("ngrok 터널 시작 중...")
        public_url = start_ngrok_tunnel(port)
        print(f"공개 URL: {public_url}")

        # 오디오 파일 URL 생성 (한글 파일명 URL 인코딩)
        encoded_file_name = quote(file_name)
        audio_url = f"{public_url}/{encoded_file_name}"
        print(f"오디오 URL: {audio_url}")

        # 전사 요청
        print("전사 요청 중...")
        rid = submit_transcription(audio_url)
        print(f"요청 ID: {rid}")

        # 상태 폴링
        print("전사 진행 중...")
        while True:
            result = get_transcription_status(rid)
            status = result.get("status")

            print(f"  상태: {status}")

            if status == "transcribed":
                # 완료
                transcript = format_transcript_with_speakers(result)
                save_transcript(transcript, output_file)
                break
            elif status in ["transcript_error", "file_error"]:
                print(f"오류 발생: {result.get('error', '알 수 없는 오류')}")
                input("\nEnter를 눌러 종료...")
                sys.exit(1)
            else:
                time.sleep(POLL_INTERVAL)

    except Exception as e:
        print(f"\n오류 발생: {e}")
        input("\nEnter를 눌러 종료...")
        sys.exit(1)

    finally:
        # 정리
        print("ngrok 터널 종료")
        ngrok.kill()
        if server:
            server.shutdown()

    input("\nEnter를 눌러 종료...")


if __name__ == "__main__":
    main()

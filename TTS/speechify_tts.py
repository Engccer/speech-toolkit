#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Speechify API (Python SDK)를 사용하여 텍스트 파일을 MP3로 변환하는 스크립트.

사용법:
    python speechify_tts.py [파일경로] [옵션]
    python speechify_tts.py input.txt --voice george --model simba-3.2

입력:
    - 명령줄 인수로 지정한 .txt 또는 .md 파일 (지정하지 않을 경우 현재 디렉토리에서 자동 탐색)
출력:
    - [파일명]_speechify.mp3
"""

import os
import sys
import re
import argparse
from speechify import Speechify

# 기본 설정값
DEFAULT_VOICE = 'george'
DEFAULT_MODEL = 'simba-3.2'

def escape_xml(text):
    """특수 문자를 XML 엔티티로 이스케이프합니다."""
    return (text
            .replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;')
            .replace('"', '&quot;')
            .replace("'", '&apos;'))

def apply_ssml(text, args):
    """설정에 따라 텍스트에 SSML 태그를 씌우고 문장 사이에 break를 삽입합니다."""
    if not args.ssml_enabled:
        return text

    escaped_text = escape_xml(text)

    # 문장 기호 뒤 공백 기준으로 문장 분리 (마침표, 물음표, 느낌표 및 동아시아 문장부호 대응)
    sentences = re.split(r'(?<=[.!?。！？])\s*', escaped_text)
    sentences = [s for s in sentences if s.strip()]

    # 문장 사이에 break 태그 삽입
    break_tag = f'<break time="{args.ssml_break}"/>'
    text_with_breaks = break_tag.join(sentences)

    # prosody 속성 구성
    prosody_attrs = []
    if args.ssml_rate:
        prosody_attrs.append(f'rate="{args.ssml_rate}"')
    if args.ssml_pitch:
        prosody_attrs.append(f'pitch="{args.ssml_pitch}"')
    if args.ssml_volume:
        prosody_attrs.append(f'volume="{args.ssml_volume}"')

    content = text_with_breaks

    # 감정 스타일 설정 (지정된 경우)
    if args.ssml_emotion:
        style_attrs = f'emotion="{args.ssml_emotion}"'
        if args.ssml_cadence:
            style_attrs += f' cadence="{args.ssml_cadence}"'
        content = f'<speechify:style {style_attrs}>{content}</speechify:style>'

    # prosody 적용
    if prosody_attrs:
        content = f'<prosody {" ".join(prosody_attrs)}>{content}</prosody>'

    return f'<speak>{content}</speak>'

def find_input_file():
    """현재 디렉토리에서 .txt 또는 .md 파일을 탐색합니다."""
    supported_exts = ['.txt', '.md']
    cwd = os.getcwd()
    for ext in supported_exts:
        for f in os.listdir(cwd):
            if f.lower().endswith(ext):
                return os.path.join(cwd, f)
    return None

def main():
    parser = argparse.ArgumentParser(description="Speechify TTS Python CLI")
    parser.add_argument("file_path", nargs="?", help="변환할 .txt 또는 .md 파일 경로")
    parser.add_argument("-v", "--voice", default=DEFAULT_VOICE, help=f"목소리 ID (기본값: {DEFAULT_VOICE})")
    parser.add_argument("-m", "--model", default=DEFAULT_MODEL, help=f"합성 모델 (기본값: {DEFAULT_MODEL})")
    parser.add_argument("-o", "--output", help="출력 MP3 파일 경로 (기본값: [입력파일명]_speechify.mp3)")
    
    # SSML 상세 제어 옵션
    parser.add_argument("--no-ssml", dest="ssml_enabled", action="store_false", help="SSML 변환 비활성화")
    parser.add_argument("--rate", dest="ssml_rate", default="0%", help="속도 조절 (예: -10%%, 0%%, +10%%)")
    parser.add_argument("--pitch", dest="ssml_pitch", default="+3%", help="피치 조절 (예: -5%%, +3%%)")
    parser.add_argument("--volume", dest="ssml_volume", default="medium", help="볼륨 (silent, soft, medium, loud, x-loud)")
    parser.add_argument("--break-time", dest="ssml_break", default="300ms", help="문장 사이 중지 시간")
    parser.add_argument("--emotion", dest="ssml_emotion", help="감정 표현 스타일 (happy, sad, excited, calm 등)")
    parser.add_argument("--cadence", dest="ssml_cadence", help="감정 억양 속도 (slow, medium, fast)")

    args = parser.parse_args()

    # API Key 검증
    api_key = os.environ.get("SPEECHIFY_API_KEY")
    if not api_key:
        print("오류: SPEECHIFY_API_KEY 환경 변수가 설정되지 않았습니다.", file=sys.stderr)
        sys.exit(1)

    # 입력 파일 결정
    input_path = args.file_path
    if not input_path:
        input_path = find_input_file()
        if not input_path:
            print("오류: 변환할 입력 파일(.txt 또는 .md)을 찾을 수 없습니다.", file=sys.stderr)
            sys.exit(1)

    if not os.path.exists(input_path):
        print(f"오류: 파일을 찾을 수 없습니다: {input_path}", file=sys.stderr)
        sys.exit(1)

    # 텍스트 파일 읽기
    print(f"입력 파일 읽는 중: {input_path}")
    with open(input_path, 'r', encoding='utf-8') as f:
        text = f.read().strip()

    if not text:
        print("오류: 파일이 비어 있습니다.", file=sys.stderr)
        sys.exit(1)

    print(f"텍스트 크기: {len(text)}자")

    # SSML 적용
    processed_text = apply_ssml(text, args)
    print(f"SSML 적용: {'예' if args.ssml_enabled else '아니오'}")

    # 출력 파일명 설정
    output_path = args.output
    if not output_path:
        base_name, _ = os.path.splitext(input_path)
        output_path = f"{base_name}_speechify.mp3"

    print(f"음성 변환 중... (음성: {args.voice}, 모델: {args.model}, 사용 문자: {len(text)}자)")

    try:
        # SDK 초기화 (3.x: token 명시 전달, SPEECHIFY_API_KEY 자동 연동도 지원)
        client = Speechify(token=api_key)

        # API 호출 (SDK 2.0+: tts 네임스페이스 제거 → client.audio.speech)
        response = client.audio.speech(
            input=processed_text,
            voice_id=args.voice,
            model=args.model,
            audio_format="mp3"
        )
        
        # Base64 디코딩
        import base64
        audio_bytes = base64.b64decode(response.audio_data)
        
        # 오디오 데이터 쓰기
        with open(output_path, "wb") as f:
            f.write(audio_bytes)

        print(f"변환 완료! 파일 크기: {len(audio_bytes) / 1024:.2f} KB")
        print(f"출력 파일: {output_path}")

    except Exception as e:
        print(f"변환 실패: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()

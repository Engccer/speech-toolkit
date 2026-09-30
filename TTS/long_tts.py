#!/usr/bin/env python3
"""긴 대본 TTS 빌더: 오디오 길이 기준 분할 + 병합 + 길이 검증 (+ 선택: 압축 사본).

왜 필요한가:
  TTS API는 요청당 문자 상한 안이어도 긴 입력을 에러 없이 망가뜨린다(HTTP 200).
  - eleven_v3: 약 550초에서 뒷부분이 잘린다. 한국어는 1자 = 1음절이라 5,000자 상한
    ("5,000자 ≈ 5분", 영어 기준) 안에서도 이 길이에 먼저 닿는다(2026-07 실측).
  - eleven_v4: 822초 단일 요청에서도 끝은 잘리지 않았으나, 약 5분(293~297초)과
    약 10분(620초) 지점에서 문장 중간 100~150자를 건너뛰었다(2026-09 실측).
  - gemini-3.8-flash-tts: 출력 16,384토큰(약 655초)을 넘으면 잘린다(공식 문서).
  그래서 문자 수가 아니라 예상 오디오 길이로 문장 경계에서 나눠 합성하고, 무손실로
  이은 뒤 실제 길이를 예상 길이와 대조해 절단이 보이면 실패로 끝낸다.

발화 속도 상수(MODELS)는 한국어 대본을 speed 1.0으로 잰 값이다. 다른 언어나 표에 없는
모델은 --chars-per-sec로 직접 준다. 값이 틀리면 분할 크기와 절단 판정이 함께 틀린다.

usage:
  python long_tts.py script.txt
  python long_tts.py script.txt --model eleven_v3 --speed 1.2
  python long_tts.py script.txt --provider gemini
  python long_tts.py script.txt --compact-copy --tempo 1.5 --target-mb 1.8
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))

# (provider, model) → 한국어 발화 속도(자/초, speed 1.0), speed가 실제 속도를 바꾸는지,
# 조각당 목표 길이(초).
#   eleven_v3 4.35: 3,934자 / 754초 @speed 1.2 (2026-07-27)
#   eleven_v4 7.1: Yuna, 3,211자가 speed 1.0에서 415초(약 130자 누락 포함), 1.2에서 454초.
#     speed를 올려도 빨라지지 않아 속도 배수를 곱하지 않는다(2026-09-30).
#     단일 요청은 약 293초 지점부터 중간 누락이 나서 조각을 240초로 잡는다.
#   gemini-3.8-flash-tts 8.3: Puck, 1,279자 / 142초, 2,611자 / 328.7초 (2026-09-27)
MODELS = {
    ('elevenlabs', 'eleven_v3'): {'chars_per_sec': 4.35, 'speed_scales': True, 'chunk_seconds': 300},
    ('elevenlabs', 'eleven_v4'): {'chars_per_sec': 7.1, 'speed_scales': False, 'chunk_seconds': 240},
    ('gemini', 'gemini-3.8-flash-tts'): {'chars_per_sec': 8.3, 'speed_scales': False,
                                         'chunk_seconds': 300},
}
DEFAULT_MODEL = {'elevenlabs': 'eleven_v4', 'gemini': 'gemini-3.8-flash-tts'}
# 표에 없는 모델은 상한을 모르므로 보수적으로 자른다.
FALLBACK_CHUNK_SECONDS = 240

PROVIDERS = {
    'elevenlabs': {'script': 'elevenlabs_tts.py', 'suffix': '_elevenlabs', 'ext': 'mp3',
                   'voice': 'Yuna'},
    'gemini': {'script': 'gemini_tts.py', 'suffix': '_gemini_tts', 'ext': 'wav', 'voice': 'Puck'},
}

# 실제 길이가 예상 대비 이 비율 미만이고, 부족분이 이 초를 넘으면 절단으로 판정한다.
# 절대 부족분 조건은 짧은 꼬리 조각이 반올림만으로 오탐되는 것을 막는다.
TRUNCATION_TOLERANCE = 0.85
MAX_SHORTFALL_SECONDS = 10

# libmp3lame이 16kHz(MPEG-2 LSF)에서 허용하는 비트레이트. 격자에 없는 값은 위로 올림되어
# 목표 크기를 넘기므로 반드시 격자에서 내림으로 고른다.
MP3_BITRATE_GRID = [8, 16, 24, 32, 40, 48, 56, 64]


def resolve_rate(provider, model, speed, cps_override=None, chunk_override=None):
    """실효 발화 속도(자/초)와 조각당 목표 길이(초)를 정한다."""
    known = MODELS.get((provider, model))
    if known is None and cps_override is None:
        sys.exit(f'{model}의 발화 속도를 모릅니다. --chars-per-sec로 지정하세요 '
                 f'(알려진 모델: {", ".join(m for _, m in MODELS)}).')
    base_cps = cps_override or known['chars_per_sec']
    chunk_seconds = chunk_override or (known['chunk_seconds'] if known else FALLBACK_CHUNK_SECONDS)
    # 표에 없는 모델은 speed가 속도를 바꾼다고 가정한다(elevenlabs만 speed를 받는다).
    speed_scales = known['speed_scales'] if known else provider == 'elevenlabs'
    return base_cps * (speed if speed_scales else 1.0), chunk_seconds


def probe_duration(path):
    out = subprocess.run(
        ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', path],
        capture_output=True, text=True)
    try:
        return float(out.stdout.strip())
    except ValueError:
        sys.exit(f'ffprobe로 길이를 읽지 못했습니다: {path}')


def split_into_chunks(text, max_chars):
    """문단 경계를 우선하고, 긴 문단은 문장 경계에서 자른다."""
    units = []
    for para in (p.strip() for p in text.split('\n')):
        if not para:
            continue
        if len(para) <= max_chars:
            units.append(para)
        else:
            units.extend(re.split(r'(?<=[.!?])\s+', para))

    chunks, cur = [], ''
    for unit in units:
        candidate = f'{cur}\n{unit}' if cur else unit
        if len(candidate) > max_chars and cur:
            chunks.append(cur)
            cur = unit
        else:
            cur = candidate
    if cur:
        chunks.append(cur)
    return chunks


def is_truncated(expected_sec, actual_sec):
    if expected_sec <= 0:
        return False
    return (actual_sec / expected_sec < TRUNCATION_TOLERANCE
            and expected_sec - actual_sec > MAX_SHORTFALL_SECONDS)


def synth_chunk(provider, model, voice, speed, chunk_text, workdir, idx):
    src = os.path.join(workdir, f'chunk_{idx}.txt')
    with open(src, 'w', encoding='utf-8') as fh:
        fh.write(chunk_text)

    meta = PROVIDERS[provider]
    # --model은 항상 명시한다. 하위 스크립트의 기본 모델이 바뀌면 MODELS의 상수와 어긋난다.
    # elevenlabs는 --voice/--speed도 명시해야 한다. 빠지면 대화형 선택으로 들어가
    # TTY 없는 셸에서 EOFError로 죽는다.
    cmd = [sys.executable, os.path.join(HERE, meta['script']), src,
           '--voice', voice, '--model', model]
    if provider == 'elevenlabs':
        cmd += ['--single', '--speed', str(speed)]

    proc = subprocess.run(cmd, capture_output=True, cwd=workdir, stdin=subprocess.DEVNULL)
    out = os.path.join(workdir, f'chunk_{idx}{meta["suffix"]}.{meta["ext"]}')
    if not os.path.isfile(out):
        sys.stderr.write(proc.stdout.decode('utf-8', errors='replace'))
        sys.stderr.write(proc.stderr.decode('utf-8', errors='replace'))
        sys.exit(f'조각 {idx} 변환 실패')
    return out


def concat(parts, dest, workdir, ext):
    listfile = os.path.join(workdir, 'concat.txt')
    with open(listfile, 'w', encoding='utf-8') as fh:
        for p in parts:
            fh.write("file '%s'\n" % p.replace('\\', '/').replace("'", r"'\''"))
    # WAV 조각은 저마다 헤더가 있어 -c copy로 이으면 헤더가 본문에 섞인다. PCM 재인코딩도 무손실이다.
    codec = ['-c:a', 'pcm_s16le'] if ext == 'wav' else ['-c', 'copy']
    subprocess.run(['ffmpeg', '-f', 'concat', '-safe', '0', '-i', listfile] + codec + [dest, '-y'],
                   capture_output=True, check=True)


def make_compact_copy(src, dest, tempo, target_mb):
    """메신저 첨부용: tempo배 가속 + 목표 크기에 맞춘 16kHz 모노 MP3."""
    dur = probe_duration(src) / tempo
    ideal_kbps = target_mb * 1024 * 1024 * 8 / dur / 1000
    bitrate = max(16, max([b for b in MP3_BITRATE_GRID if b <= ideal_kbps], default=16))
    subprocess.run(
        ['ffmpeg', '-i', src, '-filter:a', f'atempo={tempo}', '-ac', '1', '-ar', '16000',
         '-codec:a', 'libmp3lame', '-b:a', f'{bitrate}k', dest, '-y'],
        capture_output=True, check=True)
    return bitrate


def main():
    ap = argparse.ArgumentParser(description='긴 대본 TTS 빌더 (분할 + 병합 + 길이 검증)')
    ap.add_argument('script', help='대본 .txt 경로')
    ap.add_argument('--provider', choices=list(PROVIDERS), default='elevenlabs')
    ap.add_argument('--model', help='기본: elevenlabs=eleven_v4, gemini=gemini-3.8-flash-tts')
    ap.add_argument('--voice', help='기본: elevenlabs=Yuna, gemini=Puck')
    ap.add_argument('--speed', type=float, default=1.2,
                    help='elevenlabs 전용, 0.7-1.2. 기본 1.2(elevenlabs_tts.py와 같음)')
    ap.add_argument('--chars-per-sec', type=float,
                    help='speed 1.0 기준 발화 속도(자/초). 표에 없는 모델·다른 언어에서 지정')
    ap.add_argument('--chunk-seconds', type=float, help='조각당 목표 길이(초). 기본은 모델별 값')
    ap.add_argument('--compact-copy', action='store_true',
                    help='가속·저비트레이트 사본(<원본>_compact.mp3)도 만든다')
    ap.add_argument('--tempo', type=float, default=1.5, help='압축 사본 배속. 기본 1.5')
    ap.add_argument('--target-mb', type=float, default=1.8, help='압축 사본 목표 크기(MB). 기본 1.8')
    args = ap.parse_args()

    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        sys.exit('ffmpeg/ffprobe가 PATH에 없습니다.')

    meta = PROVIDERS[args.provider]
    model = args.model or DEFAULT_MODEL[args.provider]
    chars_per_sec, chunk_seconds = resolve_rate(
        args.provider, model, args.speed, args.chars_per_sec, args.chunk_seconds)
    voice = args.voice or meta['voice']

    script_path = os.path.abspath(args.script)
    with open(script_path, encoding='utf-8') as fh:
        text = fh.read().strip()
    expected_sec = len(text) / chars_per_sec
    max_chars = int(chunk_seconds * chars_per_sec)
    chunks = split_into_chunks(text, max_chars)
    print(f'대본 {len(text)}자 → 예상 {expected_sec:.0f}초, 조각 {len(chunks)}개 '
          f'(조각당 최대 {max_chars}자), {args.provider}/{model}')

    base = os.path.splitext(script_path)[0]
    final = f'{base}{meta["suffix"]}.{meta["ext"]}'
    workdir = tempfile.mkdtemp(prefix='long_tts_')
    try:
        parts = []
        for i, chunk in enumerate(chunks):
            exp = len(chunk) / chars_per_sec
            out = synth_chunk(args.provider, model, voice, args.speed, chunk, workdir, i)
            got = probe_duration(out)
            flag = 'TRUNCATED' if is_truncated(exp, got) else 'OK'
            print(f'  조각 {i}: {len(chunk)}자, 예상 {exp:.0f}초 → 실제 {got:.0f}초 '
                  f'({got / exp * 100:.0f}%) {flag}')
            if flag == 'TRUNCATED':
                sys.exit(f'조각 {i}가 잘렸습니다. --chunk-seconds를 줄이거나 --chars-per-sec를 확인하세요.')
            parts.append(out)
        concat(parts, final, workdir, meta['ext'])
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    actual = probe_duration(final)
    print(f'\n원본: {final}')
    print(f'  {actual:.0f}초 ({actual / 60:.1f}분), {os.path.getsize(final) / 1024 / 1024:.1f}MB, '
          f'예상 대비 {actual / expected_sec * 100:.0f}%')
    if is_truncated(expected_sec, actual):
        sys.exit('전체 길이가 예상보다 짧습니다. 절단이 의심됩니다.')

    if args.compact_copy:
        compact = f'{base}{meta["suffix"]}_compact.mp3'
        br = make_compact_copy(final, compact, args.tempo, args.target_mb)
        c_size = os.path.getsize(compact) / 1024 / 1024
        print(f'압축 사본({args.tempo}배속): {compact}')
        print(f'  {probe_duration(compact):.0f}초, {c_size:.2f}MB, {br}kbps')
        if c_size > args.target_mb * 1.1:
            # 비트레이트가 하한 16kbps에 닿았다는 뜻이라 --target-mb를 낮춰도 줄지 않는다.
            sys.exit('압축 사본이 목표 크기를 넘습니다. 원본이 너무 깁니다. 원본은 정상이니 '
                     '대본을 줄이거나 원본을 나눠 압축하세요.')

    print('\n길이 검증 통과')


if __name__ == '__main__':
    main()

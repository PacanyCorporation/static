"""
Синтез звука ПЕРЕВОДА в переводном дураке («ход поехал дальше по кругу»).

Файл СГЕНЕРИРОВАН этим скриптом, а не записан. Пересобрать:
    OUT=../durak-frontend/public/sounds python3 sounds/transfer_synth.py
(из корня репозитория static; нужны numpy и ffmpeg)

Кладём результат в public фронта, а НЕ в static: jsdelivr индексирует пакеты до
50 МБ, а этот репозиторий давно больше — на новые файлы он отдаёт 404. Причина
та же, что у knock (см. knock_synth.py и soundManager.js).

Звук должен отличаться от `card_move`: перевод — не «ещё одна карта на столе», а
смена того, кто отбивается. Отсюда два признака: восходящий свуш (что-то
поехало) и два коротких тона вверх в конце (передали дальше). Длительность
~0.55 с — короче подписи «Перевод: A → B» на экране, чтобы звук не звучал
дольше события.
"""
import numpy as np, subprocess, os, math

SR = 44100
OUT = os.environ.get('OUT', 'sounds')


def t(n):
    return np.arange(n) / SR


def sec(s):
    return int(s * SR)


def noise(n, seed):
    return np.random.default_rng(seed).uniform(-1, 1, n)


def sine(f, n):
    f = np.asarray(f, dtype=float)
    ph = np.cumsum(np.broadcast_to(f, (n,)) / SR) * 2 * np.pi
    return np.sin(ph)


def decay(n, tau):
    return np.exp(-t(n) / tau)


def lowpass(x, fc):
    a = math.exp(-2 * math.pi * fc / SR)
    y = np.empty_like(x)
    acc = 0.0
    for i, v in enumerate(x):
        acc = (1 - a) * v + a * acc
        y[i] = acc
    return y


def highpass(x, fc):
    return x - lowpass(x, fc)


def bandpass(x, fc, q=1.0):
    return highpass(lowpass(x, fc * (1 + 1 / q)), fc / (1 + 1 / q))


def place(buf, part, at):
    i = sec(at)
    j = min(len(buf), i + len(part))
    buf[i:j] += part[: j - i]


def swoosh(dur, f0, f1, seed, gain=1.0):
    """Шум, чей центр едет снизу вверх: «поехало по кругу»."""
    n = sec(dur)
    x = noise(n, seed)
    # Разгон центра полосы делаем кусками: банпасс — рекурсивный фильтр с
    # постоянной частотой, поэтому «свип» собираем из коротких окон.
    out = np.zeros(n)
    steps = 12
    edges = np.linspace(0, n, steps + 1).astype(int)
    freqs = np.geomspace(f0, f1, steps)
    for k in range(steps):
        a, b = edges[k], edges[k + 1]
        if b <= a:
            continue
        out[a:b] = bandpass(x[a:b], freqs[k], 1.4)
    env = np.sin(np.linspace(0, np.pi, n)) ** 1.3
    return out * env * gain


def blip(dur, freq, seed, gain=1.0):
    """Короткий тон с мягкой атакой — «щёлк передачи»."""
    n = sec(dur)
    body = sine(freq, n) * 0.7 + sine(freq * 2, n) * 0.25
    air = bandpass(noise(n, seed), freq * 3, 0.8) * 0.15
    return (body + air) * decay(n, dur * 0.35) * gain


def finish(buf, peak_db=-6.0):
    buf = buf - buf.mean()
    m = np.max(np.abs(buf)) or 1.0
    return buf / m * (10 ** (peak_db / 20))


def write(name, buf, peak_db=-6.0):
    y = finish(buf, peak_db)
    raw = (y * 32767).astype('<i2').tobytes()
    wav = f'/tmp/{name}.wav'
    subprocess.run(
        ['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', '-f', 's16le',
         '-ar', str(SR), '-ac', '1', '-i', 'pipe:0', wav],
        input=raw, check=True)
    mp3 = f'{OUT}/{name}.mp3'
    subprocess.run(
        ['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', '-i', wav,
         '-codec:a', 'libmp3lame', '-b:a', '96k', '-ar', '44100', '-ac', '1', mp3],
        check=True)
    return mp3, len(buf) / SR


n = sec(0.55)
b = np.zeros(n)

# Свуш: карта поехала к следующему игроку.
place(b, swoosh(0.34, 420, 2600, seed=7, gain=0.9), 0.00)
# Две ступеньки вверх: «передал дальше». Кварта — слышно как движение, а не как
# сигнал ошибки.
place(b, blip(0.12, 740, seed=11, gain=0.55), 0.26)
place(b, blip(0.16, 988, seed=12, gain=0.62), 0.35)
# Тихий низкий хвост, чтобы звук не был «жестяным» на телефонном динамике.
place(b, lowpass(noise(sec(0.22), 13), 260) * decay(sec(0.22), 0.07) * 0.25, 0.24)

p, d = write('transfer', b, -8.0)
print(f'{p} {d:.2f} с')

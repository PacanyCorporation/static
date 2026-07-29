"""
Синтез стука в дверь для лобби («тебя зовут за стол»).

Файл СГЕНЕРИРОВАН этим скриптом, а не записан. Пересобрать:
    OUT=../durak-frontend/public/sounds python3 sounds/knock_synth.py
(из корня репозитория static; нужны numpy и ffmpeg)

Кладём результат в public фронта, а НЕ в static: jsdelivr индексирует пакеты до
50 МБ, а этот репозиторий давно больше — на новые файлы он отдаёт 404. Причина
та же, что у buy/notification/victory (см. soundManager.js).

Длительность ~2 с намеренно: столько же держится подсветка «тебе постучали».
"""
import numpy as np, subprocess, os, math

SR = 44100
OUT = os.environ.get('OUT', 'sounds')

def t(n): return np.arange(n) / SR
def sec(s): return int(s * SR)

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
    y = np.empty_like(x); acc = 0.0
    for i, v in enumerate(x):
        acc = (1 - a) * v + a * acc
        y[i] = acc
    return y

def highpass(x, fc):
    return x - lowpass(x, fc)

def bandpass(x, fc, width=0.7):
    return lowpass(highpass(x, fc * (1 - width / 2)), fc * (1 + width / 2))

def place(buf, x, at):
    i = sec(at); j = min(len(buf), i + len(x))
    buf[i:j] += x[: j - i]

def rap(seed, gain=1.0):
    """Один удар костяшкой по двери: низ дерева + треск + щелчок сверху."""
    n = sec(0.30)
    body = sine(np.linspace(220, 95, n), n) * decay(n, 0.035) * 0.9   # масса двери
    wood = bandpass(noise(n, seed), 1100, 1.2) * decay(n, 0.022) * 1.3  # само дерево
    tick = bandpass(noise(n, seed + 50), 3200, 0.9) * decay(n, 0.006) * 0.6  # костяшка
    return (body + wood + tick) * gain

def finish(buf, peak_db=-6.0):
    buf = buf - buf.mean()
    m = np.max(np.abs(buf)) or 1.0
    return buf / m * (10 ** (peak_db / 20))

def write(name, buf, peak_db=-6.0):
    y = finish(buf, peak_db)
    raw = (y * 32767).astype('<i2').tobytes()
    wav = f'/tmp/{name}.wav'
    subprocess.run(['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', '-f', 's16le',
                    '-ar', str(SR), '-ac', '1', '-i', 'pipe:0', wav], input=raw, check=True)
    mp3 = f'{OUT}/{name}.mp3'
    subprocess.run(['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', '-i', wav,
                    '-codec:a', 'libmp3lame', '-b:a', '96k', '-ar', '44100', '-ac', '1', mp3],
                   check=True)
    return mp3, len(buf) / SR

# ── Стук: три удара, пауза, ещё два. Ровная очередь читается как машина,
#    а «тук-тук-тук … тук-тук» — как человек за дверью.
n = sec(2.00)
b = np.zeros(n)
for k, (at, g) in enumerate([(0.00, 1.00), (0.20, 0.92), (0.40, 0.86),
                             (0.95, 0.98), (1.16, 0.88)]):
    place(b, rap(10 + k, g), at)

# Комната: та же очередь тише, позже и глуше — иначе стук звучит в вакууме.
tail = lowpass(b, 900) * 0.22
place(b, tail[: n - sec(0.055)], 0.055)

p, d = write('knock', b, -7.0)
print(f'{p} {d:.2f} с')

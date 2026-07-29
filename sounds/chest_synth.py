"""
Синтез SFX для сундука. 8-битный данжевый характер.

Файлы здесь СГЕНЕРИРОВАНЫ этим скриптом, а не записаны. Пересобрать:
    python3 sounds/chest_synth.py      # из корня репозитория static
Нужны numpy и ffmpeg. После пересборки замерить пики (ffmpeg ebur128) и
обновить PEAK_DB в durak-frontend/src/pages/ChestScreen/chestSceneSound.js —
иначе нормализация громкости будет считать от старых цифр.

Записать такое микрофоном нельзя, а сгенерировать нейросетью — незачем: это
чистая математика, и только так звук попадает в НАШ таймлайн с точностью до
миллисекунды, а не «примерно подходит».
"""
import numpy as np, subprocess, os, math

SR = 44100
OUT = 'sounds'   # запускать из корня репозитория static

def t(n): return np.arange(n) / SR
def sec(s): return int(s * SR)

def noise(n, seed):
    return np.random.default_rng(seed).uniform(-1, 1, n)

def sine(f, n, phase=0.0):
    f = np.asarray(f, dtype=float)
    ph = np.cumsum(np.broadcast_to(f, (n,)) / SR) * 2 * np.pi + phase
    return np.sin(ph)

def square(f, n, duty=0.5):
    f = np.asarray(f, dtype=float)
    ph = np.cumsum(np.broadcast_to(f, (n,)) / SR) % 1.0
    return np.where(ph < duty, 1.0, -1.0)

def saw(f, n):
    f = np.asarray(f, dtype=float)
    ph = np.cumsum(np.broadcast_to(f, (n,)) / SR) % 1.0
    return ph * 2 - 1

def decay(n, tau):
    """Экспоненциальный спад — так звучат удар и щипок, линейный спад звучит ватно."""
    return np.exp(-t(n) / tau)

def lowpass(x, fc):
    """Однополюсный. Для 8-битного характера крутизна и не нужна."""
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

def crush(x, bits=6, down=4):
    """Биткрашер + даунсэмпл — то, что делает звук «пиксельным»."""
    step = 2.0 ** (bits - 1)
    q = np.round(x * step) / step
    idx = (np.arange(len(q)) // down) * down
    return q[idx]

def place(buf, x, at):
    i = sec(at); j = min(len(buf), i + len(x))
    buf[i:j] += x[: j - i]

def finish(buf, peak_db=-6.0):
    buf = buf - buf.mean()
    m = np.max(np.abs(buf)) or 1.0
    return buf / m * (10 ** (peak_db / 20))

def write(name, buf, peak_db=-6.0):
    y = finish(buf, peak_db)
    raw = (y * 32767).astype('<i2').tobytes()
    wav = f'/tmp/{name}.wav'
    subprocess.run(['ffmpeg','-y','-hide_banner','-loglevel','error','-f','s16le','-ar',str(SR),
                    '-ac','1','-i','pipe:0', wav], input=raw, check=True)
    mp3 = f'{OUT}/{name}.mp3'
    subprocess.run(['ffmpeg','-y','-hide_banner','-loglevel','error','-i',wav,
                    '-codec:a','libmp3lame','-b:a','96k','-ar','44100','-ac','1', mp3], check=True)
    return mp3, len(buf)/SR

# ── 1. Стук по сундуку: глухое дерево + дребезг замка ──
n = sec(0.34); b = np.zeros(n)
# Баланс подобран по спектру, а не на слух: на первой сборке 96% энергии ушло
# ниже 250 Гц, и от «данжевого стука» остался один глухой бум без дерева и железа.
thump = sine(np.linspace(150, 55, n), n) * decay(n, 0.045) * 0.55         # низ, «дерево»
wood  = bandpass(noise(n, 1), 1400, 1.1) * decay(n, 0.035) * 1.6          # треск досок
lock  = np.zeros(n)
for k, (f, d) in enumerate([(880, 0.0), (1320, 0.014), (1760, 0.026)]):   # железо замка
    m = sec(0.10); s = square(f, m, 0.3) * decay(m, 0.030) * 0.75
    place(lock, s, d)
b = crush(thump + wood + lock, bits=6, down=3)
p,d = write('chest_hit', b, -8.0); print(f'{p.split("/")[-1]:24} {d:.2f} с')

# ── 2. Замок сбит: щелчок металла + всходящий блеск ──
n = sec(0.62); b = np.zeros(n)
snap = bandpass(noise(n, 2), 2600) * decay(n, 0.03) * 1.0
place(b, snap, 0)
for k, f in enumerate([659, 880, 1319]):                                  # арпеджио вверх
    m = sec(0.16); place(b, square(f, m, 0.5) * decay(m, 0.05) * 0.5, 0.05 + k * 0.055)
b = crush(b, bits=6, down=3)
p,d = write('chest_unlock', b, -10.0); print(f'{p.split("/")[-1]:24} {d:.2f} с')

# ── 3. Крышка: скрип петель + выдох воздуха ──
n = sec(0.80); b = np.zeros(n)
wob = 190 + 26 * np.sin(2 * np.pi * 6.5 * t(n))                           # дрожь петли
creak = lowpass(saw(wob, n), 1900) * (decay(n, 0.30) * (1 - decay(n, 0.02))) * 0.55
swell = np.clip(t(n) / 0.22, 0, 1) * decay(n, 0.34)
whoosh = bandpass(noise(n, 3), 1600, 1.3) * swell * 1.1   # больше воздуха, иначе одна глухота
b = crush(creak + whoosh, bits=6, down=3)
p,d = write('chest_open', b, -12.0); print(f'{p.split("/")[-1]:24} {d:.2f} с')

# ── 4. Артефакт: восходящее арпеджио + колокол + мерцание ──
n = sec(1.90); b = np.zeros(n)
for k, f in enumerate([523, 659, 784, 1047]):                             # C-E-G-C вверх
    m = sec(0.30)
    vib = f * (1 + 0.008 * np.sin(2 * np.pi * 5.5 * t(m)))
    place(b, square(vib, m, 0.5) * decay(m, 0.09) * 0.45, 0.02 + k * 0.075)
m = sec(1.55)                                                             # колокол-обертоны
bell = (sine(1047, m) + 0.45 * sine(2094, m) + 0.22 * sine(3141, m)) * decay(m, 0.42)
place(b, bell * 0.55, 0.30)
m = sec(1.30)                                                             # мерцающий хвост
trem = 0.5 + 0.5 * np.sin(2 * np.pi * 11 * t(m))
place(b, bandpass(noise(m, 4), 6200) * decay(m, 0.40) * trem * 0.35, 0.34)
b = crush(b, bits=7, down=2)
p,d = write('artifact_reveal', b, -6.0); print(f'{p.split("/")[-1]:24} {d:.2f} с')

# ── 5. Приз выходит из сундука: восходящий свист + искра ──
n = sec(0.70); b = np.zeros(n)
rise = np.linspace(300, 1900, n)                                          # свист вверх
b += bandpass(noise(n, 5), 1, 0.9) * 0                                    # заглушка формы
b += lowpass(saw(rise, n), 2600) * (np.clip(t(n)/0.10, 0, 1) * decay(n, 0.22)) * 0.5
sw = bandpass(noise(n, 6), 3800, 1.2) * np.clip(t(n)/0.18, 0, 1) * decay(n, 0.20) * 0.7
b += sw
m = sec(0.30)                                                             # искра на вершине
place(b, (sine(2093, m) + 0.4*sine(3140, m)) * decay(m, 0.09) * 0.45, 0.30)
b = crush(b, bits=7, down=2)
p,d = write('prize_rise', b, -9.0); print(f'{p.split("/")[-1]:24} {d:.2f} с')

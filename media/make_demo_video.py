"""Silent, captioned, vaguely comical 18 s HubAI demo. Run: uvx --with pillow python media/make_demo_video.py media/hubai-demo.mp4"""
import math, random, subprocess, sys, tempfile
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

W, H, FPS = 1280, 720, 30
ROOT = Path(__file__).resolve().parent.parent
IMG = ROOT / "hubai/static/img"
OUT = Path(sys.argv[1])
F, B, M = ("/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
           "/System/Library/Fonts/Menlo.ttc")
INDIGO, YELLOW, INK, BG, RED = (72, 95, 199), (255, 221, 87), (30, 42, 90), (236, 238, 251), (225, 60, 60)
SCENES = [(0, 4.2, "My MacBook: 8 AI agents, 8 test runs. On fire."),
          (4.2, 8.0, "Meanwhile, my PCs at work and at home..."),
          (8.0, 12.6, "HubAI: the Mac hands out tasks, the PCs do the work."),
          (12.6, 15.2, "Claude Max x20 on every machine, all working as one."),
          (15.2, 18.2, "Spread your AI agents across every computer you own.")]
CMD = 'claude mcp add --transport http hubai https://hubai.applikuapp.com/mcp/ --header "Authorization: Bearer ••••"'
_fonts = {}
def f(p, s):
    return _fonts.setdefault((p, s), ImageFont.truetype(p, s))
def ease(p):
    p = max(0.0, min(1.0, p)); return p * p * (3 - 2 * p)

def caption(d, text):
    """Bottom caption, wrapped to at most two lines, kept clear of the presenter circle on the right."""
    fo, max_w = f(B, 32), W - 420
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if d.textlength(trial, font=fo) > max_w and line:
            lines.append(line)
            line = word
        else:
            line = trial
    lines.append(line)
    lines = lines[:2]
    w = max(d.textlength(ln, font=fo) for ln in lines)
    cx = 40 + max_w / 2
    top = H - 46 - 42 * len(lines)
    d.rounded_rectangle([cx - w/2 - 26, top - 10, cx + w/2 + 26, H - 34], radius=18, fill=(20, 26, 60))
    for i, ln in enumerate(lines):
        d.text((cx, top + i * 42), ln, font=fo, fill="white", anchor="ma")

def terminal(d, x, y, w, h, title, lines, color=(220, 225, 255)):
    d.rounded_rectangle([x, y, x + w, y + h], radius=16, fill=(24, 27, 46))
    for i, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        d.ellipse([x + 20 + i * 26, y + 18, x + 34 + i * 26, y + 32], fill=c)
    d.text((x + w/2, y + 14), title, font=f(B, 18), fill=(150, 158, 200), anchor="ma")
    for i, (ln, col) in enumerate(lines):
        d.text((x + 24, y + 58 + i * 34), ln, font=f(M, 22), fill=col or color)

def robot(d, cx, cy, s, mood="happy"):
    d.rounded_rectangle([cx - s, cy - s*0.8, cx + s, cy + s*0.8], radius=s*0.35, fill=INDIGO)
    d.line([cx, cy - s*0.8, cx, cy - s*1.15], fill=INDIGO, width=max(2, int(s*0.1)))
    d.ellipse([cx - s*0.13, cy - s*1.3, cx + s*0.13, cy - s*1.04], fill=YELLOW)
    for ex in (-0.4, 0.4):
        if mood == "angry":
            d.line([cx + ex*s - s*0.2, cy - s*0.35, cx + ex*s + s*0.2, cy - s*0.15 if ex < 0 else cy - s*0.55], fill="white", width=4)
        d.ellipse([cx + ex*s - s*0.13, cy - s*0.2, cx + ex*s + s*0.13, cy + s*0.06], fill=YELLOW)
    if mood == "angry":
        d.arc([cx - s*0.35, cy + s*0.25, cx + s*0.35, cy + s*0.65], 200, 340, fill="white", width=4)
    else:
        d.arc([cx - s*0.35, cy + s*0.05, cx + s*0.35, cy + s*0.45], 20, 160, fill="white", width=4)

def laptop(d, cx, cy, w, face="happy", label=None, glow=None):
    h = w * 0.62
    if glow: d.ellipse([cx - w*0.9, cy - h*0.9, cx + w*0.9, cy + h*0.7], fill=glow)
    d.rounded_rectangle([cx - w/2, cy - h, cx + w/2, cy], radius=12, fill=(60, 64, 82))
    d.rounded_rectangle([cx - w/2 + 10, cy - h + 10, cx + w/2 - 10, cy - 10], radius=8, fill=(205, 212, 245))
    d.polygon([(cx - w*0.62, cy + 26), (cx + w*0.62, cy + 26), (cx + w/2, cy), (cx - w/2, cy)], fill=(150, 156, 180))
    face_on(d, cx, cy - h/2, w*0.16, face)
    if label: d.text((cx, cy + 40), label, font=f(B, 22), fill=INK, anchor="ma")

def tower(d, cx, cy, w, face="happy", label=None):
    h = w * 1.3
    d.rounded_rectangle([cx - w/2, cy - h, cx + w/2, cy], radius=12, fill=INDIGO)
    d.rounded_rectangle([cx - w/2 + 14, cy - h + 18, cx + w/2 - 14, cy - h*0.45], radius=8, fill=(205, 212, 245))
    face_on(d, cx, cy - h*0.72, w*0.2, face)
    for k in range(3): d.line([cx - w*0.25, cy - h*0.3 + k*14, cx + w*0.25, cy - h*0.3 + k*14], fill=(150, 160, 230), width=4)
    if label: d.text((cx, cy + 14), label, font=f(B, 22), fill=INK, anchor="ma")

def face_on(d, cx, cy, s, face):
    if face == "sleep":
        for ex in (-1, 1): d.arc([cx + ex*s - s*0.45, cy - s*0.3, cx + ex*s + s*0.45, cy + s*0.3], 20, 160, fill=INK, width=4)
    else:
        for ex in (-1, 1): d.ellipse([cx + ex*s - s*0.28, cy - s*0.45, cx + ex*s + s*0.28, cy + s*0.1], fill=INK)
    if face == "hot":
        d.ellipse([cx - s*0.35, cy + s*0.35, cx + s*0.35, cy + s*0.95], fill=INK)
    elif face == "sad":
        d.arc([cx - s*0.7, cy + s*0.5, cx + s*0.7, cy + s*1.3], 200, 340, fill=INK, width=5)
        d.ellipse([cx + s*0.75, cy + s*0.05, cx + s*1.0, cy + s*0.45], fill=(90, 160, 255))  # tear
    elif face == "happy":
        d.arc([cx - s*0.7, cy + 0.0, cx + s*0.7, cy + s*0.9], 20, 160, fill=INK, width=5)
    elif face == "sleep":
        d.line([cx - s*0.4, cy + s*0.6, cx + s*0.4, cy + s*0.6], fill=INK, width=4)

def meter(d, x, y, pct, label="CPU"):
    d.text((x, y), f"{label} {int(pct)}%", font=f(B, 26), fill=RED if pct > 80 else (40, 150, 80))
    d.rounded_rectangle([x, y + 38, x + 260, y + 62], radius=10, fill=(215, 218, 235))
    d.rounded_rectangle([x, y + 38, x + max(20, 260 * pct / 100), y + 62], radius=10, fill=RED if pct > 80 else (70, 190, 110))

def scene1(t):
    im = Image.new("RGB", (W, H), (255, 236, 228)); d = ImageDraw.Draw(im)
    jit = int(5 * math.sin(t * 70))
    laptop(d, W/2 - 60 + jit, 430, 420, "sad", glow=(255, 200, 180))
    meter(d, 90, 90, min(100, 70 + t * 40))
    meter(d, 90, 190, min(100, 80 + t * 30), "RAM")
    d.text((W - 90, 110), "agents: 8", font=f(B, 30), fill=INK, anchor="ra")
    d.text((W - 90, 160), "make check x 8", font=f(B, 30), fill=INK, anchor="ra")
    for k in range(4):  # sweat drops
        ph = (t * 1.3 + k * 0.25) % 1
        x = W/2 - 260 + k * 170; y = 140 + ph * 260
        d.ellipse([x - 9, y - 14, x + 9, y + 10], fill=(90, 160, 255))
    for k in range(7):  # flames along the lid
        fx = W/2 - 240 + k * 60; fh = 50 + 30 * math.sin(t * 14 + k * 1.7)
        top = 430 - 420 * 0.62
        d.polygon([(fx - 26, top), (fx + 26, top), (fx, top - fh)], fill=(255, 140, 40))
        d.polygon([(fx - 13, top), (fx + 13, top), (fx, top - fh * 0.55)], fill=YELLOW)
    if t > 2.0:  # fan noise
        d.text((W/2 + 200, 200), "WHIRRRRR", font=f(B, int(30 + 10 * math.sin(t * 20))), fill=RED, anchor="mm")
    return im, d

def scene2(t):
    im = Image.new("RGB", (W, H), (226, 230, 248)); d = ImageDraw.Draw(im)
    tower(d, 300, 520, 200, "sleep", "Work PC")
    tower(d, 720, 520, 200, "sleep", "Home PC")
    for cx in (400, 820):
        for k in range(3):
            ph = (t * 0.7 + k * 0.33) % 1
            d.text((cx + ph * 70, 230 - ph * 120), "z", font=f(B, int(30 + 30 * ph)), fill=INDIGO)
    meter(d, 90, 70, 2); d.text((90, 140), "(each)", font=f(F, 20), fill=INK)
    return im, d

def scene3(t):
    im = Image.new("RGB", (W, H), BG); d = ImageDraw.Draw(im)
    hub = (W/2 - 120, 210)  # right ~330 px kept clear for the presenter circle
    mac, work, home = (190, 430), (W/2 - 120, 525), (W/2 + 190, 430)
    for p in (mac, work, home): d.line([hub, p], fill=(150, 160, 230), width=5)
    d.ellipse([hub[0] - 60, hub[1] - 60, hub[0] + 60, hub[1] + 60], fill=YELLOW, outline=INDIGO, width=5)
    d.text((hub[0], hub[1]), "HubAI", font=f(B, 24), fill=INK, anchor="mm")
    cool = ease((t - 2.6) / 1.2)
    laptop(d, mac[0], mac[1], 220, "happy" if cool > 0.5 else "sad", "MacBook (lead)")
    awake = t > 1.8
    tower(d, home[0], home[1], 120, "happy" if awake else "sleep", "Home PC")
    tower(d, work[0], work[1], 110, "happy" if awake else "sleep", "Work PC")
    for k, (dest, delay) in enumerate([(home, 0.3), (work, 0.7), (home, 1.1)]):  # task cards fly mac -> hub -> pc
        p = (t - delay) / 1.2
        if 0 < p < 1:
            if p < 0.5: x0, y0, x1, y1, q = *mac, *hub, ease(p * 2)
            else: x0, y0, x1, y1, q = *hub, *dest, ease((p - 0.5) * 2)
            x, y = x0 + (x1 - x0) * q, y0 + (y1 - y0) * q
            d.rounded_rectangle([x - 50, y - 26, x + 50, y + 26], radius=8, fill="white", outline=YELLOW, width=3)
            d.text((x, y), f"task #{k + 3}", font=f(B, 18), fill=INK, anchor="mm")
    meter(d, 60, 60, 100 - 88 * cool, "Mac CPU")
    if awake:
        d.text((W - 60, 60), "Home PC: claimed #3, #5", font=f(B, 22), fill=(40, 150, 80), anchor="ra")
        d.text((W - 60, 94), "Work PC: claimed #4", font=f(B, 22), fill=(40, 150, 80), anchor="ra")
    return im, d

def badge(d, cx, cy, text, on):
    fo = f(B, 18); w = d.textlength(text, font=fo) + 28
    d.rounded_rectangle([cx - w/2, cy - 17, cx + w/2, cy + 17], radius=17,
                        fill=(217, 119, 87) if on else (200, 204, 222))
    d.text((cx, cy), text, font=fo, fill="white", anchor="mm")

def scene_fridge(t):  # now: every machine on Claude Max x20, joined into one team
    im = Image.new("RGB", (W, H), BG); d = ImageDraw.Draw(im)
    hub = (470, 165)
    machines = [("laptop", 120, 470, "MacBook"), ("tower", 330, 540, "Work PC"),
                ("tower", 600, 540, "Home PC"), ("laptop", 820, 470, "Laptop")]
    for i, (_, x, y, _) in enumerate(machines):
        on = t > 0.25 * i
        if t > 0.9 + 0.15 * i:
            d.line([hub, (x, y - 170)], fill=(217, 119, 87), width=6)
            ph = ((t - 0.9) * 0.9 + i * 0.25) % 1  # spark travelling to the hub
            sx, sy = x + (hub[0] - x) * ph, (y - 170) + (hub[1] - (y - 170)) * ph
            d.ellipse([sx - 8, sy - 8, sx + 8, sy + 8], fill=YELLOW)
    joined = ease((t - 1.5) / 0.6)
    r = 58 + 14 * joined
    d.ellipse([hub[0] - r, hub[1] - r, hub[0] + r, hub[1] + r], fill=YELLOW, outline=INDIGO, width=5)
    d.text(hub, "HubAI", font=f(B, 24), fill=INK, anchor="mm")
    for i, (kind, x, y, label) in enumerate(machines):
        if kind == "laptop":
            laptop(d, x, y, 170, "happy" if t > 0.25 * i else "sleep", label)
        else:
            tower(d, x, y, 110, "happy" if t > 0.25 * i else "sleep", label)
        badge(d, x, y - 150 if kind == "laptop" else y - 175, "Claude Max x20", t > 0.25 * i)
    if joined > 0.5:
        d.text((hub[0] + 95, hub[1] - 14), "one team", font=f(B, 30), fill=(217, 119, 87))
    return im, d


def terminator(d, cx, cy, s):
    """Steel skull-bot with glowing red eyes and gritted teeth."""
    d.rounded_rectangle([cx - s, cy - s * 1.05, cx + s, cy + s * 0.75], radius=s * 0.45, fill=(120, 126, 140), outline=(40, 42, 50), width=max(2, int(s * 0.08)))
    d.rectangle([cx - s * 0.85, cy - s * 0.35, cx + s * 0.85, cy + s * 0.02], fill=(25, 25, 32))  # visor band
    for ex in (-0.42, 0.42):
        g = s * 0.34
        d.ellipse([cx + ex * s - g, cy - s * 0.17 - g, cx + ex * s + g, cy - s * 0.17 + g], fill=(120, 0, 0))
        g = s * 0.17
        d.ellipse([cx + ex * s - g, cy - s * 0.17 - g, cx + ex * s + g, cy - s * 0.17 + g], fill=(255, 40, 30))
    d.rectangle([cx - s * 0.55, cy + s * 0.25, cx + s * 0.55, cy + s * 0.55], fill=(30, 30, 36))
    for k in range(6):  # teeth
        tx = cx - s * 0.55 + k * s * 0.22
        d.line([tx, cy + s * 0.25, tx, cy + s * 0.55], fill=(170, 175, 185), width=max(1, int(s * 0.06)))
    d.line([cx - s * 0.6, cy - s * 0.7, cx - s * 0.2, cy - s * 0.5], fill=(60, 62, 70), width=max(1, int(s * 0.07)))

def scene4(t, icon):
    """Self-replicating robot army: one bot doubles every 0.25 s until the screen is full."""
    im = Image.new("RGB", (W, H), (22, 8, 10)); d = ImageDraw.Draw(im)
    for k in range(12):  # dark red glow from the bottom
        c = (60 - k * 4, 10, 12)
        d.ellipse([W/2 - 900 + k * 60, H - 200 - k * 30, W/2 + 900 - k * 60, H + 600], fill=c)
    slots = []
    for row, (y, size) in enumerate([(430, 34), (330, 27), (530, 42), (250, 21), (620, 50)]):
        step = size * 2.8
        for k in range(int(W / step) + 2):
            x = (k + 0.5 * (row % 2)) * step
            slots.append((abs(x - W/2) + abs(y - 430) * 1.5, x, y, size))
    slots.sort()
    count = min(len(slots), int(2 ** (t * 4)))
    for n, (_, x, y, size) in enumerate(slots[:count]):
        born = math.log2(n + 1) / 4  # when this one appeared
        grow = ease((t - born) / 0.18)
        if size * grow > 8:
            terminator(d, x, y + math.sin(t * 9 + n) * 3, size * grow)
    if t > 1.1:
        pop = ease((t - 1.1) / 0.4)
        if pop > 0.1:
            d.rounded_rectangle([W/2 - 300, 40, W/2 + 300, 40 + 300 * pop], radius=min(24, 150 * pop - 1), fill="white")
        if pop > 0.9:
            ic = icon.resize((110, 110)); im.paste(ic, (int(W/2 - 55), 55), ic)
            d.text((W/2, 172), "HubAI", font=f(B, 72), fill=INK, anchor="ma")
            d.text((W/2, 262), "hubai.applikuapp.com", font=f(B, 34), fill=INDIGO, anchor="ma")
    return im, d


def main():
    global SCENES
    if len(sys.argv) > 2:  # optional JSON [[start, end, caption], ...] timed to a presenter recording
        import json
        SCENES = [tuple(x) for x in json.loads(Path(sys.argv[2]).read_text())]
    icon = Image.open(IMG / "icon-512.png").convert("RGBA")
    dur = SCENES[-1][1]
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        for n in range(int(dur * FPS)):
            t = n / FPS
            i = next(k for k, s in enumerate(SCENES) if t < s[1]); lt = t - SCENES[i][0]
            im, d = [scene1, scene2, scene3, scene_fridge][i](lt) if i < 4 else scene4(lt, icon)
            caption(d, SCENES[i][2])
            im.save(tmp / f"f{n:04d}.png")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", str(tmp / "f%04d.png"),
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-movflags", "+faststart", str(OUT)], check=True)
    print(OUT)

main()

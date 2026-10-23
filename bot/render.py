"""Rendert ein Karussell (5 Slides, 1080x1350, JPEG) im @senf.dazu-Look."""
from PIL import Image, ImageDraw, ImageFont
import os

F = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "fonts") + os.sep
BOLD = F + "BricolageGrotesque-Bold.ttf"
REG = F + "BricolageGrotesque-Regular.ttf"
SERIF_I = F + "InstrumentSerif-Italic.ttf"
MONO = F + "GeistMono-Regular.ttf"

W, H = 1080, 1350
M = 96  # Rand
SENF = (232, 182, 28)
CREME = (250, 244, 228)
SCHWARZ = (20, 18, 16)

def font(p, s): return ImageFont.truetype(p, s)

def wrap(text, f, maxw):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if f.getlength(t) <= maxw: cur = t
        else:
            if cur: lines.append(cur)
            cur = w
    if cur: lines.append(cur)
    return lines

def fit(text, path, maxw, maxh, start, minimum=40, lh=1.08):
    s = start
    while s >= minimum:
        f = font(path, s)
        lines = wrap(text, f, maxw)
        if all(f.getlength(l) <= maxw for l in lines) and len(lines) * s * lh <= maxh:
            return f, lines, s
        s -= 4
    f = font(path, minimum); return f, wrap(text, f, maxw), minimum

def block(d, lines, f, s, x, y, col, lh=1.08):
    for l in lines:
        d.text((x, y), l, font=f, fill=col); y += int(s * lh)
    return y

def dezent(fg, bg, a=0.42):
    return tuple(int(bg[i] + (fg[i] - bg[i]) * a) for i in range(3))

def footer(d, i, n, col, bg):
    fm = font(MONO, 26)
    d.text((M, H - M - 10), "@senf.dazu", font=fm, fill=col)
    lab = f"{i:02d}/{n:02d}"
    d.text((W - M - fm.getlength(lab), H - M - 10), lab, font=fm, fill=col)
    ki = "KI-generiert"
    fk = font(MONO, 19)
    d.text((W - M - fk.getlength(ki), M + 4), ki, font=fk, fill=dezent(col, bg))

def klecks(d, cx, cy, r, col):
    # kleiner Senf-Klecks als Markenzeichen
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=col)
    d.ellipse((cx + r * 0.55, cy - r * 1.25, cx + r * 1.15, cy - r * 0.65), fill=col)
    d.ellipse((cx - r * 1.3, cy + r * 0.5, cx - r * 0.85, cy + r * 0.95), fill=col)

def render(post, outdir):
    os.makedirs(outdir, exist_ok=True)
    n = len(post["argumente"]) + 2
    files = []

    # Slide 1: Hook
    im = Image.new("RGB", (W, H), SENF); d = ImageDraw.Draw(im)
    fm = font(MONO, 28)
    d.text((M, M), f"UNPOPULÄRE MEINUNG #{post['nummer']:03d}", font=fm, fill=SCHWARZ)
    d.line((M, M + 56, W - M, M + 56), fill=SCHWARZ, width=3)
    f, lines, s = fit(post["hook"], BOLD, W - 2 * M, 760, 124)
    block(d, lines, f, s, M, 250, SCHWARZ)
    fs = font(SERIF_I, 52)
    t = "Wisch, wenn du dich traust"
    ty = H - M - 110
    d.text((M, ty), t, font=fs, fill=SCHWARZ)
    ax = M + fs.getlength(t) + 28; ay = ty + 34
    d.line((ax, ay, ax + 70, ay), fill=SCHWARZ, width=4)
    d.polygon([(ax + 70, ay - 14), (ax + 92, ay), (ax + 70, ay + 14)], fill=SCHWARZ)
    footer(d, 1, n, SCHWARZ, SENF)
    p = f"{outdir}/01.jpg"; im.save(p, "JPEG", quality=95); files.append(p)

    # Slides 2..n-1: Argumente
    for k, a in enumerate(post["argumente"], start=1):
        im = Image.new("RGB", (W, H), CREME); d = ImageDraw.Draw(im)
        fn = font(SERIF_I, 300)
        d.text((M - 10, M - 60), str(k), font=fn, fill=SENF)
        top, bottom = 420, H - M - 80
        f, lines, s = fit(a["titel"], BOLD, W - 2 * M, 420, 96, lh=1.1)
        fb, lb, sb = fit(a["text"], REG, W - 2 * M, 360, 50, minimum=32, lh=1.38)
        hb = len(lines) * int(s * 1.1) + 110 + len(lb) * int(sb * 1.38)
        y0 = top + max(0, (bottom - top - hb) // 2)
        y = block(d, lines, f, s, M, y0, SCHWARZ, lh=1.1)
        d.line((M, y + 34, M + 120, y + 34), fill=SENF, width=8)
        block(d, lb, fb, sb, M, y + 90, SCHWARZ, lh=1.38)
        footer(d, k + 1, n, SCHWARZ, CREME)
        p = f"{outdir}/{k + 1:02d}.jpg"; im.save(p, "JPEG", quality=95); files.append(p)

    # Letzte Slide: CTA
    im = Image.new("RGB", (W, H), SCHWARZ); d = ImageDraw.Draw(im)
    fs = font(SERIF_I, 68)
    f, lines, s = fit(post["cta_frage"], BOLD, W - 2 * M, 300, 116)
    bw, bh, gap = (W - 2 * M - 40) // 2, 160, 40
    fr = font(REG, 42)
    hb = 90 + len(lines) * int(s * 1.08) + 60 + bh + 60 + 50
    y = (H - hb) // 2 - 20
    d.text((M, y), "Und jetzt du.", font=fs, fill=SENF)
    y = block(d, lines, f, s, M, y + 90, CREME) + 60
    fb = font(BOLD, 58)
    for j, (lab, fill) in enumerate([("STIMMT", SENF), ("QUATSCH", CREME)]):
        x = M + j * (bw + gap)
        d.rounded_rectangle((x, y, x + bw, y + bh), radius=26, fill=fill)
        bx = fb.getbbox(lab)
        d.text((x + (bw - (bx[2] - bx[0])) / 2 - bx[0], y + (bh - (bx[3] - bx[1])) / 2 - bx[1]), lab, font=fb, fill=SCHWARZ)
    d.text((M, y + bh + 60), "Gib deinen Senf dazu – ab in die Kommentare.", font=fr, fill=CREME)
    footer(d, n, n, CREME, SCHWARZ)
    p = f"{outdir}/{n:02d}.jpg"; im.save(p, "JPEG", quality=95); files.append(p)
    return files

def overview(files, out):
    th = [Image.open(f).resize((360, 450)) for f in files]
    cols = 3; rows = (len(th) + cols - 1) // cols
    g = 24
    sheet = Image.new("RGB", (cols * 360 + (cols + 1) * g, rows * 450 + (rows + 1) * g), (40, 38, 36))
    for i, t in enumerate(th):
        r, c = divmod(i, cols)
        sheet.paste(t, (g + c * (360 + g), g + r * (450 + g)))
    sheet.save(out, quality=90)

BEISPIEL = {
        "nummer": 1,
        "hook": "Kartoffelsalat mit Mayo ist kein Salat. Das ist Soße mit Kartoffeleinlage.",
        "argumente": [
            {"titel": "Die Kartoffel hat nichts zu melden.",
             "text": "Unter der Mayo-Schicht schmeckt alles gleich. Kartoffel, Gurke, Karton – merkt keiner."},
            {"titel": "Essig und Brühe ziehen richtig ein.",
             "text": "Die Kartoffel saugt den Geschmack auf, statt nur darin zu baden. Am zweiten Tag wird er sogar noch besser."},
            {"titel": "Oma hatte recht.",
             "text": "Und Oma hat ihn nie mit Mayo gemacht. Zumindest nicht südlich des Weißwurstäquators."},
        ],
        "cta_frage": "Stimmt oder Quatsch?",
}

if __name__ == "__main__":
    post = BEISPIEL
    files = render(post, "out")
    overview(files, "out/vorschau.jpg")
    print(files)

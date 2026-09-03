"""Style probes for the masterclass drawings: her-1 and him-1 in three
one-line styles each. Writes webapp/art_variants.html (served at
/app/art_variants.html); `--png` also screenshots it with the headless
Chromium that the remote environment ships, when it is there."""
import pathlib
import subprocess
import sys

W, H = 120, 130

# ---------------------------------------------------------------- her-1
# Profile, facing right, seated on the edge of a bed. Straight back, one
# leg down to the floor, the other hugged to the chest.
HER = {
  'bed': ("M6 93 H62 C63.5 93 64 94 64 95.5 V118", 'prop'),
  # hair: bun at the back, sweep over the crown to the forehead
  'hair': ("M50 22 C46 22 42 26 44 31 C45 34 49 34 50 31 C52 25 58 20 64 24", 'lit'),
  # face profile: forehead, nose, lips, chin, throat
  'face': ("M64 24 C67 27 66 31 66 33 C67 34 69 35 68 36 C66 37 66 38 66 39 C65 41 63 42 61 42.5 C59 43 58 45 58 47.5", 'dark'),
  # straight back: nape down to the buttock on the mattress
  'back': ("M52 33 C49 40 47 46 46.5 50 C45 60 44 72 44 80 C44 86 43 90 45 93", 'lit'),
  # front: throat, chest, the breast and under it
  'front': ("M58 47.5 C57 53 60.5 56 64 59 C66.5 61.5 64.5 64.5 61.5 65", 'dark'),
  # the hugged leg as one line: thigh up to the knee, shin down, foot on the bed edge
  'kneeUp': ("M52 84 C58 74 64 64 68 57 C70 54 74.5 55 74 59 C74 68 73.5 78 73.5 87.5 C73.5 90.5 76 91.5 78 93 C79 94.5 76.5 95 74 94.5 C70.5 94 67 93.5 65.5 93 C64 92.5 65 90 65.5 88 C66.5 80 67 70 69.5 62", 'dark'),
  # arm: upper arm along the front, forearm across the shin, a soft hand
  'arm': ("M53 53 C55 60 57 67 60 73 C62 76.5 66.5 75 71 73 C74 71.5 78 70.5 79.5 71.5 C80.5 73 78.5 74.5 76 74 M73 75 C75.5 76.5 79 76 80 74.5", 'dark'),
  # the extended leg comes out from behind the hugged one and down to the floor
  'legDown': ("M57 90 C68 90.5 81 93 88 98 C94 103 100 110 106 115 C108 117 111 117 110 118.5 C108 119.5 104 119 102 118 C96 116 92 112 86 106 C79 100 71 96 64.5 94", 'lit'),
}

# ---------------------------------------------------------------- him-1
# Back view, standing, feet shoulder-width apart, hands clasped behind the
# head, elbows out: the V silhouette. Light from the left.
HIM = {
  # the back of the head with the hair mass; hands cradling the nape
  'head': ("M52 25 C50.5 14 58 11.5 60 11.5 C62 11.5 69.5 14 68 25", 'lit'),
  'hands': ("M50 23 C52 28 56 30.5 60 30 C64 30.5 68 28 70 23 M57.5 29.5 L60 26.5 L62.5 29.5", 'dark'),
  # arms: shoulder up and out to the elbow, forearm back to the head
  'armL': ("M42 40 C35 36 28 31 24 27 C21 24 23 20 27 21 C35 22 43 24 50 25", 'lit'),
  'armLu': ("M39 47 C34 43 29 38 25 33 C23 31 22 29 24 27", 'lit'),
  'armR': ("M78 40 C85 36 92 31 96 27 C99 24 97 20 93 21 C85 22 77 24 70 25", 'dark'),
  'armRu': ("M81 47 C86 43 91 38 95 33 C97 31 98 29 96 27", 'dark'),
  # trapezius from each deltoid up to the neck
  'shL': ("M40 42 C47 38 52 36 56 33", 'dark'),
  'shR': ("M80 42 C73 38 68 36 64 33", 'dark'),
  # lats to the waist, the hip, the outer thigh and calf; open at the foot
  'sideL': ("M39 47 C42 58 48 66 49 74 C50 80 46 84 46 90 C46 96 48 102 47 108 C46.5 112 45.5 115 45.5 117", 'lit'),
  'sideR': ("M81 47 C78 58 72 66 71 74 C70 80 74 84 74 90 C74 96 72 102 73 108 C73.5 112 74.5 115 74.5 117", 'dark'),
  # the cleft, the glute folds and the inner legs
  'cleft': ("M60 84 C60 87 60 90 60 92.5", 'dark'),
  'gluteL': ("M48 90.5 C51.5 88 56.5 89 59 92.5", 'dark'),
  'gluteR': ("M72 90.5 C68.5 88 63.5 89 61 92.5", 'dark'),
  'innerL': ("M55 97 C56 105 54.5 111 53.5 117", 'dark'),
  'innerR': ("M65 97 C64 105 65.5 111 66.5 117", 'dark'),
  # the spine, short and soft
  'spine': ("M60 44 C59 52 60 60 60 68", 'dark'),
}

STYLES = {
  'one':   'Одна линия',
  'light': 'Свет толщиной линии',
  'echo':  'Двойная линия',
}

def stroke(style, weight):
    if style == 'one':
        return 'stroke-width:1.35'
    if style == 'light':
        return {'lit': 'stroke-width:3.0', 'dark': 'stroke-width:1.1', 'prop': 'stroke-width:1.0;opacity:.55'}[weight]
    return 'stroke-width:1.3'

def figure(pose, style):
    parts = []
    for d, w in pose.values():
        op = ';opacity:.5' if w == 'prop' and style != 'light' else ''
        parts.append(f'<path d="{d}" style="{stroke(style, w)}{op}"/>')
    body = '\n'.join(parts)
    if style == 'echo':
        echo = '\n'.join(f'<path d="{d}" style="stroke-width:0.9"/>'
                         for d, w in pose.values() if w != 'prop')
        return (f'<g class="echo" transform="translate(60 70) rotate(-3) translate(-57 -70)">{echo}</g>'
                f'<g class="line">{body}</g>')
    return f'<g class="line">{body}</g>'

def svg(pose, style, dark=True):
    return (f'<svg viewBox="0 0 {W} {H}" class="{"dark" if dark else "light"}">' +
            figure(pose, style) + '</svg>')

CSS = """
body { margin:0; background:#1C0414; font-family: Inter, system-ui, sans-serif; color:#FBE9F4; padding: 18px; }
h1 { font-size: 15px; margin: 0 0 12px; font-weight: 600; opacity:.85 }
.grid { display:grid; grid-template-columns: repeat(3, 1fr); gap: 18px; }
.card { background: rgba(255,255,255,.05); border-radius:16px; padding: 14px 12px 10px; text-align:center; }
.card.white { background:#F6F1F3; color:#2A1220; }
svg { width: 100%; height:auto; display:block; }
path { fill:none; stroke:currentColor; stroke-linecap:round; stroke-linejoin:round; }
.echo path { stroke:#E86BB5; opacity:.55; }
.white .echo path { stroke:#C4256E; opacity:.45; }
.cap { font-size: 11px; opacity:.75; margin-top: 6px; }
.tag { font-size: 10px; opacity:.5; }
"""

def page():
    cards = []
    for key, pose, label in (('her', HER, 'Её поза 1 · Утренняя нега'), ('him', HIM, 'Его поза 1 · Статика')):
        for dark in (True, False):
            for i, (sk, sname) in enumerate(STYLES.items(), 1):
                cards.append(f'<div class="card {"" if dark else "white"}" id="{key}-{sk}-{"d" if dark else "w"}">'
                             f'{svg(pose, sk, dark)}<div class="cap">{label}</div>'
                             f'<div class="tag">вариант {i} · {sname}</div></div>')
    return f'<!doctype html><meta charset="utf-8"><title>Варианты рисунков</title><style>{CSS}</style>' \
           f'<h1>Мастер-класс: варианты стиля рисунков</h1><div class="grid">{"".join(cards)}</div>'

out = pathlib.Path(__file__).resolve().parent.parent / 'webapp' / 'art_variants.html'
out.write_text(page(), encoding='utf-8')
SHELL = "/opt/pw-browsers/chromium_headless_shell-1194/chrome-linux/headless_shell"
if "--png" in sys.argv and pathlib.Path(SHELL).exists():
    subprocess.run([SHELL, '--headless', '--no-sandbox', '--disable-gpu',
                    '--hide-scrollbars', '--window-size=1300,3200',
                    f'--screenshot={out.with_suffix(".png")}', out.as_uri()],
                   check=True, capture_output=True)
    print(out.with_suffix(".png"))

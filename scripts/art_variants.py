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

# ---------------------------------------------------------------- round two
# Three more takes, all in the single-line style: the drawing changes,
# the line does not.

# «Минимум»: the fewest strokes that still read, and air between them.
HER_MIN = {
  'crown': ("M62 24.5 C56 19.5 50 22 50 29 C48 36 46 44 46 52 C44.5 64 44 76 44 84 C44 89 43 92 45 94", 'lit'),
  'face': ("M64 25 C67 29 68.5 33 67.5 36 C66 38 65 41 62 42.5", 'dark'),
  'breast': ("M59 50 C61 54 64 57 63.5 61", 'dark'),
  'knee': ("M52 84 C58 74 64 64 68 57 C71 54 75 56 74 60 C73.5 70 73.5 80 73.5 90 C73.5 92 76 93 78 94", 'dark'),
  'arm': ("M55 55 C57 63 59 70 61.5 74 C64 76.5 70 74 76 72", 'dark'),
  'leg': ("M58 91 C70 91 82 94 89 99 C96 105 101 111 107 117", 'lit'),
}
HIM_MIN = {
  'head': ("M52 25 C50.5 14 58 11.5 60 11.5 C62 11.5 69.5 14 68 25", 'lit'),
  'hands': ("M50 23 C52 28 56 30.5 60 30 C64 30.5 68 28 70 23", 'dark'),
  'armL': ("M42 40 C35 36 28 31 24 27 C21 24 23 20 27 21 C35 22 43 24 50 25", 'lit'),
  'armR': ("M78 40 C85 36 92 31 96 27 C99 24 97 20 93 21 C85 22 77 24 70 25", 'dark'),
  'sideL': ("M39 47 C42 58 48 66 49 74 C50 80 46 84 46 90 C46 96 48 102 47 108 C46.5 112 45.5 115 45.5 117", 'lit'),
  'sideR': ("M81 47 C78 58 72 66 71 74 C70 80 74 84 74 90 C74 96 72 102 73 108 C73.5 112 74.5 115 74.5 117", 'dark'),
  'glutes': ("M48 90.5 C51.5 88 56.5 89 59 92.5 M72 90.5 C68.5 88 63.5 89 61 92.5", 'dark'),
}

# «Крупный план»: the full drawing, scaled up until the frame crops it.
HER_CLOSE_T = 'translate(8 0) scale(1.45) translate(-40 -22)'
HIM_CLOSE_T = 'translate(60 0) scale(1.35) translate(-60 -20)'

# «Непрерывная»: one path, the pen never lifts. Hers starts at the hip,
# climbs the hugged leg, runs down the foot and the extended leg to the
# floor, back along the mattress, up the spine, over the bun and the face,
# and finishes on the hand.
HER_FLOW = {
  'all': ("M52 84 C58 74 64 64 68 57 C70 54 74.5 55 74 59 C74 68 73.5 78 73.5 87.5"
          " C73.5 90.5 76 91.5 78 93 C79 94.5 76.5 95 74 94.5 C70.5 94 67 93.5 65.5 93"
          " C68 92.5 72 91.5 76 92 C82 93 87 96 89 99 C95 105 101 111 107 117"
          " C108 118.5 111 118 110 118.5 C108 119.5 104 119 102 118 C96 116 92 112 86 106"
          " C79 100 71 96 64.5 94 C58 93 51 93 45 93.5 C43 91 44 86 44 80 C44 72 45 60 46.5 50"
          " C47 46 49 40 52 33 C51.5 32 50.5 31.5 50 31 C49 34 45 34 44 31 C42 26 46 22 50 22"
          " C54 20 59 20 64 24 C67 27 66 31 66 33 C67 34 69 35 68 36 C66 37 66 38 66 39"
          " C65 41 63 42 61 42.5 C59 43 58 45 58 47.5 C57 53 60.5 56 64 59 C66.5 61.5 64.5 64.5 61.5 65"
          " C60 68 59.5 71 60.5 73 C62 76.5 66.5 75 71 73 C74 71.5 78 70.5 79.5 71.5"
          " C80.5 73 78.5 74.5 76 74 C74.5 74.5 74 76 76 76.5", 'dark'),
  'bed': ("M6 93 H43 M64 95.5 V118", 'prop'),
}
# His body is one path from the left foot up the leg and the lat, along the
# arm to the hands, and back down the other side to the right foot; the
# head with the shoulders is a second stroke, the spine a third.
HIM_FLOW = {
  'body': ("M45.5 117 C45.5 115 46.5 112 47 108 C48 102 46 96 46 90 C46 84 50 80 49 74"
           " C48 66 42 58 39 47 C34 43 29 38 25 33 C22 30 22 24 27 21 C35 22 43 24 50 25"
           " C52 28 56 30.5 60 30 C64 30.5 68 28 70 25 C77 24 85 22 93 21 C98 24 98 30 95 33"
           " C91 38 86 43 81 47 C78 58 72 66 71 74 C70 80 74 84 74 90 C74 96 72 102 73 108"
           " C73.5 112 74.5 115 74.5 117", 'dark'),
  'head': ("M40 42 C47 38 52 36 56 33 C51 30 50.5 14 60 11.5 C69.5 14 69 30 64 33"
           " C68 36 73 38 80 42", 'dark'),
  'spine': ("M60 44 C59 52 60 60 60 68 M60 84 C60 88 60 90 60 92.5 C57.5 89.5 52 88.5 48 90.5"
            " M60 92.5 C62.5 89.5 68 88.5 72 90.5", 'dark'),
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

def figure(pose, style, transform=''):
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
    t = f' transform="{transform}"' if transform else ''
    return f'<g class="line"{t}>{body}</g>'

def svg(pose, style, dark=True, transform=''):
    return (f'<svg viewBox="0 0 {W} {H}" class="{"dark" if dark else "light"}">' +
            figure(pose, style, transform) + '</svg>')

CSS = """
body { margin:0; background:#1C0414; font-family: Inter, system-ui, sans-serif; color:#FBE9F4; padding: 18px; }
h1 { font-size: 15px; margin: 0 0 12px; font-weight: 600; opacity:.85 }
.grid { display:grid; grid-template-columns: repeat(3, 1fr); gap: 18px; }
.card { background: rgba(255,255,255,.05); border-radius:16px; padding: 14px 12px 10px; text-align:center; }
.card.white { background:#F6F1F3; color:#2A1220; }
svg { width: 100%; height:auto; display:block; }
path { fill:none; stroke:currentColor; stroke-linecap:round; stroke-linejoin:round; vector-effect: non-scaling-stroke; }
.echo path { stroke:#E86BB5; opacity:.55; }
.white .echo path { stroke:#C4256E; opacity:.45; }
.cap { font-size: 11px; opacity:.75; margin-top: 6px; }
.tag { font-size: 10px; opacity:.5; }
"""

ROUND_TWO = (
  ('Минимум', 'min'),
  ('Крупный план', 'close'),
  ('Непрерывная', 'flow'),
)

def cards_for(key, label, full, mini, flow, close_t):
    out = []
    for dark in (True, False):
        for i, (sk, sname) in enumerate(STYLES.items(), 1):
            out.append(card(key, sk, dark, svg(full, sk, dark), label, i, sname))
        takes = ((mini, ''), (full, close_t), (flow, ''))
        for i, ((sname, sk), (pose, t)) in enumerate(zip(ROUND_TWO, takes, strict=True), 4):
            out.append(card(key, sk, dark, svg(pose, 'one', dark, t), label, i, sname))
    return out

def card(key, sk, dark, body, label, i, sname):
    return (f'<div class="card {"" if dark else "white"}" id="{key}-{sk}-{"d" if dark else "w"}">'
            f'{body}<div class="cap">{label}</div>'
            f'<div class="tag">вариант {i} · {sname}</div></div>')

def page():
    cards = cards_for('her', 'Её поза 1 · Утренняя нега', HER, HER_MIN, HER_FLOW, HER_CLOSE_T)
    cards += cards_for('him', 'Его поза 1 · Статика', HIM, HIM_MIN, HIM_FLOW, HIM_CLOSE_T)
    return f'<!doctype html><meta charset="utf-8"><title>Варианты рисунков</title><style>{CSS}</style>' \
           f'<h1>Мастер-класс: варианты стиля рисунков</h1><div class="grid">{"".join(cards)}</div>'

out = pathlib.Path(__file__).resolve().parent.parent / 'webapp' / 'art_variants.html'
out.write_text(page(), encoding='utf-8')
SHELL = "/opt/pw-browsers/chromium_headless_shell-1194/chrome-linux/headless_shell"
if "--png" in sys.argv and pathlib.Path(SHELL).exists():
    subprocess.run([SHELL, '--headless', '--no-sandbox', '--disable-gpu',
                    '--hide-scrollbars', '--window-size=1300,6400',
                    f'--screenshot={out.with_suffix(".png")}', out.as_uri()],
                   check=True, capture_output=True)
    print(out.with_suffix(".png"))

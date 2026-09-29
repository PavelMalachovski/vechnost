"""The twenty-nine pictures of the masterclass, one scene each.

Every scene is a photograph taken in a dark room with one lamp, the way the
masterclass teaches: the light stands where the card says, the camera where
the phone would be. The free steps (light, camera, editing) are shot in
lingerie, because nobody has confirmed their age to read them; the pose
steps sit behind the 18+ question and the paywall, and imply nudity without
showing any - the body is a smooth figure, and the pose and the shadow do
the covering.

Units are centimetres; x runs to the frame's right, y up, z toward the
camera. A body at yaw 0 faces the camera.
"""

from __future__ import annotations

import numpy as np

from .body import Body, Skeleton, orient
from .render import Blinds, Light, Material, Scene
from .sdf import ellipsoid, nrm, plane, round_box, round_cone, smin, ssub

I3 = np.eye(3)
UP = np.array([0.0, 1.0, 0.0])
TOWARD = np.array([0.0, 0.0, 1.0])

WARM = (1.0, 0.84, 0.66)
PINK = (1.0, 0.70, 0.60)
DAY = (1.0, 0.97, 0.92)
COLD = (0.84, 0.92, 1.0)

SKIN_F = Material((0.72, 0.53, 0.45), "skin", spec=0.28, shine=26)
SKIN_M = Material((0.64, 0.44, 0.34), "skin", spec=0.30, shine=26)
SKIN_WET = Material((0.60, 0.42, 0.33), "skin", spec=0.9, shine=60)
HAIR = Material((0.05, 0.035, 0.03), "hair", spec=0.4, shine=18)
HAIR_WET = Material((0.03, 0.025, 0.02), "hair", spec=0.9, shine=40)
OUTFITS = {
    "lingerie": Material((0.16, 0.025, 0.055), "cloth", spec=0.3, shine=28, sheen=0.3),
    "boxers": Material((0.03, 0.03, 0.035), "cloth", spec=0.1, shine=12, sheen=0.1),
    "jeans": Material((0.05, 0.065, 0.09), "cloth", spec=0.02, shine=6, sheen=0.12),
    "towel": Material((0.72, 0.72, 0.70), "cloth", sheen=0.05),
    "sheet": Material((0.78, 0.74, 0.70), "cloth", sheen=0.08),
}
WALL = Material((0.20, 0.17, 0.16))
FLOOR = Material((0.16, 0.11, 0.085), spec=0.06, shine=30)
LINEN = Material((0.58, 0.53, 0.50), "cloth", sheen=0.05)
WOOD = Material((0.10, 0.065, 0.05), spec=0.08, shine=24)
RUG = Material((0.20, 0.12, 0.12), "cloth", sheen=0.1)
CERAMIC = Material((0.80, 0.80, 0.80), spec=0.5, shine=60)
TILE = Material((0.30, 0.32, 0.34), spec=0.2, shine=40)
GLASS = Material((0.01, 0.01, 0.012), spec=0.8, shine=80)
BOOKS = [Material((0.25, 0.08, 0.08)), Material((0.07, 0.12, 0.18)), Material((0.28, 0.22, 0.12))]

STYLE = {"wrap": 0.35, "sss": (0.95, 0.40, 0.28), "rim": 2.2}
AMBIENT = (0.012, 0.009, 0.010)
POST = {
    "exposure": 1.0,
    "bloom": 0.12,
    "bloom_sigma": 0.02,
    "bloom_threshold": 1.0,
    "vignette": 0.55,
    "grain": 0.045,
    "lift": (0.085, 0.018, 0.062),
    "highlight_tint": (1.03, 1.0, 0.95),
}


class Shot:
    """A scene, the camera that photographs it and how it is developed."""

    def __init__(self, scene, eye, at, fov, up=(0.0, 1.0, 0.0), style=None, **post):
        self.scene = scene
        self.cam = {"eye": eye, "at": at, "fov": fov, "up": up}
        distance = float(np.linalg.norm(np.asarray(at) - np.asarray(eye)))
        self.post = {**POST, "dof": (distance, 180.0, 0.006), **post}
        self.style = {**STYLE, **(style or {})}
        self.split = False  # the edit card: colour on the left, b/w on the right


def person(pose, hair=None, outfit=None, bare=None, wet=False):
    body = Body(Skeleton(pose), hair=hair, outfit=outfit, bare=bare)
    if pose["sex"] == "f":
        skin = SKIN_F
    else:
        skin = SKIN_WET if wet else SKIN_M
    sc = Scene(body, skin, HAIR_WET if wet else HAIR, OUTFITS.get(outfit))
    sc.ambient = np.asarray(AMBIENT)
    return sc


# --- the room ----------------------------------------------------------


def floor(sc, mat=FLOOR):
    sc.add(lambda p: plane(p, UP, 0.0), mat, shadow=False)


def wall(sc, z, mat=WALL):
    """The wall behind, facing the camera at depth z."""
    sc.add(lambda p: plane(p, TOWARD, z), mat, shadow=False)


def box(sc, center, half, mat, r=1.0, R=I3, shadow=True):
    c = np.asarray(center, dtype=np.float64)
    sc.add(lambda p: round_box(p, c, R, half, r), mat, shadow)


def bed(sc, x0, x1, z0, z1, top=46.0, pillow=None, folds=0.0):
    cx, cz = (x0 + x1) / 2, (z0 + z1) / 2
    hx, hz = (x1 - x0) / 2, (z1 - z0) / 2
    c = np.array([cx, top - 10.0, cz])

    def mattress(p):
        d = round_box(p, c, I3, (hx, 10.0, hz), 6.0)
        if folds:
            # Rumpled linen: a slow ripple across the top.
            d = d + folds * np.sin(p[:, 0] * 0.21 + np.sin(p[:, 2] * 0.13) * 2.0) * np.sin(
                p[:, 2] * 0.17
            )
        return d

    sc.add(mattress, LINEN)
    box(sc, (cx, (top - 20.0) / 2, cz), (hx + 2, (top - 20.0) / 2, hz + 2), WOOD, r=2.0)
    if pillow is not None:
        box(sc, pillow, (15.0, 6.0, 26.0), LINEN, r=5.5)


def window(sc, wall_z, x0, x1, y0, y1, glow, power, radius=42.0):
    """A window in the back wall: bright panes, a frame, and the daylight."""
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    hx, hy = (x1 - x0) / 2, (y1 - y0) / 2
    for c, b in [
        ((cx, cy, wall_z + 2), (1.6, hy, 2.0)),
        ((cx, cy + hy * 0.08, wall_z + 2), (hx, 1.6, 2.0)),
        ((cx, y0 - 2, wall_z + 3), (hx + 4, 3.5, 4.0)),
    ]:
        box(sc, c, b, WOOD, r=0.8, shadow=False)

    def pane(p):
        inside = (np.abs(p[:, 0] - cx) < hx) & (np.abs(p[:, 1] - cy) < hy)
        return (inside & (p[:, 2] < wall_z + 0.5)).astype(np.float64)

    sc.glows.append((pane, np.asarray(glow, dtype=np.float64)))
    sc.lights.append(Light((cx, cy, wall_z + 16), DAY, power, radius))


def halo(sc, wall_z, cx, cy, sigma, colour):
    """Light spilling onto the wall behind a figure, from a lamp at its back."""

    def glow(p):
        on = p[:, 2] < wall_z + 0.5
        r2 = (p[:, 0] - cx) ** 2 + (p[:, 1] - cy) ** 2
        return on * np.exp(-r2 / (sigma * sigma)) * 0.95

    sc.glows.append((glow, np.asarray(colour, dtype=np.float64)))


def chair(sc, x, z, facing, seat=46.0, back=True):
    """A wooden chair whose sitter faces `facing` degrees (0 = the camera)."""
    t = np.radians(facing)
    fwd = np.array([np.sin(t), 0.0, np.cos(t)])
    side = np.array([np.cos(t), 0.0, -np.sin(t)])
    R = np.stack([side, UP, fwd], axis=1)
    c = np.array([x, seat - 2.0, z])
    box(sc, c, (21.0, 2.0, 20.0), WOOD, r=1.2, R=R)
    for sx in (-18.0, 18.0):
        for sz in (-17.0, 17.0):
            foot = c + side * sx + fwd * sz
            top = foot.copy()
            foot[1] = 0.0
            sc.add(lambda p, a=foot, b=top: round_cone(p, a, b, 1.6, 1.8), WOOD)
    if back:
        for sx in (-18.0, 18.0):
            a = c + side * sx - fwd * 18.0
            b = a + UP * 44.0 - fwd * 3.0
            sc.add(lambda p, a=a, b=b: round_cone(p, a, b, 1.8, 1.6), WOOD)
        rail = c - fwd * 21.0 + UP * 40.0
        box(sc, rail, (20.0, 4.0, 1.4), WOOD, r=1.0, R=R)


def wrap(sk, bare="r"):
    """A sheet wrapped round a seated body, knees and all, one shoulder out,
    its end pooled on the floor. A volume of its own round the skeleton: an
    outfit that follows the skin reads as tights."""
    trunk = (sk.P + sk.Rp[:, 1] * 2.0, sk.C + sk.Rc[:, 1] * 3.0, 17.5, 15.0)
    legs = []
    for side in "lr":
        h, k, a = sk.leg[side][:3]
        legs.append((h, k, 11.0, 8.5))
        legs.append((k, a, 8.5, 7.0))
    pool = np.array([sk.P[0] + 4.0, 1.0, sk.P[2] + 10.0])
    edge_n = nrm(sk.Rc[:, 1] + sk.Rc[:, 0] * (-0.6 if bare == "r" else 0.6))
    edge_at = sk.C + sk.Rc[:, 1] * 3.0

    def field(p):
        d = np.maximum(round_cone(p, *trunk), (p - edge_at) @ edge_n)
        for a, b, r1, r2 in legs:
            d = smin(d, round_cone(p, a, b, r1, r2), 6.0)
        floor_pool = ellipsoid(p, pool, I3, (58.0, 2.6, 50.0))
        d = smin(d, floor_pool, 8.0)
        folds = np.sin(p[:, 0] * 0.28 + p[:, 2] * 0.11) * np.sin(p[:, 1] * 0.2 + p[:, 2] * 0.23)
        return d + 0.3 * folds

    return field


def lamp(sc, x, y, z, colour, power, radius=18.0, shade=(2.4, 1.4, 1.1)):
    """A table lamp with fabric thrown over its shade: the shade glows."""
    a = np.array([x, y, z])
    sc.add(lambda p: round_cone(p, a, a + UP * 18.0, 5.0, 2.0), WOOD, shadow=False)
    s0, s1 = a + UP * 16.0, a + UP * 36.0

    def cloth(p):
        d = round_cone(p, s0, s1, 15.0, 10.0)
        return d + 0.8 * np.sin(np.arctan2(p[:, 2] - z, p[:, 0] - x) * 7.0) * np.clip(
            (s1[1] - p[:, 1]) / 20.0, 0, 1
        )

    sc.add(cloth, Material((1, 1, 1), "emit", emit=shade), shadow=False)
    sc.lights.append(Light(a + UP * 26.0, colour, power, radius))


# --- the scenes --------------------------------------------------------

SCENES = {}


def scene(key):
    def register(fn):
        SCENES[key] = fn
        return fn

    return register


def f_pose(pelvis, yaw=0.0, pitch=0.0, roll=0.0, chest=None, head=None, **limbs):
    return _pose("f", pelvis, yaw, pitch, roll, chest, head, limbs)


def m_pose(pelvis, yaw=0.0, pitch=0.0, roll=0.0, chest=None, head=None, **limbs):
    return _pose("m", pelvis, yaw, pitch, roll, chest, head, limbs)


def _pose(sex, pelvis, yaw, pitch, roll, chest, head, limbs):
    chest = chest if chest is not None else (yaw, pitch, -roll)
    head = head if head is not None else chest
    pose = {
        "sex": sex,
        "pelvis": pelvis,
        "pelvis_frame": orient(yaw, pitch, roll) if np.ndim(yaw) == 0 else yaw,
        "chest_frame": orient(*chest) if len(chest) == 3 and np.ndim(chest[0]) == 0 else chest,
        "head_frame": orient(*head) if len(head) == 3 and np.ndim(head[0]) == 0 else head,
    }
    pose.update(limbs)
    return pose


def rel(*pts):
    return ("rel", *pts)


def to(*pts):
    return ("to", *pts)


# Step 1 - light. Lingerie: these cards are free and ask no age.


@scene("light-side")
def light_side():
    pose = f_pose(
        (0.0, 95.0, 0.0), -20, 0, -4, chest=(-15, 0, 4), head=(-60, -5, 6),
        arm_r=rel((8, 20, -4), (-6, 26, -9), (-12, 22, -6)),
        arm_l=rel((6, -26, -3), (-2, -46, 6), (-4, -61, 9)),
        leg_l=rel((-3, -44, 10), (-2, -85, 4), (-1, -91, 22)),
    )  # fmt: skip
    sc = person(pose, outfit="lingerie")
    floor(sc)
    wall(sc, -140.0)
    sc.lights.append(Light((-175, 135, 20), WARM, 40000, 9, spot=((0, 125, 0), 22, 38)))
    return Shot(sc, (0, 128, 390), (0, 125, 0), 16.5, style={"wrap": 0.1, "rim": 0.6})


@scene("light-rim")
def light_rim():
    pose = f_pose(
        (0.0, 95.0, 0.0), -30, 0, 3, chest=(-35, 0, -3), head=(-85, -8, 0),
        arm_r=rel((13, 25, -2), (-6, 36, 0), (-14, 33, 2)),
        leg_l=rel((-2, -44, 8), (-1, -86, 2), (0, -92, 20)),
    )  # fmt: skip
    sc = person(pose, outfit="lingerie")
    floor(sc)
    wall(sc, -90.0)
    halo(sc, -90.0, 5.0, 128.0, 55.0, (1.6, 1.25, 0.95))
    sc.lights.append(Light((5, 128, -35), WARM, 9000, 6, spot=((0, 125, 10), 40, 70)))
    return Shot(sc, (45, 118, 380), (5, 115, 0), 26.0)


@scene("light-soft")
def light_soft():
    pose = f_pose(
        (10.0, 58.0, -10.0), -35, 0, 5, chest=(-40, -3, 0), head=(-70, 8, -6),
        leg_l=to((8, 50, 30), (43, 49, 18), (48, 47, 2)),
        leg_r=to((-12, 50, 24), (26, 48, 36), (40, 47, 44)),
        arm_l=to((28, 78, 4), (30, 54, 10), (31, 46, 22)),
        arm_r=to((-22, 100, -8), (-6, 118, -16), (4, 124, -14)),
    )  # fmt: skip
    sc = person(pose, outfit="lingerie")
    floor(sc)
    wall(sc, -120.0)
    bed(sc, -60.0, 110.0, -110.0, 40.0, folds=0.5)
    box(sc, (-95, 30, -60), (22, 30, 20), WOOD, r=1.5)
    lamp(sc, -95.0, 60.0, -60.0, PINK, 30000)
    return Shot(sc, (60, 85, 340), (-25, 70, -20), 32.0)


@scene("light-stripes")
def light_stripes():
    pose = f_pose(
        (0.0, 95.0, 0.0), 160, 0, 4, chest=(150, 0, -3), head=(100, -5, 0),
        arm_l=rel((12, -18, -8), (-2, -32, 2), (-6, -44, 6)),
        leg_r=rel((-3, -44, 10), (-2, -85, 4), (-1, -91, 22)),
    )  # fmt: skip
    sc = person(pose, outfit="lingerie")
    floor(sc)
    wall(sc, -120.0)
    blinds = Blinds((-90, 0, 0), (1, 0, 0), (0, 1, 0.15), 9.0, 0.5)
    sc.lights.append(
        Light((-240, 140, 40), WARM, 60000, 6, spot=((0, 120, 0), 18, 30), blinds=blinds)
    )
    return Shot(sc, (30, 120, 380), (0, 115, 0), 24.0)


# Step 2 - the camera.


@scene("camera-height")
def camera_height():
    pose = f_pose(
        (40.0, 95.0, 0.0), -90, 0, 3, chest=(-90, 0, -2), head=(-90, 2, 0),
        leg_l=rel((-2, -44, 8), (-1, -86, 2), (0, -92, 20)),
    )  # fmt: skip
    sc = person(pose, outfit="lingerie")
    floor(sc)
    wall(sc, -110.0)
    box(sc, (-70, 40, 0), (25, 40, 22), WOOD, r=1.5)
    for (cx, cy, hx, hy, hz), mat in zip(
        [(-70, 83, 12, 3, 9), (-71, 89, 11, 3, 8), (-70, 94.5, 10, 2.5, 8.5)], BOOKS, strict=True
    ):
        box(sc, (cx, cy, 0), (hx, hy, hz), mat, r=0.6)
    t = np.radians(-30.0)
    R = np.stack([[np.cos(t), 0, -np.sin(t)], [0, 1, 0], [np.sin(t), 0, np.cos(t)]], axis=1)
    phone = np.array([-68.0, 105.0, 0.0])
    box(sc, phone, (0.45, 8.0, 3.8), GLASS, r=0.4, R=R)

    def screen(p):
        q = (p - phone) @ R
        on = (q[:, 0] < -0.3) & (np.abs(q[:, 1]) < 7.2) & (np.abs(q[:, 2]) < 3.3)
        return on.astype(np.float64)

    sc.glows.append((screen, np.array([0.5, 0.75, 0.95])))
    sc.lights.append(Light((-150, 180, 150), WARM, 50000, 15))
    return Shot(sc, (0, 105, 520), (-10, 100, 0), 24.0)


@scene("camera-exposure")
def camera_exposure():
    pose = f_pose(
        (0.0, 58.0, 0.0), 35, -15, 0, chest=(35, -20, 0), head=(45, -20, 0),
        arm_l=to((8, 76, -30), (10, 52, -36), (11, 46, -50)),
        arm_r=to((-28, 76, -14), (-32, 52, -20), (-34, 46, -34)),
        leg_l=to((22, 55, 40), (26, 10, 48), (32, 2, 66)),
        leg_r=to((10, 55, 44), (14, 10, 54), (20, 2, 72)),
    )  # fmt: skip
    sc = person(pose, outfit="lingerie")
    floor(sc)
    wall(sc, -130.0)
    bed(sc, -150.0, 80.0, -120.0, 20.0, folds=0.4)
    sc.lights.append(Light((-170, 140, 60), WARM, 42000, 10, spot=((0, 80, 0), 25, 45)))
    return Shot(sc, (0, 80, 380), (0, 75, 0), 30.0, exposure=0.85)


@scene("camera-focus")
def camera_focus():
    pose = f_pose(
        (0.0, 95.0, 0.0), 30, 0, 0, chest=(28, 0, 0), head=(85, -10, 0),
    )  # fmt: skip
    sc = person(pose, outfit="lingerie")
    wall(sc, -120.0)
    sc.lights.append(Light((-120, 170, 60), WARM, 26000, 10))
    return Shot(sc, (-12, 149, 95), (3, 144, 5), 22.0, dof=(92.0, 16.0, 0.014))


# Step 3 - poses for her. Behind the 18+ question and the paywall.


@scene("her-1")
def her_1():
    pose = f_pose(
        (-12.0, 55.0, 0.0), ((1, 0.15, -0.2), (0, 1, 0)), 0, 0,
        chest=((1, -0.2, -0.3), (0.2, 1, 0)), head=((1, -0.35, 0.3), (0.35, 1, 0)),
        leg_r=to((7, 97, 7), (7, 54, 8), (26, 47, 8)),
        leg_l=to((31, 49.5, -10), (55, 17, -10), (66, 1.5, -10)),
        arm_r=to((3, 86, 17), (11.5, 84, 6), (10, 83, -9)),
        arm_l=to((1, 87, -5), (11.5, 83.5, 3), (12, 72, 8)),
    )  # fmt: skip
    sc = person(pose)
    floor(sc)
    wall(sc, -115.0)
    bed(sc, -142.0, 30.0, -100.0, 40.0, pillow=(-122.0, 52.0, -40.0), folds=0.4)
    sc.lights.append(Light((-175, 108, 95), WARM, 52000, 12, spot=((-10, 82, 0), 24, 44)))
    sc.lights.append(Light((170, 70, 260), (0.75, 0.62, 0.70), 2600, 60))
    return Shot(sc, (15, 78, 420), (15, 70, 0), 22.5)


@scene("her-2")
def her_2():
    pose = f_pose(
        (-5.0, 58.0, 0.0), ((0, 0.1, 1), (1, 0.12, 0)), 0, 0,
        chest=((0, -0.2, 1), (0.75, 0.66, 0)), head=((0.1, -0.05, 1), (0.5, 0.86, 0)),
        arm_l=to((46, 49, 15), (68, 48, 22), (82, 47, 20)),
        arm_r=to((34, 114, 14), (48, 108, 2), (52, 104, 10)),
        leg_l=to((-50, 49, 6), (-92, 49, 8), (-112, 47, 4)),
        leg_r=to((-25, 52, 32), (-55, 50, 6), (-72, 48, 0)),
    )  # fmt: skip
    sc = person(pose)
    floor(sc)
    wall(sc, -110.0)
    bed(sc, -150.0, 110.0, -80.0, 45.0, folds=0.5)
    sc.lights.append(Light((40, 230, -150), WARM, 60000, 20))
    sc.lights.append(Light((-150, 120, 250), (0.75, 0.62, 0.70), 3000, 60))
    return Shot(sc, (-10, 105, 390), (-10, 70, 0), 30.0)


@scene("her-3")
def her_3():
    pose = f_pose(
        (0.0, 95.0, 0.0), 180, 0, -5, chest=(180, -4, 4), head=(-125, -5, 0),
        arm_l=rel((10, 24, -4), (-4, 36, -8), (-12, 38, -9)),
        arm_r=rel((10, 24, -4), (-4, 36, -8), (-12, 38, -9)),
        leg_l=rel((-3, -44, -8), (-2, -85, -4), (-1, -91, -22)),
    )  # fmt: skip
    sc = person(pose, hair="held")
    floor(sc)
    wall(sc, -90.0)
    window(sc, -90.0, -95.0, -20.0, 60.0, 210.0, (4.0, 3.95, 3.8), 20000, 35.0)
    sc.lights.append(Light((0, 110, 400), (0.7, 0.6, 0.7), 3000, 80))
    return Shot(sc, (15, 120, 380), (-5, 115, 0), 29.0)


@scene("her-4")
def her_4():
    pose = f_pose(
        (0.0, 13.0, 0.0), 25, -15, 0, chest=(25, 20, 0), head=(-15, 28, 0),
        leg_l=to((14, 50, 24), (16, 7, 36), (22, 2, 55)),
        leg_r=to((2, 50, 30), (4, 7, 42), (12, 2, 60)),
        arm_l=to((26, 36, 22), (10, 36, 44), (-2, 36, 46)),
        arm_r=to((-12, 38, 36), (8, 34, 46), (20, 35, 44)),
    )  # fmt: skip
    sc = person(pose)
    floor(sc)
    wall(sc, -130.0)
    sc.add(wrap(sc.body.sk, bare="r"), OUTFITS["sheet"])
    sc.lights.append(Light((-180, 160, 80), (1.0, 0.92, 0.84), 45000, 45))
    return Shot(sc, (40, 75, 330), (0, 35, 0), 24.0)


@scene("her-5")
def her_5():
    pose = f_pose(
        (0.0, 95.0, 0.0), ((-1, -0.12, 0), (0, 1, 0)), 0, 0,
        chest=((-1, 0.2, 0), (0.16, 1, 0)), head=((-1, 0.22, 0), (-0.05, 1, 0)),
        leg_r=((-0.03, -1, 0), (0.02, -1, 0), (-1, -0.25, 0)),
        leg_l=((-0.342, -0.94, 0.02), (0.5, -0.866, 0), (-0.59, -0.81, 0)),
        arm_l=((0.12, -1, 0.12), (0.03, -1, 0.04), (-0.08, -1, 0)),
        arm_r=((0.15, -1, -0.12), (0.06, -1, -0.04), (0.0, -1, 0)),
    )  # fmt: skip
    sc = person(pose)
    floor(sc)
    wall(sc, -90.0)
    window(sc, -90.0, -42.0, 42.0, 32.0, 206.0, (4.0, 3.95, 3.8), 16000)
    sc.lights.append(Light((60, 90, 380), (0.7, 0.6, 0.7), 2200, 80))
    return Shot(sc, (-2, 100, 400), (-2, 96, 0), 28.5)


@scene("her-6")
def her_6():
    pose = f_pose(
        (0.0, 58.0, 20.0), ((0, 1, 0), (0, 0, -1)), 0, 0,
        chest=((0, 1, 0.1), (0, 0.05, -1)), head=((0.35, 0.94, 0), (0, 0, -1)),
        arm_l=rel((14, 22, 2), (-2, 30, -4), (-10, 26, -6)),
        arm_r=rel((14, 22, 2), (-2, 30, -4), (-10, 26, -6)),
        leg_l=rel((18, -30, 26), (4, -62, 4), (4, -80, 0)),
        leg_r=rel((-4, -28, 34), (-8, -64, 6), (-8, -82, 2)),
    )  # fmt: skip
    sc = person(pose)
    floor(sc)
    bed(sc, -120.0, 120.0, -130.0, 110.0)
    sc.lights.append(Light((-120, 260, -60), WARM, 55000, 30))
    return Shot(sc, (10, 290, 60), (0, 50, 0), 38.0, up=(0.0, 0.0, -1.0))


@scene("her-7")
def her_7():
    pose = f_pose(
        (0.0, 95.0, 0.0), 15, 0, 3, chest=(10, 0, -2), head=(-30, 10, 0),
        arm_l=to((21, 117, 7), (12, 136, 15), (6, 144, 9)),
        arm_r=to((-19, 127.5, 11), (7, 132, 17.5), (15, 133, 14.5)),
    )  # fmt: skip
    sc = person(pose)
    wall(sc, -120.0)
    sc.lights.append(Light((-150, 140, 60), WARM, 30000, 3))
    return Shot(sc, (0, 126, 330), (0, 125, 0), 10.0)


@scene("her-8")
def her_8():
    pose = f_pose(
        (0.0, 12.0, 0.0), 0, -5, 0, chest=(0, 55, 0), head=(12, 75, 8),
        leg_l=to((30, 28, 30), (-8, 8, 42), (-20, 4, 34)),
        leg_r=to((-30, 28, 30), (8, 10, 46), (20, 6, 38)),
        arm_l=to((30, 33, 31), (4, 34, 38), (-10, 34, 36)),
        arm_r=to((-30, 33, 31), (-4, 36, 40), (10, 36, 38)),
    )  # fmt: skip
    sc = person(pose)
    floor(sc)
    wall(sc, -140.0)
    box(sc, (0, 0.6, 5), (70, 0.6, 60), RUG, r=0.5, shadow=False)
    sc.lights.append(Light((0, 150, -140), WARM, 30000, 15))
    sc.lights.append(Light((0, 110, 400), (0.7, 0.6, 0.7), 2000, 80))
    return Shot(sc, (0, 90, 300), (0, 36, 10), 22.0)


@scene("her-9")
def her_9():
    pose = f_pose(
        (0.0, 95.0, 0.0), -35, 0, -4, chest=(-30, 0, 3), head=(-60, -6, 0),
        arm_l=rel((13, -17, -6), (-4, -31, 1), (-9, -36, 5)),
        arm_r=rel((13, -17, -6), (-4, -31, 1), (-9, -36, 5)),
        leg_l=rel((-3, -44, 10), (-2, -85, 4), (-1, -91, 22)),
    )  # fmt: skip
    sc = person(pose)
    floor(sc)
    wall(sc, -110.0)
    blinds = Blinds((-80, 0, 0), (1, 0, 0), (0, 1, 0.12), 8.0, 0.55)
    sc.lights.append(
        Light((-230, 150, 60), WARM, 70000, 5, spot=((0, 120, 0), 20, 32), blinds=blinds)
    )
    return Shot(sc, (10, 118, 400), (0, 112, 0), 26.0)


@scene("her-10")
def her_10():
    pose = f_pose(
        (0.0, 58.0, 0.0), 180, -5, 0, chest=(180, 20, 0), head=(165, 55, 0),
        leg_l=rel((16, -8, 38), (18, -48, 34), (18, -54, 48)),
        leg_r=rel((16, -8, 38), (18, -48, 34), (18, -54, 48)),
        arm_l=rel((12, -14, 18), (-10, -12, 24), (-20, -11, 22)),
        arm_r=rel((12, -14, 18), (-10, -12, 24), (-20, -11, 22)),
    )  # fmt: skip
    sc = person(pose)
    floor(sc)
    wall(sc, -130.0)
    chair(sc, 0.0, -5.0, 0.0)
    sc.lights.append(Light((-200, 140, 20), WARM, 50000, 8, spot=((0, 95, 0), 22, 40)))
    return Shot(sc, (20, 105, 360), (0, 85, 0), 25.0)


# Step 4 - poses for him.


@scene("him-1")
def him_1():
    pose = m_pose(
        (0.0, 102.5, 0.0), ((0, 0, -1), (0, 1, 0)), 0, 0,
        chest=((0, 0.05, -1), (0, 1, 0.02)), head=((0, -0.06, -1), (0, 1, 0)),
        leg_l=((-0.15, -0.99, 0), (-0.14, -0.99, 0), (-0.25, -0.3, -1)),
        leg_r=((0.15, -0.99, 0), (0.14, -0.99, 0), (0.25, -0.3, -1)),
        arm_l=to((-44, 172, 6), (-14, 176, 12), (0, 176, 12.5)),
        arm_r=to((44, 172, 6), (14, 176, 12), (0, 176, 12.5)),
    )  # fmt: skip
    sc = person(pose)
    floor(sc)
    wall(sc, -160.0)
    sc.lights.append(Light((-240, 160, 30), (1.0, 0.86, 0.68), 86000, 5, spot=((0, 150, 0), 8, 16)))
    sc.lights.append(Light((200, 120, 160), (0.7, 0.62, 0.72), 3000, 60))
    return Shot(sc, (0, 104, 420), (0, 98, 0), 27.5)


@scene("him-2")
def him_2():
    pose = m_pose(
        (0.0, 14.0, -26.0), 15, -20, 0, chest=(15, -10, 0), head=(30, 25, 5),
        leg_l=to((22, 10, 18), (40, 7, 60), (44, 21, 79)),
        leg_r=to((-10, 52, -6), (-8, 9, 18), (-6, 2, 40)),
        arm_r=to((-10, 56, -4), (0, 76, -22), (4, 84, -20)),
        arm_l=to((20, 34, -36), (26, 16, -6), (28, 12, 10)),
    )  # fmt: skip
    sc = person(pose)
    floor(sc)
    wall(sc, -40.0)
    sc.lights.append(Light((10, 240, 10), WARM, 70000, 8, spot=((0, 70, -25), 14, 30)))
    return Shot(sc, (70, 75, 330), (5, 55, -20), 27.0)


@scene("him-3")
def him_3():
    pose = m_pose(
        (0.0, 103.0, 0.0), -8, 0, 0, chest=(-5, 0, 0), head=(20, -4, 0),
        arm_l=to((24, 125, -9), (12, 104, -17), (3, 104, -16)),
        arm_r=to((-22, 125, -12), (-9, 104, -18), (-2, 104, -16)),
    )  # fmt: skip
    sc = person(pose, outfit="jeans")
    floor(sc)
    wall(sc, -140.0)
    sc.lights.append(Light((190, 140, 40), WARM, 55000, 5, spot=((0, 120, 0), 18, 32)))
    return Shot(sc, (0, 125, 430), (0, 118, 0), 20.0)


@scene("him-4")
def him_4():
    pose = m_pose(
        (0.0, 103.0, 0.0), 0, 0, 0, chest=(0, -6, 0), head=(0, -10, 0),
        arm_l=rel((4, 30, 1), (6, 56, 1), (-10, 70, 0)),
        arm_r=rel((4, 30, 1), (6, 56, 1), (-10, 70, 0)),
    )  # fmt: skip
    sc = person(pose, outfit="boxers")
    floor(sc)
    wall(sc, -140.0)
    sc.lights.append(Light((60, 190, 330), WARM, 90000, 45))
    return Shot(sc, (0, 135, 470), (0, 130, 0), 25.0)


@scene("him-5")
def him_5():
    pose = m_pose(
        (0.0, 103.0, 0.0), 90, 0, 0, chest=(90, -3, 0), head=(90, -5, 0),
        leg_r=rel((1, -44, 10), (0, -87, 6), (1, -93, 26)),
    )  # fmt: skip
    sc = person(pose)
    floor(sc)
    wall(sc, -100.0)
    halo(sc, -100.0, 0.0, 120.0, 70.0, (3.0, 2.8, 2.6))
    sc.lights.append(Light((-20, 130, -95), DAY, 25000, 50))
    return Shot(sc, (0, 110, 420), (0, 105, 0), 28.0)


@scene("him-6")
def him_6():
    pose = m_pose(
        (0.0, 100.0, 25.0), 180, 15, 0, chest=(180, 35, 0), head=(180, 50, 0),
        arm_l=rel((6, 22, 22), (4, 36, 44), (4, 44, 56)),
        arm_r=rel((6, 22, 22), (4, 36, 44), (4, 44, 56)),
        leg_l=rel((2, -44, -12), (3, -88, -16), (3, -95, 6)),
        leg_r=rel((2, -44, -12), (3, -88, -16), (3, -95, 6)),
    )  # fmt: skip
    sc = person(pose)
    floor(sc)
    wall(sc, -40.0)
    sc.lights.append(Light((-210, 150, 60), WARM, 60000, 6, spot=((0, 130, 0), 20, 36)))
    return Shot(sc, (120, 130, 400), (0, 115, 0), 27.0)


@scene("him-7")
def him_7():
    pose = m_pose(
        (0.0, 60.0, 6.0), 15, -5, 0, chest=(15, 42, 0), head=(15, 62, 0),
        leg_l=to((20, 53, 51), (21, 6, 53), (26, 1, 76)),
        leg_r=to((-6, 53, 56), (-5, 6, 58), (0, 1, 81)),
        arm_l=to((24, 66, 40), (14, 56, 56), (10, 44, 60)),
        arm_r=to((-8, 68, 46), (6, 56, 60), (8, 44, 62)),
    )  # fmt: skip
    sc = person(pose, outfit="towel", wet=True)
    floor(sc, TILE)
    wall(sc, -70.0, TILE)
    outer = np.array([0.0, 26.0, -30.0])
    inner = np.array([0.0, 36.0, -30.0])

    def tub(p):
        d = round_box(p, outer, I3, (80.0, 26.0, 36.0), 8.0)
        return ssub(round_box(p, inner, I3, (72.0, 26.0, 29.0), 10.0), d, 2.0)

    sc.add(tub, CERAMIC)
    sc.lights.append(Light((-90, 210, 170), COLD, 70000, 25))
    sc.lights.append(Light((80, 90, 260), (0.6, 0.65, 0.7), 12000, 70))
    return Shot(sc, (60, 95, 330), (0, 70, 0), 29.0)


@scene("him-8")
def him_8():
    pose = m_pose(
        (0.0, 20.0, -60.0), ((0, -1, 0.05), (0, 0.15, 1)), 0, 0,
        chest=((0, -0.94, 0.34), (0, 0.34, 0.94)), head=((0, 0.1, 1), (0, 1, -0.1)),
        arm_l=to((18, 3.5, -2), (6, 3.5, 22), (-4, 3, 32)),
        arm_r=to((-18, 3.5, -2), (-6, 3.5, 22), (4, 3, 32)),
        leg_l=to((10, 7, -108), (11, 5, -155), (11, 1, -178)),
        leg_r=to((-10, 7, -108), (-11, 5, -155), (-11, 1, -178)),
    )  # fmt: skip
    sc = person(pose)
    floor(sc)
    wall(sc, -200.0)
    box(sc, (0, 0.6, -40), (90, 0.6, 120), RUG, r=0.5, shadow=False)
    sc.lights.append(Light((-170, 120, -40), DAY, 45000, 40))
    sc.lights.append(Light((60, 70, 320), (0.7, 0.6, 0.7), 2500, 60))
    return Shot(sc, (15, 45, 300), (0, 32, 0), 22.0)


@scene("him-9")
def him_9():
    pose = m_pose(
        (0.0, 60.0, 0.0), 90, -5, 0, chest=(90, 3, 0), head=(70, 0, 0),
        leg_l=rel((0, -4, 46), (0, -48, 50), (0, -54, 70)),
        leg_r=rel((-6, 6, 44), (-14, -26, 64), (-16, -34, 82)),
        arm_r=rel((2, -26, 8), (-2, -36, 30), (-4, -38, 44)),
    )  # fmt: skip
    sc = person(pose)
    floor(sc)
    wall(sc, -130.0)
    chair(sc, 0.0, 0.0, 90.0, seat=48.0)
    sc.lights.append(Light((160, 190, 120), (1.0, 0.72, 0.48), 50000, 6, spot=((0, 80, 0), 15, 28)))
    return Shot(sc, (-20, 90, 400), (5, 78, 0), 26.0)


@scene("him-10")
def him_10():
    pose = m_pose(
        (0.0, 103.0, 0.0), 90, 0, 0, chest=(90, -2, 0), head=(90, 5, 0),
        arm_l=to((6, 133, -20), (16, 141, -2), (13, 142, 12)),
        arm_r=to((6, 130, 20), (15, 138, 2), (12, 140, -12)),
    )  # fmt: skip
    sc = person(pose)
    wall(sc, -140.0)
    sc.lights.append(Light((170, 190, 60), WARM, 50000, 3))
    return Shot(sc, (0, 137, 330), (0, 136, 0), 11.0)


# Step 5 - editing and safety. Lingerie again: free, and no age asked.


@scene("edit-bw")
def edit_bw():
    pose = f_pose(
        (-12.0, 58.0, 0.0), 70, -5, 0, chest=(60, 0, 0), head=(40, 12, 0),
        leg_l=to((32, 52, -6), (36, 10, 0), (44, 2, 16)),
        leg_r=to((30, 60, 8), (46, 26, 22), (60, 20, 30)),
        arm_l=to((6, 80, -10), (24, 64, 2), (32, 62, 8)),
        arm_r=to((-10, 80, 18), (20, 66, 12), (30, 63, 8)),
    )  # fmt: skip
    sc = person(pose, outfit="lingerie")
    floor(sc)
    wall(sc, -120.0)
    bed(sc, -160.0, -2.0, -100.0, 40.0, folds=0.4)
    sc.lights.append(Light((-150, 130, 150), WARM, 45000, 10))
    shot = Shot(sc, (-4, 85, 380), (-4, 80, 0), 29.0)
    shot.split = True
    return shot


@scene("edit-privacy")
def edit_privacy():
    pose = f_pose(
        (0.0, 95.0, 0.0), 20, 0, -3, chest=(15, 0, 3), head=(40, -5, 4),
        arm_l=rel((12, -14, 6), (-4, 4, 12), (-10, 10, 10)),
    )  # fmt: skip
    sc = person(pose, outfit="lingerie")
    wall(sc, -120.0)
    sc.lights.append(Light((-160, 170, 100), WARM, 45000, 12))
    return Shot(sc, (0, 140, 400), (0, 138, 0), 15.0)

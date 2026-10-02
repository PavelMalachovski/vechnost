"""The twenty-eight pictures of the masterclass, one scene each.

Every scene is a photograph taken in a dark room with one lamp, the way the
masterclass teaches: the light stands where the card says, the camera where
the phone would be. The free steps (light, camera, editing) are shot in
lingerie, because nobody has confirmed their age to read them; the pose
steps sit behind the 18+ question and the paywall and imply nudity without
showing any anatomy - the pose, a sheet or the shadow does the covering.
Every pose for him is shot in trousers (jeans in «Контраст», which names
them): the poses are about his back, shoulders and arms.

Units are centimetres; x runs to the frame's right, y up, z toward the
camera. A body at yaw 0 faces the camera. Poses are the old drawings'
(skeleton.pose); the real body reaches for their joints with its own
proportions.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import materials as M
from . import props as P
from .outfits import shoulder_towel, wrapped_sheet
from .people import Person
from .skeleton import pose, rel, to
from .studio import COLD, DAY, FILL, PINK, WARM, area, camera, point, reset, spot


@dataclass
class Shot:
    """How a scene is developed: its exposure (stops), and whether it is
    the editing card, colour on the left and black and white on the right."""

    exposure: float = 0.0
    split: bool = False


SCENES = {}


def scene(key):
    def register(fn):
        SCENES[key] = fn
        return fn

    return register


def f_pose(pelvis, yaw=0.0, pitch=0.0, roll=0.0, chest=None, head=None, **limbs):
    return pose("f", pelvis, yaw, pitch, roll, chest, head, **limbs)


def m_pose(pelvis, yaw=0.0, pitch=0.0, roll=0.0, chest=None, head=None, **limbs):
    return pose("m", pelvis, yaw, pitch, roll, chest, head, **limbs)


def bedroom(wall_z, x0, x1, z0, z1, top=46.0, pillow=None, duvet=None):
    """Floor, back wall, a made bed; a pillow at `pillow` and a duvet
    dropped at `duvet` ((x, z) centre, (w, d) size) if asked for."""
    P.floor()
    P.wall(wall_z)
    frame, mattress, linen = P.bed(x0, x1, z0, z1, top=top)
    solid = [mattress]
    if pillow is not None:
        solid.append(
            P.pillow(
                (pillow[0], top + 14.0, pillow[1]),
                linen,
                half=(24.0, 9.0, 34.0),
                rest_on=[mattress],
            )
        )
    if duvet is not None:
        (cx, cz), size = duvet
        cover = P.mat("duvet", M.fabric, "duvet", (0.62, 0.58, 0.55), 0.55, 0.92, 900.0, 0.1)
        sheet = P.cloth_sheet((cx, top + 22.0, cz), size, cover, noise=7.0, seed=4)
        P.drape([sheet], [*solid, frame], frames=60, bend=0.08, mass=0.5)
        solid.append(sheet)
    return [frame, *solid]


# Step 1 - light. Lingerie: these cards are free and ask no age.


@scene("light-side")
def light_side():
    reset()
    P.floor()
    P.wall(-140.0)
    Person(
        f_pose(
            (0.0, 95.0, 0.0), -20, 0, -4, chest=(-15, 0, 4), head=(-60, -5, 6),
            arm_r=rel((8, 20, -4), (-6, 26, -9), (-12, 22, -6)),
            arm_l=rel((6, -26, -3), (-2, -46, 6), (-4, -61, 9)),
            leg_l=rel((-3, -44, 10), (-2, -85, 4), (-1, -91, 22)),
        ),
        outfit="lingerie", ground=0.0,
    )  # fmt: skip
    spot((-175, 135, 20), (0, 125, 0), WARM, 360.0, radius=10.0, cone=40.0, blend=0.4, name="key")
    camera((0, 128, 390), (0, 125, 0), 16.5, fstop=2.8)
    return Shot()


@scene("light-rim")
def light_rim():
    reset()
    P.floor()
    P.wall(-90.0)
    Person(
        f_pose(
            (0.0, 95.0, 0.0), -30, 0, 3, chest=(-35, 0, -3), head=(-85, -8, 0),
            arm_r=rel((13, 25, -2), (-6, 36, 0), (-14, 33, 2)),
            leg_l=rel((-2, -44, 8), (-1, -86, 2), (0, -92, 20)),
        ),
        outfit="lingerie", ground=0.0,
    )  # fmt: skip
    # The lamp stands behind her and lights the wall and her outline, never her front.
    spot((30, 140, -45), (0, 125, 10), WARM, 900.0, radius=6.0, cone=80.0, blend=0.6, name="rim")
    point((5, 128, -60), (1.0, 0.78, 0.58), 60.0, radius=8.0, name="glow")
    area((150, 110, 350), (0, 110, 0), FILL, 5.0, size=200.0, name="fill")
    camera((45, 118, 380), (5, 115, 0), 26.0, fstop=2.8, focus=(0, 125, 0))
    return Shot()


@scene("light-soft")
def light_soft():
    reset()
    solid = bedroom(-120.0, -60.0, 110.0, -110.0, 40.0, pillow=(80.0, -80.0))
    P.box((-95, 30, -60), (22, 30, 20), P.mat("wood", M.wood), bevel=1.5, name="nightstand")
    P.lamp(-95.0, 60.0, -60.0, PINK, watts=240.0, glow=6.0)
    Person(
        f_pose(
            (10.0, 58.0, -10.0), -35, 0, 5, chest=(-40, -3, 0), head=(-70, 8, -6),
            leg_l=to((8, 50, 30), (43, 49, 18), (48, 47, 2)),
            leg_r=to((-12, 50, 24), (26, 48, 36), (40, 47, 44)),
            arm_l=to((28, 78, 4), (30, 54, 10), (31, 46, 22)),
            arm_r=to((-22, 100, -8), (-6, 118, -16), (4, 124, -14)),
        ),
        outfit="lingerie", colliders=solid,
    )  # fmt: skip
    # The shaded lamp lights her from behind; a little warmth from the
    # camera's side keeps the lingerie from melting into her shadow.
    area((120, 110, 260), (0, 95, -10), PINK, 30.0, size=120.0, name="fill")
    camera((60, 85, 340), (-25, 70, -20), 32.0, fstop=2.8, focus=(5, 90, -10))
    return Shot()


@scene("light-stripes")
def light_stripes():
    reset()
    P.floor()
    P.wall(-120.0)
    Person(
        f_pose(
            (0.0, 95.0, 0.0), 160, 0, 4, chest=(150, 0, -3), head=(100, -5, 0),
            arm_l=rel((12, -18, -8), (-2, -32, 2), (-6, -44, 6)),
            leg_r=rel((-3, -44, 10), (-2, -85, 4), (-1, -91, 22)),
        ),
        outfit="lingerie", ground=0.0,
    )  # fmt: skip
    lamp = (-240, 140, 40)
    P.blinds(lamp, (0, 120, 0), period=9.0, duty=0.5, gap=0.55)
    spot(lamp, (0, 120, 0), WARM, 900.0, radius=1.5, cone=26.0, blend=0.3, name="key")
    camera((30, 120, 380), (0, 115, 0), 24.0, fstop=2.8)
    return Shot()


# Step 2 - the camera.


@scene("camera-height")
def camera_height():
    reset()
    P.floor()
    P.wall(-110.0)
    P.box((-70, 40, 0), (25, 40, 22), P.mat("wood", M.wood), bevel=1.5, name="nightstand")
    top = P.books(-70.0, 80.0, 0.0)
    P.phone((-68.0, top + 8.0, 0.0), yaw=-30.0)
    Person(
        f_pose(
            (40.0, 95.0, 0.0), -90, 0, 3, chest=(-90, 0, -2), head=(-90, 2, 0),
            leg_l=rel((-2, -44, 8), (-1, -86, 2), (0, -92, 20)),
        ),
        outfit="lingerie", ground=0.0,
    )  # fmt: skip
    spot((-150, 180, 150), (20, 110, 0), WARM, 420.0, radius=10.0, cone=40.0, blend=0.6, name="key")
    camera((0, 105, 520), (-10, 100, 0), 24.0, fstop=4.0, focus=(20, 100, 0))
    return Shot()


@scene("camera-exposure")
def camera_exposure():
    reset()
    solid = bedroom(-130.0, -150.0, 80.0, -120.0, 20.0)
    Person(
        f_pose(
            (0.0, 58.0, 0.0), 35, -15, 0, chest=(35, -20, 0), head=(45, -20, 0),
            arm_l=to((8, 76, -30), (10, 52, -36), (11, 46, -50)),
            arm_r=to((-28, 76, -14), (-32, 52, -20), (-34, 46, -34)),
            leg_l=to((22, 55, 40), (26, 10, 48), (32, 2, 66)),
            leg_r=to((10, 55, 44), (14, 10, 54), (20, 2, 72)),
        ),
        outfit="lingerie", colliders=solid,
    )  # fmt: skip
    spot((-170, 140, 60), (0, 80, 0), WARM, 380.0, radius=5.0, cone=50.0, blend=0.5, name="key")
    camera((0, 80, 380), (0, 75, 0), 30.0, fstop=2.8)
    return Shot(exposure=-0.4)


@scene("camera-focus")
def camera_focus():
    reset()
    P.wall(-120.0)
    Person(
        f_pose((0.0, 95.0, 0.0), 30, 0, 0, chest=(28, 0, 0), head=(85, -10, 0)),
        outfit="lingerie", ground=0.0,
    )  # fmt: skip
    area((-120, 170, 60), (0, 140, 0), WARM, 350.0, size=25.0, name="key")
    camera((-12, 149, 95), (3, 144, 5), 22.0, fstop=1.6, focus=(-2, 139, 6))
    return Shot()


# Step 3 - poses for her. Behind the 18+ question and the paywall.


@scene("her-1")
def her_1():
    reset()
    solid = bedroom(
        -115.0,
        -142.0,
        30.0,
        -100.0,
        40.0,
        pillow=(-118.0, -55.0),
        duvet=((-88.0, -38.0), (100.0, 80.0)),
    )
    Person(
        f_pose(
            (-12.0, 55.0, 0.0), ((1, 0.15, -0.2), (0, 1, 0)), 0, 0,
            chest=((1, -0.2, -0.3), (0.2, 1, 0)), head=((1, -0.35, 0.3), (0.35, 1, 0)),
            leg_r=to((7, 97, 7), (7, 54, 8), (26, 47, 8)),
            leg_l=to((31, 49.5, -10), (55, 17, -10), (66, 1.5, -10)),
            arm_r=to((3, 86, 17), (11.5, 84, 6), (10, 83, -9)),
            arm_l=to((1, 87, -5), (11.5, 83.5, 3), (12, 72, 8)),
        ),
        colliders=solid,
    )  # fmt: skip
    spot((-175, 108, 95), (-10, 82, 0), WARM, 260.0, radius=6.0, cone=46.0, blend=0.55, name="key")
    area((170, 90, 260), (0, 70, 0), FILL, 40.0, size=180.0, name="fill")
    camera((15, 78, 420), (15, 70, 0), 22.5, fstop=2.8, focus=(0, 80, 0))
    return Shot()


@scene("her-2")
def her_2():
    reset()
    solid = bedroom(-110.0, -150.0, 110.0, -80.0, 45.0, pillow=(85.0, -40.0))
    Person(
        # On her right side, her back to the camera: the line from the waist
        # over the hip is the horizon the card is named for.
        f_pose(
            (-5.0, 58.0, 0.0), ((0, 0.1, -1), (1, 0.12, 0)), 0, 0,
            chest=((0, -0.2, -1), (0.75, 0.66, 0)), head=((0.1, -0.05, -1), (0.5, 0.86, 0)),
            arm_r=to((46, 49, -15), (68, 48, -22), (82, 47, -20)),
            arm_l=to((34, 114, -14), (48, 108, -2), (52, 104, -10)),
            leg_r=to((-50, 49, -6), (-92, 49, -8), (-112, 47, -4)),
            leg_l=to((-25, 52, -32), (-55, 50, -6), (-72, 48, 0)),
        ),
        colliders=solid,
    )  # fmt: skip
    spot((40, 230, -150), (0, 70, 0), WARM, 1500.0, radius=12.0, cone=60.0, blend=0.6, name="key")
    spot((-120, 160, -120), (-20, 70, 0), WARM, 500.0, radius=6.0, cone=50.0, blend=0.6, name="rim")
    area((-150, 120, 250), (0, 70, 0), FILL, 20.0, size=180.0, name="fill")
    camera((-10, 105, 390), (-10, 70, 0), 30.0, fstop=2.8, focus=(10, 80, 0))
    return Shot(exposure=0.5)


@scene("her-3")
def her_3():
    reset()
    P.floor()
    P.wall(-90.0)
    P.window(-90.0, -95.0, -20.0, 60.0, 210.0, watts=500.0, glow=10.0)
    Person(
        f_pose(
            (0.0, 95.0, 0.0), 180, 0, -5, chest=(180, -4, 4), head=(-125, -5, 0),
            arm_l=rel((10, 24, -4), (-4, 36, -8), (-12, 38, -9)),
            arm_r=rel((10, 24, -4), (-4, 36, -8), (-12, 38, -9)),
            # A hand's width between the thighs, as drawn: pressed together
            # they overlap, and the window shines through the seam.
            leg_l=rel((3, -44, -8), (5, -85, -4), (6, -91, -22)),
            leg_r=rel((3, -45, 0.5), (4, -87, -1.0), (5, -93, 18.0)),
        ),
        hair="held", ground=0.0,
    )  # fmt: skip
    area((0, 110, 400), (0, 110, 0), FILL, 12.0, size=200.0, name="fill")
    camera((15, 120, 380), (-5, 115, 0), 29.0, fstop=2.8)
    return Shot()


@scene("her-4")
def her_4():
    reset()
    ground = P.floor()
    P.wall(-130.0)
    her = Person(
        f_pose(
            (0.0, 13.0, 0.0), 25, -15, 0, chest=(25, 20, 0), head=(-50, 30, 0),
            leg_l=to((14, 50, 24), (16, 7, 36), (22, 2, 55)),
            leg_r=to((2, 50, 30), (4, 7, 42), (12, 2, 60)),
            arm_l=to((26, 36, 22), (10, 36, 44), (-2, 36, 46)),
            arm_r=to((-12, 38, 36), (8, 34, 46), (20, 35, 44)),
        ),
        ground=0.0,
    )  # fmt: skip
    wrapped_sheet(her.h, bare="r", colliders=[ground])
    # Soft light, as the card says, from high on the left, as drawn; she
    # looks down toward it, away from the phone.
    area((-160, 190, 60), (0, 45, 0), WARM, 330.0, size=90.0, name="key")
    area((150, 120, -100), (0, 50, 0), WARM, 60.0, size=60.0, name="rim")
    camera((40, 75, 330), (0, 35, 0), 24.0, fstop=2.8, focus=(5, 45, 20))
    return Shot()


@scene("her-5")
def her_5():
    reset()
    P.floor(M.floorboards((0.07, 0.045, 0.032), gloss=0.22, figure=0.12))
    P.wall(-90.0)
    P.window(-90.0, -42.0, 42.0, 32.0, 206.0, watts=300.0, glow=14.0)
    Person(
        f_pose(
            (0.0, 95.0, 0.0), ((-1, -0.12, 0), (0, 1, 0)), 0, 0,
            chest=((-1, 0.2, 0), (0.16, 1, 0)), head=((-1, 0.22, 0), (-0.05, 1, 0)),
            leg_r=((-0.03, -1, 0), (0.02, -1, 0), (-1, -0.25, 0)),
            leg_l=((-0.342, -0.94, 0.02), (0.5, -0.866, 0), (-0.59, -0.81, 0)),
            arm_l=((0.12, -1, 0.12), (0.03, -1, 0.04), (-0.08, -1, 0)),
            arm_r=((0.15, -1, -0.12), (0.06, -1, -0.04), (0.0, -1, 0)),
        ),
        ground=0.0,
    )  # fmt: skip
    area((60, 100, 380), (0, 100, 0), FILL, 6.0, size=200.0, name="fill")
    camera((-2, 100, 400), (-2, 96, 0), 28.5, fstop=2.8, focus=(0, 110, 0))
    return Shot()


@scene("her-6")
def her_6():
    reset()
    solid = bedroom(-200.0, -100.0, 100.0, -175.0, 85.0)
    her = Person(
        f_pose(
            (0.0, 58.0, -25.0), ((0.35, 0.94, 0), (0, 0, -1)), 0, 0,
            chest=((-0.1, 1, 0), (0, 0.05, -1)),
            head=((-0.25, 0.83, -0.5), (0, -0.5, -0.87)),
            arm_l=rel((14, 22, 2), (-2, 30, -4), (-10, 26, -6)),
            arm_r=rel((14, 22, 2), (-2, 30, -4), (-10, 26, -6)),
            leg_l=to((32, 64, 8), (14, 53, 40), (12, 49, 56)),
            leg_r=to((20, 76, 7), (2, 55, 39), (0, 51, 55)),
        ),
        hair="lying", colliders=solid,
    )  # fmt: skip
    # The phone at her feet, as the card draws it: the knees, tilted aside
    # under the sheet, fill the front of the frame; the chin is lifted away.
    cover = P.mat("duvet", M.fabric, "duvet", (0.62, 0.58, 0.55), 0.55, 0.92, 900.0, 0.1)
    sheet = P.cloth_sheet((6.0, 86.0, 6.0), (150.0, 136.0), cover, noise=3.0, seed=6)
    P.drape([sheet], [her.body, *solid], frames=60, bend=0.06, mass=0.4)
    # The lamp stands behind the bed-head, above her, and rakes down the body.
    spot((-70, 190, -170), (5, 62, -5), WARM, 900.0, radius=12.0, cone=60.0, blend=0.6, name="key")
    area((120, 150, 260), (0, 60, -20), FILL, 14.0, size=150.0, name="fill")
    camera((60, 205, 190), (0, 60, -30), 27.0, fstop=4.0, focus=(10, 68, 0))
    return Shot()


@scene("her-7")
def her_7():
    reset()
    P.wall(-120.0)
    Person(
        f_pose(
            (0.0, 95.0, 0.0), 15, 0, 3, chest=(10, 0, -2), head=(-30, 10, 0),
            arm_l=to((21, 117, 7), (12, 136, 15), (6, 144, 9)),
            # The forearm across both breasts, the hand over the far one.
            arm_r=to((-19, 133, 13), (7, 136, 18.5), (15, 136, 15)),
        ),
        ground=0.0,
    )  # fmt: skip
    spot((-150, 140, 60), (0, 125, 0), WARM, 380.0, radius=1.5, cone=36.0, blend=0.3, name="key")
    camera((0, 126, 330), (0, 125, 0), 10.0, fstop=2.8, focus=(0, 128, 10))
    return Shot()


@scene("her-8")
def her_8():
    reset()
    P.floor()
    P.wall(-140.0)
    rug = P.rug((0, 0.6, 12), (75, 65))
    Person(
        f_pose(
            # Cross-legged, the knees up and wide, leaning forward: the
            # elbows on the knees, the forearms crossed between them and the
            # forehead resting on them. Long hair falls from the bowed head
            # over the arms.
            (0.0, 11.0, -4.0), 0, 22, 0, chest=(0, 57, 0), head=(0, 98, 0),
            arm_l=to((13.5, 20.8, 44.0), (-7.0, 33.0, 47.0), (-17.0, 34.0, 41.0)),
            arm_r=to((-12.6, 23.2, 46.6), (7.0, 37.0, 46.0), (17.0, 38.0, 40.0)),
            leg_l=to((30.4, 24.0, 33.4), (-8.0, 6.0, 30.0), (-21.0, 3.0, 27.0)),
            leg_r=to((-30.3, 24.8, 33.1), (8.0, 7.0, 38.0), (21.0, 4.0, 35.0)),
        ),
        hair="down", melanin=0.72, ground=1.2, colliders=[rug],
    )  # fmt: skip
    # The lamp behind her, as the card says: it draws the line of the
    # shoulders and the back and shines through the edge of the hair.
    spot((-40, 150, -130), (0, 35, 10), WARM, 650.0, radius=10.0, cone=60.0, blend=0.6, name="key")
    area((150, 90, 250), (0, 30, 20), FILL, 8.0, size=160.0, name="fill")
    # From her side and a little in front: the curve of the back, the soft
    # line of the shoulders and the hair falling over the arms.
    camera((230, 78, 100), (0, 26, 21), 30.0, fstop=2.8, focus=(0, 38, 18))
    return Shot()


@scene("her-9")
def her_9():
    reset()
    P.floor()
    P.wall(-110.0)
    Person(
        f_pose(
            # In profile, facing the blinds: the stripes wrap her front and
            # side, and the near thigh covers what a front view shows.
            (0.0, 95.0, 0.0), -90, 0, -4, chest=(-85, 0, 3), head=(-95, -6, 0),
            arm_l=rel((13, -17, -6), (-4, -31, 1), (-9, -36, 5)),
            arm_r=rel((13, -17, -6), (-4, -31, 1), (-9, -36, 5)),
            leg_l=rel((-3, -44, 10), (-2, -85, 4), (-1, -91, 22)),
        ),
        ground=0.0,
    )  # fmt: skip
    lamp = (-230, 150, 60)
    P.blinds(lamp, (0, 120, 0), period=8.0, duty=0.55, gap=0.55)
    spot(lamp, (0, 120, 0), WARM, 1000.0, radius=1.5, cone=28.0, blend=0.3, name="key")
    # A rim behind her draws the back the blinds leave dark.
    spot((140, 160, -90), (0, 110, 0), WARM, 260.0, radius=8.0, cone=40.0, blend=0.5, name="rim")
    camera((10, 118, 400), (0, 112, 0), 26.0, fstop=2.8)
    return Shot(exposure=0.5)


# Step 4 - poses for him.


@scene("him-1")
def him_1():
    reset()
    P.floor()
    P.wall(-160.0)
    Person(
        m_pose(
            (0.0, 102.5, 0.0), ((0, 0, -1), (0, 1, 0)), 0, 0,
            chest=((0, 0.05, -1), (0, 1, 0.02)), head=((0, -0.06, -1), (0, 1, 0)),
            leg_l=((-0.15, -0.99, 0), (-0.14, -0.99, 0), (-0.25, -0.3, -1)),
            leg_r=((0.15, -0.99, 0), (0.14, -0.99, 0), (0.25, -0.3, -1)),
            arm_l=to((-44, 172, 6), (-14, 176, 12), (0, 176, 12.5)),
            arm_r=to((44, 172, 6), (14, 176, 12), (0, 176, 12.5)),
        ),
        outfit="trousers", ground=0.0,
    )  # fmt: skip
    spot(
        (-190, 250, 150),
        (0, 140, 0),
        (1.0, 0.82, 0.62),
        900.0,
        radius=5.0,
        cone=30.0,
        blend=0.6,
        name="key",
    )
    area((200, 120, 160), (0, 110, 0), FILL, 25.0, size=160.0, name="fill")
    camera((0, 104, 420), (0, 98, 0), 27.5, fstop=2.8, focus=(0, 120, 0))
    return Shot()


@scene("him-2")
def him_2():
    reset()
    P.floor()
    P.wall(-40.0)
    Person(
        m_pose(
            (0.0, 14.0, -26.0), 15, -20, 0, chest=(15, -10, 0), head=(30, 25, 5),
            # The knee nearer the camera is the one drawn up: it hides the lap.
            leg_l=to((10, 52, -6), (8, 9, 18), (6, 2, 40)),
            leg_r=to((-22, 10, 18), (-40, 7, 60), (-44, 21, 79)),
            arm_l=to((10, 56, -4), (0, 76, -22), (-4, 84, -20)),
            arm_r=to((-20, 34, -36), (-26, 16, -6), (-28, 12, 10)),
        ),
        outfit="trousers", ground=0.0,
    )  # fmt: skip
    area((15, 230, 20), (0, 60, -25), WARM, 380.0, size=45.0, name="key")
    camera((70, 75, 330), (5, 55, -20), 27.0, fstop=2.8)
    return Shot()


@scene("him-3")
def him_3():
    reset()
    P.floor()
    P.wall(-140.0)
    Person(
        m_pose(
            (0.0, 103.0, 0.0), -8, 0, 0, chest=(-5, 0, 0), head=(20, -4, 0),
            arm_l=to((24, 125, -9), (12, 104, -17), (3, 104, -16)),
            arm_r=to((-22, 125, -12), (-9, 104, -18), (-2, 104, -16)),
        ),
        outfit="jeans", ground=0.0,
    )  # fmt: skip
    spot((190, 140, 40), (0, 120, 0), WARM, 700.0, radius=3.0, cone=34.0, blend=0.45, name="key")
    camera((0, 125, 430), (0, 118, 0), 20.0, fstop=2.8)
    return Shot()


@scene("him-4")
def him_4():
    reset()
    P.floor()
    P.wall(-140.0)
    # A stretch, turned toward the lamp: one hand holds the other wrist
    # over the head, the face lifted to the light and away from the phone,
    # which stands at navel height.
    Person(
        m_pose(
            (0.0, 103.0, 0.0), -30, 0, 0, chest=(-25, -8, 3), head=(-55, -25, 0),
            arm_l=rel((8, 24, 3), (-15, 50, 4), (-22, 56, 5)),
            arm_r=rel((8, 24, 3), (-17, 53, 3), (-24, 64, 2)),
        ),
        outfit="trousers", ground=0.0,
    )  # fmt: skip
    # Frontal and diffused, as the card says; a rim keeps him off the wall.
    area((40, 190, 330), (0, 130, 0), WARM, 300.0, size=140.0, name="key")
    spot((150, 180, -120), (0, 150, 0), WARM, 300.0, radius=8.0, cone=22.0, blend=0.5, name="rim")
    camera((60, 110, 400), (0, 138, 0), 27.0, fstop=2.8, focus=(0, 130, 0))
    return Shot()


@scene("him-5")
def him_5():
    reset()
    P.floor()
    P.wall(-100.0)
    Person(
        m_pose(
            (0.0, 103.0, 0.0), 90, 0, 0, chest=(90, -3, 0), head=(90, -5, 0),
            leg_r=rel((1, -44, 10), (0, -87, 6), (1, -93, 26)),
        ),
        outfit="trousers", ground=0.0,
    )  # fmt: skip
    P.halo(-100.0, 0.0, 120.0, DAY, 900.0, cone=70.0)
    area((-20, 130, -80), (0, 120, 60), DAY, 350.0, size=80.0, name="back")
    camera((0, 110, 420), (0, 105, 0), 28.0, fstop=2.8)
    return Shot()


@scene("him-6")
def him_6():
    reset()
    P.floor()
    P.wall(-51.8)
    Person(
        m_pose(
            # One line from the heels to the hands: a step back from the
            # wall, leaning into it, the palms flat on it over the head and
            # the head bowed between the arms.
            (0.0, 91.3, 14.0), 180, 25, 0, chest=(180, 27, 0), head=(180, 55, 0),
            arm_l=to((-37.7, 154.4, -29.4), (-28.0, 171.0, -49.0), (-30.0, 186.0, -44.0)),
            arm_r=to((37.7, 154.4, -29.4), (28.0, 171.0, -49.0), (30.0, 186.0, -44.0)),
            leg_l=to((-10.3, 41.6, 19.7), (-9.0, 8.2, 52.8), (-9.5, 1.0, 34.0)),
            leg_r=to((10.3, 41.6, 19.7), (9.0, 8.2, 52.8), (9.5, 1.0, 34.0)),
        ),
        outfit="trousers", ground=0.0,
    )  # fmt: skip
    # From behind and to his right; the lamp on his left, level with him,
    # rakes across the back and along the wall: the near half of the back
    # turns away into shadow, as the card says.
    spot((-200, 180, 30), (0, 130, -15), WARM, 800.0, radius=10.0, cone=40.0, blend=0.5, name="key")
    area((220, 120, 300), (0, 110, 0), FILL, 6.0, size=150.0, name="fill")
    camera((135, 125, 300), (0, 112, -15), 30.0, fstop=4.0, focus=(0, 130, -10))
    return Shot()


@scene("him-7")
def him_7():
    reset()
    tiles = P.mat("tiles", M.tiles, (0.16, 0.18, 0.20))
    P.floor(tiles)
    P.wall(-70.0, tiles)
    tub = P.tub((0.0, 26.0, -30.0))
    him = Person(
        m_pose(
            (0.0, 60.0, 6.0), 15, -5, 0, chest=(15, 42, 0), head=(15, 62, 0),
            leg_l=to((20, 53, 51), (21, 6, 53), (26, 1, 76)),
            leg_r=to((-6, 53, 56), (-5, 6, 58), (0, 1, 81)),
            arm_l=to((24, 66, 40), (14, 56, 56), (10, 44, 60)),
            arm_r=to((-8, 68, 46), (6, 56, 60), (8, 44, 62)),
        ),
        outfit="trousers", wet=True, colliders=[tub],
    )  # fmt: skip
    shoulder_towel(him.h, "l", colliders=[tub])
    area((-90, 210, 170), (0, 70, 0), COLD, 300.0, size=40.0, name="key")
    area((80, 90, 260), (0, 70, 0), (0.6, 0.65, 0.7), 25.0, size=140.0, name="fill")
    camera((60, 95, 330), (0, 70, 0), 29.0, fstop=2.8)
    return Shot(exposure=-0.5)


@scene("him-8")
def him_8():
    reset()
    P.floor()
    P.wall(-130.0)
    P.chair(0.0, 5.0, 0.0, seat=48.0)
    Person(
        m_pose(
            # Astride the chair, facing its back: a leg down either side of
            # the seat, the forearms folded on its top rail, the head bowed
            # over them.
            (0.0, 60.0, 12.0), 180, -5, 0, chest=(180, 25, 0), head=(165, 58, 0),
            arm_l=to((-17.8, 85.6, -21.6), (6.0, 98.5, -17.0), (18.0, 98.5, -16.0)),
            arm_r=to((19.2, 84.6, -20.5), (-6.0, 95.0, -17.0), (-18.0, 95.0, -16.0)),
            leg_l=to((-22.8, 49.2, -34.4), (-26.0, 8.0, -12.0), (-27.0, 1.0, -30.0)),
            leg_r=to((22.8, 49.2, -34.4), (26.0, 8.0, -12.0), (27.0, 1.0, -30.0)),
        ),
        outfit="trousers",
    )  # fmt: skip
    # From the side, as the card says, high and broad, so the shoulder
    # blades and the line of the shoulders carry the picture.
    spot((-200, 170, 50), (0, 100, 0), WARM, 520.0, radius=18.0, cone=44.0, blend=0.5, name="key")
    area((180, 120, 260), (0, 90, 0), FILL, 5.0, size=150.0, name="fill")
    camera((20, 108, 360), (0, 88, 0), 25.0, fstop=2.8, focus=(0, 100, 5))
    return Shot()


@scene("him-9")
def him_9():
    reset()
    P.floor()
    P.wall(-130.0)
    P.chair(0.0, 0.0, 90.0, seat=48.0)
    Person(
        m_pose(
            (0.0, 60.0, 0.0), 90, -5, 0, chest=(90, 3, 0), head=(70, 0, 0),
            leg_l=rel((0, -4, 46), (0, -48, 50), (0, -54, 70)),
            leg_r=rel((-6, 6, 44), (-14, -26, 64), (-16, -34, 82)),
            arm_r=rel((2, -26, 8), (-2, -36, 30), (-4, -38, 44)),
        ),
        outfit="trousers",
    )  # fmt: skip
    spot(
        (160, 190, 120),
        (0, 80, 0),
        (1.0, 0.72, 0.48),
        600.0,
        radius=3.0,
        cone=30.0,
        blend=0.45,
        name="key",
    )
    camera((-20, 90, 400), (5, 78, 0), 26.0, fstop=2.8)
    return Shot()


@scene("him-10")
def him_10():
    reset()
    P.wall(-140.0)
    Person(
        m_pose(
            # Face on, as the card says: the arms folded across the chest,
            # the right forearm over the left, each hand on the other arm.
            (0.0, 103.0, 0.0), 0, 0, 0, chest=(0, 2, 0), head=(0, 8, 0),
            arm_l=to((20.0, 124.9, 7.8), (-3.0, 130.0, 22.0), (-15.0, 135.0, 15.0)),
            arm_r=to((-15.5, 127.2, 12.6), (4.0, 128.0, 32.0), (17.0, 134.0, 15.0)),
        ),
        outfit="trousers", ground=0.0,
    )  # fmt: skip
    # A hard lamp from the right: one half of the torso and the folded arms
    # in light, the other in deep shadow, every muscle drawn by the edge.
    spot((210, 160, 30), (0, 128, 5), WARM, 650.0, radius=1.5, cone=30.0, blend=0.3, name="key")
    # A faint rim behind the dark side keeps its outline off the wall.
    spot((-160, 175, -130), (0, 130, 0), WARM, 90.0, radius=4.0, cone=30.0, blend=0.5, name="rim")
    # Only the torso: from under the chin to the belt.
    camera((0, 128.5, 330), (0, 128.5, 0), 9.8, fstop=2.8, focus=(0, 128.5, 20))
    return Shot()


# Step 5 - editing and safety. Lingerie again: free, and no age asked.


@scene("edit-bw")
def edit_bw():
    reset()
    solid = bedroom(-120.0, -160.0, -2.0, -100.0, 40.0)
    Person(
        f_pose(
            (-12.0, 58.0, 0.0), 70, -5, 0, chest=(60, 0, 0), head=(40, 12, 0),
            leg_l=to((32, 52, -6), (36, 10, 0), (44, 2, 16)),
            leg_r=to((30, 60, 8), (46, 26, 22), (60, 20, 30)),
            arm_l=to((6, 80, -10), (24, 64, 2), (32, 62, 8)),
            arm_r=to((-10, 80, 18), (20, 66, 12), (30, 63, 8)),
        ),
        outfit="lingerie", colliders=solid,
    )  # fmt: skip
    area((-150, 130, 150), (0, 80, 0), WARM, 700.0, size=40.0, name="key")
    camera((-4, 85, 380), (-4, 80, 0), 29.0, fstop=2.8)
    return Shot(split=True)


@scene("edit-privacy")
def edit_privacy():
    reset()
    P.wall(-120.0)
    Person(
        f_pose(
            (0.0, 95.0, 0.0), 20, 0, -3, chest=(15, 0, 3), head=(40, -5, 4),
            arm_l=rel((12, -14, 6), (-4, 4, 12), (-10, 10, 10)),
        ),
        outfit="lingerie", ground=0.0,
    )  # fmt: skip
    area((-160, 170, 100), (0, 130, 0), WARM, 600.0, size=30.0, name="key")
    camera((0, 140, 400), (0, 138, 0), 15.0, fstop=2.8)
    return Shot()

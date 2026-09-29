"""The two people in the pictures: generic, model-like builds - nobody's
likeness. A slim, toned woman about 172 cm tall and an athletic man about
182 cm, both around 25-30."""

from .makehuman import Shape

HER = Shape(
    gender=0.0, age=0.52, muscle=0.58, weight=0.42, height=0.55, proportions=1.0,
    cupsize=0.55, firmness=0.7, race={"caucasian": 0.8, "african": 0.1, "asian": 0.1},
    details={
        "measure-waist-circ-decr": 0.35, "buttocks-volume-incr": 0.25,
        "upperlegs-height-incr": 0.25, "lowerlegs-height-incr": 0.15, "stomach-pregnant-decr": 0.3,
    },
)  # fmt: skip

HIM = Shape(
    gender=1.0, age=0.54, muscle=0.8, weight=0.46, height=0.55, proportions=1.0,
    race={"caucasian": 0.8, "african": 0.1, "asian": 0.1},
    details={
        "measure-shoulder-dist-incr": 0.25, "measure-waist-circ-decr": 0.3,
        "torso-muscle-dorsi-incr": 0.35, "torso-muscle-pectoral-incr": 0.2, "stomach-pregnant-decr": 0.4,
        "hip-scale-horiz-decr": 0.25, "measure-hips-circ-decr": 0.2, "buttocks-volume-decr": 0.2,
    },
)  # fmt: skip

SKIN = {"f": (0.60, 0.40, 0.31), "m": (0.54, 0.35, 0.26)}

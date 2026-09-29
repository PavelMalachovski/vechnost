"""A person in a scene: the body built, posed from the scene's joints, set
down on whatever it rests on, dressed, and with hair, brows and lashes
grown after the pose so they fall the way this pose makes them fall."""

from __future__ import annotations

import bpy
import numpy as np

from . import cast, outfits
from . import materials as M
from .human import Human, grow_brows, grow_hair, grow_lashes
from .pose import Poser, target
from .skeleton import Skeleton


def lowest(ob) -> float:
    """The lowest point of an object's evaluated surface (Blender z)."""
    dg = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(dg)
    me = ev.to_mesh()
    co = np.zeros(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    ev.to_mesh_clear()
    mw = np.array(ob.matrix_world)
    return float((co.reshape(-1, 3) @ mw[:3, :3].T + mw[:3, 3])[:, 2].min())


class Person:
    """`pose` is a scene pose (skeleton.pose); `ground`, a height in cm to
    set the lowest point of the body on; `outfit`, one of lingerie, boxers,
    jeans, towel; `hair`, a style (long for her and short for him unless
    told); `grip`, where held hair is held (by default between the hands)."""

    def __init__(
        self,
        pose,
        hair=None,
        outfit=None,
        wet=False,
        colliders=(),
        ground=None,
        iris=None,
        melanin=0.9,
    ):
        self.sk = Skeleton(pose)
        sex = self.sk.sex
        self.skin = M.skin(cast.SKIN[sex], wet=wet, name=f"skin_{sex}")
        self.h = Human(
            cast.HER if sex == "f" else cast.HIM,
            name="her" if sex == "f" else "him",
            skin=self.skin,
            iris=iris,
        )
        Poser(self.h.arm).apply(target(self.sk))
        bpy.context.view_layer.update()
        if ground is not None:
            self.h.arm.location.z += ground / 100.0 - lowest(self.h.ob)
            bpy.context.view_layer.update()
        if outfit == "towel":
            outfits.towel(self.h, colliders)
        elif outfit is not None:
            {"lingerie": outfits.lingerie, "boxers": outfits.boxers, "jeans": outfits.jeans}[
                outfit
            ](self.h)
        style = hair or ("long" if sex == "f" else ("wet" if wet else "short"))
        grip = None
        if style == "held":
            # Between the hands, where the fingers close round it.
            grip = sum(self.h.bone_now(f"finger3-1.{s}") for s in "LR") / 2
        hair_mat = M.hair(melanin=melanin, redness=0.3, wet=wet, name="hair")
        many = style in ("long", "held")
        self.hair = grow_hair(
            self.h, style, [self.h.ob, *colliders], hair_mat, grip=grip,
            strands=65000 if many else 70000, guides=600 if many else 900,
        )  # fmt: skip
        grow_brows(self.h, hair_mat)
        grow_lashes(self.h, M.hair(melanin=0.95, redness=0.2, rough=0.4, name="lash"))

    @property
    def body(self):
        return self.h.ob

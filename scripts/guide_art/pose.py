"""Posing MakeHuman's default skeleton from joint targets.

The trunk takes whole frames: the pelvis goes where it is told and turns
as told, the five spine bones share the turn from pelvis to chest, the
three neck bones and the head share the turn from chest to head. Each limb
is a two-segment reach: the wrist (ankle) goes to its target, the elbow
(knee) bends toward its hint, lengths stay the body's own, and the hand
(foot) turns toward the fingertips (toes) target. A raised arm takes its
collarbone and shoulder blade along a little, as a real one does, so the
shoulder keeps its shape. Everything is in Blender world space; `Target`
holds scene centimetres.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import bpy
import numpy as np
from mathutils import Matrix, Quaternion, Vector

from .studio import V

# Scene axes (x right, y up, z toward the camera) to Blender's.
C = np.array([[1.0, 0.0, 0.0], [0.0, 0.0, -1.0], [0.0, 1.0, 0.0]])


def frame_to_blender(R) -> Matrix:
    """A frame given in scene axes, as a Blender rotation. The body's own
    axes at rest are the scene's (left = +x, up = +y, facing = +z), so a
    frame whose columns are the body's axes is also the turn from rest."""
    return Matrix((C @ np.asarray(R, float) @ C.T).tolist())


def _nrm(v: Vector) -> Vector:
    return v.normalized() if v.length > 1e-9 else Vector((0.0, 0.0, 1.0))


def rotation_between(a0: Vector, n0: Vector, a1: Vector, n1: Vector) -> Matrix:
    """The rotation taking direction a0 to a1 and, as nearly as it can, n0 to n1."""
    a0, a1 = _nrm(a0), _nrm(a1)
    n0 = _nrm(n0 - a0 * n0.dot(a0))
    n1 = _nrm(n1 - a1 * n1.dot(a1))
    m0 = Matrix((a0, n0, a0.cross(n0))).transposed()
    m1 = Matrix((a1, n1, a1.cross(n1))).transposed()
    return m1 @ m0.transposed()


def swing(a: Vector, b: Vector) -> Matrix:
    return _nrm(a).rotation_difference(_nrm(b)).to_matrix()


@dataclass
class Limb:
    hint: np.ndarray  # elbow / knee, scene cm
    target: np.ndarray  # wrist / ankle
    tip: np.ndarray  # fingertips / toes
    curl: float = 0.3  # fingers: 0 straight, 1 a fist


@dataclass
class Target:
    """A pose in scene centimetres: the pelvis point (between the hip
    joints), the three frames, and the four limbs."""

    pelvis: np.ndarray
    pelvis_frame: np.ndarray
    chest_frame: np.ndarray
    head_frame: np.ndarray
    limbs: dict[str, Limb] = field(default_factory=dict)


def _s(side):
    return "L" if side == "l" else "R"


SPINE = ("spine05", "spine04", "spine03", "spine02", "spine01")
NECK = ("neck01", "neck02", "neck03")


def arm_chain(side):
    s = _s(side)
    return {
        "girdle": (f"clavicle.{s}", f"shoulder01.{s}"),
        "upper": (f"upperarm01.{s}", f"upperarm02.{s}"),
        "lower": (f"lowerarm01.{s}", f"lowerarm02.{s}"),
        "end": f"wrist.{s}",
        "tip": f"finger3-1.{s}",
    }


def leg_chain(side):
    s = _s(side)
    return {
        "upper": (f"upperleg01.{s}", f"upperleg02.{s}"),
        "lower": (f"lowerleg01.{s}", f"lowerleg02.{s}"),
        "end": f"foot.{s}",
    }


class Poser:
    def __init__(self, arm_ob):
        self.ob = arm_ob
        self.pose = arm_ob.pose
        self.bones = arm_ob.data.bones
        for pb in self.pose.bones:
            pb.rotation_mode = "QUATERNION"

    def _update(self):
        bpy.context.view_layer.update()

    def rest_rot(self, name) -> Matrix:
        return self.bones[name].matrix_local.to_3x3()

    def head_now(self, name) -> Vector:
        self._update()
        return self.pose.bones[name].matrix.translation.copy()

    def place(self, name, rot: Matrix, head: Vector | None = None):
        """Set a bone's armature-space rotation (and head, for a root)."""
        h = head if head is not None else self.head_now(name)
        m = rot.to_4x4()
        m.translation = h
        self.pose.bones[name].matrix = m
        self._update()

    def turn(self, name, R: Matrix, head: Vector | None = None):
        """Give a bone its rest orientation turned by R (world)."""
        self.place(name, R @ self.rest_rot(name), head)

    def turn_all(self, names, R: Matrix):
        for n in names:
            self.turn(n, R)

    def seg(self, names):
        """Rest start and end of a run of bones."""
        return self.bones[names[0]].head_local.copy(), self.bones[names[-1]].tail_local.copy()

    # --- the whole figure ----------------------------------------------
    def apply(self, t: Target):
        for pb in self.pose.bones:
            pb.matrix_basis = Matrix.Identity(4)
        self._update()
        Rp = frame_to_blender(t.pelvis_frame)
        Rc = frame_to_blender(t.chest_frame)
        Rh = frame_to_blender(t.head_frame)
        hips = (self.bones["upperleg01.L"].head_local + self.bones["upperleg01.R"].head_local) / 2
        offset = self.bones["root"].head_local - hips
        self.turn("root", Rp, V(t.pelvis) + Rp @ offset)
        rel = (Rc @ Rp.transposed()).to_quaternion()
        for k, name in enumerate(SPINE, start=1):
            self.turn(name, Quaternion().slerp(rel, k / len(SPINE)).to_matrix() @ Rp)
        relh = (Rh @ Rc.transposed()).to_quaternion()
        for k, name in enumerate(NECK, start=1):
            self.turn(name, Quaternion().slerp(relh, 0.6 * k / len(NECK)).to_matrix() @ Rc)
        self.turn("head", Rh)
        for side in "lr":
            self.turn(f"breast.{_s(side)}", Rc)
        for side in "lr":
            limb = t.limbs.get("leg_" + side)
            if limb is not None:
                self._leg(side, limb, Rp)
        for side in "lr":
            limb = t.limbs.get("arm_" + side)
            if limb is not None:
                self._arm(side, limb, Rc)
            else:
                self._fingers(side, 0.3)
        self._breasts(Rc)

    def _reach(self, upper, lower, root: Vector, hint: Vector, target: Vector, frame: Matrix):
        """Two segments from `root` toward `target`, bending toward `hint`:
        their new rotations, and where the end lands."""
        u0, u1 = self.seg(upper)
        l0, l1 = self.seg(lower)
        L1, L2 = (u1 - u0).length, (l1 - l0).length
        u = target - root
        d = min(max(u.length, abs(L1 - L2) + 1e-3), L1 + L2 - 1e-4)
        u = _nrm(u)
        a = (L1 * L1 - L2 * L2 + d * d) / (2 * d)
        r = max(L1 * L1 - a * a, 0.0) ** 0.5
        c = root + u * a
        p = hint - c
        p = p - u * p.dot(u)
        if p.length < 1e-6:
            p = frame @ Vector((0.0, -1.0, 0.0))
            p = p - u * p.dot(u)
        mid = c + _nrm(p) * r
        end = root + u * d
        n0 = (u1 - u0).cross(l1 - l0)
        n1 = (mid - root).cross(end - mid)
        if n0.length < 1e-6:
            n0 = self.rest_rot(upper[0]) @ Vector((1.0, 0.0, 0.0))
        if n1.length < 1e-6:
            n1 = frame @ n0
        return (
            rotation_between(u1 - u0, n0, mid - root, n1),
            rotation_between(l1 - l0, n0, end - mid, n1),
            end,
        )

    def _arm(self, side, limb: Limb, Rc: Matrix):
        ch = arm_chain(side)
        for b in ch["girdle"]:
            self.turn(b, Rc)
        root = self.head_now(ch["upper"][0])
        target = V(limb.target)
        # The shoulder girdle follows the arm a little: a fifth of the swing
        # from the arm's rest direction toward the target, a third of that on
        # the collarbone.
        u0, u1 = self.seg(ch["upper"])
        rest_dir = Rc @ (u1 - u0)
        want = target - root
        q = rest_dir.rotation_difference(want)
        share = 0.22 * min(
            1.0, max(0.0, (want.normalized().dot(Rc @ Vector((0, 0, 1))) + 0.7) / 1.2)
        )
        girdle = Quaternion().slerp(q, share)
        self.turn(ch["girdle"][0], Quaternion().slerp(girdle, 0.4).to_matrix() @ Rc)
        self.turn(ch["girdle"][1], girdle.to_matrix() @ Rc)
        root = self.head_now(ch["upper"][0])
        Ru, Rl, wrist = self._reach(ch["upper"], ch["lower"], root, V(limb.hint), target, Rc)
        self.turn_all(ch["upper"], Ru)
        self.turn_all(ch["lower"], Rl)
        # The hand rides on the forearm, then swings toward the fingertips.
        w0 = self.bones[ch["end"]].head_local
        f0 = self.bones[ch["tip"]].head_local
        carried = Rl @ (f0 - w0)
        want = V(limb.tip) - wrist
        S = swing(carried, want) if want.length > 1e-4 else Matrix.Identity(3)
        self.turn(ch["end"], S @ Rl)
        self._fingers(side, limb.curl)

    def _fingers(self, side, curl):
        """Curl the fingers about their own bend axis (local x)."""
        s = _s(side)
        for f in range(1, 6):
            for k in (1, 2, 3):
                name = f"finger{f}-{k}.{s}"
                if name not in self.pose.bones:
                    continue
                amount = curl * (0.4 if f == 1 else 1.0) * (0.7 if k == 1 else 1.0)
                self.pose.bones[name].rotation_quaternion = Quaternion(
                    Vector((1.0, 0.0, 0.0)), amount
                )
        self._update()

    def _leg(self, side, limb: Limb, Rp: Matrix):
        ch = leg_chain(side)
        self.turn_all(ch["upper"], Rp)
        root = self.head_now(ch["upper"][0])
        Ru, Rl, ankle = self._reach(
            ch["upper"], ch["lower"], root, V(limb.hint), V(limb.target), Rp
        )
        self.turn_all(ch["upper"], Ru)
        self.turn_all(ch["lower"], Rl)
        f0, f1 = self.bones[ch["end"]].head_local, self.bones[ch["end"]].tail_local
        carried = Rl @ (f1 - f0)
        want = V(limb.tip) - ankle
        S = swing(carried, want) if want.length > 1e-4 else Matrix.Identity(3)
        self.turn(ch["end"], S @ Rl)

    def _breasts(self, Rc: Matrix):
        """Breasts settle a little toward the floor, however the chest lies."""
        down = Rc.transposed() @ Vector((0.0, 0.0, -1.0))  # gravity in chest axes
        for s in "LR":
            name = f"breast.{s}"
            b0, b1 = self.bones[name].head_local, self.bones[name].tail_local
            rest = b1 - b0
            tilt = _nrm(rest).rotation_difference(_nrm(rest + down * rest.length * 0.35))
            self.turn(name, Rc @ Quaternion().slerp(tilt, 0.5).to_matrix())


def target(sk) -> Target:
    """A target from a resolved scene pose (skeleton.Skeleton): its joints
    are where the real body's joints should go."""
    hips = (sk.H["l"] + sk.H["r"]) / 2
    limbs = {}
    for side in "lr":
        _s0, e, w, t = sk.arm[side][:4]
        limbs["arm_" + side] = Limb(e, w, t)
        _h, k, a, toe = sk.leg[side][:4]
        limbs["leg_" + side] = Limb(k, a, toe)
    return Target(hips, sk.Rp, sk.Rc, sk.Rh, limbs)

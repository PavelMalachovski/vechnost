"""The studio: scene reset, units, the camera, the lamps and the shutter.

Scenes are written in the masterclass's own units - centimetres, x to the
frame's right, y up, z toward the camera - and turned here into Blender's
metres with z up, so a scene reads the way it always has.
"""

from __future__ import annotations

import math

import bpy
import numpy as np
from mathutils import Matrix, Vector

WARM = (1.0, 0.80, 0.60)
PINK = (1.0, 0.68, 0.58)
DAY = (1.0, 0.96, 0.90)
COLD = (0.80, 0.90, 1.0)
FILL = (0.75, 0.62, 0.72)


def V(p) -> Vector:
    """A point in scene centimetres, in Blender's metres."""
    x, y, z = (float(c) for c in p)
    return Vector((x / 100.0, -z / 100.0, y / 100.0))


def D(v) -> Vector:
    """A direction in scene axes, in Blender's."""
    x, y, z = (float(c) for c in v)
    return Vector((x, -z, y)).normalized()


def reset(width=540, height=585, samples=192, world=(0.010, 0.006, 0.009)):
    """An empty scene set up like the camera the pictures are taken with:
    Cycles on the CPU, denoised, AgX, a near-black aubergine world."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    cy = sc.cycles
    cy.device = "CPU"
    cy.samples = samples
    cy.use_adaptive_sampling = True
    cy.adaptive_threshold = 0.008
    cy.use_denoising = True
    cy.denoiser = "OPENIMAGEDENOISE"
    cy.max_bounces = 10
    cy.diffuse_bounces = 4
    cy.glossy_bounces = 4
    cy.transmission_bounces = 8
    cy.transparent_max_bounces = 16
    cy.caustics_reflective = False
    cy.caustics_refractive = False
    cy.blur_glossy = 1.0
    cy.sample_clamp_indirect = 8.0
    cy.seed = 7
    sc.render.resolution_x = width
    sc.render.resolution_y = height
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_depth = "16"
    sc.view_settings.view_transform = "AgX"
    for look in ("AgX - Base Contrast", "None"):
        try:
            sc.view_settings.look = look
            break
        except TypeError:
            continue
    w = bpy.data.worlds.new("world")
    sc.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (*world, 1.0)
    return sc


def look_at(obj, eye, at, up=(0.0, 1.0, 0.0)):
    """Point an object's -Z at `at` from `eye`, its +Y toward `up`."""
    e, a = V(eye), V(at)
    f = (a - e).normalized()
    r = f.cross(D(up))
    if r.length < 1e-6:
        r = f.cross(Vector((0.0, 1.0, 0.0)))
    r.normalize()
    u = r.cross(f)
    m = Matrix(((r.x, u.x, -f.x), (r.y, u.y, -f.y), (r.z, u.z, -f.z)))
    obj.matrix_world = Matrix.Translation(e) @ m.to_4x4()


def camera(eye, at, fov, up=(0.0, 1.0, 0.0), fstop=2.8, focus=None):
    """A full-frame camera, `fov` degrees top to bottom, focused on `focus`
    (the point it looks at, unless told otherwise)."""
    sc = bpy.context.scene
    data = bpy.data.cameras.new("camera")
    data.sensor_fit = "VERTICAL"
    data.sensor_height = 24.0
    data.sensor_width = 24.0 * sc.render.resolution_x / sc.render.resolution_y
    data.lens = 12.0 / math.tan(math.radians(fov) / 2)
    data.clip_start = 0.05
    data.clip_end = 60.0
    if fstop:
        data.dof.use_dof = True
        data.dof.aperture_fstop = fstop
        data.dof.aperture_blades = 7
        data.dof.focus_distance = (V(focus if focus is not None else at) - V(eye)).length
    ob = bpy.data.objects.new("camera", data)
    sc.collection.objects.link(ob)
    look_at(ob, eye, at, up)
    sc.camera = ob
    return ob


def _light(kind, name, pos, color, watts):
    data = bpy.data.lights.new(name, kind)
    data.color = color
    data.energy = watts
    ob = bpy.data.objects.new(name, data)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = V(pos)
    return ob


def spot(pos, at, color, watts, radius=4.0, cone=40.0, blend=0.35, name="spot"):
    """A lamp aimed at `at`: `cone` is the beam's full angle in degrees and
    `radius` the bulb's size in centimetres (bigger, softer shadows)."""
    ob = _light("SPOT", name, pos, color, watts)
    ob.data.spot_size = math.radians(cone)
    ob.data.spot_blend = blend
    ob.data.shadow_soft_size = radius / 100.0
    look_at(ob, pos, at)
    return ob


def area(pos, at, color, watts, size=60.0, size_y=None, shape="DISK", spread=180.0, name="area"):
    """A softbox or a window: a glowing surface facing `at`."""
    ob = _light("AREA", name, pos, color, watts)
    d = ob.data
    if size_y is None:
        d.shape = shape
        d.size = size / 100.0
    else:
        d.shape = "RECTANGLE"
        d.size = size / 100.0
        d.size_y = size_y / 100.0
    d.spread = math.radians(spread)
    look_at(ob, pos, at)
    return ob


def point(pos, color, watts, radius=5.0, name="point"):
    ob = _light("POINT", name, pos, color, watts)
    ob.data.shadow_soft_size = radius / 100.0
    return ob


def shoot(path) -> np.ndarray:
    """Render the scene to a 16-bit PNG and read it back as display values
    in 0-1, top row first."""
    sc = bpy.context.scene
    sc.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    img = bpy.data.images.load(str(path))
    img.colorspace_settings.name = "Non-Color"
    w, h = img.size
    px = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    bpy.data.images.remove(img)
    return px.reshape(h, w, 4)[::-1, :, :3].astype(np.float64)

"""The room: floor, walls, a window, the bed, a chair, a lamp, small things,
and cloth that is dropped onto them and left to settle.

All sizes are centimetres in scene axes (x right, y up, z toward the
camera), like the scenes themselves.
"""

from __future__ import annotations

import math

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

from . import materials as M
from .studio import D, V, area, point, spot

_CACHE: dict[str, bpy.types.Material] = {}


def mat(key, factory, *a, **kw):
    """One material per key per scene."""
    try:
        alive = key in _CACHE and _CACHE[key].name in bpy.data.materials
    except ReferenceError:  # the scene was reset under it
        alive = False
    if not alive:
        _CACHE[key] = factory(*a, **kw)
    return _CACHE[key]


def link(ob):
    bpy.context.scene.collection.objects.link(ob)
    return ob


def mesh_object(name, verts, faces, material=None, smooth=True):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], [], [tuple(f) for f in faces])
    me.update()
    if smooth:
        me.shade_smooth()
    ob = link(bpy.data.objects.new(name, me))
    if material is not None:
        me.materials.append(material)
    return ob


def _rot4(rot):
    """A rotation given as columns in scene axes, as a Blender 4x4."""
    if rot is None:
        return Matrix.Identity(4)
    r = np.asarray(rot, dtype=float)
    cols = [D(r[:, 0]), D(-r[:, 2]), D(r[:, 1])]
    return Matrix(
        (
            (cols[0].x, cols[1].x, cols[2].x, 0),
            (cols[0].y, cols[1].y, cols[2].y, 0),
            (cols[0].z, cols[1].z, cols[2].z, 0),
            (0, 0, 0, 1),
        )
    )


def box(center, half, material, bevel=1.0, rot=None, name="box", segments=3):
    """A box with rounded edges: `half` are its half-sizes along its own x
    (right), y (up) and z (toward the camera), `rot` its axes in scene axes."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    hx, hy, hz = half
    me.transform(Matrix.Diagonal((2 * hx / 100.0, 2 * hz / 100.0, 2 * hy / 100.0, 1.0)))
    ob = link(bpy.data.objects.new(name, me))
    ob.matrix_world = Matrix.Translation(V(center)) @ _rot4(rot)
    if bevel > 0:
        bv = ob.modifiers.new("bevel", "BEVEL")
        bv.width = bevel / 100.0
        bv.segments = segments
        bv.limit_method = "NONE"
    me.shade_smooth()
    me.materials.append(material)
    return ob


def cylinder(a, b, r1, r2, material, name="cyl", segments=48, caps=True):
    """A (possibly tapered) cylinder from a to b, radii in centimetres."""
    pa, pb = V(a), V(b)
    axis = pb - pa
    bm = bmesh.new()
    bmesh.ops.create_cone(
        bm, cap_ends=caps, cap_tris=False, segments=segments,
        radius1=r1 / 100.0, radius2=r2 / 100.0, depth=axis.length,
    )  # fmt: skip
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = link(bpy.data.objects.new(name, me))
    q = Vector((0, 0, 1)).rotation_difference(axis.normalized())
    ob.matrix_world = Matrix.Translation((pa + pb) / 2) @ q.to_matrix().to_4x4()
    me.shade_smooth()
    me.materials.append(material)
    return ob


def floor(material=None, size=1400.0):
    material = material or mat("floor", M.floorboards)
    s = size / 200.0
    return mesh_object(
        "floor", [(-s, -s, 0), (s, -s, 0), (s, s, 0), (-s, s, 0)], [(0, 1, 2, 3)], material, False
    )


def wall(z, material=None, width=1400.0, height=500.0, x=0.0):
    """The wall behind, facing the camera at depth z."""
    material = material or mat("wall", M.plaster)
    x0, x1 = (x - width / 2) / 100, (x + width / 2) / 100
    yb, top = -z / 100.0, height / 100
    return mesh_object(
        "wall",
        [(x0, yb, 0), (x1, yb, 0), (x1, yb, top), (x0, yb, top)],
        [(0, 1, 2, 3)],
        material,
        False,
    )


def bed(x0, x1, z0, z1, top=46.0, linen=(0.46, 0.43, 0.41), rumpled=1.3):
    """A low bed: a wooden base, a mattress under a fitted sheet."""
    cx, cz = (x0 + x1) / 2, (z0 + z1) / 2
    hx, hz = (x1 - x0) / 2, (z1 - z0) / 2
    sheet = mat(f"linen{linen}", M.fabric, "linen", linen, 0.5, 0.9, 1100.0, 0.08)
    base_h = top - 22.0
    frame = box(
        (cx, base_h / 2, cz),
        (hx + 3, base_h / 2, hz + 3),
        mat("bedwood", M.wood),
        bevel=1.2,
        name="bedframe",
    )
    mattress = box(
        (cx, top - 11.0, cz), (hx, 11.0, hz), sheet, bevel=6.0, segments=5, name="mattress"
    )
    if rumpled:
        rumple(mattress, amount=rumpled, scale=0.07)
    return frame, mattress, sheet


def rumple(ob, amount=1.2, scale=0.08, seed=3):
    """Displace a surface a little along its normal, like slept-in linen."""
    tex = bpy.data.textures.new(f"rumple{seed}", "CLOUDS")
    tex.noise_scale = scale
    tex.noise_depth = 2
    sd = ob.modifiers.new("dense", "SUBSURF")
    sd.levels = sd.render_levels = 3
    sd.subdivision_type = "SIMPLE"
    d = ob.modifiers.new("rumple", "DISPLACE")
    d.texture = tex
    d.strength = amount / 100.0
    sm = ob.modifiers.new("soft", "SMOOTH")
    sm.factor = 0.6
    sm.iterations = 3
    return ob


def _settle(obs, colliders, frames):
    """Run the scene's cloth for `frames` frames and freeze each piece where
    it lies."""
    sc = bpy.context.scene
    added = []
    for c in colliders:
        if "collision" not in c.modifiers:
            c.modifiers.new("collision", "COLLISION")
            c.collision.thickness_outer = 0.004
            c.collision.cloth_friction = 20.0
            added.append(c)
    sc.frame_start, sc.frame_end = 1, frames
    for f in range(1, frames + 1):
        sc.frame_set(f)
    dg = bpy.context.evaluated_depsgraph_get()
    for ob in obs:
        new = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
        mats = list(ob.data.materials)
        ob.modifiers.clear()
        ob.data = new
        if not new.materials:
            for m in mats:
                new.materials.append(m)
        new.shade_smooth()
    for c in added:
        c.modifiers.remove(c.modifiers["collision"])
    sc.frame_set(1)


def _cloth(ob, mass, bend, frames, pressure=0.0, pin=None, shrink=0.0, self_collide=True):
    cl = ob.modifiers.new("cloth", "CLOTH")
    st = cl.settings
    st.quality = 6
    st.mass = mass
    st.tension_stiffness = st.compression_stiffness = 12.0
    st.shear_stiffness = 8.0
    st.bending_stiffness = bend
    st.air_damping = 2.0
    if pressure:
        st.use_pressure = True
        st.uniform_pressure_force = pressure
    if pin:
        st.vertex_group_mass = pin
        st.pin_stiffness = 1.0
    if shrink:
        st.shrink_min = shrink
    cl.collision_settings.distance_min = 0.004
    cl.collision_settings.use_self_collision = self_collide
    cl.collision_settings.self_distance_min = 0.003
    cl.point_cache.frame_end = frames
    return cl


def pillow(center, material, half=(30.0, 8.0, 22.0), pressure=6.0, frames=30, rest_on=()):
    """A pillow: a closed cloth bag, blown up by pressure and let settle."""
    hx, hy, hz = half
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=14, use_grid_fill=True)
    me = bpy.data.meshes.new("pillow")
    bm.to_mesh(me)
    bm.free()
    me.transform(Matrix.Diagonal((2 * hx / 100, 2 * hz / 100, hy / 100, 1.0)))
    ob = link(bpy.data.objects.new("pillow", me))
    ob.location = V(center)
    me.materials.append(material)
    me.shade_smooth()
    _cloth(ob, 0.3, 0.3, frames, pressure=pressure, self_collide=False)
    _settle([ob], rest_on, frames)
    sd = ob.modifiers.new("smooth", "SUBSURF")
    sd.levels = sd.render_levels = 1
    return ob


def cloth_sheet(center, size, material, res=1.8, noise=6.0, seed=1, name="sheet"):
    """A flat sheet `size` (w, d) centimetres, a thread every `res` cm, held
    level at `center` and a little crumpled, ready to be dropped."""
    w, d = size
    nx, nz = max(2, int(w / res)), max(2, int(d / res))
    rng = np.random.default_rng(seed)
    X, Z = np.meshgrid(
        np.linspace(-w / 2, w / 2, nx + 1), np.linspace(-d / 2, d / 2, nz + 1), indexing="ij"
    )
    Y = np.zeros_like(X)
    for _ in range(6):
        kx, kz = rng.normal(size=2) * 0.06
        Y += noise * np.sin(X * kx + Z * kz + rng.random() * 6.28) / 3
    pts = np.stack([X, Y, Z], axis=-1).reshape(-1, 3) + np.asarray(center, float)
    verts = np.stack([pts[:, 0] / 100, -pts[:, 2] / 100, pts[:, 1] / 100], axis=1)
    faces = [
        (i * (nz + 1) + k, (i + 1) * (nz + 1) + k, (i + 1) * (nz + 1) + k + 1, i * (nz + 1) + k + 1)
        for i in range(nx)
        for k in range(nz)
    ]
    return mesh_object(name, verts, faces, material)


def cloth_tube(center, axis, radius, height, material, name="tube", res=0.018):
    """An open ring of cloth round `axis` (Blender metres), its top edge in a
    vertex group `top` to hold it by. Starts `height` tall below `center`."""
    axis = np.asarray(axis, float) / np.linalg.norm(axis)
    a = np.cross(axis, [0.0, 1.0, 0.0])
    if np.linalg.norm(a) < 1e-3:
        a = np.cross(axis, [1.0, 0.0, 0.0])
    a /= np.linalg.norm(a)
    b = np.cross(axis, a)
    nu = max(12, int(2 * math.pi * radius / res))
    nv = max(4, int(height / res))
    verts = []
    for j in range(nv + 1):
        for i in range(nu):
            t = 2 * math.pi * i / nu
            verts.append(
                np.asarray(center)
                + (a * math.cos(t) + b * math.sin(t)) * radius
                - axis * height * j / nv
            )
    faces = [
        (j * nu + i, j * nu + (i + 1) % nu, (j + 1) * nu + (i + 1) % nu, (j + 1) * nu + i)
        for j in range(nv)
        for i in range(nu)
    ]
    ob = mesh_object(name, verts, faces, material)
    top = ob.vertex_groups.new(name="top")
    top.add(list(range(nu)), 1.0, "REPLACE")
    return ob


def cloth_wrap(centre, up, fwd, radius, top, spread, material, name="wrap", res=0.02, flare=1.7):
    """Cloth round a body's back and sides: an arc of `spread` degrees
    centred behind it (Blender metres), from its top edge - as high as `top`
    on the side `top` is on, a hand lower on the other - down to the floor,
    widening as it falls so it pools. The top edge is the vertex group `top`."""
    u = np.asarray(up, float) / np.linalg.norm(up)
    f = np.asarray(fwd, float) / np.linalg.norm(fwd)
    r = np.cross(f, u)
    c = np.asarray(centre, float)
    t_top = float((np.asarray(top) - c) @ u)
    side = float(np.sign((np.asarray(top) - c) @ r)) or 1.0
    reach = float(c[2]) / max(u[2], 0.3) + 0.02  # down to the floor along the trunk
    na = max(16, int(math.radians(spread) * radius * flare / res))
    nv = max(8, int((t_top + reach) / res))
    verts = []
    for j in range(nv + 1):
        for i in range(na + 1):
            th = math.radians(180.0 - spread / 2 + spread * i / na)
            s = math.sin(th) * side
            h_top = t_top - 0.14 * (1 - s) / 2
            h = h_top - (h_top + reach) * j / nv
            rad = radius * (1 + (flare - 1) * (j / nv) ** 2)
            verts.append(c + u * h + (f * math.cos(th) + r * math.sin(th)) * rad)
    faces = [
        (j * (na + 1) + i, j * (na + 1) + i + 1, (j + 1) * (na + 1) + i + 1, (j + 1) * (na + 1) + i)
        for j in range(nv)
        for i in range(na)
    ]
    ob = mesh_object(name, verts, faces, material)
    ob.vertex_groups.new(name="top").add(list(range(na + 1)), 1.0, "REPLACE")
    return ob


def drape(sheets, colliders, frames=45, mass=0.35, bend=0.6, thickness=0.6, pin=None, shrink=0.0):
    """Let cloth fall onto the colliders, freeze it where it lies, give it a
    thickness and smooth it."""
    for s in sheets:
        _cloth(s, mass, bend, frames, pin=pin, shrink=shrink)
    _settle(sheets, colliders, frames)
    for s in sheets:
        so = s.modifiers.new("thick", "SOLIDIFY")
        so.thickness = thickness / 100.0
        so.offset = 0.0
        sd = s.modifiers.new("smooth", "SUBSURF")
        sd.levels = sd.render_levels = 1


def window(wall_z, x0, x1, y0, y1, watts=900.0, color=(1.0, 0.97, 0.93), glow=6.0, sill=True):
    """A window in the back wall: bright panes behind a frame, and the
    daylight coming in through it."""
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    hx, hy = (x1 - x0) / 2, (y1 - y0) / 2
    paint = mat("paint", M.principled, "paint", (0.55, 0.52, 0.50), 0.35)
    pane = [
        V((x0, y0, wall_z + 0.2)),
        V((x1, y0, wall_z + 0.2)),
        V((x1, y1, wall_z + 0.2)),
        V((x0, y1, wall_z + 0.2)),
    ]
    mesh_object(
        "pane", pane, [(0, 1, 2, 3)], mat(f"pane{glow}", M.emit, "pane", color, glow), smooth=False
    )
    t = 3.0
    for c, h in [
        ((cx, y1 + t / 2, wall_z + 3), (hx + t, t / 2, 3)),
        ((cx, y0 - t / 2, wall_z + 3), (hx + t, t / 2, 3)),
        ((x0 - t / 2, cy, wall_z + 3), (t / 2, hy + t, 3)),
        ((x1 + t / 2, cy, wall_z + 3), (t / 2, hy + t, 3)),
        ((cx, cy, wall_z + 2.5), (1.4, hy, 2.5)),
        ((cx, y0 + (y1 - y0) * 0.58, wall_z + 2.5), (hx, 1.4, 2.5)),
    ]:
        box(c, h, paint, bevel=0.4, name="frame")
    if sill:
        box((cx, y0 - t - 2.0, wall_z + 7), (hx + 10, 2.0, 7), paint, bevel=0.5, name="sill")
    light = area(
        (cx, cy, wall_z + 8), (cx, cy - 20, wall_z + 200), color, watts,
        size=2 * hx, size_y=2 * hy, spread=160.0, name="daylight",
    )  # fmt: skip
    light.visible_camera = False
    return light


def blinds(light_pos, at, width=120.0, height=160.0, period=9.0, duty=0.5, gap=0.35):
    """Venetian blinds between a lamp and what it lights: real slats, so the
    stripes fall on the body and bend round it."""
    lp, ap = np.asarray(light_pos, float), np.asarray(at, float)
    c = lp + (ap - lp) * gap
    f = (ap - lp) / np.linalg.norm(ap - lp)
    right = np.cross(f, [0.0, 1.0, 0.0])
    right /= np.linalg.norm(right)
    up = np.cross(right, f)
    R = np.stack([right, up, -f], axis=1)
    slat = mat("slat", M.principled, "slat", (0.3, 0.28, 0.26), 0.6)
    for i in range(int(height // period)):
        y = -height / 2 + (i + 0.5) * period
        box(
            tuple(c + up * y),
            (width / 2, period * duty / 2, 0.3),
            slat,
            bevel=0.0,
            rot=R,
            name="slat",
        )


def halo(wall_z, x, y, color, watts, cone=60.0):
    """Light thrown on the wall behind a figure by a lamp at its back."""
    return spot(
        (x, y - 20, wall_z + 70),
        (x, y, wall_z),
        color,
        watts,
        radius=8.0,
        cone=cone,
        blend=1.0,
        name="halo",
    )


def chair(x, z, facing=0.0, seat=46.0, back=True):
    """A wooden chair whose sitter faces `facing` degrees (0 = the camera)."""
    wood = mat("chairwood", M.wood, (0.12, 0.075, 0.05), 0.4)
    t = math.radians(facing)
    fwd = np.array([math.sin(t), 0.0, math.cos(t)])
    side = np.array([math.cos(t), 0.0, -math.sin(t)])
    R = np.stack([side, [0.0, 1.0, 0.0], fwd], axis=1)
    c = np.array([x, seat - 2.0, z])
    box(tuple(c), (21.0, 2.0, 20.0), wood, bevel=0.8, rot=R, name="seat")
    for sx in (-18.0, 18.0):
        for sz in (-17.0, 17.0):
            foot = c + side * sx + fwd * sz
            top = foot.copy()
            foot[1] = 0.0
            cylinder(tuple(foot), tuple(top), 1.7, 1.9, wood, name="leg")
    if back:
        for sx in (-18.0, 18.0):
            a = c + side * sx - fwd * 18.0
            cylinder(
                tuple(a), tuple(a + np.array([0, 44.0, 0]) - fwd * 3.0), 1.9, 1.6, wood, name="post"
            )
        box(
            tuple(c - fwd * 21.0 + np.array([0, 40.0, 0])),
            (20.0, 4.0, 1.2),
            wood,
            bevel=0.6,
            rot=R,
            name="rail",
        )


def lamp(x, y, z, color=(1.0, 0.72, 0.52), watts=40.0, glow=3.0):
    """A table lamp with fabric over its shade: the shade glows, the bulb
    lights the room."""
    base = mat("lampbase", M.principled, "lampbase", (0.05, 0.04, 0.035), 0.3)
    cylinder((x, y, z), (x, y + 2.0, z), 7.0, 7.0, base, name="lampfoot")
    cylinder((x, y + 2.0, z), (x, y + 20.0, z), 1.0, 1.0, base, name="stem")
    shade = cylinder(
        (x, y + 16.0, z),
        (x, y + 36.0, z),
        15.0,
        10.0,
        mat(f"shade{color}", M.lampshade, color, glow),
        name="shade",
        caps=False,
    )
    shade.modifiers.new("thick", "SOLIDIFY").thickness = 0.004
    return point((x, y + 26.0, z), color, watts, radius=3.0, name="bulb")


def books(x, y, z, colors=((0.25, 0.08, 0.08), (0.07, 0.12, 0.18), (0.28, 0.22, 0.12))):
    top = y
    for i, colr in enumerate(colors):
        h = 3.0 - 0.3 * i
        box(
            (x + (i - 1) * 0.8, top + h, z),
            (12 - i, h, 9 - 0.4 * i),
            mat(f"book{colr}", M.principled, "book", colr, 0.55),
            bevel=0.3,
            name="book",
        )
        top += 2 * h
    return top


def phone(pos, yaw=-30.0, screen=(0.5, 0.75, 0.95)):
    """A phone standing on its edge, its screen lit."""
    t = math.radians(yaw)
    R = np.array([[math.cos(t), 0, math.sin(t)], [0, 1, 0], [-math.sin(t), 0, math.cos(t)]])
    box(
        pos,
        (0.45, 8.0, 3.8),
        mat("phone", M.principled, "phone", (0.01, 0.01, 0.012), 0.15),
        bevel=0.35,
        rot=R,
        name="phone",
    )
    face = np.asarray(pos, float) - R[:, 0] * 0.47
    box(
        tuple(face),
        (0.02, 7.2, 3.3),
        mat("screen", M.emit, "screen", screen, 2.0),
        bevel=0.0,
        rot=R,
        name="screen",
    )


def rug(center, half, color=(0.20, 0.12, 0.12)):
    m = mat(f"rug{color}", M.fabric, "rug", color, 0.8, 0.95, 300.0, 0.3, fuzz=0.3)
    return box(center, (half[0], 0.6, half[1]), m, bevel=0.5, name="rug")


def tub(center, half=(80.0, 26.0, 36.0), wall=7.0):
    """A bathtub: a ceramic shell with a rounded hollow."""
    ceramic = mat("ceramic", M.ceramic)
    outer = box(center, half, ceramic, bevel=8.0, segments=6, name="tub")
    inner = box(
        (center[0], center[1] + wall + 4, center[2]),
        (half[0] - wall, half[1], half[2] - wall),
        ceramic, bevel=10.0, segments=6, name="hollow",
    )  # fmt: skip
    b = outer.modifiers.new("hollow", "BOOLEAN")
    b.operation = "DIFFERENCE"
    b.object = inner
    b.solver = "EXACT"
    inner.hide_render = True
    inner.hide_viewport = True
    return outer

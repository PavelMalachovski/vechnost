"""Materials: skin, hair, cloth and the room, as Cycles node trees.

Everything is procedural - noise for pores and plaster, a brick pattern for
floorboards and tiles, a wave for wood grain and the twill of denim - so the
repository ships no textures and a picture is rebuilt from code alone.
"""

from __future__ import annotations

import math

import bpy


class Tree:
    """A small helper around a material's node tree."""

    def __init__(self, name):
        self.mat = bpy.data.materials.new(name)
        self.mat.use_nodes = True
        self.nt = self.mat.node_tree
        for n in list(self.nt.nodes):
            self.nt.nodes.remove(n)
        self.out = self.nt.nodes.new("ShaderNodeOutputMaterial")

    def node(self, kind, **inputs):
        """A node; `_name=` sets a property, any other keyword an input
        (a value, or a socket to link from)."""
        n = self.nt.nodes.new(kind)
        # Properties first: a node's sockets can depend on them (the skin
        # method is what gives the Principled BSDF its subsurface IOR).
        for k, v in inputs.items():
            if k.startswith("_"):
                setattr(n, k[1:], v)
        for k, v in inputs.items():
            if not k.startswith("_"):
                self.set(n, k, v)
        return n

    def set(self, node, name, value):
        sock = node.inputs[name]
        if isinstance(value, bpy.types.NodeSocket):
            self.nt.links.new(value, sock)
        elif isinstance(value, (tuple, list)) and len(value) == 3 and sock.type == "RGBA":
            sock.default_value = (*value, 1.0)
        else:
            sock.default_value = value

    def link(self, a, b):
        self.nt.links.new(a, b)

    def surface(self, shader):
        self.link(shader.outputs[0], self.out.inputs["Surface"])
        return self.mat

    def coords(self, kind="Object"):
        return self.node("ShaderNodeTexCoord").outputs[kind]


def _bump(t, height, strength, distance=0.002):
    return t.node("ShaderNodeBump", Strength=strength, Distance=distance, Height=height)


def _mix(t, fac, a, b):
    """A colour between a and b by `fac`."""
    m = t.node("ShaderNodeMix", _data_type="RGBA", Factor=fac)
    for sock, v in ((6, a), (7, b)):
        if isinstance(v, bpy.types.NodeSocket):
            t.link(v, m.inputs[sock])
        else:
            m.inputs[sock].default_value = (*v, 1.0)
    return m.outputs[2]


def principled(name, color, rough=0.5, **extra):
    t = Tree(name)
    b = t.node("ShaderNodeBsdfPrincipled", **{"Base Color": color, "Roughness": rough}, **extra)
    return t.surface(b)


def emit(name, color, strength):
    t = Tree(name)
    return t.surface(t.node("ShaderNodeEmission", Color=color, Strength=strength))


def plaster(color=(0.20, 0.17, 0.16)):
    """A painted wall: a faint mottle in the colour and a fine orange peel."""
    t = Tree("plaster")
    co = t.coords()
    big = t.node("ShaderNodeTexNoise", Vector=co, Scale=2.5, Detail=4.0, Roughness=0.5)
    fine = t.node("ShaderNodeTexNoise", Vector=co, Scale=180.0, Detail=2.0)
    col = _mix(t, big.outputs["Fac"], tuple(c * 0.86 for c in color), color)
    b = t.node("ShaderNodeBsdfPrincipled", **{"Base Color": col, "Roughness": 0.85})
    t.link(_bump(t, fine.outputs["Fac"], 0.08).outputs[0], b.inputs["Normal"])
    return t.surface(b)


def floorboards(color=(0.16, 0.10, 0.07), board=0.14, gloss=0.35, figure=0.35):
    """Oiled planks: boards of slightly different tone, grain along each."""
    t = Tree("floor")
    co = t.coords()
    brick = t.node(
        "ShaderNodeTexBrick",
        Vector=co,
        Scale=1.0,
        **{"Mortar Size": 0.0015, "Brick Width": 1.6, "Row Height": board, "Bias": 0.0},
        _offset=0.37,
    )
    brick.inputs["Color1"].default_value = (*color, 1)
    brick.inputs["Color2"].default_value = (*(c * 0.78 for c in color), 1)
    brick.inputs["Mortar"].default_value = (0.02, 0.012, 0.01, 1)
    grain = t.node(
        "ShaderNodeTexWave",
        Vector=co,
        Scale=45.0,
        Distortion=2.5,
        Detail=4.0,
        **{"Detail Scale": 2.0},
        _wave_type="BANDS",
        _bands_direction="X",
    )
    mul = t.node("ShaderNodeMix", _data_type="RGBA", _blend_type="MULTIPLY", Factor=figure)
    t.link(brick.outputs["Color"], mul.inputs[6])
    t.link(grain.outputs["Color"], mul.inputs[7])
    rough = t.node(
        "ShaderNodeMapRange",
        Value=grain.outputs["Fac"],
        **{"To Min": gloss, "To Max": gloss + 0.05},
    )
    b = t.node("ShaderNodeBsdfPrincipled", **{"Base Color": mul.outputs[2]})
    t.link(rough.outputs[0], b.inputs["Roughness"])
    t.link(_bump(t, brick.outputs["Fac"], 0.25, 0.004).outputs[0], b.inputs["Normal"])
    return t.surface(b)


def wood(color=(0.10, 0.06, 0.045), gloss=0.35):
    t = Tree("wood")
    grain = t.node(
        "ShaderNodeTexWave",
        Vector=t.coords(),
        Scale=4.0,
        Distortion=7.0,
        Detail=3.0,
        _wave_type="BANDS",
        _bands_direction="Z",
    )
    col = _mix(t, grain.outputs["Fac"], tuple(c * 0.7 for c in color), color)
    return t.surface(t.node("ShaderNodeBsdfPrincipled", **{"Base Color": col, "Roughness": gloss}))


def fabric(name, color, sheen=0.6, rough=0.85, weave=900.0, bump=0.12, fuzz=0.0):
    """Woven cloth: a fine weave in the normal and the sheen of fibres."""
    t = Tree(name)
    co = t.coords()
    w1 = t.node(
        "ShaderNodeTexWave", Vector=co, Scale=weave, _wave_type="BANDS", _bands_direction="X"
    )
    w2 = t.node(
        "ShaderNodeTexWave", Vector=co, Scale=weave, _wave_type="BANDS", _bands_direction="Y"
    )
    cross = t.node("ShaderNodeMath", _operation="MULTIPLY")
    t.link(w1.outputs["Fac"], cross.inputs[0])
    t.link(w2.outputs["Fac"], cross.inputs[1])
    mottle = t.node("ShaderNodeTexNoise", Vector=co, Scale=20.0, Detail=3.0)
    col = _mix(t, mottle.outputs["Fac"], tuple(c * 0.9 for c in color), color)
    b = t.node(
        "ShaderNodeBsdfPrincipled",
        **{
            "Base Color": col,
            "Roughness": rough,
            "Sheen Weight": sheen,
            "Sheen Roughness": 0.4,
            "Specular IOR Level": 0.25,
        },
    )
    normal = _bump(t, cross.outputs[0], bump, 0.001)
    if fuzz > 0:
        n = t.node("ShaderNodeTexNoise", Vector=co, Scale=400.0, Detail=6.0, Roughness=0.8)
        fb = _bump(t, n.outputs["Fac"], fuzz, 0.002)
        t.link(normal.outputs[0], fb.inputs["Normal"])
        normal = fb
    t.link(normal.outputs[0], b.inputs["Normal"])
    return t.surface(b)


def terry(color=(0.80, 0.79, 0.76)):
    """A bath towel: soft loops that scatter the light, no shine at all."""
    return fabric("terry", color, sheen=1.0, rough=1.0, weave=300.0, bump=0.2, fuzz=0.6)


def garment(name, color, kind="satin", band=0.0, band_color=None):
    """A close-fitting garment cut from the body: its edge is where the
    `cut` field it carries crosses zero; a band that wide along the edge
    (a hem, a waistband) takes `band_color`."""
    t = Tree(name)
    attr = t.node("ShaderNodeAttribute", _attribute_name="cut", _attribute_type="GEOMETRY")
    cut = attr.outputs["Fac"]
    mask = t.node(
        "ShaderNodeMapRange",
        Value=cut,
        **{"From Min": -0.08, "From Max": 0.08},
        _interpolation_type="SMOOTHSTEP",
    )
    co = t.coords()
    if kind == "satin":
        col = color
        fabric_in = {
            "Roughness": 0.3,
            "Anisotropic": 0.5,
            "Sheen Weight": 0.6,
            "Sheen Tint": color,
            "Specular IOR Level": 0.7,
        }
    elif kind == "denim":
        twill = t.node(
            "ShaderNodeTexWave",
            Vector=co,
            Scale=520.0,
            _wave_type="BANDS",
            _bands_direction="DIAGONAL",
        )
        fade = t.node("ShaderNodeTexNoise", Vector=co, Scale=6.0, Detail=4.0)
        col = _mix(
            t,
            fade.outputs["Fac"],
            tuple(c * 0.75 for c in color),
            tuple(min(1, c * 1.6) for c in color),
        )
        fabric_in = {"Roughness": 0.9, "Sheen Weight": 0.5, "Specular IOR Level": 0.2}
    else:
        col = color
        fabric_in = {
            "Roughness": 0.8,
            "Sheen Weight": 0.3,
            "Sheen Tint": color,
            "Specular IOR Level": 0.3,
        }
    if band > 0:
        edge = t.node(
            "ShaderNodeMapRange",
            Value=cut,
            **{"From Min": band - 0.15, "From Max": band + 0.15, "To Min": 1.0, "To Max": 0.0},
        )
        col = _mix(t, edge.outputs[0], col, band_color or tuple(c * 0.5 for c in color))
    b = t.node("ShaderNodeBsdfPrincipled", **{"Base Color": col}, **fabric_in)
    if kind == "denim":
        t.link(_bump(t, twill.outputs["Fac"], 0.35, 0.0015).outputs[0], b.inputs["Normal"])
    else:
        weave = t.node("ShaderNodeTexNoise", Vector=co, Scale=900.0, Detail=2.0)
        t.link(_bump(t, weave.outputs["Fac"], 0.05, 0.0008).outputs[0], b.inputs["Normal"])
    clear = t.node("ShaderNodeBsdfTransparent")
    mix = t.node("ShaderNodeMixShader")
    t.link(mask.outputs[0], mix.inputs[0])
    t.link(clear.outputs[0], mix.inputs[1])
    t.link(b.outputs[0], mix.inputs[2])
    return t.surface(mix)


def ceramic(color=(0.82, 0.82, 0.80)):
    return principled("ceramic", color, 0.12, **{"Coat Weight": 0.6, "Coat Roughness": 0.05})


def tiles(color=(0.30, 0.32, 0.34), size=0.15):
    t = Tree("tiles")
    brick = t.node(
        "ShaderNodeTexBrick",
        Vector=t.coords(),
        Scale=1.0,
        **{"Mortar Size": 0.003, "Brick Width": size, "Row Height": size, "Bias": 0.0},
        _offset=0.0,
    )
    brick.inputs["Color1"].default_value = (*color, 1)
    brick.inputs["Color2"].default_value = (*(c * 0.92 for c in color), 1)
    brick.inputs["Mortar"].default_value = (0.5, 0.5, 0.48, 1)
    rough = t.node(
        "ShaderNodeMapRange", Value=brick.outputs["Fac"], **{"To Min": 0.7, "To Max": 0.08}
    )
    b = t.node("ShaderNodeBsdfPrincipled", **{"Base Color": brick.outputs["Color"]})
    t.link(rough.outputs[0], b.inputs["Roughness"])
    t.link(_bump(t, brick.outputs["Fac"], 0.3, 0.003).outputs[0], b.inputs["Normal"])
    return t.surface(b)


def lampshade(color=(1.0, 0.72, 0.52), glow=4.0):
    """Fabric over a lamp: light comes through it, warm."""
    t = Tree("shade")
    tr = t.node("ShaderNodeBsdfTranslucent", Color=color)
    e = t.node("ShaderNodeEmission", Color=color, Strength=glow)
    add = t.node("ShaderNodeAddShader")
    t.link(tr.outputs[0], add.inputs[0])
    t.link(e.outputs[0], add.inputs[1])
    return t.surface(add)


def skin(tone=(0.60, 0.40, 0.31), rough=0.56, wet=False, name="skin"):
    """Skin: light scattered deep and red beneath it, pores in the normal, a
    faint mottle and flush in the colour, a thin oily coat - and, wet, a film
    of water standing in drops."""
    t = Tree(name)
    co = t.coords()
    mottle = t.node("ShaderNodeTexNoise", Vector=co, Scale=14.0, Detail=6.0, Roughness=0.55)
    blush = t.node("ShaderNodeTexNoise", Vector=co, Scale=3.0, Detail=2.0)
    hi = (min(tone[0] * 1.06, 1.0), tone[1] * 1.02, tone[2] * 0.98)
    base = _mix(t, mottle.outputs["Fac"], tuple(c * 0.9 for c in tone), hi)
    red = t.node("ShaderNodeMix", _data_type="RGBA", _blend_type="MULTIPLY")
    flush = t.node(
        "ShaderNodeMapRange",
        Value=blush.outputs["Fac"],
        **{"From Min": 0.45, "From Max": 0.75, "To Max": 0.25},
    )
    t.link(flush.outputs[0], red.inputs[0])
    t.link(base, red.inputs[6])
    red.inputs[7].default_value = (1.0, 0.82, 0.80, 1.0)
    pores = t.node("ShaderNodeTexVoronoi", Vector=co, Scale=1400.0, _feature="F1", Randomness=1.0)
    fine = t.node("ShaderNodeTexNoise", Vector=co, Scale=700.0, Detail=4.0, Roughness=0.7)
    relief = t.node("ShaderNodeMath", _operation="ADD")
    t.link(pores.outputs["Distance"], relief.inputs[0])
    t.link(fine.outputs["Fac"], relief.inputs[1])
    rvar = t.node(
        "ShaderNodeMapRange",
        Value=fine.outputs["Fac"],
        **{"To Min": rough - 0.08, "To Max": rough + 0.08},
    )
    b = t.node(
        "ShaderNodeBsdfPrincipled",
        **{
            "Base Color": red.outputs[2],
            "Subsurface Weight": 1.0,
            "Subsurface Radius": (1.0, 0.36, 0.18),
            "Subsurface Scale": 0.012,
            "Subsurface IOR": 1.4,
            "Specular IOR Level": 0.5,
            "Coat Weight": 0.9 if wet else 0.06,
            "Coat Roughness": 0.04 if wet else 0.35,
            "Coat IOR": 1.33 if wet else 1.45,
        },
        _subsurface_method="RANDOM_WALK_SKIN",
    )
    t.link(rvar.outputs[0], b.inputs["Roughness"])
    bmp = _bump(t, relief.outputs[0], 0.035 if wet else 0.06, 0.0006)
    t.link(bmp.outputs[0], b.inputs["Normal"])
    if wet:
        drops = t.node("ShaderNodeTexVoronoi", Vector=co, Scale=90.0, _feature="SMOOTH_F1")
        shape = t.node(
            "ShaderNodeMapRange",
            Value=drops.outputs["Distance"],
            **{"From Max": 0.18, "To Min": 1.0, "To Max": 0.0},
        )
        db = _bump(t, shape.outputs[0], 0.25, 0.002)
        t.link(bmp.outputs[0], db.inputs["Normal"])
        t.link(db.outputs[0], b.inputs["Coat Normal"])
    return t.surface(b)


def hair(melanin=0.88, redness=0.35, rough=0.32, wet=False, name="hair"):
    t = Tree(name)
    h = t.node(
        "ShaderNodeBsdfHairPrincipled",
        Melanin=melanin,
        **{
            "Melanin Redness": redness,
            "Roughness": 0.16 if wet else rough,
            "Radial Roughness": 0.3 if wet else 0.55,
            "Coat": 0.2 if wet else 0.05,
            "IOR": 1.55,
            "Random Color": 0.12,
            "Random Roughness": 0.15,
        },
        _parametrization="MELANIN",
        _model="CHIANG",
    )
    return t.surface(h)


def eye(center, gaze=(0.0, -1.0, 0.0), iris=(0.10, 0.055, 0.03), name="eye"):
    """An eyeball: sclera, an iris and a pupil round the line of sight (in
    the eye's own rest coordinates), under a wet cornea."""
    t = Tree(name)
    co = t.coords("Object")
    sub = t.node("ShaderNodeVectorMath", _operation="SUBTRACT")
    t.link(co, sub.inputs[0])
    sub.inputs[1].default_value = tuple(center)
    unit = t.node("ShaderNodeVectorMath", _operation="NORMALIZE")
    t.link(sub.outputs[0], unit.inputs[0])
    dot = t.node("ShaderNodeVectorMath", _operation="DOT_PRODUCT")
    t.link(unit.outputs[0], dot.inputs[0])
    dot.inputs[1].default_value = tuple(gaze)

    def disc(deg_out, deg_in):
        m = t.node(
            "ShaderNodeMapRange",
            **{
                "From Min": math.cos(math.radians(deg_out)),
                "From Max": math.cos(math.radians(deg_in)),
            },
            _interpolation_type="SMOOTHSTEP",
        )
        t.link(dot.outputs["Value"], m.inputs["Value"])
        return m.outputs[0]

    ring = t.node("ShaderNodeTexNoise", Vector=co, Scale=900.0, Detail=2.0)
    iris_col = _mix(
        t, ring.outputs["Fac"], tuple(c * 0.6 for c in iris), tuple(min(c * 1.6, 1) for c in iris)
    )
    col = _mix(t, disc(33.0, 30.0), (0.72, 0.68, 0.64), iris_col)
    col = _mix(t, disc(12.0, 10.0), col, (0.005, 0.004, 0.004))
    b = t.node(
        "ShaderNodeBsdfPrincipled",
        **{
            "Base Color": col,
            "Roughness": 0.35,
            "Coat Weight": 1.0,
            "Coat Roughness": 0.02,
            "Coat IOR": 1.376,
            "Subsurface Weight": 0.2,
            "Subsurface Radius": (0.4, 0.2, 0.2),
            "Subsurface Scale": 0.002,
        },
    )
    return t.surface(b)

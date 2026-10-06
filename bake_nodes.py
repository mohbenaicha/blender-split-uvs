"""Shared bake helpers: which image to read, and how Cycles should bake.

The node-rewiring helpers that used to live here were superseded by
`bake_material.build_pass_material`, which builds a throwaway material per pass
instead of mutating the artist's material. Nothing called them any more.
"""


def source_image_of(material):
    """The image feeding Base Color, which is the atlas being resampled.

    Falls back to the first image texture node in the tree when Base Color is not
    wired, so a material with a non-standard graph still bakes something.
    """
    if material is None or not material.use_nodes:
        return None
    principled = next(
        (n for n in material.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None
    )
    if principled is not None:
        socket = principled.inputs.get("Base Color")
        if socket is not None:
            for link in socket.links:
                if link.from_node.type == 'TEX_IMAGE' and link.from_node.image:
                    return link.from_node.image
    for node in material.node_tree.nodes:
        if node.type == 'TEX_IMAGE' and node.image:
            return node.image
    return None


def bake_settings(scene):
    """Switch the scene to Cycles and configure it for a texture bake.

    Cycles is the only engine that implements `bpy.ops.object.bake`; EEVEE raises
    "Current render engine does not support baking". Callers are responsible for
    restoring `scene.render.engine` afterwards.

    The sample count is clamped because a bake reads deterministic shader values
    rather than simulating light transport, so extra samples only cost time.
    """
    scene.render.engine = 'CYCLES'
    scene.cycles.samples = min(scene.cycles.samples, 4)
    scene.cycles.use_denoising = False
    settings = scene.render.bake
    settings.target = 'IMAGE_TEXTURES'
    settings.use_selected_to_active = False
    settings.use_clear = True
    settings.use_split_materials = False
    settings.margin_type = 'EXTEND'
    settings.save_mode = 'INTERNAL'
    return settings

"""Material node plumbing for baking.

Every mutation here is destructive to the material, so callers must snapshot the
node tree first (see `nodes.snapshot`/`nodes.restore`) and restore it afterwards.
This module deliberately contains no policy about when that happens.
"""

import bpy

TARGET_NODE_NAME = "UVREPACK_BAKE_TARGET"


def activate_target(material) -> None:
    """Make the bake target the tree's only selected and active node.

    Cycles bakes into the active image texture node. Any node added after it is
    selected by default, which steals that status and silently bakes nothing --
    so this must be re-asserted after every rewiring step.
    """
    node_tree = getattr(material, "node_tree", None)
    if node_tree is None:
        return
    target = node_tree.nodes.get(TARGET_NODE_NAME)
    if target is None:
        return
    # Order matters: assigning `active` clears other nodes' selection, so the
    # target must be selected *after* it becomes active, not before.
    node_tree.nodes.active = target
    for node in node_tree.nodes:
        node.select = node is target


def source_image_of(material):
    """The image feeding Base Color, which is the atlas being resampled.

    Returns the first image texture node in the tree when Base Color is not
    wired, so a material with a non-standard graph still bakes something.
    """
    if not material.use_nodes:
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


def ensure_target_image(material, image) -> None:
    """Add or update the image node Cycles writes into.

    Cycles bakes into the image node that is *active* in the node tree, so this
    node must also be made active.
    """
    node_tree = material.node_tree
    node = node_tree.nodes.get(TARGET_NODE_NAME)
    if node is None:
        node = node_tree.nodes.new('ShaderNodeTexImage')
        node.name = TARGET_NODE_NAME
        node.label = "UV Repack bake target"
        node.location = (-900, -400)
        node.hide = True
    node.image = image
    activate_target(material)


def remove_target_image(material) -> None:
    node_tree = material.node_tree
    node = node_tree.nodes.get(TARGET_NODE_NAME)
    if node is not None:
        node_tree.nodes.remove(node)


def separate_channel(node_tree, material, source_image, channel: str | None) -> None:
    """Route one channel of `source_image` into the material output as emission.

    `channel` None means the whole RGB value is emitted (Base Color). A channel
    letter isolates one scalar through a Separate Color node, which is how the
    R/G/B parts of a packed ORM map are baked independently.
    """
    output = next(
        (n for n in node_tree.nodes if n.type == 'OUTPUT_MATERIAL'), None
    )
    if output is None:
        raise ValueError(f"{material.name}: material has no output node")

    source = next(
        (n for n in node_tree.nodes if n.type == 'TEX_IMAGE' and n.image is source_image),
        None,
    )
    if source is None:
        source = node_tree.nodes.new('ShaderNodeTexImage')
        source.image = source_image

    emission = node_tree.nodes.new('ShaderNodeEmission')

    if channel is None:
        node_tree.links.new(source.outputs["Color"], emission.inputs["Color"])
    else:
        split = node_tree.nodes.new('ShaderNodeSeparateColor')
        node_tree.links.new(source.outputs["Color"], split.inputs["Color"])
        node_tree.links.new(split.outputs[channel], emission.inputs["Color"])

    for link in list(output.inputs["Surface"].links):
        node_tree.links.remove(link)
    node_tree.links.new(emission.outputs["Emission"], output.inputs["Surface"])

    # Adding nodes selected them, so the bake target lost active status.
    activate_target(material)


def bake_settings(scene):
    """Bake settings, with sample count clamped.

    A bake reads deterministic shader values, not light transport, so a high
    sample count only costs time.
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

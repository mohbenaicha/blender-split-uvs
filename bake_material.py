"""Materials built from scratch for one bake pass.

Rather than rewiring the artist's material and fighting Blender's node
active/select state, each pass gets a throwaway material containing exactly two
nodes: the image to bake into, and an emission shader carrying the value to
write. Nodes are created in that order, so the image node is the tree's active
node by construction and no selection juggling is needed.

The source atlas is only *referenced* by the emission shader, never modified.
"""

import bpy

BAKE_MATERIAL_PREFIX = "UVREPACK_BAKE_"


def build_pass_material(name: str, source_image, target_image, channel: str | None):
    """A material that emits one value from `source_image` into `target_image`.

    `channel` None emits the whole RGB value; a channel name isolates one scalar
    through a Separate Color node, which is how the R/G/B parts of a packed ORM
    map are baked separately.
    """
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    node_tree = material.node_tree
    node_tree.nodes.clear()

    # Created first, so Blender makes it the active node on its own.
    target = node_tree.nodes.new('ShaderNodeTexImage')
    target.name = "BAKE_TARGET"
    target.image = target_image
    target.location = (-600, 0)

    output = node_tree.nodes.new('ShaderNodeOutputMaterial')
    output.location = (300, 0)

    emission = node_tree.nodes.new('ShaderNodeEmission')
    emission.location = (0, 0)

    source = node_tree.nodes.new('ShaderNodeTexImage')
    source.name = "SOURCE"
    source.image = source_image
    source.location = (-900, 0)

    if channel is None:
        node_tree.links.new(source.outputs["Color"], emission.inputs["Color"])
    else:
        split = node_tree.nodes.new('ShaderNodeSeparateColor')
        split.location = (-300, 0)
        node_tree.links.new(source.outputs["Color"], split.inputs["Color"])
        node_tree.links.new(split.outputs[channel], emission.inputs["Color"])

    node_tree.links.new(emission.outputs["Emission"], output.inputs["Surface"])

    node_tree.nodes.active = target
    return material


def free_pass_material(material) -> None:
    """Remove a throwaway material and anything it owned."""
    if material is None:
        return
    images = [
        node.image
        for node in getattr(material, "node_tree", None).nodes
        if node.type == 'TEX_IMAGE' and node.image
    ] if material.use_nodes else []
    bpy.data.materials.remove(material)
    for image in images:
        if image.users == 0:
            bpy.data.images.remove(image)

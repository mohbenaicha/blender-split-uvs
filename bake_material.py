"""Materials for baking, and for the result the bake leaves behind.

Two jobs live here:

- `build_pass_material` makes a throwaway material that emits one value from the
  source atlas, so Cycles can bake it into a target image. Created with the
  target image node first, which makes it the tree's active node by construction
  and avoids fighting Blender's node active/select state.
- `build_result_material` makes the material the user keeps: the baked base
  colour, normal and ORM images wired back into a Principled BSDF, so the object
  looks the same as before the repack.
"""

import bpy

BAKE_MATERIAL_PREFIX = "UVREPACK_BAKE_"
RESULT_MATERIAL_SUFFIX = "_repacked"


def build_pass_material(
    name: str,
    source_image,
    target_image,
    channel: str | None,
    source_uv_layer: str | None = None,
):
    """A material that emits one value from `source_image` into `target_image`.

    `channel` None emits the whole RGB value; a channel name isolates one scalar
    through a Separate Color node, which is how the R/G/B parts of a packed ORM
    map are baked separately.

    `source_uv_layer` is the layer the source image must be read through -- the
    preserved pre-repack atlas mapping. Without it the image would be sampled at
    the packed coordinates and the bake would copy the wrong part of the atlas.
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

    if source_uv_layer:
        uv_node = node_tree.nodes.new('ShaderNodeUVMap')
        uv_node.uv_map = source_uv_layer
        uv_node.location = (-1150, 0)
        node_tree.links.new(uv_node.outputs["UV"], source.inputs["Vector"])

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
    """Remove a throwaway material, leaving its images alone.

    The images are the bake results and outlive the scaffolding, so they are
    deliberately not removed here.
    """
    if material is None:
        return
    for node in list(getattr(material, "node_tree", None).nodes):
        if node.type == 'TEX_IMAGE':
            node.image = None
    bpy.data.materials.remove(material)


def _resolve_image(value):
    """Accept an image datablock or its name, so callers can use either."""
    if value is None:
        return None
    if isinstance(value, str):
        return bpy.data.images.get(value)
    return value


def _add_image_node(node_tree, image, location):
    node = node_tree.nodes.new('ShaderNodeTexImage')
    node.image = image
    node.location = location
    return node


def orm_channels_are_separate(source_material) -> bool:
    """Whether the source splits a packed map into roughness and metallic.

    If it does not, the baked ORM image's green and blue carry whatever the
    source had, so wiring them to Roughness and Metallic would be wrong.
    """
    if source_material is None or not source_material.use_nodes:
        return False
    principled = next(
        (n for n in source_material.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'),
        None,
    )
    if principled is None:
        return False
    for socket_name in ("Roughness", "Metallic"):
        socket = principled.inputs.get(socket_name)
        if socket is None:
            continue
        for link in socket.links:
            if link.from_node.type == 'SEPARATE_COLOR':
                return True
    return False


def build_result_material(name: str, images: dict, split_orm: bool):
    """A Principled material driven by the baked images.

    `images` maps pass keys ("basecolor", "normal", "orm") to image names.
    Returns None when there is no base colour to show, since a material without
    it would render as flat grey and hide the bake entirely.
    """
    base_image = _resolve_image(images.get("basecolor"))
    if base_image is None:
        return None

    material = bpy.data.materials.new(name)
    material.use_nodes = True
    node_tree = material.node_tree
    node_tree.nodes.clear()

    output = node_tree.nodes.new('ShaderNodeOutputMaterial')
    output.location = (500, 0)
    principled = node_tree.nodes.new('ShaderNodeBsdfPrincipled')
    principled.location = (100, 0)
    node_tree.links.new(principled.outputs["BSDF"], output.inputs["Surface"])

    base = _add_image_node(node_tree, base_image, (-500, 300))
    node_tree.links.new(base.outputs["Color"], principled.inputs["Base Color"])

    normal_image = _resolve_image(images.get("normal"))
    if normal_image is not None:
        tex = _add_image_node(node_tree, normal_image, (-700, 0))
        # Do not touch tex.image.colorspace_settings here: assigning a colorspace
        # to an existing image frees its pixel buffer, which would blank the bake.
        normal_map = node_tree.nodes.new('ShaderNodeNormalMap')
        normal_map.location = (-300, 0)
        node_tree.links.new(tex.outputs["Color"], normal_map.inputs["Color"])
        node_tree.links.new(normal_map.outputs["Normal"], principled.inputs["Normal"])

    orm_image = _resolve_image(images.get("orm"))
    if orm_image is not None:
        tex = _add_image_node(node_tree, orm_image, (-700, -350))
        if split_orm:
            split = node_tree.nodes.new('ShaderNodeSeparateColor')
            split.location = (-350, -350)
            node_tree.links.new(tex.outputs["Color"], split.inputs["Color"])
            node_tree.links.new(split.outputs["Green"], principled.inputs["Roughness"])
            node_tree.links.new(split.outputs["Blue"], principled.inputs["Metallic"])

    return material


def apply_result_material(target, slot_index: int, material) -> None:
    """Assign a result material to one material slot, taking over the source slot.

    The original material is left in the file untouched, so the user can still
    get back to the atlas layout by reassigning it.
    """
    if material is None or slot_index >= len(target.material_slots):
        return
    target.material_slots[slot_index].material = material

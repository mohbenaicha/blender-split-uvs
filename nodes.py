"""Undo support for in-place material rewiring.

Baking needs the material to temporarily emit a specific value. Rewiring a node
tree is destructive, so every mutation is bracketed by a snapshot taken before
and a restore applied in a `finally`. Without this a failed bake would leave the
scene's materials silently rewritten.
"""

import bpy
from contextlib import contextmanager

SNAPSHOT_NAME = "UVREPACK_SNAPSHOT"


def snapshot(material) -> dict:
    """Record enough of a node tree to rebuild it exactly."""
    if not material.use_nodes:
        return {"use_nodes": False}

    node_tree = material.node_tree
    nodes = []
    for node in node_tree.nodes:
        record = {
            "name": node.name,
            # bl_idname ('ShaderNodeBsdfPrincipled') is what nodes.new() wants;
            # node.type ('BSDF_PRINCIPLED') is only an enum name and is rejected.
            "idname": node.bl_idname,
            "label": node.label,
            "location": tuple(node.location),
            "image": getattr(getattr(node, "image", None), "name", None),
            "inputs": {},
        }
        for socket in node.inputs:
            if socket.is_linked or not hasattr(socket, "default_value"):
                # Shader sockets carry no value to save, only links.
                continue
            record["inputs"][socket.identifier] = _read(socket)
        nodes.append(record)

    links = [
        (
            link.from_node.name,
            link.from_socket.identifier,
            link.to_node.name,
            link.to_socket.identifier,
        )
        for link in node_tree.links
    ]
    return {"use_nodes": True, "nodes": nodes, "links": links}


def _read(socket):
    value = socket.default_value
    try:
        return tuple(value)
    except TypeError:
        return value


def _write(socket, value):
    if isinstance(value, tuple):
        socket.default_value = value
    else:
        socket.default_value = value


def restore(material, data: dict) -> None:
    """Rebuild the node tree from a snapshot, dropping everything added since."""
    if not data.get("use_nodes"):
        material.use_nodes = False
        return

    material.use_nodes = True
    node_tree = material.node_tree
    node_tree.nodes.clear()

    for record in data["nodes"]:
        node = node_tree.nodes.new(record["idname"])
        if node is None:
            raise ValueError(f"could not rebuild node {record['name']} ({record['idname']})")
        node.name = record["name"]
        node.label = record["label"]
        node.location = record["location"]
        if record["image"]:
            node.image = bpy.data.images.get(record["image"])
        for identifier, value in record["inputs"].items():
            socket = node.inputs.get(identifier)
            if socket is not None and hasattr(socket, "default_value"):
                _write(socket, value)

    for from_node, from_socket, to_node, to_socket in data["links"]:
        source = node_tree.nodes.get(from_node)
        target = node_tree.nodes.get(to_node)
        if source is None or target is None:
            continue
        output = source.outputs.get(from_socket)
        input_ = target.inputs.get(to_socket)
        if output is not None and input_ is not None:
            node_tree.links.new(output, input_)


@contextmanager
def preserved(materials):
    """Restore every given material's node tree on exit, success or failure."""
    snapshots = [(material, snapshot(material)) for material in materials]
    try:
        yield
    finally:
        for material, data in snapshots:
            restore(material, data)


def bake_size_guard(resolution: int, object_count: int) -> int:
    """Bytes one bake tree holds at once: source images plus one output image.

    Only a rough figure -- the point is to refuse an obvious runaway before
    Blender allocates it, not to be exact.
    """
    per_image = resolution * resolution * 4
    return per_image * 2 * object_count


def recommended_resolution(uv_coverage: float, atlas_resolution: int) -> int:
    """Smallest power of two that preserves an object's existing texel density.

    An object holding `c` of the atlas owns `c * atlas^2` texels. A square image
    of side `atlas * sqrt(c)` holds the same count, so nothing is lost and
    smaller objects stop paying for space they never used.
    """
    exact = atlas_resolution * (max(uv_coverage, 0.0) ** 0.5)
    size = 64
    while size < exact:
        size *= 2
    return max(64, min(size, 8192))

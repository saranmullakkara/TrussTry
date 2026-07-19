"""
=====================================================================
  core/project_io.py

  Save/load a Model to/from a TrussTry project file (.json).

  Depends on: core.model, core.materials, core.sections
=====================================================================
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Union

from core.materials import Material, MATERIAL_LIBRARY, get_material
from core.sections import Section, SECTION_LIBRARY, get_section
from core.model import Model

PROJECT_FILE_VERSION = 1


def _material_to_dict(material: Material) -> Dict[str, Any]:
    # If it's a known library material, save it by name so re-loading
    # picks up any future library updates; otherwise inline the values.
    if MATERIAL_LIBRARY.get(material.name) == material:
        return {"ref": material.name}
    return {
        "name": material.name,
        "E": material.E,
        "yield_stress": material.yield_stress,
        "density": material.density,
    }


def _material_from_dict(d: Dict[str, Any]) -> Material:
    if "ref" in d:
        return get_material(d["ref"])
    return Material(
        name=d["name"],
        E=d["E"],
        yield_stress=d.get("yield_stress", 0.0),
        density=d.get("density", 0.0),
    )


def _section_to_dict(section: Section) -> Dict[str, Any]:
    if SECTION_LIBRARY.get(section.name) == section:
        return {"ref": section.name}
    return {
        "name": section.name,
        "area": section.area,
        "moment_of_inertia": section.moment_of_inertia,
    }


def _section_from_dict(d: Dict[str, Any]) -> Section:
    if "ref" in d:
        return get_section(d["ref"])
    return Section(
        name=d["name"],
        area=d["area"],
        moment_of_inertia=d.get("moment_of_inertia", 0.0),
    )


def model_to_dict(model: Model) -> Dict[str, Any]:
    """Serialize a Model to a plain JSON-able dict."""
    return {
        "version": PROJECT_FILE_VERSION,
        "nodes": [
            {"id": n.id, "x": n.x, "y": n.y} for n in model.nodes.values()
        ],
        "elements": [
            {
                "id": e.id,
                "node_i": e.node_i,
                "node_j": e.node_j,
                "material": _material_to_dict(e.material),
                "section": _section_to_dict(e.section),
                "type_name": e.type_name,
            }
            for e in model.elements.values()
        ],
        "boundary_conditions": [
            {"node_id": bc.node_id, "fix_x": bc.fix_x, "fix_y": bc.fix_y}
            for bc in model.boundary_conditions.values()
        ],
        "loads": [
            {"node_id": ld.node_id, "fx": ld.fx, "fy": ld.fy}
            for ld in model.loads.values()
        ],
    }


def model_from_dict(data: Dict[str, Any]) -> Model:
    """Deserialize a plain dict (as produced by model_to_dict) into a
    fresh Model instance."""
    model = Model()

    for n in data.get("nodes", []):
        node = model.add_node(n["x"], n["y"])
        # add_node() auto-assigns sequential ids; force it back to the
        # id that was actually saved so element references still line up.
        del model.nodes[node.id]
        node.id = n["id"]
        model.nodes[node.id] = node
    if model.nodes:
        model._next_node_id = max(model.nodes) + 1

    for e in data.get("elements", []):
        material = _material_from_dict(e["material"]) if "material" in e else None
        section = _section_from_dict(e["section"]) if "section" in e else None
        elem = model.add_element(e["node_i"], e["node_j"], material, section)
        del model.elements[elem.id]
        elem.id = e["id"]
        elem.type_name = e.get("type_name", "Truss2D")
        model.elements[elem.id] = elem
    if model.elements:
        model._next_elem_id = max(model.elements) + 1

    for bc in data.get("boundary_conditions", []):
        model.add_support(bc["node_id"], bc.get("fix_x", True), bc.get("fix_y", True))

    for ld in data.get("loads", []):
        model.add_load(ld["node_id"], ld.get("fx", 0.0), ld.get("fy", 0.0))

    return model


def save_project(model: Model, path: Union[str, Path]) -> None:
    """Write `model` to `path` as pretty-printed JSON."""
    path = Path(path)
    path.write_text(json.dumps(model_to_dict(model), indent=2))


def load_project(path: Union[str, Path]) -> Model:
    """Read a TrussTry project file and return a populated Model."""
    path = Path(path)
    data = json.loads(path.read_text())
    version = data.get("version")
    if version != PROJECT_FILE_VERSION:
        raise ValueError(
            f"Unsupported project file version {version!r} in {path} "
            f"(expected {PROJECT_FILE_VERSION!r})."
        )
    return model_from_dict(data)

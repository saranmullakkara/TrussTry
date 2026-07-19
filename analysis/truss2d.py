"""
=====================================================================
  analysis/truss2d.py

  Concrete 2D truss finite-element solver.

  This module ports the existing ``truss_solver.TrussSolver2D`` into
  the modular TrussTry architecture. Three things change from the
  original:

  1. **Subclasses core.solver.Solver** -- so anything that only needs
     to know "this is a solver" can type-hint against the abstract
     base class without importing numpy or this package.

  2. **Accepts a core.model.Model directly** via the class method
     ``from_model()``.  The lower-level dict/list constructor
     ``TrussSolver2D(nodes=..., elements=..., ...)`` is preserved
     unchanged so existing call sites and unit tests keep working.

  3. **Error classes re-exported from core.solver** -- callers that
     only import from ``core`` can catch ``SolverError`` /
     ``SingularStiffnessMatrixError`` / ``InvalidModelError`` without
     depending on this package.

  All finite-element mathematics is preserved exactly from the
  original ``truss_solver.py``.

  Depends on: core.solver, core.model, numpy
=====================================================================
"""

from __future__ import annotations

from typing import Any, Dict, Hashable, List, Optional, Tuple

import numpy as np

from core.model import Model
from core.solver import (
    Solver,
    SolverError,          # noqa: F401  (re-export for convenience)
    SingularStiffnessMatrixError,
    InvalidModelError,
)

NodeId = Hashable


class TrussSolver2D(Solver):
    """
    A GUI-safe, reusable 2D truss finite element solver.

    Every truss element is a two-force (axial-only) member. Each node
    has 2 degrees of freedom: translation in X and translation in Y.

    Construction
    ------------
    Preferred: use the ``from_model()`` class method to build a solver
    from a ``core.model.Model`` instance -- this is the path the GUI
    and analysis runners take.

    Alternatively, supply raw dicts/lists (the original API) -- useful
    for unit tests and standalone scripts:

        solver = TrussSolver2D(
            nodes={1: (0.0, 0.0), 2: (4.0, 0.0), 3: (2.0, 3.0)},
            elements=[
                {"node_i": 1, "node_j": 2, "E": 200e9, "A": 0.01},
                {"node_i": 2, "node_j": 3, "E": 200e9, "A": 0.01},
                {"node_i": 1, "node_j": 3, "E": 200e9, "A": 0.01},
            ],
            loads={3: (0.0, -10000.0)},
            boundary_conditions={1: (True, True), 2: (False, True)},
        )
        results = solver.solve()

    Public API
    ----------
    solve(deformation_scale=1.0) -> dict
        Runs the full analysis and returns a results dictionary (see
        ``solve()`` docstring for the exact schema).
    """

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def __init__(
        self,
        nodes: Dict[NodeId, Tuple[float, float]],
        elements: List[Dict],
        loads: Optional[Dict[NodeId, Tuple[float, float]]] = None,
        boundary_conditions: Optional[Dict[NodeId, Tuple[bool, bool]]] = None,
    ) -> None:
        self._nodes_raw = dict(nodes)
        self._elements_input = list(elements)
        self._loads_raw = dict(loads) if loads else {}
        self._bcs_raw = dict(boundary_conditions) if boundary_conditions else {}

        self._validate_inputs()
        self._build_internals()

    @classmethod
    def from_model(
        cls,
        model: Model,
        deformation_scale: float = 1.0,
    ) -> "TrussSolver2D":
        """
        Build a solver from a ``core.model.Model``.

        Parameters
        ----------
        model : Model
            Populated structural model (nodes, elements, supports,
            loads). Must have at least one node, one element, and
            enough boundary conditions to make the structure stable.
        deformation_scale : float, optional
            Not used during construction; stored so callers can pass
            it through to ``solve()`` without re-specifying it.

        Raises
        ------
        InvalidModelError
            If the model has no nodes or no elements.
        """
        nodes = {n.id: (n.x, n.y) for n in model.nodes.values()}
        elements = [
            {
                "id": e.id,
                "node_i": e.node_i,
                "node_j": e.node_j,
                "E": e.E,
                "A": e.A,
            }
            for e in model.elements.values()
        ]
        loads = {
            ld.node_id: (ld.fx, ld.fy)
            for ld in model.loads.values()
        }
        boundary_conditions = {
            bc.node_id: (bc.fix_x, bc.fix_y)
            for bc in model.boundary_conditions.values()
        }
        instance = cls(nodes, elements, loads, boundary_conditions)
        instance._default_deformation_scale = deformation_scale
        return instance

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate_inputs(self) -> None:
        if not self._nodes_raw:
            raise InvalidModelError("Model has no nodes.")
        if not self._elements_input:
            raise InvalidModelError("Model has no elements.")

        for pos, elem in enumerate(self._elements_input):
            for key in ("node_i", "node_j", "E", "A"):
                if key not in elem:
                    raise InvalidModelError(
                        f"Element at position {pos} is missing required key {key!r}."
                    )
            if elem["node_i"] not in self._nodes_raw:
                raise InvalidModelError(
                    f"Element at position {pos} references unknown node "
                    f"{elem['node_i']!r}."
                )
            if elem["node_j"] not in self._nodes_raw:
                raise InvalidModelError(
                    f"Element at position {pos} references unknown node "
                    f"{elem['node_j']!r}."
                )
            if elem["node_i"] == elem["node_j"]:
                raise InvalidModelError(
                    f"Element at position {pos} connects a node to itself "
                    f"({elem['node_i']!r})."
                )
            if elem["E"] <= 0:
                raise InvalidModelError(
                    f"Element at position {pos} has non-positive E ({elem['E']})."
                )
            if elem["A"] <= 0:
                raise InvalidModelError(
                    f"Element at position {pos} has non-positive A ({elem['A']})."
                )
            xi, yi = self._nodes_raw[elem["node_i"]]
            xj, yj = self._nodes_raw[elem["node_j"]]
            if np.hypot(xj - xi, yj - yi) == 0.0:
                raise InvalidModelError(
                    f"Element at position {pos} has zero length "
                    f"(nodes {elem['node_i']!r} and {elem['node_j']!r} "
                    f"share the same coordinates)."
                )

    # ------------------------------------------------------------------
    # Internal setup (called once in __init__)
    # ------------------------------------------------------------------

    def _build_internals(self) -> None:
        # Stable, contiguous 0-based node index (sorted by repr for
        # determinism when node ids are arbitrary hashables).
        self._node_ids: List[NodeId] = sorted(
            self._nodes_raw.keys(), key=repr
        )
        self._id_to_index: Dict[NodeId, int] = {
            nid: i for i, nid in enumerate(self._node_ids)
        }

        self.n_nodes: int = len(self._node_ids)
        self.n_dof: int = 2 * self.n_nodes

        self.node_coords: np.ndarray = np.array(
            [self._nodes_raw[nid] for nid in self._node_ids], dtype=float
        )

        # Element connectivity + material properties.
        self._element_ids: List[Hashable] = []
        elem_index_pairs: List[Tuple[int, int]] = []
        E_list: List[float] = []
        A_list: List[float] = []

        for pos, elem in enumerate(self._elements_input):
            eid = elem.get("id", pos)
            self._element_ids.append(eid)
            elem_index_pairs.append(
                (
                    self._id_to_index[elem["node_i"]],
                    self._id_to_index[elem["node_j"]],
                )
            )
            E_list.append(float(elem["E"]))
            A_list.append(float(elem["A"]))

        self.elements: np.ndarray = np.array(elem_index_pairs, dtype=int)
        self.n_elements: int = self.elements.shape[0]
        self.E: np.ndarray = np.array(E_list, dtype=float)
        self.A: np.ndarray = np.array(A_list, dtype=float)

        # Global load vector.
        self.f_global: np.ndarray = np.zeros(self.n_dof)
        for nid, (fx, fy) in self._loads_raw.items():
            if nid not in self._id_to_index:
                raise InvalidModelError(
                    f"Load references unknown node id: {nid!r}"
                )
            idx = self._id_to_index[nid]
            self.f_global[2 * idx] += float(fx)
            self.f_global[2 * idx + 1] += float(fy)

        # Fixed DOF set.
        fixed_dofs: List[int] = []
        for nid, (fix_x, fix_y) in self._bcs_raw.items():
            if nid not in self._id_to_index:
                raise InvalidModelError(
                    f"Boundary condition references unknown node id: {nid!r}"
                )
            idx = self._id_to_index[nid]
            if fix_x:
                fixed_dofs.append(2 * idx)
            if fix_y:
                fixed_dofs.append(2 * idx + 1)

        self.fixed_dofs: np.ndarray = np.array(
            sorted(set(fixed_dofs)), dtype=int
        )
        self.free_dofs: np.ndarray = np.setdiff1d(
            np.arange(self.n_dof), self.fixed_dofs
        )

        # Default deformation scale (may be overridden by from_model).
        self._default_deformation_scale: float = 1.0

    # ------------------------------------------------------------------
    # Public API (implements core.solver.Solver)
    # ------------------------------------------------------------------

    def solve(self, deformation_scale: Optional[float] = None, **kwargs) -> Dict[str, Any]:
        """
        Run the full 2D truss finite-element analysis.

        Parameters
        ----------
        deformation_scale : float, optional
            Multiplier applied to displacements *only* when computing
            ``"deformed_coords"``, for callers that want an exaggerated
            shape ready for plotting.  Defaults to the value supplied
            at construction time (1.0 unless ``from_model()`` was used
            with an explicit scale).  Has no effect on displacements,
            reactions, stress, strain, or axial force -- those are
            always physically exact.

        Returns
        -------
        dict with keys:
            ``"K_global"``            : (n_dof × n_dof) ndarray -- assembled
                                        global stiffness matrix before BCs
            ``"displacements"``       : dict[NodeId, (ux, uy)]
            ``"reactions"``           : dict[NodeId, (rx, ry)] -- nonzero
                                        only at constrained DOFs
            ``"element_stress"``      : dict[element_id, float]  (Pa)
            ``"element_strain"``      : dict[element_id, float]  (dimensionless)
            ``"element_axial_force"`` : dict[element_id, float]  (N; +tension/-compression)
            ``"deformed_coords"``     : dict[NodeId, (x, y)]

        Raises
        ------
        SingularStiffnessMatrixError
            If the reduced stiffness matrix is singular (structure is
            an unstable mechanism given the current boundary conditions).
        """
        scale = (
            deformation_scale
            if deformation_scale is not None
            else self._default_deformation_scale
        )

        K_global = self._assemble_global_stiffness()

        K_ff = K_global[np.ix_(self.free_dofs, self.free_dofs)]
        f_f = self.f_global[self.free_dofs]

        if K_ff.size == 0:
            # Every DOF is constrained: zero displacements, trivial case.
            u_f = np.zeros(0)
        else:
            try:
                if np.isclose(np.linalg.det(K_ff), 0.0):
                    raise np.linalg.LinAlgError("singular")
                u_f = np.linalg.solve(K_ff, f_f)
            except np.linalg.LinAlgError as exc:
                raise SingularStiffnessMatrixError(
                    "The reduced stiffness matrix K_ff is singular.  The "
                    "structure is an unstable mechanism given the current "
                    "boundary conditions -- check that enough DOFs are "
                    "constrained to prevent rigid-body motion."
                ) from exc

        u_global = np.zeros(self.n_dof)
        u_global[self.free_dofs] = u_f

        f_reactions_full = K_global @ u_global

        element_strain, element_stress, element_axial_force = (
            self._compute_element_response(u_global)
        )

        deformed = self.node_coords + scale * u_global.reshape(self.n_nodes, 2)

        displacements = {
            nid: (u_global[2 * i], u_global[2 * i + 1])
            for i, nid in enumerate(self._node_ids)
        }
        reactions = {
            nid: (f_reactions_full[2 * i], f_reactions_full[2 * i + 1])
            for i, nid in enumerate(self._node_ids)
            if (2 * i in self.fixed_dofs) or (2 * i + 1 in self.fixed_dofs)
        }
        deformed_coords = {
            nid: (deformed[i, 0], deformed[i, 1])
            for i, nid in enumerate(self._node_ids)
        }
        element_stress_by_id = {
            eid: element_stress[k] for k, eid in enumerate(self._element_ids)
        }
        element_strain_by_id = {
            eid: element_strain[k] for k, eid in enumerate(self._element_ids)
        }
        element_axial_force_by_id = {
            eid: element_axial_force[k] for k, eid in enumerate(self._element_ids)
        }

        return {
            "K_global": K_global,
            "displacements": displacements,
            "reactions": reactions,
            "element_stress": element_stress_by_id,
            "element_strain": element_strain_by_id,
            "element_axial_force": element_axial_force_by_id,
            "deformed_coords": deformed_coords,
        }

    # ------------------------------------------------------------------
    # Internal computation (math preserved exactly from truss_solver.py)
    # ------------------------------------------------------------------

    def _assemble_global_stiffness(self) -> np.ndarray:
        """
        Build each element's local 2×2 axial stiffness matrix,
        transform it into a 4×4 global-DOF stiffness contribution via
        K_elem = T^T @ k_local @ T, and superpose ("stamp") every
        element's contribution into the assembled global stiffness
        matrix K.
        """
        K_global = np.zeros((self.n_dof, self.n_dof))

        self._element_length = np.zeros(self.n_elements)
        self._element_T = np.zeros((self.n_elements, 2, 4))
        self._element_dof_map = np.zeros((self.n_elements, 4), dtype=int)

        for e in range(self.n_elements):
            ni, nj = self.elements[e]
            xi, yi = self.node_coords[ni]
            xj, yj = self.node_coords[nj]

            dx = xj - xi
            dy = yj - yi
            L = np.sqrt(dx**2 + dy**2)
            theta = np.arctan2(dy, dx)
            c = np.cos(theta)
            s = np.sin(theta)

            E_e = self.E[e]
            A_e = self.A[e]

            # Local 2×2 axial stiffness matrix.
            k_local = (E_e * A_e / L) * np.array(
                [[1.0, -1.0], [-1.0, 1.0]]
            )

            # 2×4 transformation matrix: global DOFs → local axial DOFs.
            T = np.array(
                [[c, s, 0.0, 0.0], [0.0, 0.0, c, s]]
            )

            # 4×4 global element stiffness: K_elem = T^T k_local T.
            K_elem = T.T @ k_local @ T

            dof_map = np.array([2 * ni, 2 * ni + 1, 2 * nj, 2 * nj + 1])

            K_global[np.ix_(dof_map, dof_map)] += K_elem

            self._element_length[e] = L
            self._element_T[e] = T
            self._element_dof_map[e] = dof_map

        return K_global

    def _compute_element_response(
        self, u_global: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Recover strain, stress, and axial force for every element
        from the solved global displacement vector.

            strain      = delta_L / L
            stress      = E * strain
            axial_force = stress * A   (+tension / −compression)
        """
        element_strain = np.zeros(self.n_elements)
        element_stress = np.zeros(self.n_elements)
        element_axial_force = np.zeros(self.n_elements)

        for e in range(self.n_elements):
            dof_map = self._element_dof_map[e]
            T = self._element_T[e]
            L = self._element_length[e]

            u_elem_global = u_global[dof_map]
            u_elem_local = T @ u_elem_global
            delta_L = u_elem_local[1] - u_elem_local[0]

            strain = delta_L / L
            stress = self.E[e] * strain
            axial_force = stress * self.A[e]

            element_strain[e] = strain
            element_stress[e] = stress
            element_axial_force[e] = axial_force

        return element_strain, element_stress, element_axial_force

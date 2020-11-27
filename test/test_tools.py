__copyright__ = "Copyright (C) 2013 Andreas Kloeckner"

__license__ = """
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
"""

import numpy as np
import numpy.linalg as la
import modepy as mp

import modepy.shapes as shp
import modepy.nodes as nd
import modepy.modes as md

from functools import partial
import pytest

import logging
logger = logging.getLogger(__name__)


# {{{ modal decay test functions

def jump(where, x):
    result = np.empty_like(x)
    result[x >= where] = 1
    result[x < where] = 0
    return result


def smooth_jump(where, x):
    return np.arctan(100*(x-where))/(0.5*np.pi)


def kink(where, x):
    result = np.empty_like(x)
    result[x >= where] = x[x >= where]
    result[x < where] = 0
    return result


def c1(where, x):
    result = np.empty_like(x)
    result[x >= where] = x[x >= where]**2
    result[x < where] = 0
    return result


def sample_polynomial(x):
    return 3*x**2 + 5*x + 3


def constant(x):
    return 5+0*x

# }}}


# {{{ test_modal_decay

@pytest.mark.parametrize(("case_name", "test_func", "dims", "n", "expected_expn"), [
    ("jump-1d", partial(jump, 0), 1, 10, -1),
    ("kink-1d", partial(kink, 0), 1, 10, -1.7),  # Slightly off from -2 (same in paper)  # noqa
    ("c1-1d", partial(c1, 0), 1, 10, -3),

    # Offset 1D tests
    ("offset-jump-1d", partial(jump, 0.8), 1, 20, -0.7),
    ("offset-kink-1d", partial(kink, 0.8), 1, 20, -0.7),  # boo
    ("offset-c1-1d", partial(c1, 0.8), 1, 20, -0.8),  # boo

    # 2D tests
    # A harsh jump introduces high-frequency wiggles transverse to the jump edge.
    # Therefore, use a smooth one.
    ("jump-2d", partial(smooth_jump, -0.1), 2, 15, -1.1),
    ("kink-2d", partial(kink, 0), 2, 15, -1.6),
    ("c1-2d", partial(c1, -0.1), 2, 15, -2.3),
    ])
def test_modal_decay(case_name, test_func, dims, n, expected_expn):
    shape = shp.Simplex(dims)
    nodes = mp.warp_and_blend_nodes(dims, n)
    basis = mp.orthonormal_basis_for_shape(shape, n)
    vdm = mp.vandermonde(basis.functions, nodes)

    f = test_func(nodes[0])
    coeffs = la.solve(vdm, f)

    if 0:
        from modepy.tools import plot_element_values
        plot_element_values(n, nodes, f, resample_n=70,
                show_nodes=True)

    from modepy.modal_decay import fit_modal_decay
    expn, _ = fit_modal_decay(coeffs.reshape(1, -1), dims, n)
    expn = expn[0]

    print(f"{case_name}: computed: {expn:g}, expected: {expected_expn:g}")
    assert abs(expn-expected_expn) < 0.1


@pytest.mark.parametrize(("case_name", "test_func", "dims", "n"), [
    ("sin-1d", np.sin, 1, 5),
    ("poly-1d", sample_polynomial, 1, 5),
    ("const-1d", constant, 1, 5),

    ("sin-2d", np.sin, 2, 5),
    ("poly-2d", sample_polynomial, 2, 5),
    ("const-2d", constant, 2, 5),
    ])
def test_residual_estimation(case_name, test_func, dims, n):
    shape = shp.Simplex(dims)

    def estimate_resid(inner_n):
        nodes = mp.warp_and_blend_nodes(dims, inner_n)
        basis = mp.orthonormal_basis_for_shape(shape, inner_n)
        vdm = mp.vandermonde(basis.functions, nodes)

        f = test_func(nodes[0])
        coeffs = la.solve(vdm, f)

        from modepy.modal_decay import estimate_relative_expansion_residual
        return estimate_relative_expansion_residual(
                coeffs.reshape(1, -1), dims, inner_n)

    resid = estimate_resid(n)
    resid2 = estimate_resid(2*n)
    print(f"{case_name}: {float(resid):g} -> {float(resid2):g}")
    assert resid2 < resid

# }}}


# {{{ test_resampling_matrix

@pytest.mark.parametrize("dims", [1, 2, 3])
@pytest.mark.parametrize("shape_cls", [shp.Simplex, shp.Hypercube])
def test_resampling_matrix(dims, shape_cls, ncoarse=5, nfine=10):
    shape = shape_cls(dims)

    coarse_nodes = nd.edge_clustered_nodes_for_shape(shape, ncoarse)
    coarse_basis = md.basis_for_shape(shape, ncoarse)

    fine_nodes = nd.edge_clustered_nodes_for_shape(shape, nfine)
    fine_basis = md.basis_for_shape(shape, nfine)

    my_eye = np.dot(
            mp.resampling_matrix(fine_basis.functions, coarse_nodes, fine_nodes),
            mp.resampling_matrix(coarse_basis.functions, fine_nodes, coarse_nodes))

    assert la.norm(my_eye - np.eye(len(my_eye))) < 3e-13

    my_eye_least_squares = np.dot(
            mp.resampling_matrix(coarse_basis.functions, coarse_nodes, fine_nodes,
                least_squares_ok=True),
            mp.resampling_matrix(coarse_basis.functions, fine_nodes, coarse_nodes),
            )

    assert la.norm(my_eye_least_squares - np.eye(len(my_eye_least_squares))) < 4e-13

# }}}


# {{{ test_diff_matrix

@pytest.mark.parametrize("dims", [1, 2, 3])
@pytest.mark.parametrize("shape_cls", [shp.Simplex, shp.Hypercube])
def test_diff_matrix(dims, shape_cls, order=5):
    shape = shape_cls(dims)

    nodes = nd.edge_clustered_nodes_for_shape(shape, order)
    basis = md.basis_for_shape(shape, order)

    diff_mat = mp.differentiation_matrices(basis.functions, basis.gradients, nodes)
    if isinstance(diff_mat, tuple):
        diff_mat = diff_mat[0]

    f = np.sin(nodes[0])

    df_dx = np.cos(nodes[0])
    df_dx_num = np.dot(diff_mat, f)

    error = la.norm(df_dx - df_dx_num) / la.norm(df_dx)
    logger.info("error: %.5e", error)
    assert error < 2.0e-4, error


@pytest.mark.parametrize("dims", [2, 3])
def test_diff_matrix_permutation(dims):
    shape = shp.Simplex(dims)
    order = 5

    from pytools import \
            generate_nonnegative_integer_tuples_summing_to_at_most as gnitstam
    node_tuples = list(gnitstam(order, dims))

    simplex_onb = mp.orthonormal_basis_for_shape(shape, order)
    nodes = np.array(mp.warp_and_blend_nodes(dims, order, node_tuples=node_tuples))
    diff_matrices = mp.differentiation_matrices(
            simplex_onb.functions, simplex_onb.gradients, nodes)

    for iref_axis in range(dims):
        perm = mp.diff_matrix_permutation(node_tuples, iref_axis)

        assert la.norm(
                diff_matrices[iref_axis]
                - diff_matrices[0][perm][:, perm]) < 1e-10

# }}}


# {{{ face mass matrices (deprecated)

@pytest.mark.parametrize("dims", [2, 3])
def test_deprecated_modal_face_mass_matrix(dims, order=3):
    # FIXME DEPRECATED remove along with modal_face_mass_matrix (>=2022)
    shape = shp.Simplex(dims)

    vertices = shp.biunit_vertices_for_shape(shape)
    basis = md.basis_for_shape(shape, order - 1)

    from modepy.matrices import modal_face_mass_matrix
    for face in shp.faces_for_shape(shape):
        face_vertices = vertices[:, face.volume_vertex_indices]

        fmm = modal_face_mass_matrix(
                basis.functions, order, face_vertices)
        fmm2 = modal_face_mass_matrix(
                basis.functions, order+1, face_vertices)

        error = la.norm(fmm - fmm2, np.inf) / la.norm(fmm2, np.inf)
        logger.info("fmm error: %.5e", error)
        assert error < 1e-11, f"error {error:.5e} on face {face.face_index}"

        fmm[np.abs(fmm) < 1e-13] = 0
        nnz = np.sum(fmm > 0)

        logger.info("fmm: nnz %d\n%s", nnz, fmm)


@pytest.mark.parametrize("dims", [2, 3])
def test_deprecated_nodal_face_mass_matrix(dims, order=3):
    # FIXME DEPRECATED remove along with nodal_face_mass_matrix (>=2022)
    volume = shp.Simplex(dims)

    vertices = shp.biunit_vertices_for_shape(volume)
    volume_nodes = nd.edge_clustered_nodes_for_shape(volume, order)
    volume_basis = md.basis_for_shape(volume, order)

    from modepy.matrices import nodal_face_mass_matrix
    for face in shp.faces_for_shape(volume):
        face_nodes = nd.edge_clustered_nodes_for_shape(face, order)
        face_vertices = vertices[:, face.volume_vertex_indices]

        fmm = nodal_face_mass_matrix(
                volume_basis.functions, volume_nodes,
                face_nodes, order, face_vertices)
        fmm2 = nodal_face_mass_matrix(
                volume_basis.functions,
                volume_nodes, face_nodes, order+1, face_vertices)

        error = la.norm(fmm - fmm2, np.inf) / la.norm(fmm2, np.inf)
        logger.info("fmm error: %.5e", error)
        assert error < 5e-11, f"error {error:.5e} on face {face.face_index}"

        fmm[np.abs(fmm) < 1e-13] = 0
        nnz = np.sum(fmm > 0)

        logger.info("fmm: nnz %d\n%s", nnz, fmm)

    logger.info("mass matrix:\n%s", mp.mass_matrix(
        md.basis_for_shape(face, order).functions,
        nd.edge_clustered_nodes_for_shape(face, order)))

# }}}


# {{{ face mass matrices

@pytest.mark.parametrize("dims", [2, 3])
@pytest.mark.parametrize("shape_cls", [shp.Simplex, shp.Hypercube])
def test_modal_mass_matrix_for_face(dims, shape_cls, order=3):
    shape = shape_cls(dims)

    vol_basis = md.basis_for_shape(shape, order)

    from modepy.matrices import modal_mass_matrix_for_face
    for face in shp.faces_for_shape(shape):
        face_basis = md.basis_for_shape(face, order)
        fmm = modal_mass_matrix_for_face(
                face, face_basis.functions, vol_basis.functions, order)
        fmm2 = modal_mass_matrix_for_face(
                face, face_basis.functions, vol_basis.functions, order+1)

        error = la.norm(fmm - fmm2, np.inf) / la.norm(fmm2, np.inf)
        logger.info("fmm error: %.5e", error)
        assert error < 1e-11, f"error {error:.5e} on face {face.face_index}"

        fmm[np.abs(fmm) < 1e-13] = 0
        nnz = np.sum(fmm > 0)

        logger.info("fmm: nnz %d\n%s", nnz, fmm)


@pytest.mark.parametrize("dims", [2, 3])
@pytest.mark.parametrize("shape_cls", [shp.Simplex, shp.Hypercube])
def test_nodal_mass_matrix_for_face(dims, shape_cls, order=3):
    volume = shape_cls(dims)
    face = shape_cls(dims - 1)

    volume_nodes = nd.edge_clustered_nodes_for_shape(volume, order)
    volume_basis = md.basis_for_shape(volume, order)
    face_nodes = nd.edge_clustered_nodes_for_shape(face, order)

    from modepy.matrices import nodal_mass_matrix_for_face
    for face in shp.faces_for_shape(volume):
        face_basis = md.basis_for_shape(face, order)
        fmm = nodal_mass_matrix_for_face(
                face, face_basis.functions, volume_basis.functions,
                volume_nodes, face_nodes, order)
        fmm2 = nodal_mass_matrix_for_face(
                face, face_basis.functions, volume_basis.functions,
                volume_nodes, face_nodes, order+1)

        error = la.norm(fmm - fmm2, np.inf) / la.norm(fmm2, np.inf)
        logger.info("fmm error: %.5e", error)
        assert error < 5e-11, f"error {error:.5e} on face {face.face_index}"

        fmm[np.abs(fmm) < 1e-13] = 0
        nnz = np.sum(fmm > 0)

        logger.info("fmm: nnz %d\n%s", nnz, fmm)

    logger.info("mass matrix:\n%s", mp.mass_matrix(
        md.basis_for_shape(face, order).functions,
        nd.edge_clustered_nodes_for_shape(face, order)))

# }}}


# {{{ test_estimate_lebesgue_constant

@pytest.mark.parametrize("dims", [1, 2])
@pytest.mark.parametrize("order", [3, 5, 8])
@pytest.mark.parametrize("shape_cls", [shp.Simplex, shp.Hypercube])
def test_estimate_lebesgue_constant(dims, order, shape_cls, visualize=False):
    logging.basicConfig(level=logging.INFO)
    shape = shape_cls(dims)

    nodes = nd.edge_clustered_nodes_for_shape(shape, order)

    from modepy.tools import estimate_lebesgue_constant
    lebesgue_constant = estimate_lebesgue_constant(order, nodes, shape=shape)
    logger.info("%s-%d/%s: %.5e", shape, dims, order, lebesgue_constant)

    if not visualize:
        return

    from modepy.tools import _evaluate_lebesgue_function
    lebesgue, equi_node_tuples, equi_nodes = \
            _evaluate_lebesgue_function(order, nodes, shape)

    import matplotlib.pyplot as plt
    fig = plt.figure()
    ax = fig.gca()
    ax.grid()

    if dims == 1:
        ax.plot(equi_nodes[0], lebesgue)
        ax.set_xlabel("$x$")
        ax.set_ylabel(fr"$\lambda_{order}$")
    elif dims == 2:
        ax.plot(nodes[0], nodes[1], "ko")
        p = ax.tricontourf(equi_nodes[0], equi_nodes[1], lebesgue, levels=16)
        fig.colorbar(p)
        ax.set_xlim([-1.1, 1.1])
        ax.set_ylim([-1.1, 1.1])
        ax.set_aspect("equal")
    else:
        raise ValueError(f"unsupported dimension: {dims}")

    shape_name = shape_cls.__name__.lower()
    fig.savefig(f"estimate_lebesgue_constant_{shape_name}_{dims}_order_{order}")

# }}}


# {{{ test_hypercube_submesh

@pytest.mark.parametrize("dims", [2, 3, 4])
def test_hypercube_submesh(dims):
    from modepy.tools import submesh_for_shape
    from pytools import generate_nonnegative_integer_tuples_below as gnitb
    shape = shp.Hypercube(dims)

    node_tuples = list(gnitb(3, dims))

    for i, nt in enumerate(node_tuples):
        logger.info("[%4d] nodes %s", i, nt)

    assert len(node_tuples) == 3**dims

    elements = submesh_for_shape(shape, node_tuples)

    for e in elements:
        logger.info("element: %s", e)

    assert len(elements) == 2**dims

# }}}


# You can test individual routines by typing
# $ python test_tools.py 'test_routine()'

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        exec(sys.argv[1])
    else:
        from pytest import main
        main([__file__])

# vim: fdm=marker

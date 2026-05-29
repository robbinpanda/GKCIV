"""Constitutive models for soft-body elasticity.

Provides both Taichi kernels (for MPM) and NumPy functions (for FEM).
Supported models:
  - Neo-Hookean
  - Corotated Linear
"""

import numpy as np
import taichi as ti


# =====================================================================
# Taichi helpers for MPM
# =====================================================================

@ti.func
def neo_hookean_pf_ft(F, mu, la):
    """Neo-Hookean: return P * F^T for MLS-MPM P2G.

    Strain energy:
        W = mu/2 * (I1 - 3) - mu * ln(J) + la/2 * (ln(J))^2

    First PK stress:
        P = mu * (F - F^{-T}) + la * ln(J) * F^{-T}

    P*F^T = mu * (F*F^T - I) + la * ln(J) * I
    """
    J = F.determinant()
    J = ti.max(J, 0.01)
    lnJ = ti.log(J)
    I = ti.Matrix.identity(ti.f32, 3)
    return mu * (F @ F.transpose() - I) + la * lnJ * I


@ti.func
def corotated_pf_ft(F, mu, la):
    """Corotated Linear: return P * F^T for MLS-MPM P2G.

    First PK stress:
        P = 2*mu*(F - R) + la*(J - 1)*J*F^{-T}

    P*F^T = 2*mu*(F - R)*F^T + la*(J - 1)*J*I
    """
    U, sig, V = ti.svd(F)
    R = U @ V.transpose()
    J = sig[0, 0] * sig[1, 1] * sig[2, 2]
    J = ti.max(J, 0.01)
    return 2.0 * mu * (F - R) @ F.transpose() + la * (J - 1.0) * J * ti.Matrix.identity(ti.f32, 3)


@ti.func
def neo_hookean_energy_density(F, mu, la):
    """Neo-Hookean strain energy density W (per unit volume)."""
    J = F.determinant()
    J = ti.max(J, 0.01)
    lnJ = ti.log(J)
    I1 = (F @ F.transpose()).trace()
    return 0.5 * mu * (I1 - 3.0) - mu * lnJ + 0.5 * la * lnJ * lnJ


@ti.func
def corotated_energy_density(F, mu, la):
    """Corotated Linear strain energy density W (per unit volume)."""
    U, sig, V = ti.svd(F)
    R = U @ V.transpose()
    J = sig[0, 0] * sig[1, 1] * sig[2, 2]
    J = ti.max(J, 0.01)
    diff = F - R
    # Frobenius norm squared
    frob_sq = (
        diff[0, 0] * diff[0, 0] + diff[0, 1] * diff[0, 1] + diff[0, 2] * diff[0, 2]
        + diff[1, 0] * diff[1, 0] + diff[1, 1] * diff[1, 1] + diff[1, 2] * diff[1, 2]
        + diff[2, 0] * diff[2, 0] + diff[2, 1] * diff[2, 1] + diff[2, 2] * diff[2, 2]
    )
    return mu * frob_sq + 0.5 * la * (J - 1.0) * (J - 1.0)


# =====================================================================
# NumPy helpers for FEM
# =====================================================================


def neo_hookean_pk1(F: np.ndarray, mu: float, la: float) -> np.ndarray:
    """Neo-Hookean first PK stress P (3x3), for FEM force computation.

    P = mu * (F - F^{-T}) + la * ln(J) * F^{-T}
    """
    J = float(np.linalg.det(F))
    if abs(J) < 1e-12:
        return np.zeros((3, 3), dtype=F.dtype)
    J = max(J, 0.01)
    F_inv_T = np.linalg.inv(F).T
    return mu * (F - F_inv_T) + la * np.log(J) * F_inv_T


def neo_hookean_pk1_and_energy(F: np.ndarray, mu: float, la: float) -> tuple[np.ndarray, float]:
    """Return (P, energy_density) for Neo-Hookean."""
    J = float(np.linalg.det(F))
    if abs(J) < 1e-12:
        return np.zeros((3, 3), dtype=F.dtype), 0.0
    J = max(J, 0.01)
    F_inv_T = np.linalg.inv(F).T
    P = mu * (F - F_inv_T) + la * np.log(J) * F_inv_T
    I1 = float(np.trace(F @ F.T))
    w = 0.5 * mu * (I1 - 3.0) - mu * np.log(J) + 0.5 * la * (np.log(J) ** 2)
    return P, w


def corotated_pk1(F: np.ndarray, mu: float, la: float) -> np.ndarray:
    """Corotated linear first PK stress P (3x3), for FEM force computation.

    P = 2*mu*(F - R) + la*(J - 1)*J*F^{-T}
    """
    U, s, Vt = np.linalg.svd(F)
    R = U @ Vt
    if np.linalg.det(R) < 0.0:
        U[:, -1] *= -1.0
        R = U @ Vt
    J = float(np.linalg.det(F))
    if abs(J) < 1e-12:
        return np.zeros((3, 3), dtype=F.dtype)
    J = max(J, 0.01)
    F_inv_T = np.linalg.inv(F).T
    return 2.0 * mu * (F - R) + la * (J - 1.0) * J * F_inv_T


def corotated_pk1_and_energy(F: np.ndarray, mu: float, la: float) -> tuple[np.ndarray, float]:
    """Return (P, energy_density) for Corotated Linear."""
    U, s, Vt = np.linalg.svd(F)
    R = U @ Vt
    if np.linalg.det(R) < 0.0:
        U[:, -1] *= -1.0
        R = U @ Vt
    J = float(np.linalg.det(F))
    if abs(J) < 1e-12:
        return np.zeros((3, 3), dtype=F.dtype), 0.0
    J = max(J, 0.01)
    F_inv_T = np.linalg.inv(F).T
    P = 2.0 * mu * (F - R) + la * (J - 1.0) * J * F_inv_T
    w = mu * np.sum((F - R) ** 2) + 0.5 * la * (J - 1.0) ** 2
    return P, w

"""Independent real-linear forward solve for the high-side mixing branch.

Input c stores physical diagonal reflections and input-referred off-diagonal
coefficients. No calibration or inverse-extraction routines are used here.
LO phase gauge is zero; arbitrary absolute LO phase is not identified by SOL.
"""
import numpy as np


def high_side_waves(c, source_match, drive, load=None):
    """Solve a=drive+E*b, with an optional physical output termination.

    b1=c11*a1+c12*conj(a2); b2=conj(c21)*conj(a1)+c22*a2.
    Shapes: c=(N,2,2), source_match=(N,2), drive=(N,2,K).
    Returns physical b waves (N,2,K).
    """
    n = len(c)
    e = np.array(source_match, dtype=complex, copy=True)
    if load is not None:
        e[:, 1] = load
    a = np.broadcast_to(np.eye(4, dtype=complex), (n, 4, 4)).copy()
    b = np.zeros_like(a)
    # z=[a1,a2,b1,b2], A*z+B*conj(z)=q.
    a[:, 0, 2] = -e[:, 0]; a[:, 1, 3] = -e[:, 1]
    a[:, 2, 0] = -c[:, 0, 0]; a[:, 3, 1] = -c[:, 1, 1]
    b[:, 2, 1] = -c[:, 0, 1]; b[:, 3, 0] = -c[:, 1, 0].conj()
    q = np.zeros((n, 4, drive.shape[-1]), complex)
    q[:, :2] = drive
    system = np.concatenate((
        np.concatenate(((a+b).real, -(a-b).imag), axis=2),
        np.concatenate(((a+b).imag, (a-b).real), axis=2)), axis=1)
    if not np.isfinite(system).all() or np.any(np.linalg.cond(system) > 1e12):
        raise ValueError('高边 LO 正向波量方程病态。')
    x = np.linalg.solve(system, np.concatenate((q.real, q.imag), axis=1))
    result = (x[:, :4] + 1j*x[:, 4:])[:, 2:]
    if not np.isfinite(result).all():
        raise ValueError('高边 LO 正向波量产生非有限值。')
    return result


def high_side_measurement(c, box1, box2):
    n = len(c)
    drive = np.zeros((n, 2, 2), complex)
    drive[:, 0, 0] = box1[2]; drive[:, 1, 1] = box2[2]
    waves = high_side_waves(c, np.column_stack((box1[1], box2[1])), drive)
    result = np.stack((box1[2], box2[2]), axis=1)[:, :, None]*waves
    result[:, 0, 0] += box1[0]; result[:, 1, 1] += box2[0]
    return result

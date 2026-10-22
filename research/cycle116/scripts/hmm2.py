"""Two-state Gaussian HMM (diagonal covariances), multi-sequence EM fit,
forward filtering. Scalar-math forward-backward (2 states) for speed.
Features per symbol: standardized H1 log returns and log high-low ranges
(standardization from the discovery period 2016-2024 of that symbol).
Fit on discovery only; filtering runs forward over the full series."""
import os, pickle, math
import numpy as np
import pandas as pd
import ovl_lib as L

CACHE = '/home/hatch/workspace/fx/work_ovl/cache/hmm_sep.pkl'


def features(sym):
    g = L.h1(sym)
    r = np.log(g['Close']).diff()
    rng = np.log(g['High'] / g['Low'])
    X = pd.DataFrame({'r': r, 'rng': rng}).dropna()
    disc = X.loc['2016-01-01':'2024-12-31']
    mu, sd = disc.mean(), disc.std()
    return (X - mu) / sd


def _emit(Z, mu, var):
    """T x 2 emission densities (unnormalized ok: we rescale)."""
    lp = np.empty((len(Z), 2))
    for k in range(2):
        lp[:, k] = -0.5 * (math.log(2 * math.pi * var[k][0] * var[k][1])
                           + (Z[:, 0] - mu[k][0]) ** 2 / var[k][0]
                           + (Z[:, 1] - mu[k][1]) ** 2 / var[k][1])
    lp -= lp.max(axis=1, keepdims=True)
    return np.exp(lp)


def _fb(Z, pi, A, mu, var):
    B = _emit(Z, mu, var)
    T = len(Z)
    a00, a01, a10, a11 = A[0][0], A[0][1], A[1][0], A[1][1]
    alpha = np.empty((T, 2))
    c = np.empty(T)
    s = pi[0] * B[0, 0] + pi[1] * B[0, 1]
    alpha[0, 0] = pi[0] * B[0, 0] / s
    alpha[0, 1] = pi[1] * B[0, 1] / s
    c[0] = s
    for t in range(1, T):
        v0 = (alpha[t - 1, 0] * a00 + alpha[t - 1, 1] * a10) * B[t, 0]
        v1 = (alpha[t - 1, 0] * a01 + alpha[t - 1, 1] * a11) * B[t, 1]
        s = v0 + v1
        alpha[t, 0] = v0 / s
        alpha[t, 1] = v1 / s
        c[t] = s
    beta = np.ones((T, 2))
    for t in range(T - 2, -1, -1):
        b0 = (a00 * B[t + 1, 0] * beta[t + 1, 0]
              + a01 * B[t + 1, 1] * beta[t + 1, 1]) / c[t + 1]
        b1 = (a10 * B[t + 1, 0] * beta[t + 1, 0]
              + a11 * B[t + 1, 1] * beta[t + 1, 1]) / c[t + 1]
        beta[t, 0] = b0
        beta[t, 1] = b1
    gamma = alpha * beta
    gamma /= gamma.sum(axis=1, keepdims=True)
    # xi sums
    xi = np.zeros((2, 2))
    for t in range(T - 1):
        m00 = alpha[t, 0] * a00 * B[t + 1, 0] * beta[t + 1, 0]
        m01 = alpha[t, 0] * a01 * B[t + 1, 1] * beta[t + 1, 1]
        m10 = alpha[t, 1] * a10 * B[t + 1, 0] * beta[t + 1, 0]
        m11 = alpha[t, 1] * a11 * B[t + 1, 1] * beta[t + 1, 1]
        s = m00 + m01 + m10 + m11
        if s > 0:
            xi[0, 0] += m00 / s
            xi[0, 1] += m01 / s
            xi[1, 0] += m10 / s
            xi[1, 1] += m11 / s
    return gamma, xi, float(np.log(c).sum())


def fit(symbols, max_iter=15):
    seqs = {}
    for s in symbols:
        Z = features(s)
        seqs[s] = Z.loc[:'2024-12-31'].to_numpy(float)
    pi = np.array([0.5, 0.5])
    A = np.array([[0.97, 0.03], [0.03, 0.97]])
    mu = np.array([[-0.4, -0.4], [0.4, 0.4]])
    var = np.ones((2, 2))
    prev = -np.inf
    for it in range(max_iter):
        gs, xs, ll = [], [], 0.0
        for s, Z in seqs.items():
            g, x, l = _fb(Z, pi, A, mu, var)
            gs.append((Z, g))
            xs.append(x)
            ll += l
        xi = sum(xs)
        A = xi / xi.sum(axis=1, keepdims=True)
        pi = np.mean([g[0] for _, g in gs], axis=0)
        for k in range(2):
            w = np.concatenate([g[:, k] for _, g in gs])
            Xall = np.concatenate([Z for Z, _ in gs])
            mu[k] = (w[:, None] * Xall).sum(axis=0) / w.sum()
            var[k] = (w[:, None] * (Xall - mu[k]) ** 2).sum(axis=0) / w.sum()
            var[k] = np.maximum(var[k], 1e-3)
        print(f'EM iter {it}: loglik {ll:.1f}', flush=True)
        if abs(ll - prev) < 1e-4 * max(1.0, abs(ll)):
            prev = ll
            break
        prev = ll
    return dict(pi=pi, A=A, mu=mu, var=var, loglik=prev, iters=it + 1)


def filter_probs(sym, params):
    Zf = features(sym)
    Z = Zf.to_numpy(float)
    pi, A, mu, var = params['pi'], params['A'], params['mu'], params['var']
    B = _emit(Z, mu, var)
    T = len(Z)
    out = np.empty((T, 2))
    a0 = pi[0] * B[0, 0]
    a1 = pi[1] * B[0, 1]
    s = a0 + a1
    a0, a1 = a0 / s, a1 / s
    out[0] = (a0, a1)
    for t in range(1, T):
        v0 = (a0 * A[0][0] + a1 * A[1][0]) * B[t, 0]
        v1 = (a0 * A[0][1] + a1 * A[1][1]) * B[t, 1]
        s = v0 + v1
        a0, a1 = v0 / s, v1 / s
        out[t] = (a0, a1)
    return pd.DataFrame(out, index=Zf.index, columns=['s0', 's1'])


def build(symbols):
    params = fit(symbols)
    probs = {s: filter_probs(s, params) for s in symbols}
    with open(CACHE, 'wb') as f:
        pickle.dump({'params': {k: params[k] for k in ['pi', 'A', 'mu', 'var']},
                     'probs': probs}, f)
    return params, probs


def load(symbols):
    if os.path.exists(CACHE):
        with open(CACHE, 'rb') as f:
            d = pickle.load(f)
        return d['params'], d['probs']
    return build(symbols)


if __name__ == '__main__':
    import json
    syms = set()
    for m in ['Sep']:
        for p in [L.MONTHS[m][2], L.MONTHS[m][3]]:
            syms |= set(pd.read_csv(p, usecols=['symbol'])['symbol'])
    params, _ = build(sorted(syms))
    print('A', params['A'].round(3).tolist(), 'mu', params['mu'].round(2).tolist())

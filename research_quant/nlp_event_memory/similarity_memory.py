from __future__ import annotations
import numpy as np

def softmax_distance_weights(distances, temperature: float = 0.25):
    values = np.asarray(distances, dtype=float)
    if not len(values): return values
    logits = -values / max(float(temperature), 1e-9)
    logits -= np.max(logits)
    weights = np.exp(logits)
    return weights / max(weights.sum(), 1e-12)

def cosine_distances(query, matrix):
    q = np.asarray(query, dtype=float).reshape(1, -1)
    m = np.asarray(matrix, dtype=float)
    qn = np.linalg.norm(q, axis=1); mn = np.linalg.norm(m, axis=1)
    similarity = (m @ q.T).ravel() / np.maximum(mn * qn[0], 1e-12)
    return 1.0 - np.clip(similarity, -1, 1)

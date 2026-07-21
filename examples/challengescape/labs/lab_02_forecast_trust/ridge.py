"""Plain-Python ridge regression + rank statistics for the forecast-trust lab.

No numpy: the design is 8 features, so normal equations with Gaussian
elimination are exact and instant. Features and target are centered/scaled on
the training statistics; the intercept is therefore unpenalized by
construction (predictions add the target mean back).
"""
from __future__ import annotations


def solve(a: list[list[float]], b: list[float]) -> list[float]:
    """Gaussian elimination with partial pivoting; a is modified in place."""
    n = len(a)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(m[r][col]))
        if abs(m[piv][col]) < 1e-12:
            m[piv][col] = 1e-12
        m[col], m[piv] = m[piv], m[col]
        for r in range(col + 1, n):
            f = m[r][col] / m[col][col]
            for c in range(col, n + 1):
                m[r][c] -= f * m[col][c]
    x = [0.0] * n
    for r in range(n - 1, -1, -1):
        s = m[r][n] - sum(m[r][c] * x[c] for c in range(r + 1, n))
        x[r] = s / m[r][r]
    return x


class Scaler:
    def __init__(self, X: list[list[float]], y: list[float]):
        n, d = len(X), len(X[0])
        self.x_mean = [sum(row[j] for row in X) / n for j in range(d)]
        self.x_std = []
        for j in range(d):
            var = sum((row[j] - self.x_mean[j]) ** 2 for row in X) / n
            self.x_std.append(var ** 0.5 or 1.0)
        self.y_mean = sum(y) / n

    def transform(self, X: list[list[float]]) -> list[list[float]]:
        return [
            [(v - m) / s for v, m, s in zip(row, self.x_mean, self.x_std)]
            for row in X
        ]


def fit_ridge(Xs: list[list[float]], yc: list[float], lam: float) -> list[float]:
    """Coefficients on standardized features against centered target."""
    d = len(Xs[0])
    xtx = [[sum(r[i] * r[j] for r in Xs) for j in range(d)] for i in range(d)]
    for i in range(d):
        xtx[i][i] += lam
    xty = [sum(r[i] * yv for r, yv in zip(Xs, yc)) for i in range(d)]
    return solve(xtx, xty)


def ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    r = [0.0] * len(values)
    for rank, i in enumerate(order):
        r[i] = float(rank)
    return r


def spearman(a: list[float], b: list[float]) -> float:
    ra, rb = ranks(a), ranks(b)
    n = len(a)
    d2 = sum((x - y) ** 2 for x, y in zip(ra, rb))
    return 1.0 - 6.0 * d2 / (n * (n * n - 1))

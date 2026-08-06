"""Is a torn knot torn in the data, or only in its 3-d shadow?

Runs the pipeline's own tearing test (galaxy.py::torn_clusters) twice over the same
knots: once on the shipped 3-d positions, once on the shipped 8-d point features (a
PCA of the standardised 32-d critic space, 60.9 % of its variance, rows unit-normalised).

The implication that matters runs one way: a separation that survives a *linear*
projection to 8-d exists in the 32-d space too, so "torn in 8-d" proves "torn in 32-d".
"Whole in 8-d" is weaker — PCA can fold two blobs together — so it is reported as
"no evidence of a tear above 8-d", not as proof of one blob.
"""

import json
import numpy as np
from sklearn.cluster import KMeans

ROOT = "app/static/lyrebird"

pts = json.load(open(f"{ROOT}/points.json"))
n = pts["n"]
cid = np.asarray(pts["clusterId"], dtype=np.int32)
src = np.asarray(pts["source"])

pos3 = np.fromfile(f"{ROOT}/positions.f32", dtype="<f4").reshape(n, 3).astype(np.float64)
lo8 = np.fromfile(f"{ROOT}/point-features.f32", dtype="<f4").reshape(n, 8).astype(np.float64)

k = int(cid.max()) + 1
print(f"{n} points, {k} knots, positions {pos3.shape}, features {lo8.shape}")


def ratio(members: np.ndarray) -> tuple[float, np.ndarray] | None:
    """The pipeline's gap/spread ratio for one knot, plus the 2-means labels."""
    if len(members) < 12:
        return None
    km = KMeans(n_clusters=2, n_init=4, random_state=0).fit(members)
    a, b = members[km.labels_ == 0], members[km.labels_ == 1]
    if len(a) < 3 or len(b) < 3:
        return None
    gap = float(np.linalg.norm(a.mean(axis=0) - b.mean(axis=0)))
    spread = 0.5 * (
        float(np.linalg.norm(a - a.mean(axis=0), axis=1).mean())
        + float(np.linalg.norm(b - b.mean(axis=0), axis=1).mean())
    )
    return gap / max(spread, 1e-9), km.labels_


rows = []
order = np.argsort(cid, kind="stable")
starts = np.searchsorted(cid[order], np.arange(k))
ends = np.searchsorted(cid[order], np.arange(k), side="right")

for c in range(k):
    idx = order[starts[c] : ends[c]]
    if len(idx) < 12:
        continue
    r3 = ratio(pos3[idx])
    r8 = ratio(lo8[idx])
    if r3 is None or r8 is None:
        continue
    # Does the 3-d split follow the field/synthetic seam?
    lab3 = r3[1]
    is_field = src[idx] == "field"
    side_a_field = is_field[lab3 == 0].mean() if (lab3 == 0).any() else 0.0
    side_b_field = is_field[lab3 == 1].mean() if (lab3 == 1).any() else 0.0
    rows.append((c, len(idx), r3[0], r8[0], abs(side_a_field - side_b_field), is_field.mean()))

arr = np.asarray([(r[1], r[2], r[3], r[4], r[5]) for r in rows])
size, t3, t8, seam, fieldshare = arr.T
print(f"\nmeasured knots (>=12 members, both splits valid): {len(rows)}")
print(f"3-d  torn (>5): {(t3 > 5).sum():5d}   severe (>8): {(t3 > 8).sum():5d}   median {np.median(t3):.3f}")
print(f"8-d  torn (>5): {(t8 > 5).sum():5d}   severe (>8): {(t8 > 8).sum():5d}   median {np.median(t8):.3f}")

torn3 = t3 > 5
print(f"\nof the {torn3.sum()} knots torn in 3-d:")
print(f"  also torn in 8-d      : {(torn3 & (t8 > 5)).sum():5d}   <- torn in the data, no projection fixes these")
print(f"  whole in 8-d          : {(torn3 & (t8 <= 5)).sum():5d}   <- torn only by the projection")
print(f"  8-d ratio median      : {np.median(t8[torn3]):.3f} (null is ~2)")
print(f"  median members        : {np.median(size[torn3]):.0f}")
print(f"  mixed field/synthetic : {(fieldshare[torn3] < 0.999).sum()} of {torn3.sum()}")
print(f"  split follows source  : {(seam[torn3] > 0.8).sum()} (|field share A - field share B| > 0.8)")

whole3 = ~torn3
print(f"\nof the {whole3.sum()} knots whole in 3-d: torn in 8-d anyway: {(whole3 & (t8 > 5)).sum()}")
print("  (a real split the 3-d projection folds shut — invisible in the picture)")

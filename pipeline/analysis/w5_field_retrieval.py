"""The arms scored on ONE query population: the 160 279 real field points.

Dropping renders changes which points exist, so retrieval over "all points" is not
comparable across arms. Field points are in every arm unchanged, and they are also the
population the question is about — a bird sings, and a recorded syllable must light its
own knot.
"""
import sys, time
from pathlib import Path

import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from w5_label_arms import load, cluster_names, unit
from lyrebird_pipeline.galaxy import FIELD_SOURCE, PointSet, cluster_plan, label_assign, type_seeds
from sklearn.cluster import KMeans

z, pts = load()

def field_retrieval(zq, pts_all, centres, names):
    uc = unit(np.asarray(centres, dtype=np.float64))
    named = np.asarray(names, dtype=object)
    idx = [i for i, (sy, s) in enumerate(zip(pts_all.syllable_id, pts_all.source))
           if sy and s == FIELD_SOURCE]
    uz = unit(zq[idx])
    own = [(pts_all.species_id[i], pts_all.syllable_id[i]) for i in idx]
    hit = 0
    for lo in range(0, uz.shape[0], 4096):
        near = (uz[lo:lo + 4096] @ uc.T).argmax(axis=1)
        for j, c in enumerate(near):
            hit += tuple(named[c]) == own[lo + j]
    return hit / len(idx), len(idx)

rows = []
k = cluster_plan(pts, z)["k"]
init, _, _ = type_seeds(z, pts, k, seed=0)
t0 = time.time(); km = KMeans(n_clusters=k, init=init, n_init=1, random_state=0).fit(z); dt = time.time() - t0
names = cluster_names(km.labels_.astype(int), pts, k)
r, n = field_retrieval(z, pts, km.cluster_centers_, names)
rows.append(("kmeans, as shipped", len(pts.species_id), k, r, dt)); print(rows[-1], flush=True)

t0 = time.time(); cid, cen, kb, _ = label_assign(z, pts, seed=0); dt = time.time() - t0
names = cluster_names(cid, pts, kb)
r, n = field_retrieval(z, pts, cen, names)
rows.append(("label assignment", len(pts.species_id), kb, r, dt)); print(rows[-1], flush=True)

has_field = {(sp, sy) for sp, sy, s in zip(pts.species_id, pts.syllable_id, pts.source) if sy and s == FIELD_SOURCE}
keep = np.array([not (sy and s != FIELD_SOURCE and (sp, sy) in has_field)
                 for sp, sy, s in zip(pts.species_id, pts.syllable_id, pts.source)])
sub = PointSet(x=pts.x[keep],
               species_id=[v for v, m in zip(pts.species_id, keep) if m],
               syllable_id=[v for v, m in zip(pts.syllable_id, keep) if m],
               song_id=[v for v, m in zip(pts.song_id, keep) if m],
               duration=[v for v, m in zip(pts.duration, keep) if m],
               source=[v for v, m in zip(pts.source, keep) if m])
zs = z[keep]
t0 = time.time(); cid, cen, kc, _ = label_assign(zs, sub, seed=0); dt = time.time() - t0
names = cluster_names(cid, sub, kc)
r, n = field_retrieval(zs, sub, cen, names)
rows.append(("label + W5", len(sub.species_id), kc, r, dt)); print(rows[-1], flush=True)

kd = cluster_plan(sub, zs)["k"]
init, _, _ = type_seeds(zs, sub, kd, seed=0)
t0 = time.time(); km = KMeans(n_clusters=kd, init=init, n_init=1, random_state=0).fit(zs); dt = time.time() - t0
names = cluster_names(km.labels_.astype(int), sub, kd)
r, n = field_retrieval(zs, sub, km.cluster_centers_, names)
rows.append(("kmeans + W5", len(sub.species_id), kd, r, dt)); print(rows[-1], flush=True)

print("\n| arm | points | k | field-point type retrieval | clustering s |")
print("|---|---|---|---|---|")
for name, npts, kk, r, dt in rows:
    print(f"| {name} | {npts} | {kk} | {r:.4f} | {dt:.1f} |")
print(f"(query population: {n} field points, identical in every arm)")

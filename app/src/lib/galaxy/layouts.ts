/**
 * The cloud's one arrangement: the measured acoustic projection, with each knot
 * expanded about its own centre.
 *
 * There used to be a second arrangement that pulled the points apart into one island
 * per species, and a morph that animated between the two. It was removed — it was
 * buggy and is worth rethinking from scratch rather than patching — so what is left is
 * the layout where distance is a measurement, plus the plumbing the rest of the galaxy
 * reads positions from.
 */
import type { BirdyAssets } from '$lib/data/types';

/**
 * Where the cluster centroids are *right now*, shared between the point cloud (which
 * writes it) and the trajectory lines and node labels (which read it). A plain object
 * rather than reactive state: consumers rebuild geometry when `version` moves.
 */
export interface LayoutView {
	centroids: Float32Array;
	/**
	 * Members per cluster. A knot with zero members has no real position — its
	 * centroid collapses to (0,0,0), the centre of the box — so no positional effect
	 * (wave, grid cross, unmatched breath) may fire for it; they all check this.
	 */
	counts: Uint32Array;
	/** Bumped whenever `centroids` moves, so consumers know to rebuild geometry. */
	version: number;
}

export function createLayoutView(assets: BirdyAssets): LayoutView {
	return {
		centroids: Float32Array.from(assets.centroids.items.flatMap((c) => c.position)),
		counts: Uint32Array.from(assets.centroids.items.map((c) => c.count ?? 0)),
		version: 0
	};
}

export interface Layout {
	/** `3 * n`, xyz per point. */
	positions: Float32Array;
	/** `3 * k`, xyz per cluster centroid, recomputed for this arrangement. */
	centroids: Float32Array;
	/** Members per cluster, from the same pass. */
	counts: Uint32Array;
}

/**
 * Where each cluster's knot sits: the mean of its points.
 *
 * A cluster is fitted in the 28-d acoustic space, so its knot is the plain mean of
 * every point it holds. Every trajectory thread and every grid strike reads the same
 * array, so the knot has to sit on the points it names or all of them terminate in the
 * void. A cluster with NO members gets (0,0,0) from this arithmetic — the centre of
 * the box, a position that is a lie — which is why `counts` travels with the layout
 * and every positional effect checks it before firing.
 */
function centroidsOf(positions: Float32Array, clusterId: number[], k: number): Float32Array {
	const sums = new Float64Array(k * 3);
	const counts = new Uint32Array(k);
	for (let i = 0; i < clusterId.length; i++) {
		const c = clusterId[i];
		if (c < 0 || c >= k) continue;
		sums[c * 3] += positions[i * 3];
		sums[c * 3 + 1] += positions[i * 3 + 1];
		sums[c * 3 + 2] += positions[i * 3 + 2];
		counts[c]++;
	}
	const out = new Float32Array(k * 3);
	for (let c = 0; c < k; c++) {
		const n = Math.max(1, counts[c]);
		out[c * 3] = sums[c * 3] / n;
		out[c * 3 + 1] = sums[c * 3 + 1] / n;
		out[c * 3 + 2] = sums[c * 3 + 2] / n;
	}
	return out;
}

/**
 * Scale applied to each knot about its own centre. **1 means the projection is drawn as
 * it is, and that is the right default.**
 *
 * Scaling a cluster about its centre keeps the centre and the internal *arrangement*,
 * so the arithmetic is harmless, but the thing the shape was carrying is its extent —
 * how tightly 64 renders of one syllable agree, how far a field cluster sprawls.
 * Halving that drew every knot as a tight dot of the same size and the corpus stopped
 * having a form: the difference between a taut cluster and a loose one, which is real
 * and measured, was gone.
 *
 * Kept as a named constant rather than deleted so the reasoning survives with it. Anything
 * other than 1 is a lie about how much the members of a cluster agree.
 */
const CLUSTER_SPACING = 1;

function expandClusters(
	positions: Float32Array,
	clusterId: number[],
	k: number,
	factor: number
): Float32Array {
	if (factor === 1) return positions;
	const centres = centroidsOf(positions, clusterId, k);
	const out = new Float32Array(positions.length);
	for (let i = 0; i < clusterId.length; i++) {
		const c = clusterId[i];
		if (c < 0 || c >= k) {
			out[i * 3] = positions[i * 3];
			out[i * 3 + 1] = positions[i * 3 + 1];
			out[i * 3 + 2] = positions[i * 3 + 2];
			continue;
		}
		for (let a = 0; a < 3; a++) {
			const centre = centres[c * 3 + a];
			out[i * 3 + a] = centre + (positions[i * 3 + a] - centre) * factor;
		}
	}
	return out;
}

/**
 * The arrangement the galaxy draws. The positions are the projection with each knot
 * expanded about its own centre; the centroids are recomputed from the result rather
 * than taken from the manifest, so the tags cannot drift from what is actually drawn.
 */
export function buildLayout(assets: BirdyAssets): Layout {
	const positions = expandClusters(
		assets.positions,
		assets.points.clusterId,
		assets.centroids.k,
		CLUSTER_SPACING
	);
	const counts = new Uint32Array(assets.centroids.k);
	for (let i = 0; i < assets.points.clusterId.length; i++) {
		const c = assets.points.clusterId[i];
		if (c >= 0 && c < counts.length) counts[c]++;
	}
	return {
		positions,
		centroids: centroidsOf(positions, assets.points.clusterId, assets.centroids.k),
		counts
	};
}

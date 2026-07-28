/**
 * Alternative arrangements of the same points, and the morph between them.
 *
 * The acoustic layout answers "what sounds like what". It cannot answer "which of these
 * are the same bird" or "which of these mean anything", because those are not acoustic
 * questions — a great tit's alarm and a chickadee's can sit next to each other, and
 * recolouring says so only if you already believed it.
 *
 * Rearranging says it. Each grouped layout keeps every point's offset from its own
 * group's centre and moves the centres apart, so a group's internal shape survives the
 * move and you can watch where it came from. Two species that overlapped acoustically
 * visibly tear apart; a species that was already one knot barely moves. That contrast is
 * the information.
 *
 * Nothing here touches the clustering, the matching or the descriptors. It is a
 * rearrangement of where the marks are drawn, and the acoustic layout is always one
 * click away.
 */
import type { BirdyAssets } from '$lib/data/types';
import { CLAIM_COUNT } from './shaders';

export type LayoutId = 'acoustic' | 'species' | 'meaning';

/**
 * Where the cluster centroids are *right now*, shared between the point cloud (which
 * writes it) and the trajectory lines and node labels (which read it). A plain object
 * rather than reactive state: it changes every frame during a rearrangement, and lines
 * and labels have to stay welded to their knots through the whole of it.
 */
export interface LayoutView {
	centroids: Float32Array;
	/** Bumped whenever `centroids` moves, so consumers know to rebuild geometry. */
	version: number;
	morphing: boolean;
}

export function createLayoutView(assets: BirdyAssets): LayoutView {
	return {
		centroids: Float32Array.from(assets.centroids.items.flatMap((c) => c.position)),
		version: 0,
		morphing: false
	};
}

export interface Layout {
	/** `3 * n`, xyz per point. */
	positions: Float32Array;
	/** `3 * k`, xyz per cluster centroid, recomputed for this arrangement. */
	centroids: Float32Array;
}

/**
 * Group centres on a Fibonacci sphere. Evenly spaced on a sphere rather than a ring, so
 * the arrangement is still a volume you can orbit rather than a flat dial, and no two
 * groups sit behind each other from the starting camera.
 */
function groupCentres(count: number, radius: number): [number, number, number][] {
	const out: [number, number, number][] = [];
	const golden = Math.PI * (3 - Math.sqrt(5));
	for (let i = 0; i < count; i++) {
		const y = count === 1 ? 0 : 1 - (i / (count - 1)) * 2;
		const r = Math.sqrt(Math.max(0, 1 - y * y));
		const theta = golden * i;
		out.push([Math.cos(theta) * r * radius, y * radius * 0.75, Math.sin(theta) * r * radius]);
	}
	return out;
}

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
 * Pull each group away from the others while keeping its internal shape.
 *
 * `shrink` tightens each group around its own centre so the islands do not overlap once
 * they are moved; `radius` is how far apart the centres go. Both are chosen so the whole
 * arrangement still fits the same |coord| <= 1 box the acoustic one does, which keeps
 * the camera framing valid through the morph.
 */
function grouped(
	assets: BirdyAssets,
	groupOf: number[],
	groupCount: number,
	radius = 0.72,
	shrink = 0.42
): Layout {
	const n = assets.points.n;
	const source = assets.positions;
	const centres = groupCentres(groupCount, radius);

	// each group's own centre of mass in the acoustic layout
	const sums = new Float64Array(groupCount * 3);
	const counts = new Uint32Array(groupCount);
	for (let i = 0; i < n; i++) {
		const g = groupOf[i];
		if (g < 0) continue;
		sums[g * 3] += source[i * 3];
		sums[g * 3 + 1] += source[i * 3 + 1];
		sums[g * 3 + 2] += source[i * 3 + 2];
		counts[g]++;
	}

	const positions = new Float32Array(n * 3);
	let extent = 0;
	for (let i = 0; i < n; i++) {
		const g = groupOf[i];
		const c = counts[g] || 1;
		const centre = centres[g] ?? [0, 0, 0];
		for (let a = 0; a < 3; a++) {
			const mean = sums[g * 3 + a] / c;
			const v = centre[a] + (source[i * 3 + a] - mean) * shrink;
			positions[i * 3 + a] = v;
			extent = Math.max(extent, Math.abs(v));
		}
	}
	// normalise to the same box as the acoustic layout, so switching does not also zoom
	if (extent > 0) {
		for (let i = 0; i < positions.length; i++) positions[i] /= extent;
	}
	return {
		positions,
		centroids: centroidsOf(positions, assets.points.clusterId, assets.centroids.k)
	};
}

export function buildLayouts(
	assets: BirdyAssets,
	speciesIndex: Map<string, number>,
	claimOfCluster: number[]
): Record<LayoutId, Layout> {
	const n = assets.points.n;

	const speciesOf: number[] = new Array(n);
	for (let i = 0; i < n; i++) {
		speciesOf[i] = speciesIndex.get(assets.points.speciesId[i] ?? '') ?? 0;
	}
	const claimOf: number[] = new Array(n);
	for (let i = 0; i < n; i++) {
		claimOf[i] = claimOfCluster[assets.points.clusterId[i]] ?? CLAIM_COUNT - 1;
	}

	return {
		acoustic: {
			positions: assets.positions,
			centroids: Float32Array.from(assets.centroids.items.flatMap((c) => c.position))
		},
		// Tighter and further apart for twelve groups than for three. The centres go out
		// further than the groups are wide on purpose: the whole point of the rearrangement
		// is that you can see which species tore apart, and that is only visible if the
		// islands clear each other.
		species: grouped(assets, speciesOf, Math.max(1, speciesIndex.size), 0.92, 0.28),
		meaning: grouped(assets, claimOf, CLAIM_COUNT, 0.8, 0.45)
	};
}

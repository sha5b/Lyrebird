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

export type LayoutId = 'acoustic' | 'species';

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
 *
 * **The half-step in `y` is what makes it even, and leaving it out is why two islands
 * always ran into each other.** The obvious spacing, `1 - 2i/(count-1)`, walks from the
 * north pole to the south pole *inclusive*, so the first and last groups land exactly on
 * the poles where the ring radius is zero — and the second and second-to-last sit only
 * one step of latitude away with almost a full ring to spread out in. Measured on the
 * shipped corpus that put the closest pair of species centres 0.445 apart while their
 * combined reach was 0.522: two overlapping pairs out of sixty-six, both at the poles,
 * every time. Offsetting to the middle of each band puts the extremes at
 * `±(1 - 1/count)` instead, which is the standard construction and the one that actually
 * distributes by equal area. Same radius, same shrink, no overlaps, and the minimum
 * centre gap goes from 0.445 to 0.606.
 */
function groupCentres(count: number, radius: number): [number, number, number][] {
	const out: [number, number, number][] = [];
	const golden = Math.PI * (3 - Math.sqrt(5));
	for (let i = 0; i < count; i++) {
		const y = count === 1 ? 0 : 1 - (2 * i + 1) / count;
		const r = Math.sqrt(Math.max(0, 1 - y * y));
		const theta = golden * i;
		out.push([Math.cos(theta) * r * radius, y * radius * 0.75, Math.sin(theta) * r * radius]);
	}
	return out;
}

/**
 * Where each cluster's knot sits: the mean of its points.
 *
 * **With a grouping, the mean is taken over the cluster's biggest group only, and that
 * qualification is the whole correctness of the grouped layouts.**
 *
 * A cluster is fitted in the 28-d acoustic space, and species is a property of the
 * *point*, not of the cluster — so a cluster routinely holds points from several birds.
 * On the shipped corpus 147 of 176 clusters do, covering 94 % of all points, and some
 * span eleven species. Rearranging by bird therefore scatters one cluster's members
 * across up to eleven islands, and a plain mean of all of them lands in the empty space
 * between the islands rather than on any of the points it is supposed to name.
 *
 * That is not a rounding error. Measured before this: 106 of 176 tags had no member point
 * within 0.1 units, the median tag was 0.178 from the nearest point it named, and for the
 * median cluster *none* of its points fell within 0.15 of its own label. Every trajectory
 * thread and every grid strike reads the same array, so all of them terminated in the
 * void — lines to nowhere, ending on nothing.
 *
 * Averaging the modal group instead puts the knot inside the island where most of the
 * cluster is actually drawn, which is also the island the pipeline named it after:
 * `label_cluster` picks the majority species too, so the tag and its text now agree.
 */
function centroidsOf(
	positions: Float32Array,
	clusterId: number[],
	k: number,
	groupOf?: number[],
	groupCount = 0,
	/**
	 * The group each cluster *claims* to belong to, which for the Bird layout is the
	 * species written on its tag. Preferred over the modal group wherever the cluster has
	 * any members there at all.
	 *
	 * The two disagree for 23 of the shipped corpus's clusters, because the pipeline names
	 * a cluster after the majority (species, syllable, song) triple while the modal group
	 * is the majority species alone. Following the modal group there would put a tag
	 * reading "Japanese great tit — B note" inside the chickadee island, and send 15 of
	 * this bird's threads out of its own island to reach it — the same lines-to-nowhere
	 * complaint in a new form. Following the claim keeps a tag, its text, and every thread
	 * that ends on it in one place.
	 */
	claimedGroup?: Int32Array
): Float32Array {
	// Which group each cluster is drawn in. Without a grouping every point counts, which
	// is the plain mean the acoustic layout wants.
	let home: Int32Array | null = null;
	if (groupOf && groupCount > 0) {
		const tally = new Uint32Array(k * groupCount);
		for (let i = 0; i < clusterId.length; i++) {
			const c = clusterId[i];
			const g = groupOf[i];
			if (c < 0 || c >= k || g < 0 || g >= groupCount) continue;
			tally[c * groupCount + g]++;
		}
		home = new Int32Array(k).fill(-1);
		for (let c = 0; c < k; c++) {
			const claimed = claimedGroup?.[c] ?? -1;
			// The claim only wins if the cluster actually has points there; a tag has to sit
			// on something.
			if (claimed >= 0 && claimed < groupCount && tally[c * groupCount + claimed] > 0) {
				home[c] = claimed;
				continue;
			}
			let best = 0;
			for (let g = 0; g < groupCount; g++) {
				const n = tally[c * groupCount + g];
				if (n > best) {
					best = n;
					home[c] = g;
				}
			}
		}
	}

	const sums = new Float64Array(k * 3);
	const counts = new Uint32Array(k);
	for (let i = 0; i < clusterId.length; i++) {
		const c = clusterId[i];
		if (c < 0 || c >= k) continue;
		if (home && groupOf && home[c] >= 0 && groupOf[i] !== home[c]) continue;
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
 * How much of the gap between two island centres is left empty at the tightest pair.
 *
 * Below 1 the islands are provably disjoint; at 1 the closest pair just touches. A tenth
 * of the gap is enough clear paper to read the boundary as a boundary rather than as two
 * clouds that happen to end at the same place.
 */
const ISLAND_CLEARANCE = 0.9;

/**
 * The largest `shrink` at which no island reaches into another one, capped by what was
 * asked for.
 *
 * **This was a hand-tuned constant, and the tuning was done against twelve birds.** The
 * corpus is twenty-six now. Adding groups to a Fibonacci sphere pulls the centres closer
 * together — the minimum gap falls from 0.606 of the radius at twelve to 0.523 at
 * twenty-six — while each island is still nearly as wide as the acoustic layout's whole
 * box, because a bird's renders spread right across it. So the fixed 0.28 overshot the
 * limit by more than half, and 54 of the 325 island pairs interpenetrated: 1 920 points,
 * 2.7 % of the corpus, drawn nearer another bird's centre than their own. That is the
 * "particles sitting in the wrong bird" fault, and it is arithmetic rather than taste, so
 * it is measured instead of chosen — which also means it cannot come back the next time
 * the corpus grows.
 *
 * The condition is the obvious one: two islands are disjoint when the sum of their radii
 * is less than the distance between their centres. Because every member of A is within
 * r(A) of A's centre, that is also exactly the condition for no member of A to land inside
 * B, which is the thing being complained about rather than a proxy for it.
 *
 * The radius is the **furthest** member, not a percentile. A single point of one bird
 * hanging inside another bird's island is precisely the artefact this exists to remove, so
 * trimming the tail would be answering a different question. Measured on the shipped
 * corpus the two differ by 1 % anyway: these clouds have no thin tail to cut.
 */
function fitShrink(
	source: Float32Array,
	groupOf: number[],
	groupCount: number,
	counts: Uint32Array,
	means: Float64Array,
	centres: [number, number, number][],
	requested: number
): number {
	// Each group's reach at shrink = 1, so a reach scales linearly with the shrink applied.
	const reach = new Float64Array(groupCount);
	for (let i = 0; i < groupOf.length; i++) {
		const g = groupOf[i];
		if (g < 0 || g >= groupCount) continue;
		const dx = source[i * 3] - means[g * 3];
		const dy = source[i * 3 + 1] - means[g * 3 + 1];
		const dz = source[i * 3 + 2] - means[g * 3 + 2];
		const d = Math.sqrt(dx * dx + dy * dy + dz * dz);
		if (d > reach[g]) reach[g] = d;
	}

	let limit = Infinity;
	for (let a = 0; a < groupCount; a++) {
		if (!counts[a]) continue;
		for (let b = a + 1; b < groupCount; b++) {
			if (!counts[b]) continue;
			const both = reach[a] + reach[b];
			if (both <= 0) continue;
			const dx = centres[a][0] - centres[b][0];
			const dy = centres[a][1] - centres[b][1];
			const dz = centres[a][2] - centres[b][2];
			limit = Math.min(limit, Math.sqrt(dx * dx + dy * dy + dz * dz) / both);
		}
	}
	if (!Number.isFinite(limit)) return requested;
	return Math.min(requested, limit * ISLAND_CLEARANCE);
}

/**
 * Pull each group away from the others while keeping its internal shape.
 *
 * `radius` is how far out the centres go and `shrink` tightens each group around its own
 * centre. **Only their ratio matters**: the result is renormalised to the same
 * |coord| <= 1 box the acoustic layout occupies, so scaling both by the same factor gives
 * a pixel-identical arrangement. `shrink` is therefore the whole control, and it is
 * requested rather than obeyed — see `fitShrink`.
 */
function grouped(
	assets: BirdyAssets,
	groupOf: number[],
	groupCount: number,
	radius = 0.72,
	shrink = 0.42,
	/** Per cluster, the group its tag claims. See `centroidsOf`. */
	claimedGroup?: Int32Array
): Layout {
	const n = assets.points.n;
	const source = assets.positions;
	const centres = groupCentres(groupCount, radius);

	// each group's own centre of mass in the acoustic layout
	const sums = new Float64Array(groupCount * 3);
	const counts = new Uint32Array(groupCount);
	for (let i = 0; i < n; i++) {
		const g = groupOf[i];
		if (g < 0 || g >= groupCount) continue;
		sums[g * 3] += source[i * 3];
		sums[g * 3 + 1] += source[i * 3 + 1];
		sums[g * 3 + 2] += source[i * 3 + 2];
		counts[g]++;
	}
	const means = new Float64Array(groupCount * 3);
	for (let g = 0; g < groupCount; g++) {
		const c = counts[g] || 1;
		for (let a = 0; a < 3; a++) means[g * 3 + a] = sums[g * 3 + a] / c;
	}

	const fitted = fitShrink(source, groupOf, groupCount, counts, means, centres, shrink);

	const positions = new Float32Array(n * 3);
	let extent = 0;
	for (let i = 0; i < n; i++) {
		const g = groupOf[i];
		// A point in no group has no island to be moved into, so it keeps the place the
		// projection gave it. Reading `sums[-3]` here is how this used to produce NaN
		// coordinates, which a Float32Array carries all the way to the vertex buffer.
		if (g < 0 || g >= groupCount) {
			for (let a = 0; a < 3; a++) {
				const v = source[i * 3 + a];
				positions[i * 3 + a] = v;
				extent = Math.max(extent, Math.abs(v));
			}
			continue;
		}
		const centre = centres[g];
		for (let a = 0; a < 3; a++) {
			const v = centre[a] + (source[i * 3 + a] - means[g * 3 + a]) * fitted;
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
		centroids: centroidsOf(
			positions,
			assets.points.clusterId,
			assets.centroids.k,
			groupOf,
			groupCount,
			claimedGroup
		)
	};
}

/**
 * Scale applied to each knot about its own centre. **1 means the projection is drawn as
 * it is, and that is the right default.**
 *
 * This exists because the knots looked long and it seemed reasonable to shorten them. It
 * is not reasonable. Scaling a cluster about its centre keeps the centre and the internal
 * *arrangement*, so the arithmetic is harmless, but the thing the shape was carrying is
 * its extent — how tightly 64 renders of one syllable agree, how far a field cluster
 * sprawls. Halving that drew every knot as a tight dot of the same size and the corpus
 * stopped having a form: the difference between a taut cluster and a loose one, which is
 * real and measured, was gone.
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

export function buildLayouts(
	assets: BirdyAssets,
	speciesIndex: Map<string, number>
): Record<LayoutId, Layout> {
	const n = assets.points.n;

	// -1 for a species the index does not know, matching the `aSpecies` attribute the shader
	// reads. It used to be 0, which drew those points inside the *first* bird's island while
	// telling the shader they belonged to no bird — a point in a place the data does not put
	// it. `buildSpeciesIndex` appends every species the point cloud mentions, so on a
	// consistent asset set this branch is unreachable; it is here so that an inconsistent one
	// leaves the strays where the projection put them instead of filing them under a bird.
	const speciesOf: number[] = new Array(n);
	for (let i = 0; i < n; i++) {
		speciesOf[i] = speciesIndex.get(assets.points.speciesId[i] ?? '') ?? -1;
	}
	// The island each cluster's tag belongs in: the bird it is named after. See `centroidsOf`.
	const claimedSpecies = Int32Array.from(
		assets.centroids.items.map((c) => speciesIndex.get(c.speciesId) ?? -1)
	);

	const acoustic = expandClusters(
		assets.positions,
		assets.points.clusterId,
		assets.centroids.k,
		CLUSTER_SPACING
	);

	return {
		acoustic: {
			positions: acoustic,
			// Recomputed from the expanded positions rather than taken from the manifest.
			// They are the same to within rounding — expanding about the mean preserves the
			// mean — but deriving them from what is actually drawn means the tags cannot
			// drift if that ever stops being true.
			centroids: centroidsOf(acoustic, assets.points.clusterId, assets.centroids.k)
		},
		// The centres go out further than the groups are wide on purpose: the whole point of
		// the rearrangement is that you can see which species tore apart, and that is only
		// visible if the islands clear each other. `shrink` is an upper bound rather than the
		// figure used — `fitShrink` lowers it to whatever this many birds actually allows, and
		// every island shrinks by that one factor, so their relative spread, which is the
		// other thing worth reading here, survives.
		species: grouped(assets, speciesOf, Math.max(1, speciesIndex.size), 0.92, 0.28, claimedSpecies)
	};
}

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

/**
 * Each knot's distance to its nearest other knot, for the callers that quote a length in
 * knot-spacings rather than in box units — the wavefront's reach is the one that does.
 *
 * **Why this is a grid and not two nested loops.** It used to be the obvious `k²` scan,
 * which is 18 million distance tests at the shipped 4 298-knot build (about a second of
 * a frozen tab at load) and **196 million at the production build's ~14 000**, where it
 * becomes a load-time stall long enough to read as a hang. A uniform grid sized to one
 * cell per knot answers the same question exactly in roughly linear time: bucket the
 * knots, then for each one walk outward a ring of cells at a time and stop as soon as the
 * best distance found is inside the radius the searched rings have already cleared.
 *
 * **A memberless knot does not take part.** Its centroid is (0,0,0) — the centre of the
 * box, a position that is a lie, per `counts` above — so including them would put every
 * empty knot at distance 0 from every other and drag the median toward nothing. Callers
 * get the spacing of the knots that are really there.
 */
export function nearestNeighbourDistances(
	centroids: Float32Array,
	counts: Uint32Array,
	k: number
): number[] {
	const real: number[] = [];
	for (let i = 0; i < k; i++) if ((counts[i] ?? 0) > 0) real.push(i);
	if (real.length < 2) return [];

	let minX = Infinity;
	let minY = Infinity;
	let minZ = Infinity;
	let maxX = -Infinity;
	let maxY = -Infinity;
	let maxZ = -Infinity;
	for (const i of real) {
		const x = centroids[i * 3];
		const y = centroids[i * 3 + 1];
		const z = centroids[i * 3 + 2];
		if (x < minX) minX = x;
		if (x > maxX) maxX = x;
		if (y < minY) minY = y;
		if (y > maxY) maxY = y;
		if (z < minZ) minZ = z;
		if (z > maxZ) maxZ = z;
	}
	const spanX = maxX - minX;
	const spanY = maxY - minY;
	const spanZ = maxZ - minZ;
	const longest = Math.max(spanX, spanY, spanZ);
	// Every knot in one place (a degenerate build): the answer is zero everywhere, and
	// there is no grid to build.
	if (!(longest > 0)) return real.map(() => 0);
	// The cell edge divides the LONGEST axis into about the cube root of the knot count,
	// so the grid holds at most ~k cells however flat the cloud is — a cell edge taken
	// from the bounding volume instead would explode when one axis collapses.
	const divisions = Math.max(1, Math.ceil(Math.cbrt(real.length)));
	const cell = longest / divisions;
	const nx = Math.max(1, Math.min(divisions, Math.ceil(spanX / cell)));
	const ny = Math.max(1, Math.min(divisions, Math.ceil(spanY / cell)));
	const nz = Math.max(1, Math.min(divisions, Math.ceil(spanZ / cell)));
	const total = nx * ny * nz;

	const cellX = new Int32Array(real.length);
	const cellY = new Int32Array(real.length);
	const cellZ = new Int32Array(real.length);
	const starts = new Int32Array(total + 1);
	for (let n = 0; n < real.length; n++) {
		const i = real[n];
		const cx = Math.min(nx - 1, Math.max(0, Math.floor((centroids[i * 3] - minX) / cell)));
		const cy = Math.min(ny - 1, Math.max(0, Math.floor((centroids[i * 3 + 1] - minY) / cell)));
		const cz = Math.min(nz - 1, Math.max(0, Math.floor((centroids[i * 3 + 2] - minZ) / cell)));
		cellX[n] = cx;
		cellY[n] = cy;
		cellZ[n] = cz;
		starts[cx + nx * (cy + ny * cz) + 1]++;
	}
	for (let c = 0; c < total; c++) starts[c + 1] += starts[c];
	const cursor = starts.slice(0, total);
	const items = new Int32Array(real.length);
	for (let n = 0; n < real.length; n++) {
		items[cursor[cellX[n] + nx * (cellY[n] + ny * cellZ[n])]++] = n;
	}

	const out: number[] = [];
	const maxRing = nx + ny + nz;
	for (let n = 0; n < real.length; n++) {
		const i = real[n];
		const px = centroids[i * 3];
		const py = centroids[i * 3 + 1];
		const pz = centroids[i * 3 + 2];
		let best = Infinity;
		for (let r = 0; ; r++) {
			// Rings 0…r-1 have been searched, so every cell within `r - 1` cells of this
			// one is done and anything still unseen sits in a cell at least `r` away. The
			// query is somewhere inside its own cell and that cell begins one full cell
			// short of the unsearched ones, so the radius already cleared is
			// `(r - 1) * cell` — a best inside that cannot be beaten. Compared squared,
			// which is what `best` holds.
			if (r > 0) {
				const cleared = (r - 1) * cell;
				if (best <= cleared * cleared) break;
			}
			if (r > maxRing) break;
			const x0 = Math.max(0, cellX[n] - r);
			const x1 = Math.min(nx - 1, cellX[n] + r);
			const y0 = Math.max(0, cellY[n] - r);
			const y1 = Math.min(ny - 1, cellY[n] + r);
			const z0 = Math.max(0, cellZ[n] - r);
			const z1 = Math.min(nz - 1, cellZ[n] + r);
			for (let cz = z0; cz <= z1; cz++) {
				const edgeZ = Math.abs(cz - cellZ[n]) === r;
				for (let cy = y0; cy <= y1; cy++) {
					const edgeY = Math.abs(cy - cellY[n]) === r;
					for (let cx = x0; cx <= x1; cx++) {
						// Only the shell of the cube is new; its interior was ring `r - 1`.
						if (r > 0 && !edgeZ && !edgeY && Math.abs(cx - cellX[n]) !== r) continue;
						const c = cx + nx * (cy + ny * cz);
						for (let s = starts[c]; s < starts[c + 1]; s++) {
							const m = items[s];
							if (m === n) continue;
							const j = real[m];
							const dx = px - centroids[j * 3];
							const dy = py - centroids[j * 3 + 1];
							const dz = pz - centroids[j * 3 + 2];
							const d = dx * dx + dy * dy + dz * dz;
							if (d < best) best = d;
						}
					}
				}
			}
		}
		out.push(best === Infinity ? 0 : Math.sqrt(best));
	}
	return out;
}

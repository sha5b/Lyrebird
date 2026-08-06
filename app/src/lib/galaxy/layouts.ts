/**
 * The cloud's one arrangement: the measured acoustic projection, with the knots drawn
 * further apart than the projection puts them.
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
	/**
	 * Second drawn places for the knots this projection tears — see `drawnLobes`. A knot
	 * with `has[c]` set is drawn in two patches, and both of them light when it sings, so
	 * both need a name or the second one is the "lit, no label, no connection" report.
	 */
	lobes: Lobes;
	/** Bumped whenever `centroids` moves, so consumers know to rebuild geometry. */
	version: number;
}

export function createLayoutView(assets: BirdyAssets): LayoutView {
	return {
		centroids: Float32Array.from(assets.centroids.items.flatMap((c) => c.position)),
		counts: Uint32Array.from(assets.centroids.items.map((c) => c.count ?? 0)),
		// Empty until the first real layout writes one: the shipped centroid positions are
		// means, and asking which of them are torn before the arrangement exists would be
		// answering about a picture nobody is looking at.
		lobes: {
			anchors: new Float32Array(assets.centroids.k * 3),
			has: new Uint8Array(assets.centroids.k),
			counts: new Uint32Array(assets.centroids.k),
			report: { measured: 0, split: 0, medianShare: 0, ms: 0 }
		},
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
	/** What the local pass did, or null when it was off / unavailable. See `localShapes`. */
	local: LocalReport | null;
	/** Second drawn places for the knots this projection tears. See `drawnLobes`. */
	lobes: Lobes;
}

/** What the two-level pass actually did, for the interface to be able to say so. */
export interface LocalReport {
	/** Knots given a local frame (2 or more members). */
	reshaped: number;
	/** Knots left as the projection drew them: a single member, or no features. */
	skipped: number;
	/**
	 * Drawn box units per unit of feature-space spread — the one global constant that
	 * ties the local frames back to the corpus's own scale. See `localShapes`.
	 */
	scale: number;
	/** How long the pass took, ms, so a slow build shows up as a number and not a hunch. */
	ms: number;
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

/**
 * How far apart the knots are drawn, as a scale on each knot's centre: **2.0 — the gaps
 * between knots are drawn at twice what the projection puts them, and the knots
 * themselves keep their shape and extent.**
 *
 * A display transform, and the key in the interface says so. Each clustered point p with
 * knot centre c is drawn at `c * KNOT_GAP + (p - c)`, so everything the projection
 * measured *inside* a knot — the extent CLUSTER_SPACING above warns against touching —
 * is preserved exactly, and only the knot's address moves. The unclustered points stay
 * where the projection put them: they are the haze between knots, and moving them would
 * invent a structure the data does not have. (On the v6 build there are none.)
 *
 * Why it exists: at 1 the dense middle of the production corpus fused into one mass —
 * knots whose centres sit a fraction of a radius apart overdraw into a single blob
 * however the frontier thins them, and no sprite budget fixes neighbours that overlap.
 * The cost is that inter-knot distance is no longer a pure reading of the projection; it
 * is display air, uniform everywhere, so *relative* positions and every knot-to-knot
 * comparison keep their meaning. Centroids are recomputed as member means after the move
 * (buildLayout), so they scale by exactly this factor and every downstream reader —
 * waves, framing, labels, the LOD grid, the NN spacing behind uWaveLocal, the stage
 * ruler's unit — sees one consistent picture.
 *
 * **2.0 -> 3.0** (owner, 2026-08-03, on the PaCMAP build: "it tends to dense up a lot and
 * we nearly can't see the connection between them — give all nodes much more space in
 * between so they can breathe"). The measurement says the crowding is **absolute, not
 * relative**, which the obvious ratio would have hidden: PaCMAP packs the cloud about 30 %
 * tighter than cMDS did, so the median knot spacing fell **0.0395 -> 0.0280** while the
 * width-to-gap ratio actually *improved*, 2.1x to 1.49x. Everything shrank together, and a
 * thread between two knots then runs through occupied space instead of clear air — which is
 * the half of the report about connections.
 *
 * 3.0 is where the two readings agree. It restores the absolute spacing (0.0280 -> 0.042,
 * just past what v6 had) and takes the ratio to **1.0x** — the crossover where a knot is no
 * wider than the gap to its neighbour, so knots stop interpenetrating and start reading as
 * separate places with room between them. One constant if it wants dialling: 3.7 would give
 * 0.8x, 2.5 would give 1.2x.
 *
 * **2.0 was the previous answer to the same complaint, on the cMDS build** (owner,
 * 2026-08-02: "give the point cloud more space between the points — sometimes knots and
 * tones are so near each other that it looks like there is no animation between them"). The measurement behind it: on v6 the median knot's mean
 * member distance is 0.129 against a median knot spacing of 0.0395 at 1.3, so **the
 * average knot was 3.3× wider than the gap to its nearest neighbour** — the knots
 * interpenetrated everywhere and there was no gap for a response to happen *in*. At 2.0
 * that ratio is 2.1. It does not turn knots into beads, and nothing short of a lie about
 * the corpus would: the overlap is a property of `label` clustering, where a knot is
 * every sound carrying one type's name and those sounds are under no obligation to land
 * together in three dimensions.
 *
 * **The gap goes up rather than the knots coming in**, though the two are arithmetically
 * equivalent for that ratio: this way each knot's extent — how tightly its members
 * agree, which is measured — is left exactly as the projection reported it. CLUSTER_SPACING
 * above is why the other direction is not on the table.
 */
const KNOT_GAP = 3.0;

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
 * Move every knot's centre out from the origin by `factor`, carrying its members with
 * it: p → c*factor + (p − c). Knot shape and extent are untouched — only the gaps
 * grow. Unclustered points are copied through unchanged.
 */
function separateKnots(
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
			out[i * 3 + a] = centre * factor + (positions[i * 3 + a] - centre);
		}
	}
	return out;
}

/**
 * Eigenvalues and eigenvectors of a small symmetric matrix, by cyclic Jacobi.
 *
 * `d` is 8 here — the shipped per-point feature space — so the O(d³) sweep is 8×8 work
 * per knot and the whole corpus is one pass. Returns `vectors` column-major in the
 * sense that eigenvector `j` is `vectors[i * d + j]` over `i`, paired with `values[j]`.
 */
function symmetricEigen(
	input: Float64Array,
	d: number,
	a: Float64Array,
	v: Float64Array,
	values: Float64Array
): void {
	a.set(input);
	v.fill(0);
	for (let i = 0; i < d; i++) v[i * d + i] = 1;
	for (let sweep = 0; sweep < 8; sweep++) {
		let off = 0;
		for (let p = 0; p < d; p++) {
			for (let q = p + 1; q < d; q++) off += a[p * d + q] * a[p * d + q];
		}
		if (off < 1e-20) break;
		for (let p = 0; p < d; p++) {
			for (let q = p + 1; q < d; q++) {
				const apq = a[p * d + q];
				if (Math.abs(apq) < 1e-18) continue;
				const theta = (a[q * d + q] - a[p * d + p]) / (2 * apq);
				const sign = theta >= 0 ? 1 : -1;
				const t = sign / (Math.abs(theta) + Math.sqrt(theta * theta + 1));
				const c = 1 / Math.sqrt(t * t + 1);
				const s = t * c;
				for (let i = 0; i < d; i++) {
					const aip = a[i * d + p];
					const aiq = a[i * d + q];
					a[i * d + p] = c * aip - s * aiq;
					a[i * d + q] = s * aip + c * aiq;
				}
				for (let i = 0; i < d; i++) {
					const api = a[p * d + i];
					const aqi = a[q * d + i];
					a[p * d + i] = c * api - s * aqi;
					a[q * d + i] = s * api + c * aqi;
				}
				for (let i = 0; i < d; i++) {
					const vip = v[i * d + p];
					const viq = v[i * d + q];
					v[i * d + p] = c * vip - s * viq;
					v[i * d + q] = s * vip + c * viq;
				}
			}
		}
	}
	for (let i = 0; i < d; i++) values[i] = a[i * d + i];
}

/**
 * Radius of the residual ball against its root-mean-square: √(5/3). A radius drawn as
 * `R·u^(1/3)` is uniform through a ball of radius R and has RMS `R·√(3/5)`, so the
 * factor puts the RMS step exactly on the residual the three axes could not carry.
 */
const RESIDUAL_BALL = Math.sqrt(5 / 3);

/** Point indices per knot, one pass, as a flat CSR-style pair. */
function membersOf(clusterId: ArrayLike<number>, k: number): { starts: Int32Array; items: Int32Array } {
	const starts = new Int32Array(k + 1);
	for (let i = 0; i < clusterId.length; i++) {
		const c = clusterId[i];
		if (c >= 0 && c < k) starts[c + 1]++;
	}
	for (let c = 0; c < k; c++) starts[c + 1] += starts[c];
	const cursor = starts.slice(0, k);
	const items = new Int32Array(starts[k]);
	for (let i = 0; i < clusterId.length; i++) {
		const c = clusterId[i];
		if (c >= 0 && c < k) items[cursor[c]++] = i;
	}
	return { starts, items };
}

/**
 * **The two-level layout: knot centres from the global projection, members from their
 * own.** This is the fix for torn knots, and it is a change of claim, so it is written
 * out in full.
 *
 * A knot is drawn as one place — the tag, the thread, the grid strike and the wave all
 * go to its centre — but nothing in the pipeline guarantees the projection puts its
 * members in one place. Measured on the shipped build (`pipeline/analysis/tear_dims.py`),
 * **385 of 6 255 measurable knots are drawn in two blobs**, and of those **219 are one
 * blob in the 8-d feature space** and torn only by the squeeze into three dimensions.
 * For those the centre lands in the gap between the halves, the tag sits on nothing, and
 * one sung note lights two patches a box-width apart with a label on neither.
 *
 * So the arrangement is built in two levels instead of one:
 *
 * - **Where a knot is** stays the global projection's answer. Not its members' mean,
 *   which is exactly the position that can fall in the void, but the position of its
 *   *feature medoid* — the member closest to the knot's own centre in feature space.
 *   The knot is drawn where the projection put its most typical sound, which is always
 *   a real place.
 * - **What a knot looks like** becomes a 3-d principal-component projection of that
 *   knot's own members, in the 8-d feature space, laid out around that centre. A knot
 *   cannot then be torn by the global fit, because the global fit never places a member.
 *
 * **Why this loses less than it sounds — and the number this rests on has moved.** The
 * argument was that the picture's local structure was already close to noise, quoting
 * `knnAgreement` **0.0849**: 8.5 % of a point's ten nearest neighbours in 3-d share its
 * type, so what the global projection said inside a knot was mostly the residue of a fit
 * dominated by everything else, and a local projection of a couple of dozen members into
 * three dimensions could not lose much.
 *
 * **On this build that figure is 0.4574**, and the two agree on nothing. It is the
 * manifest's own `knnAgreement`, it is the number the HUD prints as `NEIGHBOURS 46 %`,
 * and re-deriving it from the 444 213 shipped per-point values gives 0.4574 to four
 * places (`scripts/verify-trust.mjs` asserts that the two halves agree). The 0.0849 was
 * real and is traceable — it is the figure `types.ts` records against the **13 748**-type
 * inventory, an older corpus than this 15 341-type one — so this is a stale number rather
 * than a wrong one, which is worse in one specific way: it reads as current and it
 * overstates the case by a factor of five.
 *
 * At 46 % the global projection's local structure is not noise, so **"this loses very
 * little" is not established by the number that was offered for it** — and that number was
 * the whole argument for spending the local structure. The layout's other reason stands
 * untouched: a knot laid out from its own members cannot be torn by the global fit, and
 * 2 035 of 6 316 measured knots are torn in the shipped positions.
 *
 * **Owner's call, taken: the default is off.** The two-level pass is kept and is one
 * argument away, because the tearing it fixes is real and measured. But it is no longer
 * what the galaxy draws by default, and the reasoning is that the two claims are not
 * symmetric. Turning it on *discards* a measured signal — 46 % neighbour agreement in the
 * global projection, which is a real acoustic arrangement inside a knot — in exchange for
 * repairing the drawing of 2 035 knots out of 6 316. When the discarded thing was 8.5 %
 * that trade was obviously worth making; at 46 % it is a trade the number no longer
 * supports, and the honest default is the arrangement that throws nothing away.
 *
 * What the picture claims is therefore one thing again: *position is the acoustic
 * arrangement, at every scale.* With the local pass on it splits in two — knot centres
 * are the coarse arrangement, spread inside a knot is that knot's own variation — and both
 * halves are true, but the reader is not told where the seam is.
 *
 * **What turning it off gives back up.** The 385 torn knots draw torn again, 219 of them
 * torn only by the squeeze into three dimensions, with the tag in the gap between the two
 * halves. That is a real cost and it is why the pass survives: `buildLayout(assets, true)`
 * restores it, and the per-knot `tearing` figure now shipped on every centroid says which
 * knots are affected. The honest repair for them is upstream in the clustering, which is
 * where it was always said to belong.
 *
 * **What it does not fix, and must not pretend to.** 166 of the 385 torn knots are two
 * blobs in the feature space too — the type genuinely holds two kinds of sound. Those
 * still draw as two lobes here, at their real separation instead of a box-width apart.
 * The honest repair for them is upstream, in the clustering, not in the layout.
 *
 * **Scale.** Local coordinates are scaled by one global constant so that the corpus's
 * *median* knot keeps exactly the extent it is drawn at today — everything tuned against
 * that (KNOT_GAP, the wave's reach, the ruler's unit) stays calibrated. Inside that, a
 * knot's drawn size becomes proportional to its true feature spread, which is what the
 * extent was always supposed to mean and what a tear was inflating.
 *
 * **Orientation carries no meaning across knots.** Each frame is that knot's own
 * principal axes, so "up" in one knot is unrelated to "up" in the next. Direction inside
 * a knot is not a claim; distance from its centre is. The signs are pinned to the
 * member with the largest coordinate so a reload draws the same picture.
 */
function localShapes(assets: BirdyAssets, positions: Float32Array): LocalReport | null {
	const features = assets.pointFeatures;
	const d = assets.pointFeatureDims;
	if (!features || d < 2) return null;
	const started = typeof performance === 'undefined' ? 0 : performance.now();
	const k = assets.centroids.k;
	const clusterId = assets.points.clusterId;
	const { starts, items } = membersOf(clusterId, k);

	const mean = new Float64Array(d);
	const cov = new Float64Array(d * d);
	// Scratch for the eigensolver, hoisted: k knots is k allocations otherwise.
	const eigA = new Float64Array(d * d);
	const eigV = new Float64Array(d * d);
	const eigValues = new Float64Array(d);
	const axis = new Int32Array(3);
	const anchor = new Float32Array(k * 3);
	const spread8 = new Float64Array(k);
	const spread3 = new Float64Array(k);
	// Written on the first pass, read on the second: the local coordinates before the
	// one global scale is known. Three per member, in `items` order.
	const localXyz = new Float64Array(items.length * 3);

	let reshaped = 0;
	let skipped = 0;
	for (let c = 0; c < k; c++) {
		const from = starts[c];
		const to = starts[c + 1];
		const n = to - from;
		if (n <= 0) continue;
		if (n === 1) {
			const i = items[from];
			anchor[c * 3] = positions[i * 3];
			anchor[c * 3 + 1] = positions[i * 3 + 1];
			anchor[c * 3 + 2] = positions[i * 3 + 2];
			skipped++;
			continue;
		}

		mean.fill(0);
		let mx = 0;
		let my = 0;
		let mz = 0;
		for (let m = from; m < to; m++) {
			const i = items[m];
			const off = i * d;
			for (let j = 0; j < d; j++) mean[j] += features[off + j];
			mx += positions[i * 3];
			my += positions[i * 3 + 1];
			mz += positions[i * 3 + 2];
		}
		for (let j = 0; j < d; j++) mean[j] /= n;
		mx /= n;
		my /= n;
		mz /= n;

		// The medoid in feature space, and the two spreads — one pass, no allocation.
		cov.fill(0);
		let bestMember = items[from];
		let bestDist = Infinity;
		let sum8 = 0;
		let sum3 = 0;
		for (let m = from; m < to; m++) {
			const i = items[m];
			const off = i * d;
			let q = 0;
			for (let j = 0; j < d; j++) {
				const dj = features[off + j] - mean[j];
				q += dj * dj;
				for (let l = j; l < d; l++) cov[j * d + l] += dj * (features[off + l] - mean[l]);
			}
			sum8 += Math.sqrt(q);
			if (q < bestDist) {
				bestDist = q;
				bestMember = i;
			}
			const dx = positions[i * 3] - mx;
			const dy = positions[i * 3 + 1] - my;
			const dz = positions[i * 3 + 2] - mz;
			sum3 += Math.sqrt(dx * dx + dy * dy + dz * dz);
		}
		for (let j = 0; j < d; j++) {
			for (let l = j + 1; l < d; l++) cov[l * d + j] = cov[j * d + l];
		}
		spread8[c] = sum8 / n;
		spread3[c] = sum3 / n;
		anchor[c * 3] = positions[bestMember * 3];
		anchor[c * 3 + 1] = positions[bestMember * 3 + 1];
		anchor[c * 3 + 2] = positions[bestMember * 3 + 2];

		symmetricEigen(cov, d, eigA, eigV, eigValues);
		// The three largest eigenvalues, by selection rather than a sort: d is 8. A space
		// with fewer than three dimensions leaves the spare axes at -1 and they draw flat.
		axis[0] = -1;
		axis[1] = -1;
		axis[2] = -1;
		for (let a = 0; a < 3; a++) {
			let best = -Infinity;
			for (let j = 0; j < d; j++) {
				if (j === axis[0] || j === axis[1]) continue;
				if (eigValues[j] > best) {
					best = eigValues[j];
					axis[a] = j;
				}
			}
		}
		/**
		 * **The five dimensions the frame cannot show come back as isotropic residue,
		 * and leaving them out was measurably wrong.**
		 *
		 * Three principal axes of an 8-d knot keep the largest separation and throw away
		 * most of the *within*-lobe spread — so a knot drawn from its top three
		 * components alone comes out tighter than it is, and any real bimodality in it
		 * reads as a cleaner split than the sounds support. Measured: the same tearing
		 * test that scores 379 knots on the global projection scored **390** on a
		 * top-3-only local frame, not because more knots were torn but because the
		 * denominator had shrunk.
		 *
		 * The residual variance is known exactly — total scatter minus what the three
		 * axes hold — so each member gets it back as a step in a direction hashed from
		 * its own index, with the radius drawn uniformly through the ball (`u^(1/3)`,
		 * scaled by √(5/3) so the root-mean-square step is exactly the residual). A
		 * fixed-length step was the first version and drew every knot as a hollow shell;
		 * filling the ball puts the density back where an isotropic residue actually
		 * lies. Deterministic, so a reload draws the same knot.
		 */
		let total = 0;
		for (let j = 0; j < d; j++) total += eigValues[j];
		let kept = 0;
		for (let a = 0; a < 3; a++) if (axis[a] >= 0) kept += eigValues[axis[a]];
		const residual = Math.sqrt(Math.max(0, total - kept) / n);
		for (let m = from; m < to; m++) {
			const i = items[m];
			const off = i * d;
			for (let a = 0; a < 3; a++) {
				const col = axis[a];
				if (col < 0) {
					localXyz[m * 3 + a] = 0;
					continue;
				}
				let p = 0;
				for (let j = 0; j < d; j++) p += (features[off + j] - mean[j]) * eigV[j * d + col];
				localXyz[m * 3 + a] = p;
			}
			if (residual > 0) {
				const h = Math.imul(i + 1, 2654435761) >>> 0;
				const g = Math.imul(i + 1, 40503) >>> 0;
				const cosT = ((h & 0xffff) / 65535) * 2 - 1;
				const phi = ((h >>> 16) / 65535) * Math.PI * 2;
				const sinT = Math.sqrt(Math.max(0, 1 - cosT * cosT));
				const r = RESIDUAL_BALL * residual * Math.cbrt((g & 0xffff) / 65535);
				localXyz[m * 3] += r * sinT * Math.cos(phi);
				localXyz[m * 3 + 1] += r * sinT * Math.sin(phi);
				localXyz[m * 3 + 2] += r * cosT;
			}
		}
		// A principal axis is only defined up to sign, and an unpinned sign would redraw
		// the knot mirrored on the next load. Pin it to the member that reaches furthest
		// along the axis: that member's coordinate is positive, always.
		for (let a = 0; a < 3; a++) {
			let far = 0;
			let mag = 0;
			for (let m = from; m < to; m++) {
				const p = localXyz[m * 3 + a];
				if (Math.abs(p) > mag) {
					mag = Math.abs(p);
					far = p;
				}
			}
			if (far < 0) for (let m = from; m < to; m++) localXyz[m * 3 + a] = -localXyz[m * 3 + a];
		}
		reshaped++;
	}

	// One global scale, so the median knot keeps the extent it is drawn at today. Taken
	// over the knots that have a measurable spread in both spaces; a ratio of medians
	// rather than a median of ratios, because a knot whose 8-d spread is near zero would
	// otherwise contribute an arbitrarily large ratio to the middle of the set.
	const s8: number[] = [];
	const s3: number[] = [];
	for (let c = 0; c < k; c++) {
		if (starts[c + 1] - starts[c] < 4) continue;
		if (!(spread8[c] > 0) || !(spread3[c] > 0)) continue;
		s8.push(spread8[c]);
		s3.push(spread3[c]);
	}
	s8.sort((a, b) => a - b);
	s3.sort((a, b) => a - b);
	const median8 = s8[s8.length >> 1] ?? 0;
	const median3 = s3[s3.length >> 1] ?? 0;
	const scale = median8 > 0 && median3 > 0 ? median3 / median8 : 1;

	for (let c = 0; c < k; c++) {
		const from = starts[c];
		const to = starts[c + 1];
		if (to - from < 2) continue;
		// The knot's drawn extent: its own feature spread at the corpus's scale. The
		// local coordinates already carry the right *relative* lengths, so this is one
		// factor per knot, not a renormalisation that would flatten every knot to one size.
		let sum = 0;
		for (let m = from; m < to; m++) {
			const x = localXyz[m * 3];
			const y = localXyz[m * 3 + 1];
			const z = localXyz[m * 3 + 2];
			sum += Math.sqrt(x * x + y * y + z * z);
		}
		const drawn = sum / (to - from);
		const want = spread8[c] * scale;
		const f = drawn > 1e-12 ? want / drawn : 0;
		for (let m = from; m < to; m++) {
			const i = items[m];
			positions[i * 3] = anchor[c * 3] + localXyz[m * 3] * f;
			positions[i * 3 + 1] = anchor[c * 3 + 1] + localXyz[m * 3 + 1] * f;
			positions[i * 3 + 2] = anchor[c * 3 + 2] + localXyz[m * 3 + 2] * f;
		}
	}
	// The single-member knots were already written to their anchor above; write them
	// through to the positions too, so every clustered point comes out of this pass.
	for (let c = 0; c < k; c++) {
		if (starts[c + 1] - starts[c] !== 1) continue;
		const i = items[starts[c]];
		positions[i * 3] = anchor[c * 3];
		positions[i * 3 + 1] = anchor[c * 3 + 1];
		positions[i * 3 + 2] = anchor[c * 3 + 2];
	}

	return {
		reshaped,
		skipped,
		scale,
		ms: typeof performance === 'undefined' ? 0 : Math.round(performance.now() - started)
	};
}

/**
 * The arrangement the galaxy draws. The positions are the projection with the knots
 * separated by KNOT_GAP; the centroids are recomputed from the result rather than
 * taken from the manifest, so the tags cannot drift from what is actually drawn.
 *
 * `local` runs the two-level pass above before the separation, which is the order that
 * matters: the members are placed around their knot's centre first, and KNOT_GAP then
 * moves the whole knot as one — exactly what it did to the projection's knots.
 */
/** Fewest members before a knot's shape is allowed to argue it is drawn in two places. */
const LOBE_MIN_MEMBERS = 12;
/** And fewest in the smaller lobe, so three stragglers cannot found a second place. */
const LOBE_MIN_SIDE = 3;
/**
 * Gap between the two halves over their own mean radius, past which the knot is drawn as
 * two places rather than one.
 *
 * Splitting a single blob scores about 2, so 2 is the null and 5 is the pipeline's own
 * threshold in `torn_clusters`. **It is used here and nowhere else on purpose: this
 * statistic is only calibrated in three dimensions.** A blob's mean radius grows like
 * sqrt(d) while the gap between its halves does not, so the same 5 is unreachable in 8-d
 * (two blobs a full 180 degrees apart score 3.61) and meaningless in 32-d. The equivalent
 * gate in the pipeline's `_type_blobs` measures the *features* and is switched off for
 * exactly that reason — it fires on knots the picture already draws as one place.
 * Measured on the drawn positions it fires on the knots that are actually drawn in two.
 */
const LOBE_RATIO = 5;

/** A knot's second drawn place, when the projection put its members in two. */
export interface Lobes {
	/** `3 * k` — the secondary anchor. Only meaningful where `has[c]` is 1. */
	anchors: Float32Array;
	has: Uint8Array;
	/** Members in the secondary lobe, so the interface can say how much of the knot it is. */
	counts: Uint32Array;
	/** Knots measured, knots split, and the median share the smaller lobe holds. */
	report: { measured: number; split: number; medianShare: number; ms: number };
}

/**
 * The knots this projection draws in two places, and a real anchor for each place.
 *
 * **This is what makes a locally-faithful projection usable.** The 2026-08-03 bake-off
 * measured the trade: PaCMAP puts 68.5 % of a point's drawn neighbours on its own type
 * against cMDS's 21.4 %, and tears 217 of 438 measurable knots against cMDS's 18. The
 * tearing is not a rounding error and not outliers — only 14 of the 217 are a few flung
 * members, while **120 are genuine second lobes holding a median 21.7 % of the knot at a
 * median 0.464 box units**. A knot is drawn as one place by every instrument in the app:
 * the tag, the thread, the grid strike and the wave all read one position. Left alone,
 * those second lobes light when the knot sings and carry no name — which is the report
 * this whole line of work started from.
 *
 * So a two-lobed knot gets **two** anchors, and each one sits on its own lobe's most
 * central member rather than on a mean, because a mean between two lobes is the void.
 * The larger lobe is the primary: it keeps the knot's identity for anything that needs a
 * single place (a song's thread runs through it, a fly-to frames it), and the secondary
 * exists so the other lit patch can be named.
 *
 * The split is deterministic — a principal-axis cut refined by two Lloyd steps, no random
 * seeding — so a reload draws the same two places. `torn_clusters` in the pipeline uses
 * k-means with a fixed seed; the two agree on genuinely separated lobes, which is the only
 * case that gets past the ratio.
 */
export function drawnLobes(positions: Float32Array, clusterId: number[], k: number): Lobes {
	const started = typeof performance === 'undefined' ? 0 : performance.now();
	const anchors = new Float32Array(k * 3);
	const has = new Uint8Array(k);
	const counts = new Uint32Array(k);

	// members per knot, in one pass
	const members: number[][] = Array.from({ length: k }, () => []);
	for (let i = 0; i < clusterId.length; i++) {
		const c = clusterId[i];
		if (c >= 0 && c < k) members[c].push(i);
	}

	const shares: number[] = [];
	let measured = 0;
	const centre = (ix: number[]) => {
		const m = [0, 0, 0];
		for (const i of ix) {
			m[0] += positions[i * 3];
			m[1] += positions[i * 3 + 1];
			m[2] += positions[i * 3 + 2];
		}
		return [m[0] / ix.length, m[1] / ix.length, m[2] / ix.length];
	};
	const meanRadius = (ix: number[], c: number[]) => {
		let s = 0;
		for (const i of ix) {
			const dx = positions[i * 3] - c[0];
			const dy = positions[i * 3 + 1] - c[1];
			const dz = positions[i * 3 + 2] - c[2];
			s += Math.hypot(dx, dy, dz);
		}
		return s / ix.length;
	};
	/** The member nearest a lobe's own centre — always a real place, never the gap. */
	const medoid = (ix: number[], c: number[]) => {
		let best = ix[0];
		let bestD = Infinity;
		for (const i of ix) {
			const d =
				(positions[i * 3] - c[0]) ** 2 +
				(positions[i * 3 + 1] - c[1]) ** 2 +
				(positions[i * 3 + 2] - c[2]) ** 2;
			if (d < bestD) {
				bestD = d;
				best = i;
			}
		}
		return best;
	};

	for (let c = 0; c < k; c++) {
		const ix = members[c];
		if (ix.length < LOBE_MIN_MEMBERS) continue;

		// Deterministic two-way cut: the knot's longest direction, then two Lloyd steps.
		// Power iteration on the covariance would be the textbook axis; the difference
		// between the two blobs' own separation and the leading eigenvector is nil once a
		// knot is bimodal enough to clear the ratio, and the farthest-pair axis needs no
		// eigen-solver and cannot fail to converge.
		const mid = centre(ix);
		let far = ix[0];
		let farD = -1;
		for (const i of ix) {
			const d =
				(positions[i * 3] - mid[0]) ** 2 +
				(positions[i * 3 + 1] - mid[1]) ** 2 +
				(positions[i * 3 + 2] - mid[2]) ** 2;
			if (d > farD) {
				farD = d;
				far = i;
			}
		}
		let a = [positions[far * 3], positions[far * 3 + 1], positions[far * 3 + 2]];
		// the member farthest from that one is the other seed
		let opp = ix[0];
		let oppD = -1;
		for (const i of ix) {
			const d =
				(positions[i * 3] - a[0]) ** 2 +
				(positions[i * 3 + 1] - a[1]) ** 2 +
				(positions[i * 3 + 2] - a[2]) ** 2;
			if (d > oppD) {
				oppD = d;
				opp = i;
			}
		}
		let b = [positions[opp * 3], positions[opp * 3 + 1], positions[opp * 3 + 2]];
		let left: number[] = [];
		let right: number[] = [];
		for (let pass = 0; pass < 3; pass++) {
			left = [];
			right = [];
			for (const i of ix) {
				const da =
					(positions[i * 3] - a[0]) ** 2 +
					(positions[i * 3 + 1] - a[1]) ** 2 +
					(positions[i * 3 + 2] - a[2]) ** 2;
				const db =
					(positions[i * 3] - b[0]) ** 2 +
					(positions[i * 3 + 1] - b[1]) ** 2 +
					(positions[i * 3 + 2] - b[2]) ** 2;
				(da <= db ? left : right).push(i);
			}
			if (!left.length || !right.length) break;
			a = centre(left);
			b = centre(right);
		}
		if (left.length < LOBE_MIN_SIDE || right.length < LOBE_MIN_SIDE) continue;

		measured++;
		const gap = Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);
		const spread = 0.5 * (meanRadius(left, a) + meanRadius(right, b));
		if (gap / Math.max(spread, 1e-9) <= LOBE_RATIO) continue;

		// Larger lobe is the primary and keeps the knot's single-place identity.
		const [bigIx, bigC, smallIx, smallC] =
			left.length >= right.length ? [left, a, right, b] : [right, b, left, a];
		const at = medoid(smallIx, smallC);
		anchors[c * 3] = positions[at * 3];
		anchors[c * 3 + 1] = positions[at * 3 + 1];
		anchors[c * 3 + 2] = positions[at * 3 + 2];
		has[c] = 1;
		counts[c] = smallIx.length;
		shares.push(smallIx.length / ix.length);
		void bigIx;
		void bigC;
	}

	shares.sort((x, y) => x - y);
	const ms = typeof performance === 'undefined' ? 0 : performance.now() - started;
	return {
		anchors,
		has,
		counts,
		report: {
			measured,
			split: shares.length,
			medianShare: shares.length ? shares[shares.length >> 1] : 0,
			ms
		}
	};
}

export function buildLayout(assets: BirdyAssets, local = false): Layout {
	const base = expandClusters(
		assets.positions,
		assets.points.clusterId,
		assets.centroids.k,
		CLUSTER_SPACING
	);
	// A copy, because the local pass writes in place and `assets.positions` is the
	// shipped projection every other reader (and a layout rebuilt with `local` off)
	// still has to be able to see.
	const reshaped = base === assets.positions ? Float32Array.from(base) : base;
	const report = local ? localShapes(assets, reshaped) : null;
	const positions = separateKnots(
		reshaped,
		assets.points.clusterId,
		assets.centroids.k,
		KNOT_GAP
	);
	const counts = new Uint32Array(assets.centroids.k);
	for (let i = 0; i < assets.points.clusterId.length; i++) {
		const c = assets.points.clusterId[i];
		if (c >= 0 && c < counts.length) counts[c]++;
	}
	return {
		positions,
		centroids: centroidsOf(positions, assets.points.clusterId, assets.centroids.k),
		counts,
		local: report,
		lobes: drawnLobes(positions, assets.points.clusterId, assets.centroids.k)
	};
}

/**
 * Each knot's distance to its nearest other knot, for the callers that quote a length in
 * knot-spacings rather than in box units — the wavefront's reach is the one that does.
 *
 * **Why this is a grid and not two nested loops.** It used to be the obvious `k²` scan,
 * which is 18 million distance tests at the debug-100 4 298-knot build (about a second of
 * a frozen tab at load) and **196 million at 13 848 knots**, where it
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

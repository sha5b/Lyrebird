/**
 * What a direction in the picture means — the readable half of an unreadable layout.
 *
 * **Measured problem.** The three axes are whatever the projector chose, and nothing in
 * the interface can say what they are. Correlating each drawn axis against every nameable
 * quantity the build ships, the strongest relationship in the whole table was knot member
 * count at **+0.26**, and duration at **+0.05**. So "left", "up" and "toward the camera"
 * carry no meaning at all, and the only channel a viewer has is proximity — which is the
 * weak one (6 % of a point's drawn neighbours share its type on the shipped build).
 *
 * **The fix is not to force the axes.** Putting duration on x and pitch on y would make
 * position readable and throw away the arrangement that carries the acoustic structure.
 * The visualization literature has the better answer: annotate the projection instead of
 * replacing it — biplots for linear projections, generalized biplots for stress-based ones
 * (Gower/Hare/Bunn), DimReader's axis lines for non-linear ones. The construction here is
 * the standard one: least-squares fit each named attribute against the drawn coordinates,
 * and the fitted gradient is the direction along which that attribute increases fastest.
 * `r2` says how much of the attribute that direction actually explains, which is the part
 * a biplot without it quietly omits — an axis with r2 = 0.05 is a arrow pointing at noise.
 *
 * **Only attributes a person can read are offered.** The descriptor is 28 dimensions and
 * 26 of them are MFCC coefficients, which name nothing anybody can hear. Two are directly
 * meaningful — spectral centroid and spectral flatness — and three more are honest
 * aggregates. Naming a direction "mfcc7_mean" would be a label, not an explanation.
 */
import type { BirdyAssets } from '$lib/data/types';

/** One nameable acoustic quantity, and where to find it in the shipped 28-d descriptor. */
interface Attribute {
	name: string;
	/** What a *higher* value means, in words a listener would use. */
	high: string;
	/** Indices into the 28-d centroid `vector`, averaged. Empty = supplied another way. */
	dims?: string[];
}

const ATTRIBUTES: Attribute[] = [
	{
		name: 'brightness',
		high: 'higher, brighter sounds',
		dims: ['log2_centroid_mean']
	},
	{
		name: 'noisiness',
		high: 'broadband hiss and rattle rather than a clear tone',
		dims: ['flatness_mean']
	},
	{
		// mfcc0 is the log-energy term of the cepstrum, so it stands in for overall level.
		name: 'loudness',
		high: 'louder sounds',
		dims: ['mfcc0_mean']
	},
	{
		// The spread terms say how much the spectrum moves across the syllable: a steady
		// whistle has low values, a rattle or a sweep high ones.
		name: 'movement',
		high: 'sounds that change more across their own length',
		dims: [
			'mfcc1_std',
			'mfcc2_std',
			'mfcc3_std',
			'mfcc4_std',
			'mfcc5_std',
			'mfcc6_std',
			'mfcc7_std'
		]
	},
	{ name: 'duration', high: 'longer calls' }
];

export interface BiplotAxis {
	name: string;
	high: string;
	/** Unit vector in drawn space: the direction this attribute increases fastest. */
	direction: [number, number, number];
	/**
	 * Share of the attribute's variance that direction explains, 0..1. **Read this before
	 * believing the arrow.** A projection is free to scatter an attribute in a way no
	 * straight direction captures, and then the fitted gradient is the best of a bad set.
	 */
	r2: number;
}

/**
 * Fit a readable direction for each named attribute against the knots' drawn positions.
 *
 * Knots rather than points: the 28-d descriptor ships per knot (`centroid-vectors.f32`)
 * and not per point, and a knot is the unit the picture places anyway. Weighted by member
 * count, so a knot holding 1 828 sounds counts for more than one holding 13 — otherwise
 * the fit is dominated by the long tail of tiny knots, which is most of them.
 */
export function biplotAxes(assets: BirdyAssets, centroids: Float32Array): BiplotAxis[] {
	const names = assets.featureSpace.dimNames ?? [];
	const items = assets.centroids.items;
	const k = items.length;
	if (!k || !names.length) return [];

	// Rows: only knots with members and a real position. A memberless knot sits at the
	// centre of the box, which is not a place, and fitting to it drags every axis inward.
	const rows: number[] = [];
	for (let c = 0; c < k; c++) {
		if ((items[c].count ?? 0) > 0) rows.push(c);
	}
	if (rows.length < 8) return [];

	const dimIndex = new Map(names.map((n, i) => [n, i]));
	const out: BiplotAxis[] = [];

	for (const attr of ATTRIBUTES) {
		const value = new Float64Array(rows.length);
		let usable = true;
		if (attr.dims) {
			const idx = attr.dims.map((d) => dimIndex.get(d)).filter((i): i is number => i !== undefined);
			if (!idx.length) {
				usable = false;
			} else {
				for (let r = 0; r < rows.length; r++) {
					const v = items[rows[r]].vector as number[] | undefined;
					if (!v) {
						usable = false;
						break;
					}
					let s = 0;
					for (const i of idx) s += v[i] ?? 0;
					value[r] = s / idx.length;
				}
			}
		} else if (attr.name === 'duration') {
			for (let r = 0; r < rows.length; r++) value[r] = items[rows[r]].meanDuration ?? 0;
		} else {
			usable = false;
		}
		if (!usable) continue;

		const fit = weightedGradient(value, centroids, rows, (c) => items[c].count ?? 0);
		if (fit) out.push({ name: attr.name, high: attr.high, ...fit });
	}
	// Strongest explanation first — that is the order a reader wants, and it puts the
	// arrows worth trusting at the top of whatever shows them.
	return out.sort((a, b) => b.r2 - a.r2);
}

/**
 * Weighted least squares of `value` on the three drawn coordinates, returning the unit
 * gradient and its R².
 *
 * Solved as a 4x4 normal-equation system by Gauss-Jordan. Four unknowns and a matrix that
 * is a weighted covariance plus a mean row: an explicit solve is a dozen lines, needs no
 * dependency, and the only degenerate case — every knot at one place, or one dead axis —
 * is caught by the pivot test and reported as no axis rather than as NaN.
 */
function weightedGradient(
	value: Float64Array,
	positions: Float32Array,
	rows: number[],
	weightOf: (knot: number) => number
): { direction: [number, number, number]; r2: number } | null {
	const n = rows.length;
	// design matrix columns: 1, x, y, z
	const A: number[][] = Array.from({ length: 4 }, () => new Array(5).fill(0));
	let wSum = 0;
	let wvSum = 0;
	for (let r = 0; r < n; r++) {
		const c = rows[r];
		const w = Math.max(1, weightOf(c));
		const t = [1, positions[c * 3], positions[c * 3 + 1], positions[c * 3 + 2]];
		for (let i = 0; i < 4; i++) {
			for (let j = 0; j < 4; j++) A[i][j] += w * t[i] * t[j];
			A[i][4] += w * t[i] * value[r];
		}
		wSum += w;
		wvSum += w * value[r];
	}

	// Gauss-Jordan with partial pivoting
	for (let col = 0; col < 4; col++) {
		let pivot = col;
		for (let r = col + 1; r < 4; r++) if (Math.abs(A[r][col]) > Math.abs(A[pivot][col])) pivot = r;
		if (Math.abs(A[pivot][col]) < 1e-12) return null;
		[A[col], A[pivot]] = [A[pivot], A[col]];
		const d = A[col][col];
		for (let j = col; j < 5; j++) A[col][j] /= d;
		for (let r = 0; r < 4; r++) {
			if (r === col) continue;
			const f = A[r][col];
			if (f === 0) continue;
			for (let j = col; j < 5; j++) A[r][j] -= f * A[col][j];
		}
	}
	const b = [A[0][4], A[1][4], A[2][4], A[3][4]];
	const g: [number, number, number] = [b[1], b[2], b[3]];
	const len = Math.hypot(g[0], g[1], g[2]);
	if (!Number.isFinite(len) || len < 1e-12) return null;

	// R², weighted, against the weighted mean
	const mean = wvSum / wSum;
	let ssRes = 0;
	let ssTot = 0;
	for (let r = 0; r < n; r++) {
		const c = rows[r];
		const w = Math.max(1, weightOf(c));
		const pred =
			b[0] + g[0] * positions[c * 3] + g[1] * positions[c * 3 + 1] + g[2] * positions[c * 3 + 2];
		ssRes += w * (value[r] - pred) ** 2;
		ssTot += w * (value[r] - mean) ** 2;
	}
	const r2 = ssTot > 0 ? Math.max(0, 1 - ssRes / ssTot) : 0;
	return { direction: [g[0] / len, g[1] / len, g[2] / len], r2 };
}

/**
 * What the three screen directions currently mean, for a camera-facing readout.
 *
 * `right`, `up` and `into` are the camera's basis in drawn space. For each one, the
 * attribute whose fitted direction aligns best with it, and by how much — so the caption
 * can say "right ≈ brighter" and be a claim rather than a decoration. `align` is the
 * cosine, signed: negative means the attribute increases the *other* way, and the caller
 * should say "left" instead of inventing an axis.
 */
export interface ScreenReading {
	axis: 'right' | 'up' | 'into';
	name: string;
	high: string;
	/** Signed cosine between the screen axis and the attribute's direction. */
	align: number;
	r2: number;
}

export function readScreenAxes(
	axes: BiplotAxis[],
	right: readonly [number, number, number],
	up: readonly [number, number, number],
	into: readonly [number, number, number],
	minR2 = 0.1
): ScreenReading[] {
	const dot = (a: readonly number[], b: readonly number[]) =>
		a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
	const strong = axes.filter((a) => a.r2 >= minR2);
	const out: ScreenReading[] = [];
	const used = new Set<string>();
	for (const [axis, basis] of [
		['right', right],
		['up', up],
		['into', into]
	] as const) {
		let best: BiplotAxis | null = null;
		let bestAlign = 0;
		for (const a of strong) {
			// One attribute per screen axis: the same quantity named as both "right" and
			// "up" tells a reader nothing about either.
			if (used.has(a.name)) continue;
			const align = dot(a.direction, basis);
			if (Math.abs(align) > Math.abs(bestAlign)) {
				best = a;
				bestAlign = align;
			}
		}
		if (!best) continue;
		used.add(best.name);
		out.push({ axis, name: best.name, high: best.high, align: bestAlign, r2: best.r2 });
	}
	return out;
}

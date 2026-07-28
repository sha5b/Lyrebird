/**
 * What a distance in the picture means as a distance in sound.
 *
 * The galaxy is a projection: 28 dimensions of MFCC statistics squeezed into 3 by
 * classical MDS. Every projection of that kind trades away some of the distances it is
 * trying to show, and the honest question a viewer has — *these two knots are a hand's
 * width apart, is that a lot?* — has no answer at all unless something on screen carries
 * the conversion. This measures it.
 *
 * ## Measured here rather than shipped
 *
 * The relation is fitted in the browser, once, from `centroids.json` — which carries both
 * each cluster's 3D `position` and its 28-d `vector`, so both sides of the comparison are
 * already loaded. 176 clusters is 15 400 pairs, a few milliseconds, and the alternative is
 * a constant baked in here that silently describes the previous build. The pipeline
 * re-places every point on every rebuild; a calibration that does not follow it is worse
 * than none, because it is wrong with authority.
 *
 * ## What the numbers actually license
 *
 * Fitted against the shipped build the relation is
 *
 *     cosine distance ≈ 0.59 × (3D distance) + 0.35,  r = 0.76
 *
 * and the intercept is the part to take seriously. It is not an artefact to be dropped:
 * it says that two clusters drawn on top of each other still differ by about a third of
 * the cosine range. The projection *compresses* — it has to, going from 28 dimensions to
 * 3 — so near distances are systematically understated. Combined with r = 0.76, what the
 * layout supports is comparison, not measurement: of two gaps, the wider one is very
 * probably the more different pair, and how much more different is a guess. The readout
 * says so rather than implying a precision the projection does not have.
 *
 * The floor and the slope are reported separately for that reason; `acousticSpan` has
 * the argument.
 */
import type { Centroids } from '$lib/data/types';

export interface AcousticScale {
	/** Cosine distance per unit of 3D distance. */
	slope: number;
	/**
	 * Cosine distance at zero separation: what two clusters drawn on top of each other
	 * still differ by. Reported on its own rather than folded into the bar's reading —
	 * see `acousticSpan`.
	 */
	floor: number;
	/** Pearson correlation of the fit, over every centroid pair. */
	r: number;
	/** Typical width of one knot, in layout units: twice the mean cluster radius. */
	knot: number;
	/** Median centre-to-centre distance between two clusters, in layout units. */
	gap: number;
}

/** Cosine distance between two equal-length vectors. */
function cosineDistance(a: number[], b: number[]): number {
	let dot = 0;
	let na = 0;
	let nb = 0;
	for (let i = 0; i < a.length; i++) {
		dot += a[i] * b[i];
		na += a[i] * a[i];
		nb += b[i] * b[i];
	}
	return 1 - dot / (Math.sqrt(na * nb) + 1e-12);
}

/**
 * Fit 3D distance against 28-d cosine distance over every pair of cluster centroids.
 *
 * Centroids rather than points, deliberately: 31 328 points is half a billion pairs, and
 * the centroids are what the labels, the trajectories and the eye are actually reading
 * distances between. A pair of clusters is the unit of the question being asked.
 */
export function measureAcousticScale(centroids: Centroids): AcousticScale | null {
	const items = centroids.items.filter((c) => c.vector?.length && c.position?.length === 3);
	if (items.length < 8) return null;

	let n = 0;
	let sx = 0;
	let sy = 0;
	let sxx = 0;
	let syy = 0;
	let sxy = 0;
	const gaps: number[] = [];
	for (let a = 0; a < items.length; a++) {
		for (let b = a + 1; b < items.length; b++) {
			const pa = items[a].position;
			const pb = items[b].position;
			const dx = pa[0] - pb[0];
			const dy = pa[1] - pb[1];
			const dz = pa[2] - pb[2];
			const x = Math.sqrt(dx * dx + dy * dy + dz * dz);
			const y = cosineDistance(items[a].vector, items[b].vector);
			n++;
			sx += x;
			sy += y;
			sxx += x * x;
			syy += y * y;
			sxy += x * y;
			gaps.push(x);
		}
	}
	if (!n) return null;

	const vx = sxx - (sx * sx) / n;
	const vy = syy - (sy * sy) / n;
	const cov = sxy - (sx * sy) / n;
	if (vx <= 0) return null;
	const slope = cov / vx;
	const intercept = sy / n - (slope * sx) / n;
	const r = vy > 0 ? cov / Math.sqrt(vx * vy) : 0;

	gaps.sort((p, q) => p - q);
	const radii = items.map((c) => c.radius ?? 0).filter((v) => v > 0);
	const meanRadius = radii.length ? radii.reduce((s, v) => s + v, 0) / radii.length : 0;

	return {
		slope,
		floor: intercept,
		r,
		knot: meanRadius * 2,
		gap: gaps[gaps.length >> 1]
	};
}

/**
 * The acoustic distance a *span* of the picture stands for — the slope term only.
 *
 * The intercept is deliberately left out of this, and putting it in was the first thing
 * tried. A scale bar carries one implicit promise, which is proportionality: half the bar
 * is half the quantity. Add a 0.35 floor to the reading and that promise breaks in the
 * most misleading direction available — at a close zoom the bar reported 0.38 for a span
 * of 0.05 units and 0.47 for four times that, so a viewer reading it as a ruler would
 * conclude that zooming in barely changes what they are looking at, when what they are
 * actually seeing is a constant being displayed as if it were a measurement.
 *
 * So the bar reports the part that genuinely scales with length, and the floor is stated
 * once, in words, as the separate fact that it is: any two clusters in this corpus differ
 * by about a third of the cosine range before separation on screen counts for anything.
 */
export function acousticSpan(scale: AcousticScale, units: number): number {
	return scale.slope * units;
}

/**
 * The nearest 1, 2 or 5 times a power of ten at or below `raw`. A ruler has to be a round
 * number or reading it off is arithmetic rather than a glance.
 */
export function niceUnits(raw: number): number {
	if (!(raw > 0)) return 0;
	const decade = Math.pow(10, Math.floor(Math.log10(raw)));
	const leading = raw / decade;
	const step = leading >= 5 ? 5 : leading >= 2 ? 2 : 1;
	return step * decade;
}

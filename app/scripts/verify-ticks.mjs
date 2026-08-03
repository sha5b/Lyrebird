/**
 * The stage's one scale: the ruler's ticks and the background grid's lines are the same set.
 *
 * The bug this replaces was not a crash and would never have been one. The grid was
 * `background-size: 120px` — fixed pixels — while the ruler's divisions re-scaled with the
 * zoom. So the stage carried two scales, and only one of them meant anything: at one zoom a
 * square was three knot spacings, at another a fifth of one. **A reader reads a grid as a
 * measure whether or not it is one**, so the squares were answering "how big is that gap"
 * with a number that had no referent.
 *
 * The claim now is geometric and exact — every grid line falls on a ruler tick — and it is the
 * kind of claim that fails by half a tile, which on screen reads as "the alignment is a bit
 * off" rather than as anything broken. So it is computed here at many zooms rather than looked
 * at once.
 *
 * Run with `npm run verify:ticks`. Exits non-zero on any disagreement.
 */
import { TARGET_PX, gridOffsetPx, tickLabel, tickStep } from '../src/lib/galaxy/ticks.ts';

let failures = 0;
const ok = (name, cond, detail = '') => {
	if (cond) console.log(`  ${name.padEnd(58)} ok${detail ? ` (${detail})` : ''}`);
	else {
		failures++;
		console.error(`  ${name.padEnd(58)} FAIL ${detail}`);
	}
};

/** A sweep across every zoom the stage plausibly reaches, in px per knot spacing. */
const ZOOMS = [];
for (let z = 0.05; z < 4000; z *= 1.07) ZOOMS.push(z);

/**
 * Where the ruler puts its ticks, transcribed from `Ruler.svelte`: outward from the centre,
 * because the projection has no meaningful origin.
 */
function rulerTicks(extent, step, pxPerKnot) {
	const px = step * pxPerKnot;
	if (!(px > 4)) return [];
	const out = [extent / 2];
	for (let k = 1; k * px <= extent / 2 + px; k++) {
		out.push(extent / 2 + k * px, extent / 2 - k * px);
	}
	return out.filter((at) => at >= 0 && at <= extent).sort((a, b) => a - b);
}

/**
 * Where CSS puts the grid's lines, transcribed from the `background-position` rule: a tile of
 * `tile` px positioned at `50% + offset`, with its 1 px line at the tile's start.
 */
function gridLines(extent, tile, offset) {
	const origin = (extent - tile) / 2 + offset;
	const out = [];
	// Walk back to the first line at or before 0, then forward across the extent.
	let first = origin;
	while (first > 0) first -= tile;
	for (let at = first; at <= extent; at += tile) if (at >= 0) out.push(at);
	return out;
}

// --- the 1-2-5 sequence ----------------------------------------------------------------
console.log('the step is a round number at every zoom');

{
	// Every step must be 1, 2 or 5 times a power of ten, or the labels stop being round and
	// the grid stops being countable.
	let bad = null;
	for (const z of ZOOMS) {
		const s = tickStep(z);
		const mag = Math.pow(10, Math.round(Math.log10(s)));
		const norm = s / mag;
		const round = [0.1, 0.2, 0.5, 1, 2, 5, 10].some((n) => Math.abs(norm - n) < 1e-9);
		if (!round) bad = { z, s, norm };
	}
	ok('every step is 1, 2 or 5 x a power of ten', !bad,
		bad ? `${bad.s} at ${bad.z} px/knot` : `${ZOOMS.length} zooms`);
}

{
	// Zooming in must never make the unit larger. A non-monotone step means the ruler counts
	// upward as you move closer, which is the opposite of what a scale does.
	let bad = null;
	for (let i = 1; i < ZOOMS.length; i++) {
		if (tickStep(ZOOMS[i]) > tickStep(ZOOMS[i - 1]) + 1e-12) bad = ZOOMS[i];
	}
	ok('the step never grows as you zoom in', !bad, bad ? `at ${bad?.toFixed(2)}` : '');
}

{
	// The drawn spacing has to stay in a readable band. Too small and the grid is texture;
	// too large and there is one square on screen and nothing to count.
	let lo = Infinity;
	let hi = 0;
	for (const z of ZOOMS) {
		const px = tickStep(z) * z;
		lo = Math.min(lo, px);
		hi = Math.max(hi, px);
	}
	// `TARGET_PX` is a FLOOR, not a midpoint, and this is where that was established rather
	// than assumed: the 1-2-5 choice rounds the step *up* to the next round number, so the
	// drawn spacing is always at least the target and at most about 2.4x it. The first version
	// of this check asserted the target was bracketed and failed, which was the check being
	// wrong about the ruler rather than the ruler being wrong.
	ok('drawn spacing never falls below the target', lo >= TARGET_PX - 1e-9,
		`min ${lo.toFixed(1)} px, target ${TARGET_PX}`);
	ok('and never exceeds 2.5x it', hi < TARGET_PX * 2.5, `max ${hi.toFixed(1)} px`);
}

// --- the grid lands on the ticks -------------------------------------------------------
console.log('\nevery grid line is a ruler tick');

{
	// The whole point. Checked at several viewport sizes, because the offset is a percentage
	// of the container and an error in it would show at some widths and not others.
	let mismatch = null;
	let compared = 0;
	for (const extent of [640, 900, 1280, 1600, 1920, 2560]) {
		for (const z of ZOOMS) {
			const step = tickStep(z);
			const tile = step * z;
			const ticks = rulerTicks(extent, step, z);
			if (!ticks.length) continue;
			const lines = gridLines(extent, tile, gridOffsetPx(tile));
			// Every tick must have a line on it. Sub-pixel tolerance, because both sides are
			// floating point and CSS rounds to device pixels anyway.
			for (const t of ticks) {
				compared++;
				if (!lines.some((l) => Math.abs(l - t) < 0.01)) {
					mismatch ??= { extent, z, t, near: lines.find((l) => Math.abs(l - t) < tile) };
				}
			}
		}
	}
	ok('every tick has a coarse grid line on it', !mismatch,
		mismatch
			? `tick ${mismatch.t.toFixed(2)} at ${mismatch.extent}px, nearest line ${mismatch.near?.toFixed(2)}`
			: `${compared} ticks over 6 viewport widths`);
}

{
	// A line at the centre specifically, which is the ruler's zero and the one tick with a
	// fixed meaning. Off by half a tile here is the failure the offset exists to prevent.
	let bad = null;
	for (const extent of [900, 1280, 1920]) {
		for (const z of ZOOMS) {
			const tile = tickStep(z) * z;
			const lines = gridLines(extent, tile, gridOffsetPx(tile));
			if (!lines.some((l) => Math.abs(l - extent / 2) < 0.01)) bad = { extent, z, tile };
		}
	}
	ok('a line falls on the centre, the ruler zero', !bad,
		bad ? `${bad.extent}px at ${bad.z.toFixed(1)} px/knot` : '');
}

{
	// Without the correction the lines sit exactly between the ticks — which is what the old
	// `50%` would have done, and it is why this offset is not cosmetic.
	const extent = 1280;
	const tile = tickStep(100) * 100;
	const naive = gridLines(extent, tile, 0);
	const centred = naive.some((l) => Math.abs(l - extent / 2) < 0.01);
	ok('and without the offset it would not', !centred, `tile ${tile} px`);
}

// --- the labels ------------------------------------------------------------------------
console.log('\nthe label matches the step');

{
	ok('a sub-unit step keeps a decimal', tickLabel(0.5, 0.5) === '0.5');
	ok('a whole step has none', tickLabel(20, 20) === '20');
	ok('zero reads as zero', tickLabel(0, 1) === '0');
	ok('a sub-unit zero still reads 0.0', tickLabel(0, 0.2) === '0.0');
	// A degenerate scale must not produce NaN in the caption.
	ok('no scale yet gives a usable step', tickStep(0) === 1 && tickStep(-5) === 1);
	ok('and NaN does not leak', Number.isFinite(tickStep(Number.NaN)) === false
		? false
		: Number.isFinite(tickStep(Number.NaN)));
}

console.log(failures ? `\n${failures} check(s) failed` : '\nall tick checks passed');
process.exit(failures ? 1 : 0);

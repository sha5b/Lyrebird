/**
 * One tick step, for everything on the stage that has to agree about scale.
 *
 * The ruler owned this arithmetic privately, and the background grid was a flat
 * `background-size: 120px` that knew nothing about it. So the stage carried **two scales at
 * once**: a ruler whose divisions changed as you zoomed, and a lattice of fixed pixel squares
 * that never did. The squares were not a unit of anything — at one zoom a square was three
 * knot spacings and at another a fifth of one — and the eye reads a grid as a measure whether
 * or not it is one, so the picture was quietly answering "how big is that gap" with a number
 * that meant nothing.
 *
 * Both read this now, which is the only way they can be trusted not to drift. A grid line and
 * a ruler tick at the same place on screen is the same claim, made twice.
 */

/**
 * The **smallest** gap a labelled tick may be drawn at, in pixels.
 *
 * Named a target for a long time, and `verify:ticks` established it is a floor: `tickStep`
 * rounds up to the next 1-2-5 value, so the drawn spacing is never under this and reaches
 * about 2.4x it just before each step change. Worth having written down, because it is what
 * bounds the grid: one square is 78 to 190 px, which is a countable lattice at every zoom.
 */
export const TARGET_PX = 78;

/**
 * A tick step in knot spacings, from the 1-2-5 sequence, so labels stay round at every zoom.
 *
 * Below one spacing it keeps going in tenths — up close a single knot fills the screen, and a
 * ruler whose smallest division is the whole knot has nothing to say.
 */
export function tickStep(pxPerKnot: number): number {
	if (!(pxPerKnot > 0)) return 1;
	const raw = TARGET_PX / pxPerKnot;
	const mag = Math.pow(10, Math.floor(Math.log10(raw)));
	const norm = raw / mag;
	const nice = norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 5 ? 5 : 10;
	return nice * mag;
}

/** How a step is written: 0.5 needs a decimal, 20 must not have one. */
export function tickLabel(value: number, step: number): string {
	return step < 1 ? value.toFixed(1) : String(Math.round(value));
}

/**
 * Where the grid's tiles must start for a line to land on the centre of the view.
 *
 * The ruler counts outward from the middle, because the projection has no meaningful origin,
 * so its zero tick is at `extent / 2` and the rest fall at `extent / 2 ± k · step`. A CSS
 * background at `background-position: 50%` puts its tile origin at `(extent − tile) / 2`,
 * which is half a tile *short* of the centre — every line would sit exactly between two
 * ticks, which looks like alignment failing rather than like a different grid. Adding half a
 * tile back is the whole correction.
 */
export function gridOffsetPx(tilePx: number): number {
	return tilePx / 2;
}

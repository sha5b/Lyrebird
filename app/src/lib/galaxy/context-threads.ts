/**
 * Which pass a backdrop thread belongs in, and how strongly it is drawn.
 *
 * This is arithmetic rather than rendering, and it is out here for the reason
 * `inventory-rows.ts` is: a wrong alpha shows up as *a thread that looks a little faint*,
 * never as an error. Nothing here imports three.js, so the whole weight channel can be
 * proven by `verify:context-threads` instead of looked at.
 *
 * The claim being drawn is `ContextPath.kind`, and the two kinds go to two passes:
 *
 *   song     an authored or recorded sequence. Even weight, the established slate ink.
 *   grammar  one transition counted from this bird's own field audio, at an alpha set by
 *            its measured probability — the number the picture used to throw away.
 */

// Extension-explicit, like `listener.ts` -> `features.ts`: `verify:context-threads` runs
// this module under node's type-stripping loader, which does no extension resolution.
import { speciesColourScaled } from './palette.ts';
import type { ContextPath } from './shaders';

/**
 * A grammar thread's two ends, as the bird's own hue walked in lightness.
 *
 * Two things changed here and both are quantities that were being thrown away.
 *
 * **Hue was a constant and is now the bird.** Every grammar thread was `PROV_LEARNED`
 * amber, so a hundred birds' transition graphs were one colour and the star around a
 * pinned knot said nothing about whose star it was. The hue is the same genus-hashed
 * `speciesColourScaled` the tag beside it already wears, so a thread and its label cannot
 * disagree — and `palette.ts`'s rule survives, because hue is still never the sole
 * carrier: the tag names the bird in text.
 *
 * **Direction was not drawn at all.** A first-order grammar is a *directed* transition —
 * "B follows A with probability p" — and a line segment has no arrowhead, so the picture
 * stated the pair and dropped the order. The `from` end is drawn darker and the `to` end
 * lighter, which reads as a thread flowing outward from the syllable that starts it. This
 * is why the band is asymmetric about 1: it has to stay inside `speciesColourScaled`'s
 * ±20 % clamp (past that the walk reads as a different bird, which is the one thing the
 * mapping forbids), and it has to be wide enough to see on a hairline.
 *
 * Songs keep the slate. The split is now a sentence: **a hued thread is counted from the
 * bird, a slate thread is a sequence we or a recordist chose.**
 */
export const FROM_LIGHT = 0.82;
export const TO_LIGHT = 1.18;

/** The `from` and `to` inks for one bird's grammar threads. */
export function grammarEnds(speciesId: string): { from: string; to: string } {
	return {
		from: speciesColourScaled(speciesId, FROM_LIGHT),
		to: speciesColourScaled(speciesId, TO_LIGHT)
	};
}

/**
 * A transition at the floor still has to be visible, and a certain one must not shout.
 *
 * `GRAMMAR_FLOOR` is 0.08, so a bare probability-as-alpha map would draw most surviving
 * transitions under 0.2 and the weighting would read as "the grammar faded out". These two
 * ends are the readable band: a floor transition lands a little under the songs' 0.28 and
 * p = 1 a little over it, so **weight rather than kind** is what changes how strongly a
 * grammar thread reads.
 */
export const WEIGHT_MIN = 0.12;
export const WEIGHT_MAX = 0.5;

/** One drawn segment: two knot indices and the alpha it is drawn at. */
export interface ThreadSegment {
	a: number;
	b: number;
	alpha: number;
}

/** The two passes. Songs carry their strength in the material, grammar per vertex. */
export interface ThreadSegments {
	songs: ThreadSegment[];
	grammar: ThreadSegment[];
}

/**
 * The probability band, clamped.
 *
 * Clamped rather than trusted because a weight outside 0..1 is a bug upstream, and letting
 * it through would paint an invisible or an over-strong thread instead of being caught.
 */
export function alphaFor(weight: number): number {
	const p = Math.min(1, Math.max(0, weight));
	return WEIGHT_MIN + (WEIGHT_MAX - WEIGHT_MIN) * p;
}

/**
 * Split the backdrop into its two passes, one segment per adjacent pair.
 *
 * `nodeCount` drops indices the corpus lacks: a song can name a syllable that owns no
 * knot in this build, and a segment to a knot that does not exist would be drawn to the
 * origin. Dropped rather than clamped, because a thread to the wrong knot is a false
 * statement about the bird while a missing thread is only a gap.
 *
 * A song of one surviving node yields no segment and that is correct — a route needs two
 * places to be a route.
 */
export function contextSegments(paths: ContextPath[], nodeCount: number): ThreadSegments {
	const songs: ThreadSegment[] = [];
	const grammar: ThreadSegment[] = [];
	for (const path of paths) {
		const nodes = path.nodes.filter((i) => Number.isInteger(i) && i >= 0 && i < nodeCount);
		const into = path.kind === 'grammar' ? grammar : songs;
		const alpha = path.kind === 'grammar' ? alphaFor(path.weight) : 1;
		for (let n = 0; n < nodes.length - 1; n++) {
			into.push({ a: nodes[n], b: nodes[n + 1], alpha });
		}
	}
	return { songs, grammar };
}

/**
 * Functional translation, in the sense the field allows (docs/03-decoding-science.md
 * §3.1, Rutz et al. 2023): match live audio to the nearest documented call type and
 * report that call's *documented function* with a confidence label — never a
 * word-for-word sentence.
 */
import type { Centroid, Centroids, Inventory } from '$lib/data/types';
import { formatRefs, speciesById } from '$lib/data/assets';

export interface Candidate {
	centroid: Centroid;
	probability: number;
	similarity: number;
	speciesCommon: string;
}

/**
 * Below this the input does not resemble the corpus well enough to name a call.
 *
 * **It did not need retuning when the match ramp did, and the reason is the point of
 * tying that ramp to percentiles.** `strength` is a smoothstep between the 5th and 90th
 * percentile of how real field syllables score against the shipped centroids, so a
 * threshold on it is really a threshold on *what share of genuine birdsong clears it* —
 * and that share is stable across rebuilds even when every cosine in the corpus moves.
 * Measured across the v5-to-v6 shift, which moved the whole distribution up 0.07-0.14:
 *
 *   gate                 old cosine  old pct     new cosine  new pct
 *   name a call (0.25)        0.698      19 %         0.802      21 %
 *   wave claim (0.15)         0.679      15 %         0.784      16 %
 *   tag claim (0.02)          0.640       9 %         0.750       8 %
 *
 * Every one lands within two points of the corpus share it used to gate. With the ramp
 * left as hand-set constants it was the opposite — the same 0.25 went from naming 81 %
 * of real syllables to naming effectively all of them.
 */
const REPORT_STRENGTH = 0.25;

export interface Reading {
	candidates: Candidate[];
	/** Best candidate, or null when nothing resembles the corpus well enough to judge. */
	best: Candidate | null;
	/** True while the input is voiced enough to judge at all — the "heard but unnamed" state. */
	active: boolean;
	/** 0..1 — how well the input matches anything at all. */
	strength: number;
	/** Rough urgency 0..1 from call rate and pitch — a documented axis, not a meaning. */
	urgency: number;
	caveat: string;
}

const CAVEAT =
	'Matched against documented call types by acoustic similarity. This reports a call’s ' +
	'documented function, not a translation into language: no bird call has been shown to ' +
	'carry propositional sentences.';

export function readActivations(
	inventory: Inventory,
	centroids: Centroids,
	activations: Float32Array,
	similarity: Float32Array,
	options: {
		active: boolean;
		strength?: number;
		onsetRate?: number;
		f0?: number;
		/**
		 * Name lookup that needs no shard (assets.speciesCommon). On a sharded build the
		 * inventory holds only the birds loaded so far, so without this a cluster of an
		 * unloaded bird would be named by its raw id.
		 */
		speciesName?: (id: string) => string;
	} = { active: false }
): Reading {
	const strength = options.strength ?? (options.active ? 1 : 0);
	const ranked: Candidate[] = centroids.items
		.map((centroid, i) => ({
			centroid,
			probability: activations[i] ?? 0,
			similarity: similarity[i] ?? 0,
			speciesCommon:
				options.speciesName?.(centroid.speciesId) ??
				speciesById(inventory, centroid.speciesId)?.common ??
				centroid.speciesId
		}))
		.sort((a, b) => b.probability - a.probability)
		.slice(0, 4);

	// Call rate and pitch both scale with threat in the species that have been tested
	// (chickadee D-note count, tit alarm rate) — reported as an axis, never as words.
	const rate = options.onsetRate ?? 0;
	const pitch = options.f0 ?? 0;
	const urgency = Math.min(1, rate / 6) * 0.6 + Math.min(1, Math.max(0, (pitch - 2000) / 5000)) * 0.4;

	// Naming a call needs more than "something is audible": the input has to actually
	// resemble a documented type. Without this the panel confidently reported a call
	// whenever a fan was running.
	const confident = options.active && strength >= REPORT_STRENGTH;
	return {
		candidates: ranked,
		best: confident && ranked.length ? ranked[0] : null,
		active: options.active,
		strength,
		urgency,
		caveat: CAVEAT
	};
}

export function confidenceLabel(confidence: string): { text: string; hint: string } {
	switch (confidence) {
		case 'experimental':
			return {
				text: 'playback-verified',
				hint: 'Function established by playback experiments on wild birds.'
			};
		case 'documented':
			return { text: 'documented', hint: 'Function described in the literature.' };
		case 'inferred':
			return { text: 'inferred', hint: 'Plausible from context, not experimentally established.' };
		case 'unlabelled':
			return {
				text: 'field recording',
				hint: 'Real audio of this species with no documented function attached.'
			};
		default:
			return { text: 'invented', hint: 'Our own mapping. Not a claim about real birds.' };
	}
}

/**
 * The *other* axis: who chose the order.
 *
 * `confidenceLabel` above answers "how strong is the claim on these sounds", and it is
 * the only badge the reading panel used to draw. That left the second axis unsayable at
 * the level of a single sounding thing, and the gap was visible: an improvised bout comes
 * back from `improvise()` as `confidence: 'unlabelled'` with `source: 'invented'`, so the
 * panel printed **"field recording"** over a phrase no bird has ever sung. The syllables
 * were field recordings and the badge was true about them; the sentence a reader took from
 * it was false about the bout.
 *
 * `Phrase.source` has carried the answer all along (`grammar.ts`) and nothing rendered it.
 * The two badges together are the project's one-line statement of the whole distinction:
 * **the bird made the sounds; we chose the order** (docs/08 §8.5, HANDOFF's own wording).
 *
 * `documented` returns null rather than a second badge. A sequence somebody recorded or
 * authored needs no disclaimer, and a badge on every phrase would spend the reader's
 * attention on the case that makes no extra claim.
 */
export function sourceLabel(
	source: 'documented' | 'invented'
): { text: string; hint: string } | null {
	if (source === 'documented') return null;
	return {
		text: 'our order',
		hint: 'The syllables are measured; the sequence they are played in is ours, not a bout any bird sang.'
	};
}

export function citationsFor(inventory: Inventory, refs: string[]): string[] {
	return formatRefs(inventory, refs);
}

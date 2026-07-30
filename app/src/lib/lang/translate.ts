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

/** Below this the input does not resemble the corpus well enough to name a call. */
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

export function citationsFor(inventory: Inventory, refs: string[]): string[] {
	return formatRefs(inventory, refs);
}

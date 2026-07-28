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

export interface Reading {
	candidates: Candidate[];
	/** Best candidate, or null when nothing is loud enough to judge. */
	best: Candidate | null;
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
	options: { active: boolean; onsetRate?: number; f0?: number } = { active: false }
): Reading {
	const ranked: Candidate[] = centroids.items
		.map((centroid, i) => ({
			centroid,
			probability: activations[i] ?? 0,
			similarity: similarity[i] ?? 0,
			speciesCommon: speciesById(inventory, centroid.speciesId)?.common ?? centroid.speciesId
		}))
		.sort((a, b) => b.probability - a.probability)
		.slice(0, 4);

	// Call rate and pitch both scale with threat in the species that have been tested
	// (chickadee D-note count, tit alarm rate) — reported as an axis, never as words.
	const rate = options.onsetRate ?? 0;
	const pitch = options.f0 ?? 0;
	const urgency = Math.min(1, rate / 6) * 0.6 + Math.min(1, Math.max(0, (pitch - 2000) / 5000)) * 0.4;

	return {
		candidates: ranked,
		best: options.active && ranked.length ? ranked[0] : null,
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
		default:
			return { text: 'invented', hint: 'Our own mapping. Not a claim about real birds.' };
	}
}

export function citationsFor(inventory: Inventory, refs: string[]): string[] {
	return formatRefs(inventory, refs);
}

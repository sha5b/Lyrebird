/**
 * Individual voices.
 *
 * Species-level differences (syllable inventory, contours, timbre, time-scale) come from
 * `data/inventory.json`. This module adds the layer below that: a *particular* bird, whose
 * deviations from its species norm are fixed for its lifetime instead of being redrawn on
 * every note. Without it a chorus is one bird with amnesia — two notes in a row are never
 * consistent with each other.
 *
 * This is not decoration. Individual identity is the most reliably documented "semantic"
 * layer in birdsong: zebra finches identify each other from single calls (Elie &
 * Theunissen 2018), and the quaver pattern of a tawny owl hoot identifies individual males
 * (Galeotti & Pavan 1991) — which is why `vibScale` exists and is held per bird.
 */
import type { Syllable } from '$lib/data/types';

export interface Individual {
	id: string;
	speciesId: string;
	/** Short human-facing name, e.g. "great tit 2". */
	label: string;
	/** Held pitch deviation in cents; roughly the spread real conspecifics show. */
	pitchCents: number;
	durScale: number;
	levelScale: number;
	/** Trill/rattle rate: part of what makes a rattle recognisable. */
	amScale: number;
	/** Vibrato rate — the owl's individual signature. */
	vibScale: number;
	harmonicScale: number;
	/** Where this bird sits, -1 left to +1 right. Fixed, because birds hold territories. */
	pan: number;
}

/** mulberry32: small, fast, and deterministic, so a bird sounds the same every session. */
function rng(seed: number): () => number {
	let a = seed >>> 0;
	return () => {
		a = (a + 0x6d2b79f5) >>> 0;
		let t = Math.imul(a ^ (a >>> 15), 1 | a);
		t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
		return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
	};
}

function hash(text: string): number {
	let h = 0x811c9dc5;
	for (let i = 0; i < text.length; i++) {
		h ^= text.charCodeAt(i);
		h = Math.imul(h, 0x01000193) >>> 0;
	}
	return h >>> 0;
}

const GOLDEN = 0.6180339887498949;

/**
 * Low-discrepancy sequence in [-1, 1]. Independent random draws cluster — two birds drawn
 * at random landed 16 cents apart in testing, which nobody can hear as two birds — so the
 * traits that carry identity are spread by index instead of sampled. `phase` decorrelates
 * one trait from another.
 */
function spread(index: number, phase: number): number {
	return (((index + 1) * GOLDEN + phase) % 1) * 2 - 1;
}

export function createIndividual(speciesId: string, index: number, commonName?: string): Individual {
	const id = `${speciesId}#${index}`;
	const r = rng(hash(id));
	const jitter = (amount: number) => (r() * 2 - 1) * amount;
	return {
		id,
		speciesId,
		label: `${commonName ?? speciesId} ${index + 1}`,
		// about a semitone of range, which is the order of variation between conspecifics
		pitchCents: spread(index, 0) * 90,
		vibScale: 1 + spread(index, 0.37) * 0.18,
		pan: spread(index, 0.71) * 0.85,
		// secondary traits: audible as character, not needed to tell birds apart
		durScale: 1 + jitter(0.09),
		levelScale: 1 + jitter(0.12),
		amScale: 1 + jitter(0.1),
		harmonicScale: 1 + jitter(0.22)
	};
}

/** A population with a stable roster: the same birds are present all session. */
export function createPopulation(
	species: { id: string; common: string }[],
	perSpecies = 2
): Individual[] {
	const birds: Individual[] = [];
	for (const s of species) {
		for (let i = 0; i < perSpecies; i++) birds.push(createIndividual(s.id, i, s.common));
	}
	return birds;
}

/**
 * Renders a syllable in one bird's voice. `tremor` is the only random part — a fraction of
 * a percent of note-to-note wobble, so the bird sounds alive without losing its identity.
 */
export function applyVoice(syllable: Syllable, bird: Individual, tremor = 0.006): Syllable {
	const wobble = () => 1 + (Math.random() * 2 - 1) * tremor;
	const pitch = Math.pow(2, bird.pitchCents / 1200) * wobble();
	return {
		...syllable,
		dur: syllable.dur * bird.durScale * wobble(),
		level: Math.min(1, syllable.level * bird.levelScale),
		am: syllable.am ? syllable.am * bird.amScale : syllable.am,
		harmonic:
			syllable.harmonic === undefined
				? undefined
				: Math.min(1, syllable.harmonic * bird.harmonicScale),
		vib: syllable.vib
			? { rate: syllable.vib.rate * bird.vibScale, depth: syllable.vib.depth }
			: undefined,
		contour: syllable.contour.map(([t, hz]) => [t, hz * pitch] as [number, number]),
		voices: transposedVoices(syllable, (hz) => hz * pitch)
	};
}

/**
 * The second voice under the same pitch change as the first.
 *
 * Its contour is the first voice's shifted by a measured ratio (docs/15 §5), so moving only the
 * first voice changes that ratio. Formants stay: they belong to the tract, not to the pitch.
 */
export function transposedVoices(
	syllable: Syllable,
	move: (hz: number) => number
): Syllable['voices'] {
	const second = syllable.voices;
	if (!second) return second;
	return {
		...second,
		contour: second.contour.map(([t, hz]) => [t, move(hz)] as [number, number])
	};
}

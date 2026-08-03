/**
 * A readable name for a syllable type that no source ever named.
 *
 * **The problem, and why the obvious fix is not available.** A type `learn` fitted from
 * field audio is called `L33`, which is a serial number and tells a reader nothing. The
 * tempting repair is to give it a real call name — `jar`, `fee-bee`, `hawk-perched` — the
 * way the documented half of the inventory is named. That is exactly the thing this project
 * may not do. Those names come out of the literature with a citation attached (`jar` is
 * Suzuki 2014 on the Japanese great tit) and they name a call's **function**. Nobody has
 * documented what `L33` is for. Printing a call name beside it would be a claim with no
 * source, which is the one failure mode the whole inventory is built to avoid.
 *
 * **What is available is the form.** The pipeline measured this syllable: its pitch track,
 * how long it lasts, which timbre class it was fitted with, whether it is amplitude- or
 * frequency-modulated, how noisy it is. Those are descriptions of the waveform, and naming
 * a sound after its shape is ordinary bioacoustic practice — a downslurred whistle is a
 * description, not an interpretation. So a fitted type is named after what it *sounds like*
 * and never after what it might *mean*:
 *
 *     L33  ->  buzzy fall · 555 Hz · 29 ms
 *     L32  ->  buzzy warble, dipping · 4.4 kHz · 251 ms
 *
 * Every term below is a threshold on a measured field, and the thresholds are named
 * constants so a reader can check what "steep" was taken to mean. Nothing here is fitted to
 * anything; these are reporting bands, not a model.
 */
import type { Syllable } from './types';

/**
 * How far the pitch must travel, as a ratio of its own median, before the sound is
 * described as rising or falling rather than level.
 *
 * A semitone is 5.9 %; this is a little over two semitones, which is about where a sweep
 * stops being vibrato and starts being the shape of the note.
 */
const SWEEP = 0.12;
/** A sweep this large is called steep. Roughly an octave. */
const STEEP = 0.6;
/** Peak or trough this far off the straight line between the ends: an arch or a dip. */
const BEND = 0.18;
/** Amplitude modulation at or above this rate is heard as a rattle rather than a trill. */
const BUZZ_HZ = 60;
/**
 * Modulation depth below this earns no word.
 *
 * Set from the corpus's own distribution rather than by taste: `amDepth` over the 13 704
 * fitted types clusters at 0.15, 0.3, 0.45, 0.6 and 0.8, and a threshold here keeps the top
 * two bands. Lower and four types in five are called trilled, which distinguishes nothing —
 * a word every row carries is not a description.
 */
const MOD_DEPTH = 0.4;
/** Frequency modulation this deep is a warble. Keeps the corpus's 0.09 and 0.4 bands. */
const VIB_DEPTH = 0.08;

/** Pitch in the unit a reader thinks in: Hz under a kilohertz, kHz above it. */
export function formatPitch(hz: number): string {
	if (!Number.isFinite(hz) || hz <= 0) return '—';
	return hz < 1000 ? `${Math.round(hz)} Hz` : `${(hz / 1000).toFixed(1)} kHz`;
}

/** The median of a syllable's pitch track, which is the pitch a listener would name. */
export function medianPitch(syllable: Pick<Syllable, 'contour'>): number {
	const hz = (syllable.contour ?? []).map((p) => p[1]).filter((v) => v > 0);
	if (!hz.length) return 0;
	const sorted = [...hz].sort((a, b) => a - b);
	const mid = sorted.length >> 1;
	return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

/**
 * The pitch track's shape, in one or two words.
 *
 * Read off the ends and the largest excursion from the line between them, which is the
 * same thing an eye does with a spectrogram. Deliberately coarse: six shapes a person can
 * hear, not a curve classification.
 */
export function contourShape(syllable: Pick<Syllable, 'contour'>): string {
	const points = (syllable.contour ?? []).filter((p) => p[1] > 0);
	if (points.length < 2) return 'flat';
	const first = points[0][1];
	const last = points[points.length - 1][1];
	const median = medianPitch(syllable) || first;
	const travel = (last - first) / median;

	// How far the track bends away from a straight line between its two ends. Positive is
	// an arch (it goes above), negative a dip.
	let bend = 0;
	for (const [t, hz] of points) {
		const straight = first + (last - first) * t;
		const off = (hz - straight) / median;
		if (Math.abs(off) > Math.abs(bend)) bend = off;
	}

	const direction =
		travel > STEEP
			? 'steep rise'
			: travel > SWEEP
				? 'rise'
				: travel < -STEEP
					? 'steep fall'
					: travel < -SWEEP
						? 'fall'
						: '';
	const shape = bend > BEND ? 'arch' : bend < -BEND ? 'dip' : '';

	if (direction && shape) return `${direction}, ${shape === 'arch' ? 'arching' : 'dipping'}`;
	return direction || shape || 'flat';
}

/**
 * The sound's quality, from the timbre class it was fitted with and its modulation.
 *
 * `timbre` is one of three the synthesiser offers, so it is the model's own word for the
 * sound rather than an inference: `pure` is a whistle, `reed` a harmonic-rich tone, `buzz`
 * a noisy one.
 *
 * **At most one modulation word, and often none.** Every one of these properties is
 * measured and several are usually present at once, so an unbudgeted list produced
 * "reedy trilled warbling two-voiced steep fall, dipping" — accurate, and past the length
 * at which a name is a name. The strongest modulation is the one worth reporting: a warble
 * you can hear over a trill you can hear is what the note sounds like.
 */
export function toneWords(syllable: Syllable): string[] {
	const words: string[] = [];
	if (syllable.timbre === 'pure') words.push('clear');
	else if (syllable.timbre === 'reed') words.push('reedy');
	else if (syllable.timbre === 'buzz') words.push('buzzy');

	const amDepth = syllable.amDepth ?? 0;
	const amRate = syllable.am ?? 0;
	const vibDepth = syllable.vib?.depth ?? 0;
	const hasAm = amDepth >= MOD_DEPTH && amRate > 0;
	const hasVib = vibDepth >= VIB_DEPTH;

	// Compared as multiples of their own thresholds, which is the only way two depths on
	// different scales can be ranked at all.
	if (hasAm && (!hasVib || amDepth / MOD_DEPTH >= vibDepth / VIB_DEPTH)) {
		words.push(amRate >= BUZZ_HZ ? 'rattling' : 'trilled');
	} else if (hasVib) {
		words.push('warbling');
	} else if (syllable.two) {
		// Two independent voices at once is the syrinx doing something no single oscillator
		// can, and it is audible — but it loses to a modulation, which is louder.
		words.push('two-voiced');
	}
	return words;
}

/**
 * The sound's form in words — quality, then modulation, then shape.
 *
 * Words only, no numbers: the pitch and the length are measurements and belong in columns
 * of their own where they can be scanned down, not buried in a sentence. `syllableName`
 * below is the one-string version for a tooltip or a log line.
 */
export function describeForm(syllable: Syllable): string {
	return [...toneWords(syllable), contourShape(syllable)].filter(Boolean).join(' ');
}

/**
 * The name to show for a syllable type.
 *
 * A documented call keeps the name its sources gave it, always — that name carries a
 * citation and this function must never displace it. Only a type with no source gets a
 * described name, and what it describes is form.
 */
export function syllableName(syllable: Syllable): string {
	if (!syllable.learned) return syllable.label;
	return `${describeForm(syllable)} · ${formatPitch(medianPitch(syllable))} · ${Math.round(syllable.dur * 1000)} ms`;
}

/**
 * Where a type's name comes from, which is the distinction the ids were carrying alone.
 *
 * `documented` — the literature named this call and the inventory cites it. Its id is the
 * source's own word for the sound (`jar`, `feebee`, `hawkPerched`), which is why the ids in
 * this half look nothing like each other.
 * `fitted` — `learn` found this type in field recordings. Its id is a serial number and its
 * name above is a description of the waveform. No source has said what it is for.
 */
export function nameSource(syllable: Syllable): 'documented' | 'fitted' {
	return syllable.learned ? 'fitted' : 'documented';
}

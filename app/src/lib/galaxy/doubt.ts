/**
 * The two numbers that drain a mark's colour, and the one rule they share.
 *
 * **Saturation is a shared channel, not two channels.** Both of these say "read this mark's
 * position with less confidence", and there is exactly one free visual channel left to say
 * it in: hue carries provenance or genus, size and ink weight carry activation and the
 * figure/ground swap, tone carries depth (the fog darkens the near side as well as paling
 * the far one, deliberately — that gradient is what makes the scatter read as a volume),
 * the inner gradient carries pitch, and the mark's edge is pinned to one pixel by `fwidth`
 * because a constant feather turns a five-pixel mark into a smudge. So the two numbers take
 * turns on saturation rather than competing for channels that are already spoken for, and
 * the switch that picks between them is what makes the comparison direct: the same marks,
 * the same frame, drained by two different doubts.
 *
 *   - **agreement** — `points.knnAgreement`, the share of a point's ten drawn neighbours
 *     that carry its own type. Doubt about *where the map put it*.
 *   - **snr** — `points.snr`, the signal-to-noise ratio of the syllable in the band it was
 *     segmented in. Doubt about *the recording the measurement came from*.
 *
 * **One value, one meaning: 1 is "no recorded reason to doubt this", 0 is "every reason".**
 * The shader drains colour by `1 - value`, so a build that ships no measurement fills with
 * 1 and draws exactly as it drew before the channel existed.
 */

/** Which number is draining colour right now; `''` is none. */
export type DoubtSource = '' | 'agreement' | 'snr';

/** Absent measurements fill with this: no recorded reason to doubt the position. */
export const NO_DOUBT = 1;

/**
 * Where the ends of the SNR ramp are put, and why it is a clamp rather than the range.
 *
 * The shipped array runs from −0.0 to **166.95 dB**, and 85 of 435 630 values sit above
 * 100 dB. An SNR of 100 dB is a ratio of ten billion; what those points actually are is a
 * syllable whose noise-floor estimate came out near zero, so the quotient blew up. Mapped
 * linearly, those 85 points would own the top of the scale and the 14.5 % of the corpus
 * below 6 dB — the sounds a viewer most needs to distrust — would be crowded into the
 * bottom few percent of the ramp.
 *
 * So the ramp is the corpus's own 5th and 95th percentiles (**2.14 and 39.34 dB** on this
 * build), computed from the shipped values rather than hardcoded, and everything outside
 * saturates. The panel prints both ends, because a clamped scale whose ends are unstated
 * invites "fully coloured" to be read as "cleanest recording in the corpus" when it means
 * "at or above the 95th percentile".
 */
export const SNR_CLAMP = { lo: 0.05, hi: 0.95 } as const;

/** The ends of a ramp, in the source's own units, plus how many values had none. */
export interface DoubtRange {
	lo: number;
	hi: number;
	absent: number;
	measured: number;
}

/**
 * The two percentiles of the finite values, by nearest rank on the sorted array.
 *
 * Nulls are counted rather than treated as zero: on this build all 8 583 of them are the
 * rendered inventory rows, which have no noise floor to measure a ratio against, so a zero
 * would report our own synthesis as the noisiest audio in the corpus.
 */
export function doubtRange(
	values: readonly (number | null | undefined)[],
	clamp: { lo: number; hi: number } = SNR_CLAMP
): DoubtRange {
	const finite: number[] = [];
	let absent = 0;
	for (const v of values) {
		if (typeof v === 'number' && Number.isFinite(v)) finite.push(v);
		else absent++;
	}
	if (!finite.length) return { lo: 0, hi: 1, absent, measured: 0 };
	finite.sort((a, b) => a - b);
	const at = (p: number) => finite[Math.min(finite.length - 1, Math.max(0, Math.round(p * (finite.length - 1))))];
	return { lo: at(clamp.lo), hi: at(clamp.hi), absent, measured: finite.length };
}

/**
 * A source array to one float per point in 0..1, ready for the `aTrust` attribute.
 *
 * `range` absent means the values are already a share — that is the agreement case, where 0
 * and 1 are the natural ends and rescaling to percentiles would make a corpus with no
 * agreement anywhere look as though half of it agreed.
 */
export function toDoubtBuffer(
	n: number,
	values: readonly (number | null | undefined)[] | undefined,
	range?: DoubtRange
): Float32Array {
	const out = new Float32Array(n).fill(NO_DOUBT);
	if (!values) return out;
	const span = range ? Math.max(1e-9, range.hi - range.lo) : 1;
	const lo = range ? range.lo : 0;
	for (let i = 0; i < n; i++) {
		const v = values[i];
		if (typeof v !== 'number' || !Number.isFinite(v)) continue;
		out[i] = Math.min(1, Math.max(0, (v - lo) / span));
	}
	return out;
}

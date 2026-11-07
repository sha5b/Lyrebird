import { knotDoubt } from '$lib/data/assets';
import type { LyrebirdAssets } from '$lib/data/types';
import type { DoubtRange } from './doubt';
import { doubtColourScaled } from './palette';

/**
 * The two doubt layers as the paths need them: which channels are on, plus the SNR ramp.
 *
 * Paths, crosses and relation threads kept the bird's hue while the points and tags under
 * them wore their doubt, so a rose knot sat at the end of a thread that said nothing about
 * it (owner, 2026-11-07: "recolor path too"). Their colours come from here so a thread's end
 * is the colour of the tag on that knot rather than a second reading of the same number.
 */
export interface DoubtLayer {
	agree: boolean;
	snr: boolean;
	range?: DoubtRange;
}

export const NO_DOUBT_LAYER: DoubtLayer = { agree: false, snr: false };

export const doubtLayerOn = (layer: DoubtLayer): boolean => layer.agree || layer.snr;

/** One knot's doubt colour. A channel that is off is left out, as `doubtColourScaled` asks. */
export function doubtKnotColour(
	assets: LyrebirdAssets,
	knot: number,
	layer: DoubtLayer,
	lightScale = 1
): string {
	return doubtColourScaled(
		{
			agree: layer.agree ? (knotDoubt(assets, assets.points.knnAgreement)[knot] ?? 1) : undefined,
			snr: layer.snr ? (knotDoubt(assets, assets.points.snr, layer.range)[knot] ?? 1) : undefined
		},
		lightScale
	);
}

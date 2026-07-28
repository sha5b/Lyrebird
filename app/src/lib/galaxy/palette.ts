/**
 * The galaxy's colour, built in OKLCH so the hues are perceptually even.
 *
 * Rotating hue in HSL at a fixed lightness produces a palette where yellow glares and
 * blue sinks — the "lightness" is nominal, not perceived. OKLCH's L really is perceived
 * lightness, so a ring of hues at one L reads as one family, which is what a resting
 * corpus should look like.
 *
 * Every category has two steps rather than one: a **pale** resting tint and a
 * **saturated** responding one. Response is then a walk along a single hue from pale to
 * full, which keeps identity fixed while intensity moves — and, unlike a walk from dark
 * to darker, it stays visible when forty points of the same cluster overlap.
 *
 * ## What colour can and cannot carry here
 *
 * Twelve hues cannot be told apart reliably by colour alone; under colour-vision
 * deficiency only about three can, on a scatter where every pair appears together. So
 * colour in this view is *orienting*, never identifying: every cluster carries a visible
 * label naming its species, selecting a bird dims the others, and the reading panel says
 * which bird it heard. Remove the colour entirely and nothing becomes unreadable. The
 * three-step meaning palette below is the one that is held to the full gate, because
 * there it is doing real categorical work.
 *
 * Measured on the twelve species hues, all pairs, against the paper surface: chroma
 * floor and lightness band pass; worst normal-vision pair ΔE 12.9 against a 15 floor,
 * worst deutan pair 1.2. Those two do not pass and cannot be made to — see the note on
 * `HUE_COUNT`. They are shipped because colour here is orienting, with identity carried
 * elsewhere; they would not be acceptable in a chart where it was not.
 */

/** sRGB gamma encoding for one channel of a linear-light value. */
function encode(channel: number): number {
	const v = channel <= 0.0031308 ? 12.92 * channel : 1.055 * Math.pow(channel, 1 / 2.4) - 0.055;
	return Math.min(1, Math.max(0, v));
}

function inGamut(rgb: [number, number, number]): boolean {
	return rgb.every((v) => v >= -1e-4 && v <= 1 + 1e-4);
}

/** OKLCH -> linear sRGB (Björn Ottosson's matrices). */
function oklchToLinear(l: number, c: number, hDeg: number): [number, number, number] {
	const h = (hDeg * Math.PI) / 180;
	const a = c * Math.cos(h);
	const b = c * Math.sin(h);

	const l_ = l + 0.3963377774 * a + 0.2158037573 * b;
	const m_ = l - 0.1055613458 * a - 0.0638541728 * b;
	const s_ = l - 0.0894841775 * a - 1.291485548 * b;

	const L = l_ * l_ * l_;
	const M = m_ * m_ * m_;
	const S = s_ * s_ * s_;

	return [
		4.0767416621 * L - 3.3077115913 * M + 0.2309699292 * S,
		-1.2684380046 * L + 2.6097574011 * M - 0.3413193965 * S,
		-0.0041960863 * L - 0.7034186147 * M + 1.707614701 * S
	];
}

/**
 * OKLCH -> `#rrggbb`, reducing chroma until the colour fits in sRGB.
 *
 * At a fixed lightness the sRGB gamut is much wider for some hues than others — a
 * saturated blue exists where an equally saturated yellow does not. Clipping the
 * channels instead would shift the hue; backing the chroma off keeps it.
 */
export function oklch(l: number, c: number, hDeg: number): string {
	let chroma = c;
	let rgb = oklchToLinear(l, chroma, hDeg);
	while (!inGamut(rgb) && chroma > 0) {
		chroma -= 0.002;
		rgb = oklchToLinear(l, chroma, hDeg);
	}
	return (
		'#' +
		rgb
			.map((v) =>
				Math.round(encode(v) * 255)
					.toString(16)
					.padStart(2, '0')
			)
			.join('')
	);
}

/** Largest chroma this hue can reach at this lightness inside sRGB. */
function maxChroma(l: number, hDeg: number): number {
	let lo = 0;
	let hi = 0.4;
	for (let i = 0; i < 24; i++) {
		const mid = (lo + hi) / 2;
		if (inGamut(oklchToLinear(l, mid, hDeg))) lo = mid;
		else hi = mid;
	}
	return lo;
}

/** Slots in the shader's palette uniforms. Species beyond this reuse a hue. */
export const PALETTE_SLOTS = 16;

// Pastel on both ends. The resting tint is barely more than tinted paper; the
// responding one is a soft colour rather than a saturated one, because the corpus is
// 4287 overlapping marks and anything heavier stacks into poster paint. Separation is
// carried by the *step* between the two, by size, and by the ring — not by loading up
// the chroma.
const REST_L = 0.9;
const REST_C = 0.042;
const HOT_C = 0.135;
const HOT_L_MIN = 0.55;
const HOT_L_MAX = 0.8;
const HOT_L_PREFERRED = 0.68;
/** Where the hue wheel starts. 35° puts a warm ochre first, which suits a paper ground. */
const HUE_START = 35;

/**
 * Lightness at which this hue can actually carry `HOT_C`.
 *
 * Holding lightness fixed across the wheel is what ruins a generated palette: sRGB has
 * far less room for a saturated yellow at L 0.58 than for a saturated blue, so several
 * hues clamp to nearly the same muddy olive — measured at ΔE 0.3, indistinguishable
 * even with full colour vision. Letting each hue sit where it can hold its chroma costs
 * some lightness evenness and buys back the separation.
 */
function hotLightness(hDeg: number): number {
	let best = HOT_L_PREFERRED;
	let bestScore = -Infinity;
	for (let l = HOT_L_MIN; l <= HOT_L_MAX + 1e-9; l += 0.01) {
		// prefer reaching the target chroma, then prefer sitting near the middle
		const score = Math.min(HOT_C, maxChroma(l, hDeg)) - 0.02 * Math.abs(l - HOT_L_PREFERRED);
		if (score > bestScore) {
			bestScore = score;
			best = l;
		}
	}
	return best;
}

/**
 * Six hues at three lightness tiers, rather than sixteen hues at one.
 *
 * Hue alone cannot carry this many categories, and the limit is arithmetic rather than a
 * matter of picking better colours: at this chroma, clearing the ΔE 15 normal-vision
 * floor needs roughly 52° between hues, so a wheel holds about seven. Sixteen evenly
 * spaced hues put adjacent pairs at ΔE 5 — the same colour, to most eyes.
 *
 * Separating on lightness as well turns one crowded axis into two roomy ones. Adjacent
 * slots differ by 60° of hue *and* a lightness tier, and slots sharing a hue differ by
 * two tiers, so no pair relies on hue alone.
 */
const HUE_COUNT = 6;
const TIERS = [0.79, 0.69, 0.59];

export function speciesPalette(): { rest: string[]; hot: string[] } {
	const rest: string[] = [];
	const hot: string[] = [];
	for (let i = 0; i < PALETTE_SLOTS; i++) {
		const hue = (HUE_START + ((i % HUE_COUNT) * 360) / HUE_COUNT) % 360;
		const tier = TIERS[Math.floor(i / HUE_COUNT) % TIERS.length];
		hot.push(oklch(tier, Math.min(HOT_C, maxChroma(tier, hue)), hue));
		// the resting tint keeps the hue but not the tier, so a corpus at rest reads as
		// one pale family instead of a stripe of light and dark
		rest.push(oklch(REST_L, REST_C, hue));
	}
	return { rest, hot };
}

/**
 * The monochrome pair. Neutral rather than a desaturated hue, so nothing in the picture
 * suggests a category that is no longer being shown, and the two ends are far enough
 * apart in lightness that response is as visible as it is in colour: ΔL* is about 55,
 * where the pale-to-saturated walk of a species hue is about 25.
 */
export const MONO_REST = '#cdd3da';
export const MONO_HOT = '#1e2836';

/**
 * The three-step meaning palette, from the validated categorical slots 1–3. Held to the
 * full all-pairs gate: worst pair ΔE 9.2 deutan, 24.0 normal, on this surface.
 */
/** Three claims plus a neutral for "no claim", which must not read as a category. */
export const CLAIM_HOT = ['#2a78d6', '#eb6834', '#1baf7a', '#7b8794'];

/** Pale companions to the above, mixed toward the paper rather than desaturated. */
export const CLAIM_REST = ['#d7e5f8', '#fae0d2', '#d2efe4', '#dfe3e8'];

/**
 * Softer steps of the same three hues, for marks that sit over the cloud — trajectory
 * threads, label rules — where the full categorical colour would shout.
 */
export const CLAIM_SOFT = ['#5b95df', '#ef8d63', '#4dc59a', '#96a0ac'];

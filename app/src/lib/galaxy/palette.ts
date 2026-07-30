/**
 * The galaxy's colour: one ink, one paper, and one accent that means "this is what you
 * asked for".
 *
 * There used to be two published categorical schemes here — Paul Tol's muted set for
 * species, Okabe & Ito for how much meaning a cluster claims — and a switch in the
 * interface to choose between them. They were good palettes and they were solving a
 * problem this picture does not have. Twelve species cannot be told apart by hue on a
 * scatter where every pair appears together; under colour-vision deficiency about three
 * can. So the hues were never identifying, only orienting, and the arrangement now orients
 * far better than they did: `Bird` gives every species an island of its own. What colour was
 * gesturing at, position says outright.
 *
 * What is left is the distinction the view actually turns on, which was always a
 * *contrast* rather than a category:
 *
 * - **rest → ink** is response. A pale mark darkens as its cluster answers the sound.
 *   ΔL* between the two ends is about 55, which is more range than the pale-to-saturated
 *   walk of any single hue had.
 * - **accent** is the one coloured thing on the field, and it means exactly one thing at
 *   a time: with no bird chosen it marks the note *being sung right now*; with a bird
 *   chosen it marks that bird's points. Both are "this is what you asked for", which is
 *   what the accent means everywhere else in the interface too.
 *
 * Because the accent is never a category, spending it this way contradicts nothing. A
 * violet knot is not a kind of bird; it is the place the sound is.
 */

/**
 * The monochrome pair. Neutral rather than a desaturated hue, so nothing in the picture
 * suggests a category, and the two ends are far enough apart in lightness that response
 * is legible on value alone.
 */
export const MONO_REST = '#cdd3da';
export const MONO_HOT = '#1e2836';

/**
 * The interface accent, and the only colour in the galaxy.
 *
 * Kept in step with `--signal` in `app.css` by hand, because the shader needs a number
 * and a CSS custom property is a string resolved at paint time.
 */
export const ACCENT = '#5b3fd6';

/**
 * The provenance quartet, used by the "colour: provenance" mode and by the orphan
 * pulse. The first three are the interface's existing confidence hues
 * (`--documented`, `--unlabelled`, `--invented` in app.css) repeated as numbers for
 * the shader, kept in step by hand exactly like `ACCENT`: blue for the authored
 * inventory, grey for types fitted to field recordings, amber for field audio with
 * no identity. The fourth reuses `--experimental`'s green for the unlabelled
 * pseudo-species — far enough from the blue, the amber and the violet accent to stay
 * separable, and an interface hue rather than a new invention.
 */
export const PROV_DOCUMENTED = '#1f5fbf';
export const PROV_LEARNED = '#7b8794';
export const PROV_CANDIDATE = '#b45309';
export const PROV_ARRIVALS = '#0b7a55';

/**
 * A stable hue per species, for the *labels* of the galaxy.
 *
 * This needs a defence, because the note at the top of this file argues against species
 * hues, and it still stands: on a static scatter, hue cannot identify a hundred species,
 * and pretending it can is how the old islands view lied. So the POINTS do not wear
 * species hues — they wear their provenance class, always. The hue lives on the label:
 * the tag dot, the tag name, the trajectory thread, the accent, and nowhere else. Hue
 * answers "which bird", the class tint answers "what kind of thing" — and a label is
 * where "which bird" is a question with a text answer right next to it, so the hue is
 * presentation, never the sole carrier.
 *
 * The hue is a hash of the species id, not an index into the inventory: learned ids
 * renumber across refits, and a colour that silently moved between two birds after a
 * rebuild would be a claim nobody made. Hashing keeps a bird's hue stable across
 * rebuilds and across machines. Lightness is held at 38 % so every hue keeps enough
 * contrast against the paper to read as a mark, and stays clear of the ink (16 %) the
 * rest of the interface is drawn in.
 */
export function speciesHue(id: string): number {
	// FNV-1a, then a golden-angle turn from the hash so near hashes still land apart.
	let h = 2166136261;
	for (let i = 0; i < id.length; i++) {
		h ^= id.charCodeAt(i);
		h = Math.imul(h, 16777619);
	}
	return ((h >>> 0) * 137.508) % 360;
}

export function speciesColour(id: string): string {
	// Comma form, not the modern space form: THREE's Color.setStyle only parses the
	// comma grammar (the space form is silently ignored and reads as white).
	return `hsl(${speciesHue(id).toFixed(1)}, 58%, 38%)`;
}

/**
 * The bird's hue with its lightness shifted a little — the only variation allowed
 * inside a species. Used for the bird's knots and songs, so two knots of one bird are
 * the same colour at slightly different depths rather than two colours: scale 0.9 is
 * the species' core knot (a touch darker, more ink), 1.1 its far edge. Anything past
 * ±20 % would start reading as a different bird, which is exactly what the mapping
 * forbids; the clamp keeps a bad input from inventing one.
 */
export function speciesColourScaled(id: string, lightScale: number): string {
	const scale = Math.min(1.2, Math.max(0.8, lightScale));
	return `hsl(${speciesHue(id).toFixed(1)}, 58%, ${(38 * scale).toFixed(1)}%)`;
}



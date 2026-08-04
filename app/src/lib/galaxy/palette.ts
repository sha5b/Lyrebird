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
 * The interface's neutral dark. Neutral rather than a desaturated hue, so nothing in
 * the picture suggests a category where none is meant. (The pale half of the old
 * monochrome pair went with the response ramp it served: the cloud's rest colour is
 * now the provenance wash, and the ramp's dark end is the class colour.)
 */
export const MONO_HOT = '#1e2836';

/**
 * The interface accent, and the only colour in the galaxy.
 *
 * Kept in step with `--signal` in `app.css` by hand, because the shader needs a number
 * and a CSS custom property is a string resolved at paint time.
 */
export const ACCENT = '#5b3fd6';

/**
 * The provenance set, used by the "colour: provenance" mode and by the orphan pulse.
 * These are the interface's existing confidence hues (app.css) repeated as numbers for
 * the shader, kept in step by hand exactly like `ACCENT`.
 *
 * The mapping is read as two questions rather than five arbitrary tags:
 *
 * - **blue** (`--documented`) — a person named this sound.
 * - **amber** (`--invented`) — we synthesized it from a type the pipeline fitted.
 * - **green** (`--experimental`) — it is a real recording, carrying a fitted type.
 * - **rose** (`--arrival`) — real audio, typed, but with no species tag at all.
 * - **grey** (`--unlabelled`) — nothing is known about it. The neutral, on the one
 *   class that genuinely makes no claim.
 *
 * **Amber and green are deliberately the widest-separated pair in the set**, because
 * they carry the two classes that between them are 97 % of the shipped corpus (53 %
 * synthesized, 44 % recorded). Hues are unchanged from the measured set; saturation
 * and lightness went UP at the owner's request ("too pastel", 2026-08-01), which moves
 * every pairwise ΔE in the safe direction (the quoted 29.4/7.3/8.6 figures were
 * measured on the older, quieter values). The rose class was the pastel one — it is
 * now a full magenta. Grey stays grey on purpose: it is the class that claims
 * nothing, and a loud neutral would be a lie.
 *
 * The set does not pretend all five separate equally. Five categorical hues cannot
 * survive colour-vision deficiency — the note at the top of this file is the same
 * argument — and two pairs here are weak (documented/field tritan, and
 * learned/unlabelled deutan). Both weak pairs involve classes that are a small
 * minority or absent from the shipped build, and the classes are named in the
 * reading panel and the legend, so hue is never the sole carrier.
 */
export const PROV_DOCUMENTED = '#1d4fd8';
export const PROV_LEARNED = '#d97706';
export const PROV_FIELD = '#059669';
export const PROV_ARRIVALS = '#db2777';
export const PROV_CANDIDATE = '#7b8794';

/** The five class colours in PROVENANCE order, for the label and thread lookups. */
const PROV_ORDER = [
	PROV_DOCUMENTED,
	PROV_LEARNED,
	PROV_FIELD,
	PROV_ARRIVALS,
	PROV_CANDIDATE
] as const;

/** Short names for the classes, so the legend and the tags agree on the wording. */
export const PROV_NAMES = [
	'documented',
	'synthesized',
	'recorded',
	'unlabelled arrival',
	'unidentified'
] as const;

/**
 * A provenance class as a colour string. Out-of-range falls back to the neutral, which
 * is the class that claims nothing — the safe thing to say when the class is unknown.
 */
export function provenanceColour(cls: number): string {
	return PROV_ORDER[cls] ?? PROV_CANDIDATE;
}

/**
 * The class colour with the same slight per-knot lightness walk the species hue gets,
 * so switching the mode changes the *hue language* of the tags and threads without
 * changing anything else about how they are drawn.
 *
 * The lightness scale arrives as the same 0.9..1.1 the species version takes. It is
 * applied in sRGB rather than HSL because these are fixed hex brand hues rather than
 * generated HSL, and re-deriving them through HSL would shift the hues the CVD
 * measurements in the note above were taken on.
 */
export function provenanceColourScaled(cls: number, lightScale: number): string {
	const scale = Math.min(1.2, Math.max(0.8, lightScale));
	const hex = provenanceColour(cls).slice(1);
	const channels = [0, 2, 4].map((i) => parseInt(hex.slice(i, i + 2), 16));
	const shifted = channels.map((c) =>
		Math.round(Math.min(255, Math.max(0, scale <= 1 ? c * scale : c + (255 - c) * (scale - 1))))
	);
	return `rgb(${shifted[0]}, ${shifted[1]}, ${shifted[2]})`;
}

/**
 * A stable hue per species, for the *labels* of the galaxy.
 *
 * This needs a defence, because the note at the top of this file argues against species
 * hues, and it still stands: on a static scatter, hue cannot identify a hundred species,
 * and pretending it can is how the old islands view lied. So the POINTS do not wear
 * species hues — they wear their provenance class, or neutral ink. The hue lives where
 * it can be read: on the label (the tag dot and the tag name), and on the response
 * accent in ink mode, which lights in the singing bird's hue. Hue answers "which
 * bird", the class tint answers "what kind of thing" — and a label is where "which
 * bird" is a question with a text answer right next to it, so the hue is
 * presentation, never the sole carrier.
 *
 * The hue is a hash, not an index into the inventory: learned ids renumber across
 * refits, and a colour that silently moved between two birds after a rebuild would be a
 * claim nobody made. Hashing keeps a bird's hue stable across rebuilds and across
 * machines. Saturation ~82 % at lightness 45 % — vivid, on the owner's call ("heatmap,
 * not pastel", 2026-08-01) — while staying light enough to read as a mark on the paper
 * and clear of the ink (16 %) the interface is drawn in.
 *
 * **What is hashed is the GENUS, not the species** (owner, 2026-08-02: "colour them by
 * the genome stuff so we can see where the birds derive from"). Hashing the whole id
 * spent the hue circle on thousands of unrelated numbers: two thrushes were as far apart as a
 * thrush and an owl, so the one thing a colour could have told you — *what kind of bird
 * just answered* — was the one thing it did not. The species id is `genus_species`, so
 * the genus is free, and on this corpus it is worth having: **about a thousand genera over thousands of
 * species, and 75.5 % of species sit in a genus with at least one sibling.**
 *
 * So: **hue is the clade, and the shade is the bird.** A genus takes one hue; each of
 * its species is jittered up to ±14° inside that band and given its own saturation
 * between 74 % and 90 %. Two *Turdus* are then two shades of one colour, and a
 * *Turdus* against a *Scytalopus* is two colours.
 *
 * **The honest limit, and it matters: genus is the deepest taxonomy this corpus holds.**
 * Family and order are not collected — nothing in the store or the inventory carries
 * them — so "broader than a genus" cannot be coloured today, and a genus hue is
 * *arbitrary*: neighbouring hues do not mean neighbouring clades, only the same hue
 * means the same genus. Adding family would be a harvest-side field, in the same class
 * of one-field change as lat/lng (WORK QUEUE §11).
 */
function hash32(text: string): number {
	// FNV-1a.
	let h = 2166136261;
	for (let i = 0; i < text.length; i++) {
		h ^= text.charCodeAt(i);
		h = Math.imul(h, 16777619);
	}
	return h >>> 0;
}

/** The clade a species id names: everything before the first underscore. */
export function speciesGenus(id: string): string {
	const cut = id.indexOf('_');
	return cut > 0 ? id.slice(0, cut) : id;
}

/** The genus's own hue — the same for every bird in it. */
export function genusHue(genus: string): number {
	// The golden angle from the hash, so near hashes still land apart on the circle.
	return (hash32(genus) * 137.508) % 360;
}

/** How far inside its genus's band one species may sit, in degrees either way. */
const SPECIES_SPREAD = 14;

export function speciesHue(id: string): number {
	const base = genusHue(speciesGenus(id));
	// A second, independent hash so the offset is not correlated with the base — with
	// one hash the members of a genus would fan out in hash order, which is nothing.
	const jitter = ((hash32(`${id}/within`) % 2001) / 2000 - 0.5) * 2 * SPECIES_SPREAD;
	return (base + jitter + 360) % 360;
}

/** Saturation 74–90 %: the second axis a species varies on inside its genus's hue. */
export function speciesSaturation(id: string): number {
	return 74 + (hash32(`${id}/sat`) % 17);
}

export function speciesColour(id: string): string {
	// Comma form, not the modern space form: THREE's Color.setStyle only parses the
	// comma grammar (the space form is silently ignored and reads as white).
	return `hsl(${speciesHue(id).toFixed(1)}, ${speciesSaturation(id)}%, 45%)`;
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
	return `hsl(${speciesHue(id).toFixed(1)}, ${speciesSaturation(id)}%, ${(45 * scale).toFixed(1)}%)`;
}

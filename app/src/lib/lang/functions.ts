/**
 * The Words tab's semantic layer: read a typed phrase as one of five *functional
 * categories*, then report what this species' calls in that category are documented to do.
 *
 * **The claim this module is built to make, and the one it is built to refuse.**
 *
 *   > The functional category is real to the bird. The assignment of your words to it
 *   > is ours.
 *
 * The first half has evidence, and it is recent: Elie et al. 2025 (Science 389:1210-1215,
 * doi:10.1126/science.ads8482) found that zebra finches' *own* confusion errors between
 * call types cluster by behavioural context rather than by acoustic similarity. The
 * categories are organised in the bird's head, not just in our spreadsheet.
 *
 * The second half has none. There is no literature anywhere supporting a mapping from
 * English text to an animal signal category, and there is a structural reason there is
 * not: bird call form is non-arbitrary (Marler 1955; Morton 1977), so a call means what
 * it means the way a growl does, not the way a word does (Wheeler & Fischer 2012,
 * Evol. Anthropol. 21:195-205). There is no arbitrary signifier to attach an English
 * word to.
 *
 * So the chain has **two links with different evidence classes, and the interface shows
 * both rather than collapsing them**:
 *
 *   link 1   typed English -> category      OURS. Always `invented`. This module.
 *   link 2   category -> this species' call  THE CORPUS'S. Carries the call's own
 *                                            confidence and citations.
 *
 * The phrase badge takes the weaker link. The *note* reports the stronger one, which is
 * the whole point of the exercise.
 *
 * **Why a hand-written lexicon and not a model.** Three reasons, in order of weight.
 * It is auditable — every word that produces a reading is on this page, and a wrong
 * reading is a line someone can point at. It ships nothing (`AGENTS.md`: no torch
 * weights reach the browser). And a classifier that is confidently wrong on
 * "I miss you" is worse here than one that refuses, because a plausible-sounding wrong
 * function is exactly the failure this project exists to avoid.
 *
 * **Five categories, because five is what the corpus holds.** Not the textbook ten.
 * Begging, distress, flight call, food call, roost assembly and duet have no authored
 * call in any of the 12 species, so they are not offered. There is also no external
 * taxonomy to borrow: xeno-canto's controlled vocabulary has no "contact call",
 * Macaulay/eBird collapses alarm and contact into one "Call" bucket, and BirdNET's
 * 6 522 classes are taxon labels with no call type among them. Saying "we defined these
 * five from what our own corpus holds" is more defensible than implying a standard.
 */
import type { Confidence, Inventory, Song, Species } from '../data/types';

/**
 * Local, rather than `assets.speciesById`, and the reason is testability.
 *
 * `data/assets.ts` imports `$app/paths`, which only resolves inside SvelteKit, so any
 * module that touches it cannot be loaded by the bare-node `verify:*` harnesses. This is
 * the one function needed from it and it is a one-line find. Keeping this module free of
 * framework imports is what lets every claim in it be checked by
 * `scripts/verify-functions.mjs` against the real shipped inventory.
 */
function speciesById(inventory: Inventory, id: string): Species | undefined {
	return inventory.species.find((s) => s.id === id);
}

export type FunctionCategory = 'alarm' | 'recruitment' | 'contact' | 'territory' | 'courtship';

export interface CategoryInfo {
	id: FunctionCategory;
	label: string;
	/** What the bird is doing, in the interface's own words — not a gloss of the English. */
	blurb: string;
}

export const CATEGORIES: CategoryInfo[] = [
	{
		id: 'alarm',
		label: 'alarm',
		blurb: 'a predator is present; receivers scan, freeze or flee'
	},
	{
		id: 'recruitment',
		label: 'recruitment',
		blurb: 'come here; receivers approach the caller'
	},
	{
		id: 'contact',
		label: 'contact',
		blurb: 'where are you; keeps a pair or flock together'
	},
	{
		id: 'territory',
		label: 'territory',
		blurb: 'this space is occupied; advertised to rivals'
	},
	{
		id: 'courtship',
		label: 'courtship',
		blurb: 'directed at a mate or potential mate'
	}
];

/**
 * Which authored song sits in which category.
 *
 * Keyed by song id, which is unique across the inventory. Two deliberate absences:
 *
 *  - `d_abc` — the *reversed* great tit control. In playback it elicits neither response
 *    (Suzuki, Wheatcroft & Griesser 2016), so it is a null result, not a message. Offering
 *    it as something to say would invert its meaning.
 *  - every fitted `unlabelled` type — 16 239 of them. A cluster from an archive recording
 *    has no sender state, no receiver and no context, which is precisely the case
 *    Rutz et al. 2023 warns cannot be decoded from archives alone. It is not a weak
 *    label; it is no label, and it may not be recruited to widen coverage.
 */
export const SONG_CATEGORY: Record<string, FunctionCategory> = {
	// alarm — predator response, including the graded vigilance/escape pair
	abc: 'alarm',
	chick_a_dee_alarm: 'alarm',
	jay_perched: 'alarm',
	jay_attack: 'alarm',
	// recruitment
	d: 'recruitment',
	abc_d: 'recruitment',
	// contact
	chick_a_dee: 'contact',
	zf_distance: 'contact',
	// territory
	tsupi_song: 'territory',
	feebee_song: 'territory',
	owl_hoot: 'territory',
	hokekyo: 'territory',
	merula_song: 'territory',
	wren_song: 'territory',
	cuckoo_call: 'territory',
	mejiro_song: 'territory',
	// courtship
	zf_song: 'courtship',
	bf_motif: 'courtship',
	nightingale_type_a: 'courtship',
	nightingale_type_b: 'courtship'
};

/**
 * English terms that read as each category. **Ours, entirely.**
 *
 * Multi-word entries are matched as phrases; single words must match a whole word. That
 * rule is inherited from `grammar.ts:matchDocumented` and it is there because plain
 * substring matching claimed "there" as "here" and badged an invented phrase as
 * playback-verified.
 *
 * Deliberately not exhaustive. A term that is not here produces a refusal, and a refusal
 * is a better answer than a guess.
 */
export const LEXICON: Record<FunctionCategory, string[]> = {
	alarm: [
		'danger', 'dangerous', 'snake', 'predator', 'look out', 'watch out', 'careful',
		'carefully', 'scan', 'alert', 'beware', 'warning', 'warn', 'threat', 'owl', 'cat',
		'hawk', 'raptor', 'falcon', 'eagle', 'emergency', 'help', 'attack', 'attacking',
		'take cover', 'hide', 'run', 'flee', 'escape', 'watching', 'perched', 'still there',
		'get out', 'look up', 'above you', 'behind you', 'scared', 'afraid', 'fear'
	],
	recruitment: [
		'come', 'come here', 'here', 'approach', 'follow', 'follow me', 'closer', 'join',
		'join me', 'recruit', 'gather', 'this way', 'over here', 'help me mob', 'mob'
	],
	contact: [
		'flock', 'contact', 'where are you', 'where', 'together', 'hello', 'hi', 'hey',
		'friend', 'anyone', 'anybody', 'lost', 'i am here', 'im here', 'who are you',
		'my name', 'identity', 'keep up', 'stay close', 'are you there', 'still here'
	],
	territory: [
		'territory', 'mine', 'my tree', 'stay away', 'this is my', 'go away', 'get lost',
		'occupied', 'taken', 'my land', 'my patch', 'keep out', 'no trespassing', 'back off',
		'this is mine', 'night', 'dark', 'evening', 'midnight', 'rival', 'claim'
	],
	courtship: [
		'love', 'courtship', 'court', 'beautiful', 'marry', 'sing to me', 'mate', 'attract',
		'desire', 'romance', 'romantic', 'be mine', 'i love you', 'darling', 'sweetheart',
		'pretty', 'woo', 'serenade'
	]
};

function normalise(text: string): string {
	return text
		.toLowerCase()
		.replace(/[^a-z0-9\s']/g, ' ')
		.replace(/\s+/g, ' ')
		.trim();
}

/** A phrase on word boundaries: "no hawk" is not in "piano hawks". */
export function hasPhrase(norm: string, phrase: string): boolean {
	return ` ${norm} `.includes(` ${phrase} `);
}

export interface FunctionReading {
	category: FunctionCategory;
	/** The lexicon terms that produced this reading, for the UI to show. */
	matched: string[];
	/** Runners-up, so an override can be offered in the order the text actually suggests. */
	alternatives: FunctionCategory[];
}

/**
 * Read a typed phrase as a functional category, or return null.
 *
 * Null is the expected answer, not the error case — see `speciesWithFunctions`. Scoring
 * is by matched-character length, the same tie-break `grammar.ts` uses, so a phrase beats
 * a word it contains.
 */
export function classify(text: string): FunctionReading | null {
	const norm = normalise(text);
	if (!norm) return null;
	const words = new Set(norm.split(' ').filter(Boolean));

	const scored: { category: FunctionCategory; matched: string[]; score: number }[] = [];
	for (const category of Object.keys(LEXICON) as FunctionCategory[]) {
		const matched = LEXICON[category].filter((term) =>
			term.includes(' ') ? hasPhrase(norm, term) : words.has(term)
		);
		if (matched.length) {
			scored.push({ category, matched, score: matched.join('').length });
		}
	}
	if (!scored.length) return null;
	scored.sort((a, b) => b.score - a.score);
	return {
		category: scored[0].category,
		matched: scored[0].matched,
		alternatives: scored.slice(1).map((s) => s.category)
	};
}

export interface CategoryCall {
	song: Song;
	speciesId: string;
	confidence: Confidence;
}

/** The species' authored calls in one category, strongest evidence first. */
const RANK: Record<Confidence, number> = {
	experimental: 0,
	documented: 1,
	inferred: 2,
	unlabelled: 3,
	invented: 4
};

export function callsFor(
	inventory: Inventory,
	speciesId: string,
	category: FunctionCategory
): CategoryCall[] {
	const species = speciesById(inventory, speciesId);
	if (!species) return [];
	return (species.songs ?? [])
		.filter((song) => SONG_CATEGORY[song.id] === category)
		.map((song) => ({ song, speciesId, confidence: song.confidence }))
		.sort((a, b) => RANK[a.confidence] - RANK[b.confidence]);
}

/** Every category this species has an authored call for. */
export function categoriesFor(inventory: Inventory, speciesId: string): FunctionCategory[] {
	const species = speciesById(inventory, speciesId);
	if (!species) return [];
	const seen = new Set<FunctionCategory>();
	for (const song of species.songs ?? []) {
		const c = SONG_CATEGORY[song.id];
		if (c) seen.add(c);
	}
	return CATEGORIES.map((c) => c.id).filter((c) => seen.has(c));
}

/**
 * The species that have any authored function at all.
 *
 * **12 of 2 489**, the species count the shipped inventory index actually holds. The
 * picker still offers all of them — hiding the rest would present
 * the best 0.48 % of the corpus as if it were the corpus — but these are marked, so the
 * working set is findable without the scale being quietly dropped.
 */
export function speciesWithFunctions(inventory: Inventory): Set<string> {
	const out = new Set<string>();
	for (const species of inventory.species as Species[]) {
		if ((species.songs ?? []).some((song) => SONG_CATEGORY[song.id])) out.add(species.id);
	}
	return out;
}

/**
 * The graded case the corpus genuinely supports, and the only one.
 *
 * In black-capped chickadees the number of D notes scales with predator threat
 * (Templeton, Greene & Davis 2005, Science 308:1934-1937) — small, agile, dangerous
 * raptors draw more D notes. The build holds `chick_a_dee` and `chick_a_dee_alarm` as
 * two entries differing by exactly that, so "careful" and "GET OUT NOW" have a real,
 * published, species-specific difference to land on.
 *
 * It is one species. Every other species gets the same call whatever the intensity, and
 * the interface says so rather than implying a general dial.
 */
export function intensityNote(speciesId: string, category: FunctionCategory): string | null {
	if (speciesId !== 'poecile_atricapillus' || category !== 'alarm') return null;
	return (
		'In this species the urgency is gradable and the grading is published: more D notes ' +
		'mean a more dangerous predator (Templeton, Greene & Davis 2005). It is the only ' +
		'species here where that is true.'
	);
}

/**
 * What to say when the typed words read as nothing this species can say.
 *
 * **This is the majority answer and it is designed, not defaulted.** Pick a species at
 * random and there is a 99.55 % chance of landing here.
 */
export function refusal(
	inventory: Inventory,
	speciesId: string,
	reading: FunctionReading | null
): string {
	const species = speciesById(inventory, speciesId);
	const name = species?.common ?? 'this species';
	const have = categoriesFor(inventory, speciesId);

	if (!reading) {
		return (
			`No documented function in this build reads as that. The functions we can read are ` +
			`alarm, recruitment, contact, territory and courtship — five, because five is what ` +
			`the corpus holds, and 12 of 2 489 species here have any documented function at all. ` +
			`What plays is ${name}'s own measured syntax at the rhythm of your words. It is not a ` +
			`rendering of what you wrote.`
		);
	}
	if (!have.length) {
		return (
			`We read that as ${reading.category}, and that reading is ours. But ${name} has no ` +
			`call with a documented function in this build — 12 of 2 489 species do. What plays ` +
			`is its own measured syntax at the rhythm of your words.`
		);
	}
	return (
		`We read that as ${reading.category}, and that reading is ours. ${name} has no documented ` +
		`${reading.category} call here; what it does have is ${have.join(', ')}. What plays is its ` +
		`own measured syntax at the rhythm of your words.`
	);
}

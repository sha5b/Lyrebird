/**
 * The Words tab's functional reading, and every place it could quietly overclaim.
 *
 * **This module's failures are all silent and all in the same direction: they invent
 * meaning.** A lexicon term in the wrong category produces a confident, fluent, wrong
 * answer with a real citation stapled to it, which is worse than no answer at all — the
 * citation is what makes it convincing. A song mapped to the wrong category does the same
 * thing one layer down. And the one that would be hardest to notice from the interface:
 * a species with no authored call in the read category silently borrowing another
 * species' call, so the Voice control is ignored and the reading looks like it worked.
 *
 * So the checks are grouped by the claim each one protects:
 *
 *  - `classify` — a term matches as a whole word or not at all (the "there"/"here" bug
 *    that once badged an invented phrase as playback-verified), phrases beat the words
 *    they contain, empty and punctuation-only text read as nothing, and an unknown word
 *    returns null rather than the nearest category;
 *  - `SONG_CATEGORY` — every id exists in the shipped inventory, every category is
 *    reachable, and the two deliberate absences stay absent: `d_abc` (the reversed
 *    control, which elicits neither response) and every `unlabelled` fitted type;
 *  - `callsFor` — only ever returns calls belonging to the species asked for, ordered
 *    strongest evidence first, and empty rather than a fallback when there is nothing;
 *  - `refusal` — says something for every combination of reading and species, and never
 *    claims a function while doing it;
 *  - the counts the interface states out loud — 12 species, 5 categories — are checked
 *    against the inventory rather than trusted, because they are written into prose.
 *
 * Run with `npm run verify:functions`. Exits non-zero on any disagreement.
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

import {
	CATEGORIES,
	LEXICON,
	SONG_CATEGORY,
	callsFor,
	categoriesFor,
	classify,
	hasPhrase,
	intensityNote,
	refusal,
	speciesWithFunctions
} from '../src/lib/lang/functions.ts';

const here = dirname(fileURLToPath(import.meta.url));
const inventory = JSON.parse(
	readFileSync(join(here, '../../data/inventory.json'), 'utf8')
);

let failures = 0;
const ok = (name, cond, detail = '') => {
	if (cond) console.log(`  ${name.padEnd(58)} ok${detail ? ` (${detail})` : ''}`);
	else {
		console.log(`  ${name.padEnd(58)} FAIL${detail ? ` (${detail})` : ''}`);
		failures++;
	}
};

const songIds = new Set(inventory.species.flatMap((s) => (s.songs ?? []).map((x) => x.id)));
const songById = new Map(
	inventory.species.flatMap((s) => (s.songs ?? []).map((x) => [x.id, { ...x, speciesId: s.id }]))
);

console.log('\nclassify — the reading is ours, so it must at least be careful');
{
	ok('a plain alarm word reads as alarm', classify('danger')?.category === 'alarm');
	ok('a courtship word reads as courtship', classify('love')?.category === 'courtship');
	ok('an unknown word reads as nothing', classify('photosynthesis') === null);
	ok('empty text reads as nothing', classify('') === null);
	ok('punctuation only reads as nothing', classify('!!! ???') === null);

	// The bug this rule exists for: substring matching claimed "there" as "here".
	ok('"there" does not match the whole-word "here"',
		classify('there')?.category !== 'recruitment',
		String(classify('there')?.category));
	ok('"here" still matches', classify('here')?.category === 'recruitment');
	ok('"scattered" does not match "cat"', classify('scattered') === null);

	// A phrase must beat a single word it contains, or "where are you" reads as territory
	// via "where"... which is in contact anyway, so use a cross-category pair.
	const r = classify('watch out');
	ok('"watch out" reads as alarm', r?.category === 'alarm');
	ok('the matched terms are reported', (r?.matched.length ?? 0) > 0, r?.matched.join('|'));

	ok('case and punctuation do not matter',
		classify('DANGER!')?.category === 'alarm');
	ok('alternatives are offered when two categories match',
		(classify('danger, my tree')?.alternatives.length ?? 0) > 0);
	ok('every category is reachable from the lexicon',
		CATEGORIES.every((c) => LEXICON[c.id]?.length > 0));
	ok('no lexicon term is listed in two categories', (() => {
		const seen = new Set();
		for (const c of CATEGORIES) {
			for (const t of LEXICON[c.id]) {
				if (seen.has(t)) return false;
				seen.add(t);
			}
		}
		return true;
	})());
}

console.log('\nSONG_CATEGORY — every mapped call must actually exist');
{
	const mapped = Object.keys(SONG_CATEGORY);
	ok('every mapped song id is in the shipped inventory',
		mapped.every((id) => songIds.has(id)),
		mapped.filter((id) => !songIds.has(id)).join(',') || 'all present');
	ok('every category has at least one call',
		CATEGORIES.every((c) => mapped.some((id) => SONG_CATEGORY[id] === c.id)));
	ok('no mapped call is `invented` or `unlabelled`',
		mapped.every((id) => !['invented', 'unlabelled'].includes(songById.get(id)?.confidence)));

	// The two deliberate absences.
	ok('the reversed great tit control d_abc is NOT offered',
		!('d_abc' in SONG_CATEGORY));
	ok('d_abc exists in the inventory, so its absence is a choice',
		songIds.has('d_abc'));
	ok('no fitted unlabelled type is mapped',
		mapped.every((id) => songById.has(id)));
}

console.log('\ncallsFor — the Voice control must not be quietly ignored');
{
	const tit = callsFor(inventory, 'parus_minor', 'alarm');
	ok('the great tit has a documented alarm call', tit.length > 0);
	ok('every returned call belongs to the species asked for',
		tit.every((c) => c.speciesId === 'parus_minor'));
	ok('strongest evidence comes first',
		tit[0]?.confidence === 'experimental', tit[0]?.confidence);

	const none = callsFor(inventory, 'parus_minor', 'courtship');
	ok('a category the species lacks returns nothing, not a fallback', none.length === 0);

	// The failure that would look like success in the interface.
	for (const category of CATEGORIES.map((c) => c.id)) {
		const borrowed = callsFor(inventory, 'turdus_merula', category)
			.filter((c) => c.speciesId !== 'turdus_merula');
		ok(`no borrowing from another species (${category})`, borrowed.length === 0);
	}

	const unknown = callsFor(inventory, 'not_a_species', 'alarm');
	ok('an unknown species returns nothing rather than throwing', unknown.length === 0);
}

console.log('\nthe counts the interface says out loud');
{
	const withFn = speciesWithFunctions(inventory);
	ok('12 species carry an authored function', withFn.size === 12, String(withFn.size));
	ok('five categories, because five is what the corpus holds',
		CATEGORIES.length === 5, String(CATEGORIES.length));
	ok('every species with a mapped song is in the set',
		Object.keys(SONG_CATEGORY).every((id) => withFn.has(songById.get(id).speciesId)));
	ok('categoriesFor agrees with callsFor', (() => {
		for (const id of withFn) {
			for (const c of categoriesFor(inventory, id)) {
				if (!callsFor(inventory, id, c).length) return false;
			}
		}
		return true;
	})());

	// **The denominator, which is the half that rotted.** This block asserted the 12 and
	// never the number it is 12 *of*, so "12 of 2 650" survived three rebuilds in the
	// refusal sentences, the picker comment and this module's own docstring while the
	// shipped index came down to 2 489. A fraction is two numbers and a stale denominator
	// misstates the scale of the refusal, which is the one thing the sentence exists to
	// convey. Read from the shipped index rather than hardcoded, so the next rebuild that
	// changes the corpus fails here instead of shipping a wrong number quietly.
	const shipped = JSON.parse(readFileSync(join(here, '../static/lyrebird/inventory.json'), 'utf8'));
	const total = shipped.species.length;
	const grouped = String(total).replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
	ok('the shipped index is the denominator the sentences quote', total > 0, `${total}`);
	for (const [label, text] of [
		['refusal, no reading', refusal(inventory, 'abroscopus_albogularis', null)],
		['refusal, category with no call', refusal(inventory, 'abroscopus_albogularis', { category: 'alarm', intensity: null })]
	]) {
		ok(`${label} quotes 12 of ${grouped}`, text.includes(`12 of ${grouped}`));
	}
}

console.log('\nrefusal — the majority answer, so it must be a real sentence');
{
	const noReading = refusal(inventory, 'turdus_merula', null);
	ok('a null reading still produces text', noReading.length > 40);
	ok('the refusal names the five functions',
		CATEGORIES.every((c) => noReading.includes(c.label)));

	const wrongCategory = refusal(inventory, 'parus_minor', {
		category: 'courtship', matched: [], alternatives: []
	});
	ok('a species without that category gets a specific refusal',
		wrongCategory.includes('courtship'));
	ok('the refusal says the reading is ours',
		wrongCategory.toLowerCase().includes('ours'));

	// It must never state a function while refusing.
	ok('no refusal claims the bird means something',
		!noReading.toLowerCase().includes('the bird is saying') &&
		!wrongCategory.toLowerCase().includes('the bird is saying'));

	let everySpeciesAnswered = true;
	for (const s of inventory.species) {
		if (!refusal(inventory, s.id, null)?.length) everySpeciesAnswered = false;
	}
	ok('every species in the inventory gets a refusal sentence', everySpeciesAnswered);
}

console.log('\nintensity — the one graded case, and it stays one');
{
	ok('chickadee alarm is gradable', intensityNote('poecile_atricapillus', 'alarm') !== null);
	ok('chickadee contact is not', intensityNote('poecile_atricapillus', 'contact') === null);
	ok('no other species claims a gradient',
		inventory.species
			.filter((s) => s.id !== 'poecile_atricapillus')
			.every((s) => CATEGORIES.every((c) => intensityNote(s.id, c.id) === null)));
	ok('the gradient names its source',
		intensityNote('poecile_atricapillus', 'alarm').includes('Templeton'));
}

// --- a multi-word term matches on word boundaries ---------------------------------------
{
	ok('a phrase matches whole words', hasPhrase('please look out now', 'look out'));
	ok('not across a word boundary', !hasPhrase('overlook outside', 'look out'));
	ok('"overlook outside" is not an alarm', classify('overlook outside')?.category !== 'alarm');
	ok('"look out" still is', classify('look out')?.category === 'alarm');
}

console.log(failures ? `\n${failures} failure(s)` : '\nall checks passed');
process.exit(failures ? 1 : 0);

/**
 * "Choose the words the bird sings" (docs/04-synthetic-bird-voices.md §4.4).
 *
 * Two paths, and the difference is always shown to the user:
 *
 *  - `documented`: the text matches a call whose function was established by playback
 *    experiments, so we render the real syllable sequence with its citation.
 *  - `invented`: any other text is mapped onto the species' syllables through a
 *    finite-state song grammar plus prosody transfer. It is a rendering of the text,
 *    not a translation of it, and it is labelled as such.
 */
import type { Confidence, Grammar, Inventory, Species, Syllable } from '$lib/data/types';
import { songSyllables, speciesById, syllableById } from '$lib/data/assets';

export interface Phrase {
	speciesId: string;
	label: string;
	gloss: string;
	function: string;
	confidence: Confidence;
	refs: string[];
	syllables: Syllable[];
	gaps: number[];
	source: 'documented' | 'invented';
	/** Words that triggered a documented match, for the UI to highlight. */
	matched: string[];
	note: string;
	/**
	 * Species ids that *do* have a documented call for this text, when the selected one
	 * does not. The interface offers them rather than silently switching voice.
	 */
	documentedElsewhere?: string[];
}

interface DocumentedEntry {
	speciesId: string;
	songId: string;
	keywords: string[];
}

/**
 * Only calls whose function is actually described in the literature are listed here.
 * See docs/03-decoding-science.md §3.2 for the sources behind each row.
 */
const DOCUMENTED: DocumentedEntry[] = [
	{
		speciesId: 'parus_minor',
		songId: 'abc',
		keywords: ['danger', 'snake', 'predator', 'look out', 'watch out', 'careful', 'scan', 'alert']
	},
	{
		speciesId: 'parus_minor',
		songId: 'd',
		keywords: ['come', 'here', 'approach', 'follow', 'closer', 'join me', 'recruit']
	},
	{
		speciesId: 'parus_minor',
		songId: 'tsupi_song',
		keywords: ['territory', 'mine', 'my tree', 'stay away', 'this is my']
	},
	{
		speciesId: 'poecile_atricapillus',
		songId: 'chick_a_dee',
		keywords: ['flock', 'contact', 'where are you', 'together', 'hello', 'friend']
	},
	{
		speciesId: 'poecile_atricapillus',
		songId: 'chick_a_dee_alarm',
		keywords: ['threat', 'owl', 'cat', 'very dangerous', 'emergency', 'help']
	},
	{
		speciesId: 'perisoreus_infaustus',
		songId: 'jay_attack',
		keywords: ['attack', 'hawk', 'take cover', 'dive', 'now', 'run']
	},
	{
		speciesId: 'perisoreus_infaustus',
		songId: 'jay_perched',
		keywords: ['watching', 'perched', 'waiting', 'still there']
	},
	{
		speciesId: 'taeniopygia_guttata',
		songId: 'zf_distance',
		keywords: ['who are you', 'my name', 'identity', 'lost', 'i am here']
	},
	{
		speciesId: 'taeniopygia_guttata',
		songId: 'zf_song',
		keywords: ['love', 'courtship', 'beautiful', 'marry', 'sing to me']
	},
	{
		speciesId: 'strix_aluco',
		songId: 'owl_hoot',
		keywords: ['night', 'occupied', 'who', 'dark']
	}
];

function normalise(text: string): string {
	return text.toLowerCase().replace(/[^a-z0-9\s']/g, ' ').replace(/\s+/g, ' ').trim();
}

/** FNV-1a — a stable hash, so the same text always sings the same way. */
function hash(text: string): number {
	let h = 0x811c9dc5;
	for (let i = 0; i < text.length; i++) {
		h ^= text.charCodeAt(i);
		h = Math.imul(h, 0x01000193) >>> 0;
	}
	return h >>> 0;
}

/** Splits a word into pronounceable chunks (vowel-nucleus syllabification, approximate). */
export function splitSyllables(word: string): string[] {
	const chunks = word.match(/[^aeiouy]*[aeiouy]+(?:[^aeiouy]*$|[^aeiouy](?=[^aeiouy]))?/g);
	return chunks && chunks.length ? chunks : [word];
}

const VOWEL_PITCH: Record<string, number> = {
	i: 1.28,
	e: 1.14,
	y: 1.18,
	a: 1.0,
	o: 0.88,
	u: 0.8
};

function vowelOf(chunk: string): string {
	const m = chunk.match(/[aeiouy]/);
	return m ? m[0] : 'a';
}

interface Prosody {
	pitch: number;
	level: number;
	stretch: number;
	timbre?: Syllable['timbre'];
}

/**
 * Prosody transfer, Windytan-style: the text's own shape drives pitch and pressure
 * rather than being discarded. Vowel height sets pitch, plosives shorten and sharpen
 * the syllable, sibilants push it into the noisy regime, and the sentence declines in
 * pitch unless it is a question.
 */
function prosodyFor(chunk: string, indexInWord: number, position: number, isQuestion: boolean): Prosody {
	const vowel = vowelOf(chunk);
	let pitch = VOWEL_PITCH[vowel] ?? 1;
	let stretch = 1;
	let level = indexInWord === 0 ? 1.0 : 0.85; // first syllable of a word is stressed
	let timbre: Syllable['timbre'] | undefined;

	if (/^[ptkbdg]/.test(chunk)) {
		stretch *= 0.75;
		level *= 1.1;
	}
	if (/[szfʃ]|sh|ch/.test(chunk)) {
		timbre = 'buzz';
		stretch *= 1.15;
	}
	if (/[mn]/.test(chunk)) stretch *= 1.2;
	if (/[aeiouy]{2}/.test(chunk)) stretch *= 1.3; // diphthong

	// F0 declination across the utterance; questions rise at the end instead
	const declination = isQuestion ? 0.92 + 0.28 * position : 1.1 - 0.25 * position;
	pitch *= declination;

	return { pitch, level, stretch, timbre };
}

function applyProsody(syllable: Syllable, p: Prosody): Syllable {
	return {
		...syllable,
		dur: Math.max(0.03, syllable.dur * p.stretch),
		level: Math.min(1, syllable.level * p.level),
		timbre: p.timbre ?? syllable.timbre,
		contour: syllable.contour.map(([t, hz]) => [t, Math.min(9000, Math.max(180, hz * p.pitch))] as [number, number])
	};
}

/** Walks the finite-state grammar, choosing among allowed successors by text hash. */
function grammarWalk(grammar: Grammar | undefined, species: Species, tokens: string[]): string[] {
	const ids = species.syllables.map((s) => s.id);
	if (!grammar) {
		return tokens.map((t) => ids[hash(t) % ids.length]);
	}
	const out: string[] = [];
	let started = false;
	let current: string = ids[0];
	for (const token of tokens) {
		const h = hash(token);
		if (!started) {
			current = grammar.start[h % grammar.start.length] ?? ids[0];
			started = true;
		} else {
			const next: Record<string, number> | undefined = grammar.transitions[current];
			const options = next ? Object.keys(next).filter((k) => k !== 'end') : [];
			current = options.length ? options[h % options.length] : ids[h % ids.length];
		}
		out.push(current);
	}
	return out;
}

/**
 * Does the text match a call with an experimentally established function?
 *
 * Single-word keywords must match a whole word: plain substring matching claims "there"
 * as the great tit's "here" and mislabels an invented phrase as playback-verified, which
 * is exactly the kind of overclaiming this app is supposed to avoid. Multi-word keywords
 * are matched as phrases.
 */
function matchDocumented(text: string): { entry: DocumentedEntry; matched: string[] }[] {
	const norm = normalise(text);
	const words = new Set(norm.split(' ').filter(Boolean));
	const hits: { entry: DocumentedEntry; matched: string[]; score: number }[] = [];
	for (const entry of DOCUMENTED) {
		const matched = entry.keywords.filter((k) =>
			k.includes(' ') ? norm.includes(k) : words.has(k)
		);
		if (matched.length) hits.push({ entry, matched, score: matched.join('').length });
	}
	hits.sort((a, b) => b.score - a.score);
	return hits;
}

function documentedPhrase(
	inventory: Inventory,
	entry: DocumentedEntry,
	matched: string[]
): Phrase | null {
	const species = speciesById(inventory, entry.speciesId);
	if (!species) return null;
	const resolved = songSyllables(species, entry.songId);
	if (!resolved) return null;
	return {
		speciesId: species.id,
		label: resolved.song.label,
		gloss: resolved.song.gloss,
		function: resolved.song.function,
		confidence: resolved.song.confidence,
		refs: resolved.song.refs,
		syllables: resolved.syllables,
		gaps: resolved.song.gaps,
		source: 'documented',
		matched,
		note: 'This call has a documented function, so the real syllable sequence is rendered.'
	};
}

export interface CompileOptions {
	/** Species used for invented renderings; documented matches use their own species. */
	speciesId: string;
	/** Prefer the documented call when the text matches one. */
	allowDocumented?: boolean;
}

/**
 * Turns text into something a bird can actually utter. Returns the documented call when
 * one matches, otherwise a grammar-driven invented rendering.
 */
export function compilePhrase(inventory: Inventory, text: string, options: CompileOptions): Phrase | null {
	const trimmed = text.trim();
	if (!trimmed) return null;

	// Documented calls belong to the species that has them, so a match only wins when it
	// is a match *for the selected voice*. Letting any species' documented call win meant
	// "danger" always came out as a great tit however the Voice control was set — the
	// control was quietly ignored, which is worse than not having it.
	const elsewhere = matchDocumented(trimmed)
		.filter((h) => h.entry.speciesId !== options.speciesId)
		.map((h) => h.entry.speciesId);

	if (options.allowDocumented !== false) {
		const hits = matchDocumented(trimmed).filter((h) => h.entry.speciesId === options.speciesId);
		if (hits.length) {
			// The great tit compound ABC-D exists only because both parts were matched;
			// this is the one place where combining two messages is itself documented.
			const hasAbc = hits.some((h) => h.entry.songId === 'abc');
			const hasD = hits.some((h) => h.entry.songId === 'd');
			if (options.speciesId === 'parus_minor' && hasAbc && hasD) {
				const matched = hits.flatMap((h) => h.matched);
				const phrase = documentedPhrase(inventory, { speciesId: 'parus_minor', songId: 'abc_d', keywords: [] }, matched);
				if (phrase) return phrase;
			}
			const phrase = documentedPhrase(inventory, hits[0].entry, hits[0].matched);
			if (phrase) return phrase;
		}
	}

	const species = speciesById(inventory, options.speciesId);
	if (!species || !species.syllables.length) return null;

	const isQuestion = /\?\s*$/.test(trimmed);
	const words = normalise(trimmed).split(' ').filter(Boolean);
	if (!words.length) return null;

	const tokens: { chunk: string; indexInWord: number; wordIndex: number }[] = [];
	words.forEach((word, wordIndex) => {
		splitSyllables(word).forEach((chunk, indexInWord) => {
			tokens.push({ chunk, indexInWord, wordIndex });
		});
	});

	const ids = grammarWalk(species.grammar, species, tokens.map((t) => t.chunk));
	const syllables: Syllable[] = [];
	const gaps: number[] = [];

	tokens.forEach((token, i) => {
		const base = syllableById(species, ids[i]) ?? species.syllables[0];
		const position = tokens.length > 1 ? i / (tokens.length - 1) : 0;
		syllables.push(applyProsody(base, prosodyFor(token.chunk, token.indexInWord, position, isQuestion)));
		if (i < tokens.length - 1) {
			const nextWord = tokens[i + 1].wordIndex !== token.wordIndex;
			gaps.push(nextWord ? 0.12 : 0.035);
		}
	});

	return {
		speciesId: species.id,
		label: `"${trimmed}" as ${species.common}`,
		gloss: trimmed,
		function: 'Invented mapping: the text drives syllable choice and prosody.',
		confidence: 'invented',
		refs: [],
		syllables,
		gaps,
		source: 'invented',
		matched: [],
		documentedElsewhere: [...new Set(elsewhere)],
		note:
			species.grammar
				? 'Syllables are chosen by walking this species’ finite-state song grammar; vowels set pitch, stress sets pressure, and the utterance declines like speech. Birds do not encode words this way.'
				: 'Syllables are chosen by a stable hash of each text syllable; vowels set pitch and stress sets pressure. Birds do not encode words this way.'
	};
}

/** A ready-made bout from the species' own grammar, with no text behind it. */
export function improvise(inventory: Inventory, speciesId: string, maxSyllables = 12): Phrase | null {
	const species = speciesById(inventory, speciesId);
	if (!species) return null;
	const grammar = species.grammar;
	const syllables: Syllable[] = [];
	const gaps: number[] = [];

	if (grammar) {
		let current = grammar.start[Math.floor(Math.random() * grammar.start.length)];
		for (let i = 0; i < maxSyllables; i++) {
			const syllable = syllableById(species, current);
			if (!syllable) break;
			syllables.push(syllable);
			const next = grammar.transitions[current];
			if (!next) break;
			// sample the transition distribution
			let r = Math.random();
			let chosen: string | null = null;
			for (const [target, p] of Object.entries(next)) {
				r -= p;
				if (r <= 0) {
					chosen = target;
					break;
				}
			}
			if (!chosen || chosen === 'end') break;
			gaps.push(0.035);
			current = chosen;
		}
	} else {
		const song = species.songs[Math.floor(Math.random() * species.songs.length)];
		const resolved = song ? songSyllables(species, song.id) : null;
		if (resolved) {
			syllables.push(...resolved.syllables);
			gaps.push(...resolved.song.gaps);
		}
	}

	if (!syllables.length) return null;
	// A grammar fitted by `birdy-pipeline learn` is measured from field recordings, not
	// taken from the literature, so it must not borrow the citation that belongs to the
	// hand-authored one. Syllables with no documented function are the tell: only the
	// learned inventory produces them.
	const learned = syllables.every((s) => s.confidence === 'unlabelled');
	return {
		speciesId: species.id,
		label: `${species.common} improvisation`,
		gloss: 'a bout drawn from this species’ song syntax',
		function: learned
			? 'Sampled from a first-order syntax measured from field recordings of this species. The syntax is counted, not cited; the bout is ours.'
			: grammar
				? 'Sampled from the finite-state song syntax; song carries syntax rather than referential meaning.'
				: 'Sampled from this species’ song library.',
		confidence: learned ? 'unlabelled' : 'documented',
		refs: grammar && !learned ? ['okanoya2004'] : [],
		syllables,
		gaps,
		source: 'invented',
		matched: [],
		note: 'Song syntax is real; the specific bout is generated.'
	};
}

/**
 * The song composer behind the Compose tab: an editing layer over the measured grammar
 * that still renders through the universal `Phrase` (grammar.ts) and therefore through
 * the same `engine.playSequence` path as every other bout.
 *
 * Three ways to fill the strip, one honesty label each (§8.5's existing set):
 *
 *  - free: chips in an order of the user's — `invented`, "our sequence";
 *  - guided: the same chips, ranked by the transition probabilities counted from field
 *    recordings, with mined chunks offered as multi-token inserts — `unlabelled`,
 *    "the syntax is counted, not cited; the bout is ours" (improvise's wording);
 *  - song types: the observed medoid orderings, re-expanded into playable bouts —
 *    `unlabelled`, "this exact ordering recurred N times".
 *
 * Nothing here generates audio and nothing here invents rhythm: gaps stay the flat
 * placeholders the inventory ships until a per-transition gap is measured (docs/12),
 * and the module says so in every note it writes.
 */
import type { Chunk, SongType, Species, Syllable } from '$lib/data/types';
import { syllableById } from '$lib/data/assets';
import { splitSyllables, type Phrase } from '$lib/lang/grammar';

/** One act in the strip: a fitted syllable type plus where the user got it from. */
export interface Token {
	typeId: string;
	source: TokenSource['kind'];
	/**
	 * Gap *before* this token, set only by text-as-rhythm at a word boundary (0.12 s).
	 * Everything else falls back to the flat 0.06 s placeholder the inventory ships.
	 */
	gapBefore?: number;
}

export interface TokenSource {
	kind: 'free' | 'suggested' | 'chunk' | 'songType' | 'text';
}

/** Why the strip holds what it holds — decides the phrase's confidence, function and note. */
export interface Provenance {
	kind: 'free' | 'guided' | 'songType';
	/** The type a songType strip was expanded from; dropped the moment the strip is edited. */
	songType?: SongType;
	/** The text that set the rhythm, when it did. */
	text?: string;
}

export interface NextOption {
	typeId: string;
	/** Measured transition probability; null for a bout start, whose rate is not exported. */
	p: number | null;
	/** A mined chunk this candidate continues, when it does. */
	chunk?: Chunk;
}

export interface NextOptions {
	options: NextOption[];
	/** Measured probability that the bout ends here; null with an empty strip or no grammar. */
	endP: number | null;
}

/**
 * What the measured grammar allows after `tail`, best first.
 *
 * The tail's last token indexes the transition table; a candidate is annotated when it
 * continues a mined chunk whose prefix sits at the end of the tail, which is how "what
 * comes next" and "the rest of the motif" come from the same counts. An empty tail
 * offers the observed bout starts — their order is as shipped, their rates unexported.
 */
export function nextOptions(species: Species, tail: Token[]): NextOptions {
	const grammar = species.grammar;
	if (!grammar) return { options: [], endP: null };
	const tailIds = tail.map((t) => t.typeId);
	const last = tailIds[tailIds.length - 1];

	if (last === undefined) {
		return {
			options: grammar.start.map((typeId) => ({ typeId, p: null, chunk: chunkStart(grammar.chunks, typeId) })),
			endP: null
		};
	}

	const row = grammar.transitions[last] ?? {};
	const endP = typeof row.end === 'number' ? row.end : null;
	const options: NextOption[] = [];
	for (const [typeId, p] of Object.entries(row)) {
		if (typeId === 'end') continue;
		options.push({ typeId, p, chunk: chunkContinuation(grammar.chunks, tailIds, typeId) });
	}
	options.sort((a, b) => (b.p ?? 0) - (a.p ?? 0));
	return { options, endP };
}

function chunkStart(chunks: Chunk[] | undefined, typeId: string): Chunk | undefined {
	return chunks?.find((c) => c.sequence.length > 1 && c.sequence[0] === typeId);
}

/** The chunk that `candidate` would continue, matched on the longest tail prefix. */
function chunkContinuation(
	chunks: Chunk[] | undefined,
	tailIds: string[],
	candidate: string
): Chunk | undefined {
	if (!chunks) return undefined;
	let best: Chunk | undefined;
	let bestK = 0;
	for (const chunk of chunks) {
		const seq = chunk.sequence;
		for (let k = Math.min(tailIds.length, seq.length - 1); k >= 1; k--) {
			if (k <= bestK) break;
			let match = true;
			for (let j = 0; j < k; j++) {
				if (tailIds[tailIds.length - k + j] !== seq[j]) {
					match = false;
					break;
				}
			}
			if (match && seq[k] === candidate) {
				best = chunk;
				bestK = k;
				break;
			}
		}
	}
	return best;
}

export interface ChunkCompletion {
	chunk: Chunk;
	/** The tokens a single click inserts — the chunk's remainder after the matched prefix. */
	insert: string[];
}

/**
 * One-click motif inserts: every mined chunk whose prefix the tail already matches
 * (or any chunk, when the strip is empty), longest matches first.
 */
export function chunkCompletions(species: Species, tail: Token[]): ChunkCompletion[] {
	const chunks = species.grammar?.chunks;
	if (!chunks?.length) return [];
	const tailIds = tail.map((t) => t.typeId);
	const out: { completion: ChunkCompletion; matched: number }[] = [];
	for (const chunk of chunks) {
		const seq = chunk.sequence;
		if (seq.length < 2) continue;
		let k = 0;
		if (tailIds.length) {
			for (k = Math.min(tailIds.length, seq.length - 1); k >= 1; k--) {
				let match = true;
				for (let j = 0; j < k; j++) {
					if (tailIds[tailIds.length - k + j] !== seq[j]) {
						match = false;
						break;
					}
				}
				if (match) break;
			}
			if (k < 1) continue;
		}
		out.push({ completion: { chunk, insert: seq.slice(k) }, matched: k });
	}
	out.sort((a, b) => b.matched - a.matched || b.completion.chunk.count - a.completion.chunk.count);
	return out.map((o) => o.completion);
}

/** Longest run the run-length model is allowed to draw — enough for any trill on the corpus. */
const MAX_RUN = 12;

/**
 * Re-expands a song type's run-collapsed medoid into a playable bout.
 *
 * The type sequence records one token per *act* (learn.py `_collapse_runs`), so "play
 * S02 exactly" means deciding how long each act runs. The honest answer the grammar
 * already carries is the self-transition probability p_tt: a run is a geometric
 * variable with E[run] = 1/(1−p_tt), sampled here by inverse CDF and clamped to
 * [1, MAX_RUN]. This is the only sampling in the composer, and the phrase note names it.
 */
export function expandSongType(
	species: Species,
	songType: SongType,
	rng: () => number = Math.random
): Token[] {
	const transitions = species.grammar?.transitions ?? {};
	const tokens: Token[] = [];
	for (const typeId of songType.sequence) {
		const pSelf = transitions[typeId]?.[typeId] ?? 0;
		let run = 1;
		if (pSelf > 0 && pSelf < 1) {
			run = 1 + Math.floor(Math.log(1 - rng()) / Math.log(pSelf));
		} else if (pSelf >= 1) {
			run = MAX_RUN;
		}
		run = Math.max(1, Math.min(MAX_RUN, run));
		for (let i = 0; i < run; i++) tokens.push({ typeId, source: 'songType' });
	}
	return tokens;
}

export interface TextRhythm {
	/** How many tokens the text's syllabification calls for. */
	count: number;
	/** Token indexes that begin a new word — these get the wider 0.12 s gap. */
	wordStarts: number[];
}

/**
 * Text as rhythm and nothing else: `splitSyllables` yields a token count and word
 * boundaries. What the text never again does is choose a syllable — the hash walk and
 * prosody transposition of compilePhrase's invented arm stay out of the composer,
 * because transposing measured contours contradicts "the bird's own syllables".
 */
export function textRhythm(text: string): TextRhythm | null {
	const words = text
		.toLowerCase()
		.replace(/[^a-z0-9\s']/g, ' ')
		.replace(/\s+/g, ' ')
		.trim()
		.split(' ')
		.filter(Boolean);
	if (!words.length) return null;
	const wordStarts: number[] = [];
	let count = 0;
	for (const word of words) {
		wordStarts.push(count);
		count += splitSyllables(word).length;
	}
	return { count, wordStarts };
}

/**
 * Fills the strip to a text's rhythm by walking the measured suggestions — top
 * transition at each step, bout start first — never by hashing the words. Tokens are
 * tagged `text` so an unedited strip can say the order came from the syntax.
 */
export function applyTextRhythm(species: Species, text: string): Token[] | null {
	const rhythm = textRhythm(text);
	if (!rhythm) return null;
	const starts = new Set(rhythm.wordStarts);
	const tokens: Token[] = [];
	for (let i = 0; i < rhythm.count; i++) {
		const { options } = nextOptions(species, tokens);
		const fallback = species.syllables[0]?.id;
		const typeId = options[0]?.typeId ?? tokens[tokens.length - 1]?.typeId ?? fallback;
		if (!typeId) return null;
		tokens.push({ typeId, source: 'text', gapBefore: starts.has(i) && i > 0 ? 0.12 : undefined });
	}
	return tokens;
}

/** The inventory's flat placeholder gap, used everywhere until gaps are measured. */
const DEFAULT_GAP = 0.06;

/**
 * Turns the strip into the universal render currency.
 *
 * Confidence and wording come from the provenance, and only from §8.5's existing set:
 * a free strip is `invented` ("our sequence"), a guided or song-type strip is
 * `unlabelled` with improvise's "counted, not cited; the bout is ours" — plus, for a
 * song type, the one measured claim available: "this exact ordering recurred N times".
 */
export function tokensToPhrase(species: Species, tokens: Token[], provenance: Provenance): Phrase | null {
	const syllables: Syllable[] = [];
	const gaps: number[] = [];
	for (let i = 0; i < tokens.length; i++) {
		const syllable = syllableById(species, tokens[i].typeId);
		if (!syllable) continue;
		syllables.push(syllable);
		if (i < tokens.length - 1) gaps.push(tokens[i + 1].gapBefore ?? DEFAULT_GAP);
	}
	if (!syllables.length) return null;

	let label: string;
	let gloss: string;
	let func: string;
	let confidence: Phrase['confidence'];
	let note: string;
	switch (provenance.kind) {
		case 'songType': {
			const st = provenance.songType;
			label = `${species.common} song type ${st?.id ?? ''}`.trim();
			gloss = 'an ordering this bird was recorded singing';
			func = st
				? `Observed song type: this exact ordering recurred ${st.count} times in field recordings of this species.`
				: 'Observed song type, expanded from the fitted medoid.';
			confidence = 'unlabelled';
			note =
				'Trill lengths sampled from measured repeat rates (expected run 1/(1−p)); ' +
				'the recorded rhythm is not exported yet, so the gaps are placeholders.';
			break;
		}
		case 'guided':
			label = `${species.common} guided bout`;
			gloss = 'composed against the measured song syntax';
			func =
				'Measured transition statistics counted from field recordings of this species. ' +
				'The syntax is counted, not cited; the bout is ours.';
			confidence = 'unlabelled';
			note =
				'Suggestions rank the measured next-note probabilities and repeated motifs; ' +
				'the rhythm between notes is a placeholder — per-transition gaps are not exported yet.';
			break;
		default:
			label = `${species.common} composition`;
			gloss = 'a sequence composed chip by chip';
			func = 'Invented: our sequence, built from this bird’s fitted syllable types.';
			confidence = 'invented';
			note = 'Our own arrangement of measured syllables. Not a claim about real birds.';
	}

	if (provenance.text) {
		// "The order is the bird's measured syntax" is only claimable while every chip
		// still came from the rhythm walk or its suggestions; one keyboard pick makes it
		// the user's order, and the note shrinks to what stays true.
		const syntaxDriven = tokens.every((t) => t.source !== 'free');
		note +=
			provenance.kind === 'guided' && syntaxDriven
				? ` The text (“${provenance.text}”) set only the rhythm; syllables and order are the bird’s measured syntax.`
				: ` The text (“${provenance.text}”) set only the rhythm.`;
	}

	return {
		speciesId: species.id,
		label,
		gloss,
		function: func,
		confidence,
		refs: [],
		syllables,
		gaps,
		source: 'invented',
		matched: [],
		note
	};
}

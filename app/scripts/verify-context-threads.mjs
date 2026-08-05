/**
 * The backdrop threads: which claim each one makes, and how strongly it is drawn.
 *
 * The bug this exists to prevent is not a crash. The measured grammar carried a transition
 * probability that was **thrown away at draw time** — read, compared against
 * `GRAMMAR_FLOOR`, then discarded, so a transition a bird makes nine times in ten was drawn
 * exactly like one it makes once in twelve. Nothing failed. The picture simply stopped
 * being a reading and became a diagram, and no test could see the difference because the
 * number never reached the geometry.
 *
 * So every check here is about a quantity *arriving*: that a grammar segment's alpha is a
 * function of its own probability, that the function is monotone, and that a song and a
 * grammar pair end up in different passes. A wrong alpha shows on screen as a line that
 * looks slightly faint — the most expensive kind of wrong, because it is legible.
 *
 * Run with `npm run verify:context-threads`. Exits non-zero on any disagreement.
 */
import {
	alphaFor,
	contextSegments,
	FROM_LIGHT,
	grammarEnds,
	TO_LIGHT,
	WEIGHT_MAX,
	WEIGHT_MIN
} from '../src/lib/galaxy/context-threads.ts';

let failures = 0;
const ok = (name, cond, detail = '') => {
	if (cond) console.log(`  ${name.padEnd(58)} ok${detail ? ` (${detail})` : ''}`);
	else {
		failures++;
		console.error(`  ${name.padEnd(58)} FAIL ${detail}`);
	}
};

/** The floor `grammarPathsOf` filters on, so the band's low end is the one drawn. */
const GRAMMAR_FLOOR = 0.08;
const near = (a, b, eps = 1e-9) => Math.abs(a - b) < eps;
const song = (nodes) => ({ nodes, kind: 'song', weight: 1 });
const pair = (a, b, weight) => ({ nodes: [a, b], kind: 'grammar', weight });

// --- the weight actually reaches the alpha --------------------------------------------
console.log('the probability arrives');

{
	// The whole point: two transitions with different probabilities must not be drawn the
	// same. This is the assertion that the discarded number is no longer discarded.
	//
	// Read through `?.` and NaN rather than indexed directly, because the mutation that
	// sends grammar to the song pass empties this array — and a check that throws reports a
	// stack trace where it should report which claim stopped being made.
	const { grammar } = contextSegments([pair(0, 1, 0.9), pair(2, 3, 0.1)], 10);
	ok('both transitions reach the grammar pass', grammar.length === 2, `${grammar.length}`);
	const hi = grammar[0]?.alpha ?? NaN;
	const lo = grammar[1]?.alpha ?? NaN;
	ok('a likely transition outdraws an unlikely one', hi > lo,
		`${hi.toFixed(3)} against ${lo.toFixed(3)}`);
	ok('and by the band, not by a hair', hi - lo > 0.25, `gap ${(hi - lo).toFixed(3)}`);
}

{
	// Monotone across the whole band, checked at every hundredth rather than at the ends:
	// a mapping that inverts or plateaus in the middle passes an ends-only test.
	let monotone = true;
	let prev = -Infinity;
	for (let p = 0; p <= 1.0001; p += 0.01) {
		const a = alphaFor(p);
		if (a < prev) monotone = false;
		prev = a;
	}
	ok('alphaFor is monotone over 0..1', monotone);
	ok('p = 0 lands on WEIGHT_MIN', near(alphaFor(0), WEIGHT_MIN), `${alphaFor(0)}`);
	ok('p = 1 lands on WEIGHT_MAX', near(alphaFor(1), WEIGHT_MAX), `${alphaFor(1)}`);
	ok('p = 0.5 lands on the midpoint', near(alphaFor(0.5), (WEIGHT_MIN + WEIGHT_MAX) / 2));
}

{
	// A floor transition must be *visible*, which is the reason the band does not start at
	// zero. If this ever fails the weighting reads as "the grammar faded out".
	const a = alphaFor(GRAMMAR_FLOOR);
	ok('a floor transition is still visible', a >= 0.1, `alpha ${a.toFixed(3)} at p = 0.08`);
	ok('and it is fainter than a song', a < 0.28, `alpha ${a.toFixed(3)} against 0.28`);
	ok('a certain transition reads over a song', alphaFor(1) > 0.28, `${alphaFor(1)}`);
}

{
	// Clamped, because a weight outside 0..1 is a bug upstream and an unclamped map would
	// paint it as an invisible or an over-strong thread instead of being caught.
	ok('a negative weight clamps to the floor', near(alphaFor(-5), WEIGHT_MIN));
	ok('a weight past 1 clamps to the ceiling', near(alphaFor(12), WEIGHT_MAX));
}

// --- the two claims go to two passes --------------------------------------------------
console.log('\nthe kinds stay apart');

{
	const { songs, grammar } = contextSegments([song([0, 1, 2]), pair(3, 4, 0.5)], 10);
	ok('a song goes to the song pass', songs.length === 2 && grammar.length === 1,
		`${songs.length} song, ${grammar.length} grammar`);
	ok('a song is drawn at even weight', songs.every((s) => s.alpha === 1));
	ok('a grammar pair is one segment', grammar.length === 1);
}

{
	// A song of n nodes is n-1 segments, so separate songs are never joined to each other.
	const { songs } = contextSegments([song([0, 1, 2, 3]), song([4, 5])], 10);
	ok('a 4-node song is 3 segments', songs.filter((s) => s.a < 4).length === 3);
	ok('two songs do not join up', !songs.some((s) => s.a === 3 && s.b === 4));
}

{
	// An unknown kind is drawn as a song rather than dropped: a thread that exists is a
	// fact about the bird, and losing it silently is worse than drawing it unweighted.
	const { songs } = contextSegments([{ nodes: [0, 1], kind: 'future', weight: 0.5 }], 10);
	ok('an unknown kind still draws', songs.length === 1 && songs[0].alpha === 1);
}

// --- nodes the corpus lacks -----------------------------------------------------------
console.log('\nmissing knots are gaps, never wrong lines');

{
	// A song can name a syllable that owns no knot in this build. Dropped rather than
	// clamped: a thread to knot 0 is a false statement, a missing thread is only a gap.
	const { songs } = contextSegments([song([0, -1, 2])], 10);
	ok('a dropped node does not become knot 0', !songs.some((s) => s.a === 0 && s.b === 0));
	ok('the surviving nodes still join', songs.length === 1 && songs[0].a === 0 && songs[0].b === 2);
}

{
	const { songs } = contextSegments([song([0, 99])], 10);
	ok('an index past the build is dropped', songs.length === 0);
	const one = contextSegments([song([5])], 10);
	ok('a single-node song draws nothing', one.songs.length === 0);
	const empty = contextSegments([], 10);
	ok('no paths draws nothing', empty.songs.length === 0 && empty.grammar.length === 0);
}

{
	// A fractional index would silently read halfway into the position buffer and draw a
	// segment from nowhere, which is why the filter tests for an integer rather than a range.
	const { songs } = contextSegments([song([0, 1.5, 2])], 10);
	ok('a fractional index is dropped', !songs.some((s) => !Number.isInteger(s.a + s.b)));
}

// --- a real bird's grammar ------------------------------------------------------------
console.log('\na measured grammar, end to end');

{
	// The shape `grammarPathsOf` emits: every surviving transition of one bird, each with
	// its own probability. Nothing here may collapse to one alpha.
	const probs = [0.08, 0.12, 0.19, 0.31, 0.44, 0.67, 0.95];
	const paths = probs.map((p, i) => pair(i, i + 1, p));
	const { grammar } = contextSegments(paths, 20);
	ok('every transition is drawn', grammar.length === probs.length, `${grammar.length}`);
	const alphas = new Set(grammar.map((s) => s.alpha.toFixed(6)));
	ok('seven probabilities give seven alphas', alphas.size === probs.length, `${alphas.size}`);
	const sorted = [...grammar].sort((x, y) => x.alpha - y.alpha);
	ok('the order is the probability order',
		sorted.every((s, i) => s.a === i), 'faintest is the floor transition');
	ok('every alpha is inside the band',
		grammar.every((s) => s.alpha >= WEIGHT_MIN - 1e-9 && s.alpha <= WEIGHT_MAX + 1e-9));
}

{
	// Songs and grammar together, which is what `showContext` actually passes.
	const { songs, grammar } = contextSegments(
		[song([0, 1, 2]), pair(0, 1, 0.9), pair(1, 2, 0.2), song([3, 4])],
		10
	);
	ok('the passes are independent', songs.length === 3 && grammar.length === 2,
		`${songs.length} song, ${grammar.length} grammar`);
	ok('a shared transition appears in both passes',
		songs.some((s) => s.a === 0 && s.b === 1) && grammar.some((s) => s.a === 0 && s.b === 1),
		'a song and a statistic about it are two claims');
}

// --- the hue names the bird, and the walk names the direction ------------------------
//
// Same failure mode as the alpha above, one channel over. A grammar thread used to be a
// flat amber for every species and both of its ends, so two quantities it holds — whose
// transition this is, and which way it runs — were legible as nothing. These checks are
// that both arrive: that two birds get two hues, that one bird's two knots do not, and
// that the `from` end is darker than the `to` end by a margin a hairline can show.
console.log('\nthe bird and the direction arrive');

/** HSL lightness out of `speciesColourScaled`'s `hsl(h, s%, l%)`. */
const lightnessOf = (css) => Number(css.match(/,\s*([\d.]+)%\)$/)?.[1] ?? NaN);
const hueOf = (css) => Number(css.match(/^hsl\(([\d.]+)/)?.[1] ?? NaN);

{
	const tit = grammarEnds('parus_major');
	const wren = grammarEnds('troglodytes_troglodytes');
	ok('two birds get two hues', hueOf(tit.from) !== hueOf(wren.from),
		`${hueOf(tit.from).toFixed(1)} against ${hueOf(wren.from).toFixed(1)}`);
	ok('one bird keeps one hue across both ends', hueOf(tit.from) === hueOf(tit.to),
		`${hueOf(tit.from).toFixed(1)}`);
	ok('the from end is the darker one', lightnessOf(tit.from) < lightnessOf(tit.to),
		`${lightnessOf(tit.from)}% into ${lightnessOf(tit.to)}%`);
	ok('and by enough to see on a hairline',
		lightnessOf(tit.to) - lightnessOf(tit.from) > 12,
		`${(lightnessOf(tit.to) - lightnessOf(tit.from)).toFixed(1)} points`);
	// Past ±20 % `speciesColourScaled` clamps, and a walk that hits the clamp would draw
	// every bird's two ends at the same two lightnesses — the direction would survive and
	// the identity would not.
	ok('the walk stays inside the species clamp',
		FROM_LIGHT >= 0.8 && TO_LIGHT <= 1.2, `${FROM_LIGHT}..${TO_LIGHT}`);
	// A knot with no species tag must not throw or come back as white: an all-synthetic
	// knot carries no majority species, and the thread still has to be drawn.
	const none = grammarEnds('');
	ok('a knot with no species still yields a colour',
		Number.isFinite(hueOf(none.from)) && Number.isFinite(lightnessOf(none.to)),
		none.from);
}

console.log(
	failures ? `\n${failures} check(s) failed` : '\nall context thread checks passed'
);
process.exit(failures ? 1 : 0);

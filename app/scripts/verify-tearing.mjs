/**
 * Per-knot tearing: is the number on the knot, does it agree with the aggregate, and does
 * a reader ever see it.
 *
 * **The failure this exists for is the third instance of one pattern.** `torn_clusters`
 * scored every knot for whether the projection draws it in two places, kept five
 * aggregates, and threw all 6 316 per-knot ratios away — so the manifest could say "2 035
 * torn, median 3.704, faithfulness 0.43 Pearson" while a viewer reading distance off one
 * particular knot had no way to learn whether that knot was one of them. `points.snr` and
 * `points.knnAgreement` were the first two instances, both measured in the pipeline and
 * drawn nowhere. The rule that came out of it: **a channel is not built until something
 * draws it**, and this asserts both halves plus the arithmetic that ties them together.
 *
 * What is checked, and why each one is a real failure mode:
 *
 *   1. **The aggregate must be reproducible from the per-knot values.** If the manifest's
 *      `measured`, `torn`, `severe` and `median` cannot be recomputed from the knots that
 *      carry a ratio, then the two were measured on different positions — which is exactly
 *      what a stale asset or a hand-patched file looks like, and nothing else would notice.
 *   2. **Absent must mean unmeasured.** 9 025 of 15 341 knots carry no value, and only
 *      6 771 of those are below the 12-point size gate; the other 2 254 are knots whose own
 *      2-means split isolates one or two outliers. A zero written for either would say
 *      "drawn in one place", which is a claim the pipeline never made.
 *   3. **The view must read it.** Both readouts, and the fact that they band rather than
 *      scale: the ratio's range here is 1.361 to 4 001.2, and a linear meter would render
 *      two thousand indistinguishable maxima.
 *
 * Run with `npm run verify:tearing`. Exits non-zero on any disagreement.
 */
import { readFileSync } from 'node:fs';

const ASSETS = process.env.LYREBIRD_ASSETS ?? 'static/lyrebird';

let failures = 0;
const ok = (name, cond, detail = '') => {
	if (cond) console.log(`  ${name.padEnd(58)} ok${detail ? ` (${detail})` : ''}`);
	else {
		failures++;
		console.error(`  ${name.padEnd(58)} FAIL ${detail}`);
	}
};

const centroids = JSON.parse(readFileSync(`${ASSETS}/centroids.json`, 'utf8'));
const manifest = JSON.parse(readFileSync(`${ASSETS}/manifest.json`, 'utf8'));
const labels = readFileSync('src/lib/galaxy/NodeLabels.svelte', 'utf8');
const page = readFileSync('src/routes/+page.svelte', 'utf8');
const types = readFileSync('src/lib/data/types.ts', 'utf8');

const items = centroids.items ?? [];
const withValue = items.filter((it) => it.tearing !== undefined);
const reported = manifest.tearing ?? null;

console.log(`the number, on ${ASSETS}`);

if (!reported) {
	ok('a build with no tearing aggregate is legal', true, 'nothing to check against');
	ok('and then no knot may claim one either', withValue.length === 0, `${withValue.length} do`);
	console.log('\nall tearing checks passed (no aggregate on this build)');
	process.exit(failures ? 1 : 0);
}

ok('every knot has an id that indexes it', items.every((it, i) => it.id === i), `k = ${items.length}`);
ok(
	'the per-knot count equals the aggregate measured',
	withValue.length === reported.measured,
	`${withValue.length} vs ${reported.measured}`
);
ok(
	'no value is zero or null — absent is how unmeasured is written',
	withValue.every((it) => typeof it.tearing === 'number' && it.tearing > 0),
	`${withValue.filter((it) => !(it.tearing > 0)).length} are not`
);

const ratios = withValue.map((it) => it.tearing).sort((a, b) => a - b);
const median = ratios.length % 2
	? ratios[(ratios.length - 1) / 2]
	: (ratios[ratios.length / 2 - 1] + ratios[ratios.length / 2]) / 2;
// **The arithmetic tie.** Recomputed from the knots, compared with what the manifest says.
ok(
	'torn (>5) recomputes to the aggregate',
	withValue.filter((it) => it.tearing > 5).length === reported.torn,
	`${withValue.filter((it) => it.tearing > 5).length} vs ${reported.torn}`
);
ok(
	'severe (>8) recomputes to the aggregate',
	withValue.filter((it) => it.tearing > 8).length === reported.severe,
	`${withValue.filter((it) => it.tearing > 8).length} vs ${reported.severe}`
);
ok(
	'the median recomputes to the aggregate',
	Math.abs(median - reported.median) < 0.002,
	`${median.toFixed(3)} vs ${reported.median}`
);

// Reported, not asserted: properties of this projection, and thresholds here would turn a
// finding into a failure. The tail is the reason the view bands instead of scaling.
const absent = items.length - withValue.length;
const small = items.filter((it) => it.tearing === undefined && (it.count ?? 0) < 12).length;
console.log(
	`\n  ${withValue.length.toLocaleString()} measured of ${items.length.toLocaleString()} knots · ` +
		`range ${ratios[0].toFixed(3)} to ${ratios[ratios.length - 1].toFixed(3)} · median ${median.toFixed(3)}` +
		`\n  ${absent.toLocaleString()} unmeasured: ${small.toLocaleString()} below the 12-point gate, ` +
		`${(absent - small).toLocaleString()} with a degenerate split`
);

console.log('\nthe reader, on src/');
ok('the type declares the field', /tearing\?: number;/.test(types));
ok('a tag can say a knot is torn', /tearingLabel/.test(labels));
ok(
	'and bands rather than printing the raw ratio on every tag',
	/c\.tearing > 8/.test(labels) && /c\.tearing > 5/.test(labels) && /return '';/.test(labels),
	'the range reaches 4 001, so a figure on a tag would imply precision'
);
ok('the pinned panel reads it', /pinned\.tearing/.test(page));
ok(
	'and states unmeasured as unmeasured',
	/not measured/.test(page) && /pinned\.tearing === undefined/.test(page),
	'absent must never render as "drawn in one place"'
);

console.log(failures ? `\n${failures} tearing checks FAILED` : '\nall tearing checks passed');
process.exit(failures ? 1 : 0);

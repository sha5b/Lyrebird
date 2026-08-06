/**
 * The contract for a syllable type that owns more than one knot.
 *
 * **The pipeline can split a type in two and the app used to silently drop the second
 * one.** `buildClusterLookup` kept the first cluster it saw per `(species, syllable)` and
 * ignored the rest, which was harmless only for as long as no type owned two. Both split
 * gates now exist — the field/synthetic seam (`SOURCE_SEED_GATE`) and a type's own
 * bimodality (`TYPE_SPLIT_SEPARATION`) — so it is not harmless any more: the second blob
 * would be drawn, never light, and never be labelled. That is the "one note shines and
 * there is no label and no connection" report with the sign flipped.
 *
 * What is asserted:
 *  - every knot a type owns is reachable, and the primary is the one the build ranked 0;
 *  - `clusterIndexFor` still returns exactly one place, because a thread is a sequence in
 *    time and a forked song line would claim the bird sang one syllable twice;
 *  - the companions a path carries stay aligned with its nodes when unplaced syllables
 *    are dropped between them;
 *  - the shipped assets are self-consistent about `blobRank` / `blobCount`.
 *
 * Run with `npm run verify:split-knots`. Exits non-zero on any disagreement.
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import {
	buildClusterLookup,
	clusterIndexFor,
	clusterIndicesFor
} from '../src/lib/data/cluster-lookup.ts';

let failures = 0;
const ok = (name, cond, detail = '') => {
	if (cond) console.log(`  ${name.padEnd(48)} ok${detail ? ` (${detail})` : ''}`);
	else {
		failures++;
		console.error(`  ${name.padEnd(48)} FAIL ${detail}`);
	}
};

/** Centroid items are the only field the lookup reads; plant them directly. */
const items = (...rows) => ({
	k: rows.length,
	items: rows.map((r, id) => ({ id, position: [0, 0, 0], ...r }))
});

console.log('a type that owns two knots');

// Deliberately out of rank order in the array, so "primary" cannot be passing by
// accident of file order — which is exactly what the old implementation relied on.
const split = items(
	{ speciesId: 'sp_a', syllableId: 'L01', count: 12, blobRank: 1, blobCount: 2 },
	{ speciesId: 'sp_b', syllableId: 'L02', count: 40 },
	{ speciesId: 'sp_a', syllableId: 'L01', count: 88, blobRank: 0, blobCount: 2 },
	{ speciesId: '', syllableId: '', count: 5 }
);
const lookup = buildClusterLookup(split);

ok('both knots are reachable', clusterIndicesFor(lookup, 'sp_a', 'L01').length === 2,
	`got ${JSON.stringify(clusterIndicesFor(lookup, 'sp_a', 'L01'))}`);
ok('the primary is the build\'s rank 0', clusterIndexFor(lookup, 'sp_a', 'L01') === 2,
	`got ${clusterIndexFor(lookup, 'sp_a', 'L01')}, expected 2`);
ok('...and it is first in the full list', clusterIndicesFor(lookup, 'sp_a', 'L01')[0] === 2);
ok('one place for the thread, still', typeof clusterIndexFor(lookup, 'sp_a', 'L01') === 'number');
ok('an unsplit type is unaffected', clusterIndicesFor(lookup, 'sp_b', 'L02').length === 1);
ok('an unplaced type resolves to nothing',
	clusterIndexFor(lookup, 'sp_z', 'L09') === -1 && clusterIndicesFor(lookup, 'sp_z', 'L09').length === 0);
ok('a knot with no syllable is never addressed', !lookup.allBySyllable.has('/'));

// A build from before the split shipped carries no ranks at all; there the sole knot is
// the primary by definition, and the lookup must not start inventing an order.
const legacy = buildClusterLookup(
	items(
		{ speciesId: 'sp_a', syllableId: 'L01', count: 30 },
		{ speciesId: 'sp_b', syllableId: 'L02', count: 10 }
	)
);
ok('a build with no blobRank still resolves',
	clusterIndexFor(legacy, 'sp_a', 'L01') === 0 && clusterIndexFor(legacy, 'sp_b', 'L02') === 1);

// Ranks absent but a type owning two anyway — a half-written build. Falling back to the
// larger blob is the same rule the pipeline applies, so the two cannot disagree.
const unranked = buildClusterLookup(
	items(
		{ speciesId: 'sp_a', syllableId: 'L01', count: 5 },
		{ speciesId: 'sp_a', syllableId: 'L01', count: 50 }
	)
);
ok('no ranks: the larger blob is the primary', clusterIndexFor(unranked, 'sp_a', 'L01') === 1);

console.log('\ncompanions stay attached to their own syllable');

/**
 * `Listener.clean` is private, so the rule it implements is restated here — the same
 * reason `check-provenance-buffers` re-derives what it checks. What matters is that a
 * dropped node takes its companions with it: index drift would light a *different*
 * type's second knot, which reads as the galaxy answering the wrong bird.
 */
function clean(nodes, times, companions) {
	const keptNodes = [];
	const keptTimes = [];
	const keptCompanions = [];
	nodes.forEach((node, i) => {
		if (node < 0) return;
		keptNodes.push(node);
		if (times?.[i]) keptTimes.push(times[i]);
		if (companions) keptCompanions.push((companions[i] ?? []).filter((c) => c >= 0));
	});
	return {
		nodes: keptNodes,
		times: times && keptTimes.length === keptNodes.length ? keptTimes : null,
		companions: keptCompanions.some((c) => c.length) ? keptCompanions : null
	};
}

const t = (n) => Array.from({ length: n }, (_, i) => ({ start: i, end: i + 1 }));
// middle syllable is unplaced; its companions must go with it, not shift onto the third
const dropped = clean([7, -1, 9], t(3), [[70], [], [90]]);
ok('a dropped node takes its companions',
	JSON.stringify(dropped.nodes) === '[7,9]' && JSON.stringify(dropped.companions) === '[[70],[90]]',
	JSON.stringify(dropped));
ok('no companions anywhere stays null', clean([1, 2], t(2), [[], []]).companions === null);
ok('companions absent entirely stays null', clean([1, 2], t(2), null).companions === null);
ok('a negative companion is dropped, not lit',
	JSON.stringify(clean([1], t(1), [[-1, 5]]).companions) === '[[5]]');

console.log('\nthe shipped assets');

// An asset root can be named, because the shipped one predates the split gates and the
// interesting case is a build that actually has split knots in it.
const dir = process.argv[2] ?? new URL('../static/lyrebird/', import.meta.url).pathname;
console.log(`  (${dir})`);
const centroids = JSON.parse(readFileSync(join(dir, 'centroids.json'), 'utf8'));
const shipped = buildClusterLookup(centroids);

let multi = 0;
let rankProblems = 0;
let countProblems = 0;
for (const [key, list] of shipped.allBySyllable) {
	if (list.length > 1) multi++;
	const ranks = list.map((i) => centroids.items[i].blobRank);
	if (ranks.every((r) => typeof r === 'number')) {
		const sorted = [...ranks].sort((a, b) => a - b);
		if (sorted.join() !== ranks.join()) rankProblems++;
		if (sorted.join() !== sorted.map((_, i) => i).join()) rankProblems++;
		const declared = centroids.items[list[0]].blobCount;
		if (declared !== undefined && declared !== list.length) countProblems++;
	}
	if (!list.length) rankProblems++, void key;
}
ok('every type resolves to at least one knot', ![...shipped.allBySyllable.values()].some((l) => !l.length));
ok('ranks are 0..n-1 and sorted primary-first', rankProblems === 0, `${rankProblems} bad`);
ok('blobCount agrees with the knots found', countProblems === 0, `${countProblems} disagree`);
console.log(
	`  ${shipped.allBySyllable.size} named types, ${multi} owning more than one knot` +
		(multi === 0 ? ' — this build predates the split gates' : '')
);

console.log(failures ? `\nsplit knots: ${failures} FAILED` : '\nsplit knots: all checks passed');
process.exit(failures ? 1 : 0);

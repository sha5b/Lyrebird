/**
 * The joined density verdict: is the channel there, does it agree with what measured it,
 * and does its absence still draw the old picture.
 *
 * The failure this exists to prevent is specific and quiet. `unassigned` does not come out
 * of the build that writes `points.json` — it is joined in from a *second* build
 * (`--clustering hdbscan`) by row index, by `analysis/v10_unknown_join.py`. Two things can
 * therefore go wrong in ways nothing else notices:
 *
 *   1. **A misaligned join.** Every array is the right length, every value is a plausible
 *      0 or 1, and the flags belong to different sounds than the rows they sit on. The
 *      picture would be confident and fictional. The join script re-derives the alignment
 *      before writing; this re-checks the *result* against the report it wrote, so a
 *      hand-edited or half-written asset cannot pass.
 *   2. **An absent channel read as a measurement.** On a build with no join, "we did not
 *      ask" must not render as "nothing was refused" — the control disables and the shader
 *      holds at 0. That is a real state (it is the state every build before this one was
 *      in), so it is asserted rather than assumed.
 *
 * Run with `npm run verify:unheard`. Exits non-zero on any disagreement.
 */
import { readFileSync, existsSync } from 'node:fs';

const ASSETS = process.env.BIRDY_ASSETS ?? 'static/birdy';
const REPORT = process.env.BIRDY_JOIN_REPORT ?? '../pipeline/analysis/v10_unknown_join.json';

let failures = 0;
const ok = (name, cond, detail = '') => {
	if (cond) console.log(`  ${name.padEnd(58)} ok${detail ? ` (${detail})` : ''}`);
	else {
		failures++;
		console.error(`  ${name.padEnd(58)} FAIL ${detail}`);
	}
};

const points = JSON.parse(readFileSync(`${ASSETS}/points.json`, 'utf8'));
const manifest = JSON.parse(readFileSync(`${ASSETS}/manifest.json`, 'utf8'));

console.log(`the channel, on ${ASSETS}`);

if (!points.unassigned) {
	// The pre-join state, and it has to stay legal.
	ok('no channel is a legal build', true, 'the control disables; nothing is claimed');
	ok(
		'and the manifest does not claim one either',
		!manifest.unassigned,
		`manifest.unassigned = ${manifest.unassigned}`
	);
	console.log('\nall unheard checks passed (no joined channel on this build)');
	process.exit(0);
}

const n = points.n;
ok('the flag is one per point', points.unassigned.length === n, `${points.unassigned.length} of ${n}`);
ok(
	'the region id is one per point',
	!points.densityRegion || points.densityRegion.length === n,
	`${points.densityRegion?.length}`
);
ok(
	'every flag is 0 or 1',
	points.unassigned.every((v) => v === 0 || v === 1),
	'a fractional flag would draw a half-refused point'
);

const refused = points.unassigned.reduce((a, v) => a + v, 0);
const share = refused / n;
ok('something was refused, and not everything', refused > 0 && refused < n,
	`${refused} of ${n} (${(share * 100).toFixed(1)} %)`);

// The two channels must agree on which points they are talking about: a point in no dense
// region must be exactly a point whose region id is -1. They are written from one array, so
// disagreement means the file was edited after the join.
if (points.densityRegion) {
	let mismatch = 0;
	for (let i = 0; i < n; i++) {
		if ((points.densityRegion[i] < 0 ? 1 : 0) !== points.unassigned[i]) mismatch++;
	}
	ok('the flag and the region id agree', mismatch === 0, `${mismatch} rows disagree`);
}

// **The shipped map cannot have measured this itself.** Its clustering is `label`, which
// assigns everything, so a non-zero `manifest.unassigned` here would mean the channel came
// from the same build — and then it would not be a second opinion at all.
ok(
	"this map's own clustering still refuses nothing",
	manifest.clustering === 'label' && !manifest.unassigned,
	`clustering=${manifest.clustering}, manifest.unassigned=${manifest.unassigned ?? 0}`
);

if (existsSync(REPORT)) {
	const report = JSON.parse(readFileSync(REPORT, 'utf8'));
	console.log('\nagainst the run that measured it');
	ok('the point count matches the join', report.points === n, `${report.points} vs ${n}`);
	ok('the refused count matches the join', report.unassigned === refused,
		`${report.unassigned} vs ${refused}`);
	ok(
		'the discovery queue is not empty',
		report.discoveryQueue?.inADenseRegion > 0,
		`${report.discoveryQueue?.inADenseRegion} unidentified points sit in a dense region`
	);
} else {
	console.log(`\n  (no join report at ${REPORT}; skipping the cross-check)`);
}

// The crossing that makes the channel worth drawing: an unidentified point is real field
// audio no type claims, and the interesting ones are those a dense region *does* claim.
// If the two were independent the shares would match; a gap is the finding.
const unidentified = [];
for (let i = 0; i < n; i++) {
	const syl = points.syllableId[i] ?? '';
	if (!syl && points.source[i] === 'field') unidentified.push(i);
}
if (unidentified.length) {
	const refusedAmong = unidentified.reduce((a, i) => a + points.unassigned[i], 0);
	console.log('\nunidentified against the verdict');
	console.log(
		`  ${unidentified.length} unidentified points; ${refusedAmong} in no dense region ` +
			`(${((refusedAmong / unidentified.length) * 100).toFixed(1)} % against ` +
			`${(share * 100).toFixed(1)} % corpus-wide)`
	);
	ok(
		'the two channels are not the same channel',
		refusedAmong !== unidentified.length && refusedAmong !== 0,
		'"no type claims it" and "no dense region claims it" have to be able to disagree'
	);
}

console.log(failures ? `\n${failures} check(s) failed` : '\nall unheard checks passed');
process.exit(failures ? 1 : 0);

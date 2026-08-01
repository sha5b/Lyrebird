/**
 * The galaxy layout's one non-obvious computation, checked against the obvious one.
 *
 * **Why this file exists.** There were no renderer tests, and the renderer's per-frame
 * and load-time costs have twice scaled with the corpus in ways nobody saw until a
 * production-sized build was loaded by hand. `nearestNeighbourDistances` is where that
 * risk is concentrated: it replaced a plain `k²` double loop (18 million distance tests
 * at the shipped build, 196 million at production's ~14 000 knots — about five seconds of
 * frozen tab) with a uniform grid and an early exit. The grid is exact, and this is what
 * says so: the same answers as brute force, on the shapes a real cloud actually takes,
 * including the degenerate ones a grid gets wrong if the early-exit radius is off by a
 * cell.
 *
 * Run with `npm run verify:layout`. Exits non-zero on any disagreement.
 */
import { nearestNeighbourDistances } from '../src/lib/galaxy/layouts.ts';

/** The `k²` loop this replaced, kept verbatim as the thing being checked against. */
function brute(cents, counts, k) {
	const real = [];
	for (let i = 0; i < k; i++) if (counts[i] > 0) real.push(i);
	if (real.length < 2) return [];
	return real.map((i) => {
		let best = Infinity;
		for (const j of real) {
			if (j === i) continue;
			const d = Math.hypot(
				cents[i * 3] - cents[j * 3],
				cents[i * 3 + 1] - cents[j * 3 + 1],
				cents[i * 3 + 2] - cents[j * 3 + 2]
			);
			if (d < best) best = d;
		}
		return best;
	});
}

/** Seeded, so a failure is reproducible rather than a coin toss. */
let seed = 12345;
const rnd = () => ((seed = (seed * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff);

/**
 * The shapes that matter. A uniform cube is the easy case; the rest are the ones that
 * break a grid. A flat sheet or a line collapses an axis, which is what makes a cell edge
 * taken from the bounding *volume* explode. Tight clumps with far outliers is the case
 * the early exit gets wrong when its cleared radius is a cell too generous. Memberless
 * knots all sit at the origin and must be excluded, not counted as coincident.
 */
const shapes = [
	[
		'uniform cube',
		(k) => {
			const c = new Float32Array(k * 3);
			for (let i = 0; i < k * 3; i++) c[i] = rnd() * 2 - 1;
			return [c, new Uint32Array(k).fill(3)];
		}
	],
	[
		'flat sheet, z collapsed',
		(k) => {
			const c = new Float32Array(k * 3);
			for (let i = 0; i < k; i++) {
				c[i * 3] = rnd();
				c[i * 3 + 1] = rnd();
			}
			return [c, new Uint32Array(k).fill(1)];
		}
	],
	[
		'one line',
		(k) => {
			const c = new Float32Array(k * 3);
			for (let i = 0; i < k; i++) c[i * 3] = rnd() * 5;
			return [c, new Uint32Array(k).fill(1)];
		}
	],
	[
		'tight clumps, far outliers',
		(k) => {
			const c = new Float32Array(k * 3);
			for (let i = 0; i < k; i++) {
				if (i % 50 === 0) {
					c[i * 3] = rnd() * 100;
					c[i * 3 + 1] = rnd() * 100;
					c[i * 3 + 2] = rnd() * 100;
				} else {
					c[i * 3] = Math.floor(i / 50) + rnd() * 0.001;
					c[i * 3 + 1] = rnd() * 0.001;
					c[i * 3 + 2] = rnd() * 0.001;
				}
			}
			return [c, new Uint32Array(k).fill(2)];
		}
	],
	[
		'half the knots memberless, at the origin',
		(k) => {
			const c = new Float32Array(k * 3);
			const n = new Uint32Array(k);
			for (let i = 0; i < k; i += 2) {
				c[i * 3] = rnd();
				c[i * 3 + 1] = rnd();
				c[i * 3 + 2] = rnd();
				n[i] = 5;
			}
			return [c, n];
		}
	],
	['every knot in one place', (k) => [new Float32Array(k * 3), new Uint32Array(k).fill(1)]]
];

/** The shipped build's k, the production build's k, and the small edge cases. */
const counts = [2, 3, 17, 200, 1024, 4298];

let failures = 0;
for (const [name, make] of shapes) {
	let worstOverall = 0;
	for (const k of counts) {
		const [cents, members] = make(k);
		const got = nearestNeighbourDistances(cents, members, k);
		const want = brute(cents, members, k);
		if (got.length !== want.length) {
			console.log(`FAIL ${name} k=${k}: ${got.length} answers, expected ${want.length}`);
			failures++;
			continue;
		}
		let worst = 0;
		for (let i = 0; i < want.length; i++) worst = Math.max(worst, Math.abs(got[i] - want[i]));
		if (worst > 1e-6) {
			console.log(`FAIL ${name} k=${k}: differs from brute force by ${worst}`);
			failures++;
		}
		worstOverall = Math.max(worstOverall, worst);
	}
	if (!failures) console.log(`  ${name.padEnd(38)} exact at every k (max diff ${worstOverall})`);
}

// The reason the grid is there at all, stated as a number rather than as a claim.
const K = 14003;
const cents = new Float32Array(K * 3);
for (let i = 0; i < K * 3; i++) cents[i] = rnd() * 2 - 1;
const members = new Uint32Array(K).fill(4);
let t = process.hrtime.bigint();
nearestNeighbourDistances(cents, members, K);
const grid = Number(process.hrtime.bigint() - t) / 1e6;
t = process.hrtime.bigint();
brute(cents, members, K);
const loop = Number(process.hrtime.bigint() - t) / 1e6;
console.log(
	`\n  at production's k=${K}: grid ${grid.toFixed(0)} ms against the k² loop's ${loop.toFixed(0)} ms`
);

if (failures) {
	console.log(`\n${failures} FAILURES`);
	process.exit(1);
}
console.log('\nlayout: all checks passed');

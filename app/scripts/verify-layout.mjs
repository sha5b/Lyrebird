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
import { buildLayout, nearestNeighbourDistances } from '../src/lib/galaxy/layouts.ts';

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

/**
 * The two-level arrangement (`localShapes`), on knots built so the right answer is known.
 *
 * The three cases that matter, and the one it must NOT "fix":
 *
 * 1. A knot the projection tore — one group of sounds in the feature space, two blobs a
 *    box-width apart in 3-d. Must come out as one blob.
 * 2. A knot that is genuinely two groups in the feature space. Must STAY two lobes: the
 *    layout is not allowed to hide a real split, only to stop the flattening inventing one.
 * 3. Extent. A knot's drawn spread has to stay proportional to its feature spread, or
 *    everything quoted against it (KNOT_GAP, the wave's reach, the ruler) drifts.
 *
 * Plus determinism: the same assets in must give the same positions out, or the picture
 * mirrors itself between reloads.
 */
console.log('\ntwo-level layout (localShapes)');

/** gap/spread between the two halves of a knot, the pipeline's own tearing statistic. */
function tornRatio(pos, idx) {
	// Split on the widest axis through the mean — enough to catch a two-blob knot, and
	// deterministic, which a k-means seeded by chance is not.
	let m = [0, 0, 0];
	for (const i of idx) for (let a = 0; a < 3; a++) m[a] += pos[i * 3 + a];
	m = m.map((v) => v / idx.length);
	let axis = 0;
	let best = -1;
	for (let a = 0; a < 3; a++) {
		let v = 0;
		for (const i of idx) v += (pos[i * 3 + a] - m[a]) ** 2;
		if (v > best) {
			best = v;
			axis = a;
		}
	}
	const lo = idx.filter((i) => pos[i * 3 + axis] < m[axis]);
	const hi = idx.filter((i) => pos[i * 3 + axis] >= m[axis]);
	if (lo.length < 2 || hi.length < 2) return 0;
	const mean = (set) => {
		const c = [0, 0, 0];
		for (const i of set) for (let a = 0; a < 3; a++) c[a] += pos[i * 3 + a];
		return c.map((v) => v / set.length);
	};
	const ca = mean(lo);
	const cb = mean(hi);
	const spreadOf = (set, c) => {
		let s = 0;
		for (const i of set)
			s += Math.hypot(pos[i * 3] - c[0], pos[i * 3 + 1] - c[1], pos[i * 3 + 2] - c[2]);
		return s / set.length;
	};
	const gap = Math.hypot(ca[0] - cb[0], ca[1] - cb[1], ca[2] - cb[2]);
	const spread = 0.5 * (spreadOf(lo, ca) + spreadOf(hi, cb));
	return gap / Math.max(spread, 1e-9);
}

/**
 * Three knots of 40 points each in an 8-d feature space, and a 3-d projection built to
 * be wrong in a specific way:
 *
 * - knot 0: one feature blob, but the projection puts half of it at x=-0.8 and half at
 *   x=+0.8 — the tear the two-level pass exists to repair.
 * - knot 1: two feature blobs, well separated. The projection draws them together; the
 *   pass must pull them apart again, because that split is in the sounds.
 * - knot 2: one feature blob, drawn as one blob. Must survive untouched in shape.
 */
{
	const D = 8;
	const PER = 40;
	const K3 = 3;
	const n = K3 * PER;
	const feat = new Float32Array(n * D);
	const pos = new Float32Array(n * 3);
	const clusterId = new Array(n);
	const unit = (row) => {
		let s = 0;
		for (let j = 0; j < D; j++) s += row[j] * row[j];
		s = Math.sqrt(s) || 1;
		for (let j = 0; j < D; j++) row[j] /= s;
		return row;
	};
	for (let c = 0; c < K3; c++) {
		for (let p = 0; p < PER; p++) {
			const i = c * PER + p;
			clusterId[i] = c;
			const row = new Float64Array(D);
			row[0] = 1;
			for (let j = 1; j < D; j++) row[j] = (rnd() - 0.5) * 0.08;
			// knot 1 is two real groups: the second half sits a long way along axis 3.
			if (c === 1 && p >= PER / 2) row[3] += 1.4;
			unit(row);
			for (let j = 0; j < D; j++) feat[i * D + j] = row[j];
			// The projection: knot 0 torn across x, knots 1 and 2 drawn as tight blobs.
			const base = [c * 0.05, 0, 0];
			pos[i * 3] = base[0] + (c === 0 ? (p % 2 ? 0.8 : -0.8) : 0) + (rnd() - 0.5) * 0.02;
			pos[i * 3 + 1] = base[1] + (rnd() - 0.5) * 0.02;
			pos[i * 3 + 2] = base[2] + (rnd() - 0.5) * 0.02;
		}
	}
	const assets = {
		positions: pos,
		pointFeatures: feat,
		pointFeatureDims: D,
		points: { n, clusterId },
		centroids: { k: K3, items: [] }
	};
	const idx = (c) => Array.from({ length: PER }, (_, p) => c * PER + p);
	const before = buildLayout(assets, false);
	const after = buildLayout(assets, true);

	const checks = [
		['knot torn by the projection is repaired', () => tornRatio(after.positions, idx(0)) < 4],
		['...and it really was torn before', () => tornRatio(before.positions, idx(0)) > 8],
		['a real split in the features survives', () => tornRatio(after.positions, idx(1)) > 5],
		['...and the projection had hidden it', () => tornRatio(before.positions, idx(1)) < 4],
		['an untorn knot stays untorn', () => tornRatio(after.positions, idx(2)) < 4],
		['every position is finite', () => after.positions.every(Number.isFinite)],
		[
			'the pass reports what it did',
			() => after.local?.reshaped === K3 && before.local === null && after.local.scale > 0
		],
		[
			'the same assets give the same positions',
			() => {
				const again = buildLayout(assets, true);
				return again.positions.every((v, i) => v === after.positions[i]);
			}
		],
		[
			'a build with no per-point features falls through',
			() => buildLayout({ ...assets, pointFeatures: null }, true).local === null
		]
	];
	for (const [name, run] of checks) {
		let ok = false;
		try {
			ok = run();
		} catch (err) {
			console.log(`  ${name}: threw ${err}`);
		}
		if (ok) console.log(`  ${name.padEnd(46)} ok`);
		else {
			console.log(`FAIL ${name}`);
			failures++;
		}
	}
	const spreadOf = (layout, c) => {
		const set = idx(c);
		const p = layout.positions;
		const m = [0, 0, 0];
		for (const i of set) for (let a = 0; a < 3; a++) m[a] += p[i * 3 + a];
		for (let a = 0; a < 3; a++) m[a] /= set.length;
		let s = 0;
		for (const i of set) s += Math.hypot(p[i * 3] - m[0], p[i * 3 + 1] - m[1], p[i * 3 + 2] - m[2]);
		return s / set.length;
	};
	// The wide knot has to be drawn wider than the tight one, which is the whole content
	// of "extent is measured". The ratio is not asserted exactly — one global scale ties
	// the corpus's median knot to its old size, and with three knots that median is noise.
	const wide = spreadOf(after, 1);
	const tight = spreadOf(after, 2);
	if (wide > tight * 2) {
		console.log(`  ${'extent follows the feature spread'.padEnd(46)} ok (${wide.toFixed(3)} vs ${tight.toFixed(3)})`);
	} else {
		console.log(`FAIL extent: wide knot ${wide.toFixed(4)} against tight knot ${tight.toFixed(4)}`);
		failures++;
	}
}

if (failures) {
	console.log(`\n${failures} FAILURES`);
	process.exit(1);
}
console.log('\nlayout: all checks passed');

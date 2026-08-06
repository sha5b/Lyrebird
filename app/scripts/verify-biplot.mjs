/**
 * What a direction in the picture means (`biplot.ts`), against planted answers.
 *
 * The fit is a weighted least squares solved by hand, and the failure that matters is
 * silent: a gradient that points the wrong way, or an r2 that flatters a direction
 * explaining nothing, would put a confident caption on a meaningless arrow. So every case
 * here plants an attribute whose true direction is known and checks the fit recovers it.
 *
 * Run with `npm run verify:biplot`. Exits non-zero on any disagreement.
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { biplotAxes, readScreenAxes } from '../src/lib/galaxy/biplot.ts';

let failures = 0;
const ok = (name, cond, detail = '') => {
	if (cond) console.log(`  ${name.padEnd(50)} ok${detail ? ` (${detail})` : ''}`);
	else {
		failures++;
		console.error(`  ${name.padEnd(50)} FAIL ${detail}`);
	}
};

const NAMES = [
	...Array.from({ length: 13 }, (_, i) => `mfcc${i}_mean`),
	...Array.from({ length: 13 }, (_, i) => `mfcc${i}_std`),
	'log2_centroid_mean',
	'flatness_mean'
];
const CENTROID = NAMES.indexOf('log2_centroid_mean');

/**
 * A synthetic corpus where brightness increases exactly along a chosen direction.
 * Positions are a deterministic lattice, so there is no seed and no flake.
 */
function planted(direction, noise = 0) {
	const items = [];
	const pos = [];
	let n = 0;
	for (let x = -3; x <= 3; x++) {
		for (let y = -3; y <= 3; y++) {
			for (let z = -3; z <= 3; z++) {
				const p = [x / 3, y / 3, z / 3];
				const v = new Array(28).fill(0);
				// a deterministic wobble, so `noise` is repeatable
				const jitter = noise * Math.sin(n * 12.9898) ;
				v[CENTROID] = p[0] * direction[0] + p[1] * direction[1] + p[2] * direction[2] + jitter;
				items.push({ speciesId: 'sp', syllableId: `L${n}`, count: 10, vector: v, meanDuration: 0.1 });
				pos.push(...p);
				n++;
			}
		}
	}
	return {
		assets: { centroids: { k: items.length, items }, featureSpace: { dimNames: NAMES } },
		positions: Float32Array.from(pos)
	};
}

console.log('the fit recovers a planted direction');

for (const dir of [
	[1, 0, 0],
	[0, 1, 0],
	[0, 0, 1],
	[0.577, 0.577, 0.577],
	[-0.6, 0.8, 0]
]) {
	const { assets, positions } = planted(dir);
	const axes = biplotAxes(assets, positions);
	const b = axes.find((a) => a.name === 'brightness');
	if (!b) {
		ok(`direction [${dir}]`, false, 'no brightness axis fitted');
		continue;
	}
	const len = Math.hypot(...dir);
	const want = dir.map((v) => v / len);
	const align = b.direction.reduce((s, v, i) => s + v * want[i], 0);
	ok(`recovers [${want.map((v) => v.toFixed(2)).join(', ')}]`, align > 0.999,
		`align ${align.toFixed(4)}, r2 ${b.r2.toFixed(3)}`);
}

{
	const { assets, positions } = planted([1, 0, 0]);
	const b = biplotAxes(assets, positions).find((a) => a.name === 'brightness');
	ok('a perfectly linear attribute reads r2 = 1', Math.abs(b.r2 - 1) < 1e-6, `r2 ${b.r2}`);
}

console.log('\nr2 is honest about how much it explains');
{
	// Same direction, increasing noise: r2 must fall monotonically while the direction
	// stays recovered. An r2 that does not move is an r2 that is not measuring anything.
	const got = [0, 0.5, 2, 8].map((noise) => {
		const { assets, positions } = planted([1, 0, 0], noise);
		return biplotAxes(assets, positions).find((a) => a.name === 'brightness');
	});
	const r2s = got.map((g) => g.r2);
	ok('r2 falls as the attribute gets noisier',
		r2s.every((v, i) => i === 0 || v < r2s[i - 1]), r2s.map((v) => v.toFixed(3)).join(' > '));
	ok('...and the direction still points the right way',
		got.every((g) => g.direction[0] > 0.7), got.map((g) => g.direction[0].toFixed(2)).join(', '));
}
{
	// An attribute that is constant everywhere has no direction. The normal equations are
	// then solvable but the gradient is zero, and returning an arrow would be an invention.
	const { assets, positions } = planted([0, 0, 0]);
	const b = biplotAxes(assets, positions).find((a) => a.name === 'brightness');
	ok('a constant attribute yields no axis, not a random one', b === undefined || b.r2 < 1e-6,
		b ? `r2 ${b.r2}` : 'absent');
}
{
	// Every knot at one place: the design matrix is singular and must be refused rather
	// than producing NaN, which would propagate into a caption.
	const items = Array.from({ length: 20 }, (_, i) => ({
		speciesId: 'sp', syllableId: `L${i}`, count: 5,
		vector: new Array(28).fill(0).map((_, d) => (d === CENTROID ? i : 0)),
		meanDuration: 0.1
	}));
	const axes = biplotAxes(
		{ centroids: { k: 20, items }, featureSpace: { dimNames: NAMES } },
		new Float32Array(60)
	);
	ok('all knots at one point yields no axes', axes.length === 0, `${axes.length} returned`);
}
{
	// Memberless knots sit at the centre of the box, which is not a place. Including them
	// would drag every direction toward the origin.
	const { assets, positions } = planted([1, 0, 0]);
	const withGhosts = {
		centroids: {
			k: assets.centroids.items.length + 30,
			items: [
				...assets.centroids.items,
				...Array.from({ length: 30 }, (_, i) => ({
					speciesId: 'sp', syllableId: `G${i}`, count: 0,
					vector: new Array(28).fill(0), meanDuration: 0
				}))
			]
		},
		featureSpace: { dimNames: NAMES }
	};
	const pos2 = new Float32Array(withGhosts.centroids.k * 3);
	pos2.set(positions);
	const b = biplotAxes(withGhosts, pos2).find((a) => a.name === 'brightness');
	ok('memberless knots are excluded from the fit', b && Math.abs(b.r2 - 1) < 1e-6,
		b ? `r2 ${b.r2.toFixed(6)}` : 'absent');
}

console.log('\nthe screen readout');
{
	const axes = [
		{ name: 'brightness', high: 'higher', direction: [0, 1, 0], r2: 0.8 },
		{ name: 'noisiness', high: 'noisier', direction: [1, 0, 0], r2: 0.5 },
		{ name: 'duration', high: 'longer', direction: [0, 0, 1], r2: 0.02 }
	];
	const r = readScreenAxes(axes, [1, 0, 0], [0, 1, 0], [0, 0, 1]);
	ok('right picks the attribute aligned with right',
		r.find((x) => x.axis === 'right')?.name === 'noisiness');
	ok('up picks brightness', r.find((x) => x.axis === 'up')?.name === 'brightness');
	ok('a weak attribute is not offered at all',
		!r.some((x) => x.name === 'duration'), JSON.stringify(r.map((x) => x.name)));
	// The sign matters: an attribute increasing to the *left* must not be captioned "right".
	const flipped = readScreenAxes(
		[{ name: 'brightness', high: 'higher', direction: [-1, 0, 0], r2: 0.8 }],
		[1, 0, 0], [0, 1, 0], [0, 0, 1]
	);
	ok('a reversed attribute reports a negative alignment',
		(flipped.find((x) => x.axis === 'right')?.align ?? 0) < 0,
		`${flipped.find((x) => x.axis === 'right')?.align}`);
	ok('one attribute is never used for two screen axes',
		new Set(r.map((x) => x.name)).size === r.length);
}

console.log('\nagainst the shipped build');
{
	const dir = new URL('../static/lyrebird/', import.meta.url).pathname;
	const centroids = JSON.parse(readFileSync(join(dir, 'centroids.json'), 'utf8'));
	const space = JSON.parse(readFileSync(join(dir, 'feature-space.json'), 'utf8'));
	const blk = centroids.vectors;
	if (blk) {
		const raw = readFileSync(join(dir, blk.file));
		const m = new Float32Array(raw.buffer, raw.byteOffset, centroids.k * blk.rowFloats);
		let at = 0;
		const off = {};
		for (const name of blk.order) {
			off[name] = at;
			at += blk.dims[name];
		}
		centroids.items.forEach((it, i) => {
			const base = i * blk.rowFloats + off.vector;
			it.vector = Array.from(m.subarray(base, base + blk.dims.vector));
		});
	}
	const pos = Float32Array.from(centroids.items.flatMap((c) => c.position));
	const axes = biplotAxes({ centroids, featureSpace: space }, pos);
	ok('the shipped build fits some readable directions', axes.length > 0, `${axes.length} axes`);
	ok('every r2 is a real number in 0..1',
		axes.every((a) => Number.isFinite(a.r2) && a.r2 >= 0 && a.r2 <= 1));
	ok('every direction is a unit vector',
		axes.every((a) => Math.abs(Math.hypot(...a.direction) - 1) < 1e-6));
	for (const a of axes) console.log(`    ${a.name.padEnd(12)} r2 ${a.r2.toFixed(3)}`);
}

console.log(failures ? `\nbiplot: ${failures} FAILED` : '\nbiplot: all checks passed');
process.exit(failures ? 1 : 0);

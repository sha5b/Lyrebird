/**
 * The song thread's geometry, and the pixel arithmetic its shader does with it.
 *
 * **A shader that fails to compile draws nothing and says so only to the console** —
 * this project lost its entire grid that way once, to a GLSL variable named `out`, and
 * nothing in the repo can see inside a shader string. So the two halves are split: the
 * buffer construction lives in `ribbon.ts` and is checked directly here, and the width
 * arithmetic the vertex shader does is *restated* here and checked against the geometry
 * it is supposed to produce. That does not prove the shader compiles. It does prove the
 * maths it implements is right, which is the half that is easy to get wrong quietly —
 * an offset that forgets the perspective divide looks fine at one depth and wrong at
 * every other.
 *
 * Run with `npm run verify:trajectory`. Exits non-zero on any disagreement.
 */
import {
	allocateRibbon,
	buildRibbon,
	RIBBON_VERTICES_PER_SEGMENT
} from '../src/lib/galaxy/ribbon.ts';

let failures = 0;
const ok = (name, cond, detail = '') => {
	if (cond) console.log(`  ${name.padEnd(50)} ok${detail ? ` (${detail})` : ''}`);
	else {
		failures++;
		console.error(`  ${name.padEnd(50)} FAIL ${detail}`);
	}
};

console.log('ribbon geometry');

const at = (arr, i, n) => Array.from({ length: n }, (_, k) => arr[i * n + k]);

// Three knots in a line, one path of two segments.
const places = [
	[0, 0, 0],
	[1, 0, 0],
	[1, 1, 0]
];
const hues = [
	[1, 0, 0],
	[0, 1, 0],
	[0, 0, 1]
];
const buffers = allocateRibbon(64);
const count = buildRibbon(
	buffers,
	[{ nodes: [0, 1, 2], pathId: 3 }],
	(k) => places[k],
	(k) => hues[k],
	64
);

ok('two segments make twelve vertices', count === 2 * RIBBON_VERTICES_PER_SEGMENT, `got ${count}`);
ok('every value is finite',
	[buffers.position, buffers.other, buffers.side, buffers.index, buffers.path]
		.every((a) => a.slice(0, count * (a.length / (64 * RIBBON_VERTICES_PER_SEGMENT))).every(Number.isFinite)));
ok('sides are only -1 and +1',
	Array.from(buffers.side.slice(0, count)).every((s) => s === -1 || s === 1));
ok('both sides appear equally',
	Array.from(buffers.side.slice(0, count)).filter((s) => s === 1).length === count / 2);
ok('the path id is carried on every vertex',
	Array.from(buffers.path.slice(0, count)).every((p) => p === 3));

// Each vertex sits on one of its segment's two ends, and `other` is always the far one.
let paired = true;
for (let v = 0; v < count; v++) {
	const seg = Math.floor(v / RIBBON_VERTICES_PER_SEGMENT);
	const self = at(buffers.position, v, 3);
	const other = at(buffers.other, v, 3);
	const ends = [places[seg], places[seg + 1]];
	const isStart = ends[0].every((c, i) => c === self[i]);
	const isEnd = ends[1].every((c, i) => c === self[i]);
	if (!isStart && !isEnd) paired = false;
	const wantOther = isStart ? ends[1] : ends[0];
	if (!wantOther.every((c, i) => c === other[i])) paired = false;
}
ok('every vertex pairs its own end with the far one', paired);

// The along-path coordinate is what the travelling swell is found from, so a vertex at
// the start of segment n must read exactly n — an off-by-one here puts the swell on the
// wrong syllable, which looks like the animation lagging rather than like a bug.
const idx = Array.from(buffers.index.slice(0, RIBBON_VERTICES_PER_SEGMENT));
ok('segment 0 spans index 0..1', Math.min(...idx) === 0 && Math.max(...idx) === 1, idx.join(','));
const idx2 = Array.from(buffers.index.slice(RIBBON_VERTICES_PER_SEGMENT, count));
ok('segment 1 spans index 1..2', Math.min(...idx2) === 1 && Math.max(...idx2) === 2, idx2.join(','));

// The gradient's endpoints are the knots' own hues; the walk between them is the
// interpolation the rasteriser does across the quad.
const startHue = at(buffers.colour, 0, 3);
ok('a vertex wears its own knot\'s hue', JSON.stringify(startHue) === JSON.stringify(hues[0]),
	startHue.join(','));

console.log('\nthe cases that would draw nothing, or NaN');

// A zero-length segment has no direction; the shader would normalise a zero vector, and
// one NaN vertex takes the whole draw call rather than its own quad.
const dupe = allocateRibbon(64);
const dupeCount = buildRibbon(
	dupe,
	[{ nodes: [0, 1, 2], pathId: 0 }],
	(k) => (k === 1 ? places[0] : places[k]),
	(k) => hues[k],
	64
);
ok('a zero-length segment is skipped, not emitted',
	dupeCount === RIBBON_VERTICES_PER_SEGMENT, `got ${dupeCount}`);

ok('a single-node path emits nothing',
	buildRibbon(allocateRibbon(8), [{ nodes: [0], pathId: 0 }], (k) => places[k], (k) => hues[k], 8) === 0);
ok('no paths emit nothing', buildRibbon(allocateRibbon(8), [], (k) => places[k], (k) => hues[k], 8) === 0);

// The cap has to bind before the buffer does, or this writes past the end of a
// Float32Array — which in JS is a silent no-op, so the failure would be a thread that
// mysteriously stops halfway.
const small = allocateRibbon(1);
const capped = buildRibbon(small, [{ nodes: [0, 1, 2], pathId: 0 }], (k) => places[k], (k) => hues[k], 1);
ok('the segment cap binds before the buffer ends',
	capped === RIBBON_VERTICES_PER_SEGMENT, `got ${capped}`);

console.log('\nthe width arithmetic the vertex shader does');

/**
 * The offset from `trajectoryRibbonVertexShader`, restated. Kept deliberately in the
 * shader's own terms — clip space, then the perspective divide — so the two can be read
 * side by side.
 */
function offsetPixels({ selfClip, otherClip, side, width, resolution }) {
	const ndc = (c) => [c[0] / c[3], c[1] / c[3]];
	const screen = (c) => {
		const n = ndc(c);
		return [n[0] * resolution[0], n[1] * resolution[1]];
	};
	const a = screen(selfClip);
	const b = screen(otherClip);
	const d = [b[0] - a[0], b[1] - a[1]];
	const len = Math.hypot(d[0], d[1]);
	const dir = [d[0] / len, d[1] / len];
	const normal = [-dir[1], dir[0]];
	const offClip = [
		(normal[0] * side * width * selfClip[3]) / resolution[0],
		(normal[1] * side * width * selfClip[3]) / resolution[1]
	];
	// where the corner lands, in pixels, relative to the centre line
	const moved = [selfClip[0] + offClip[0], selfClip[1] + offClip[1], selfClip[2], selfClip[3]];
	const p0 = screen(selfClip);
	const p1 = screen(moved);
	// screen() above is in half-pixels (ndc spans 2 over the full resolution), so the
	// distance in real pixels is half of it
	return Math.hypot(p1[0] - p0[0], p1[1] - p0[1]) / 2;
}

const resolution = [1600, 900];
// A horizontal segment at w = 1, then the same at w = 5 (five times further away).
for (const w of [1, 5, 40]) {
	const half = offsetPixels({
		selfClip: [0, 0, 0, w],
		otherClip: [0.5 * w, 0, 0, w],
		side: 1,
		width: 4,
		resolution
	});
	ok(`half-width is 2 px at w=${w} (depth-independent)`, Math.abs(half - 2) < 1e-9,
		`got ${half.toFixed(6)}`);
}

// ...and the aspect ratio must not stretch it. A vertical segment is offset horizontally,
// which is the axis with the *other* resolution, so a missing per-axis divide shows here.
const vertical = offsetPixels({
	selfClip: [0, 0, 0, 1],
	otherClip: [0, 0.5, 0, 1],
	side: 1,
	width: 4,
	resolution
});
ok('a vertical thread is the same width as a horizontal one',
	Math.abs(vertical - 2) < 1e-9, `got ${vertical.toFixed(6)}`);

const diagonal = offsetPixels({
	selfClip: [0, 0, 0, 1],
	otherClip: [0.4, 0.4, 0, 1],
	side: -1,
	width: 4,
	resolution
});
ok('and so is a diagonal one', Math.abs(diagonal - 2) < 1e-9, `got ${diagonal.toFixed(6)}`);

console.log('\nthe shader strings, as far as a text scan can go');

/**
 * **This is not a compiler and does not pretend to be one.** It catches exactly the class
 * of mistake that has actually cost this project a render pass: a GLSL *reserved word*
 * used as an identifier. `out` is the one that did it — the vertex shader silently failed
 * to compile, the grid vanished, and it took a pasted console log to find, because a dead
 * `ShaderMaterial` draws nothing and raises nothing. Everything else about the shader is
 * still only checked by looking at the screen.
 */
const RESERVED = [
	'out', 'in', 'inout', 'input', 'output', 'sampler', 'buffer', 'shared', 'layout',
	'filter', 'active', 'asm', 'union', 'enum', 'typedef', 'template', 'this', 'packed',
	'goto', 'switch', 'default', 'inline', 'noinline', 'public', 'static', 'extern',
	'external', 'interface', 'long', 'short', 'double', 'half', 'fixed', 'unsigned',
	'superp', 'namespace', 'using', 'row_major', 'partition', 'resource', 'sizeof', 'cast'
];

const shaders = await import('../src/lib/galaxy/shaders.ts');
const toCheck = Object.entries(shaders).filter(
	([name, v]) => typeof v === 'string' && /Shader$/.test(name)
);
ok('the shader module exports strings to check', toCheck.length > 0, `${toCheck.length} shaders`);

let reservedHits = 0;
for (const [name, src] of toCheck) {
	// Declarations only: `float out = ...`, `vec2 out;`, `void f(vec2 out)`. A reserved
	// word inside a comment or as part of a longer name is not a problem.
	const stripped = src.replace(/\/\*[\s\S]*?\*\//g, ' ').replace(/\/\/[^\n]*/g, ' ');
	for (const word of RESERVED) {
		const re = new RegExp(`\\b(?:float|int|bool|uint|vec[234]|ivec[234]|bvec[234]|mat[234]|void)\\s+${word}\\b`);
		if (re.test(stripped)) {
			reservedHits++;
			console.error(`  ${name}: declares a variable named "${word}", which is reserved in GLSL`);
		}
	}
}
ok('no shader declares a GLSL reserved word', reservedHits === 0, `${reservedHits} found`);

// Every varying a fragment shader reads has to be written by its vertex shader, or the
// program does not link — the same silent-nothing failure by a different route.
for (const stem of ['trajectoryRibbon', 'trajectoryPoints']) {
	const vs = shaders[`${stem}VertexShader`];
	const fs = shaders[`${stem}FragmentShader`];
	if (!vs || !fs) continue;
	const declared = new Set([...vs.matchAll(/varying\s+\w+\s+(\w+)\s*;/g)].map((m) => m[1]));
	const wanted = [...fs.matchAll(/varying\s+\w+\s+(\w+)\s*;/g)].map((m) => m[1]);
	const missing = wanted.filter((v) => !declared.has(v));
	ok(`${stem}: every varying the fragment reads is declared`, missing.length === 0,
		missing.join(', '));
	// ...and written, not just declared. A declared-but-unwritten varying links and
	// renders garbage, which is worse than not linking.
	const unwritten = wanted.filter((v) => !new RegExp(`\\b${v}\\s*=`).test(vs));
	ok(`${stem}: ...and assigned in the vertex shader`, unwritten.length === 0,
		unwritten.join(', '));
}

console.log(failures ? `\ntrajectory: ${failures} FAILED` : '\ntrajectory: all checks passed');
process.exit(failures ? 1 : 0);

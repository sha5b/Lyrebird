/**
 * What the two-level layout does to the *real* corpus, in the numbers that matter.
 *
 * `verify-layout.mjs` proves the pass is correct on knots whose right answer is known;
 * this says what it is worth on a shipped build, which is a different question and the
 * one to re-ask after every rebuild. Reports the tearing statistic before and after, the
 * widest split inside a single knot in box units, whether the knot extents held their
 * calibration, and how long the pass costs at load.
 *
 * Run with `npm run measure:layout`, or pass an asset root as the first argument.
 */
import fs from 'node:fs';
import path from 'node:path';
import { buildLayout } from '../src/lib/galaxy/layouts.ts';

const ROOT = process.argv[2] ?? path.join(import.meta.dirname, '..', 'static', 'lyrebird');
if (!fs.existsSync(path.join(ROOT, 'manifest.json'))) {
	console.log(`no galaxy at ${ROOT} — pass an asset root as the first argument`);
	process.exit(0);
}

const pts = JSON.parse(fs.readFileSync(`${ROOT}/points.json`, 'utf8'));
const n = pts.n;
const clusterId = pts.clusterId;
const positions = new Float32Array(fs.readFileSync(`${ROOT}/positions.f32`).buffer.slice(0));
const feat = new Float32Array(fs.readFileSync(`${ROOT}/point-features.f32`).buffer.slice(0));
const manifest = JSON.parse(fs.readFileSync(`${ROOT}/manifest.json`, 'utf8'));
const k = manifest.clusters;

const assets = {
	positions,
	pointFeatures: feat,
	pointFeatureDims: 8,
	points: { n, clusterId },
	centroids: { k, items: [] }
};

// --- tearing, the pipeline's own test, on whatever positions it is handed -------------
function twoMeans(pos, idx) {
	// deterministic 2-means, furthest-pair seeding, 12 iterations
	let a = 0,
		b = 1,
		best = -1;
	for (let t = 1; t < idx.length; t++) {
		const d = dist2(pos, idx[0], idx[t]);
		if (d > best) {
			best = d;
			b = t;
		}
	}
	best = -1;
	for (let t = 0; t < idx.length; t++) {
		const d = dist2(pos, idx[b], idx[t]);
		if (d > best) {
			best = d;
			a = t;
		}
	}
	let ca = [pos[idx[a] * 3], pos[idx[a] * 3 + 1], pos[idx[a] * 3 + 2]];
	let cb = [pos[idx[b] * 3], pos[idx[b] * 3 + 1], pos[idx[b] * 3 + 2]];
	const lab = new Uint8Array(idx.length);
	for (let it = 0; it < 12; it++) {
		for (let t = 0; t < idx.length; t++) {
			const i = idx[t];
			const da =
				(pos[i * 3] - ca[0]) ** 2 + (pos[i * 3 + 1] - ca[1]) ** 2 + (pos[i * 3 + 2] - ca[2]) ** 2;
			const db =
				(pos[i * 3] - cb[0]) ** 2 + (pos[i * 3 + 1] - cb[1]) ** 2 + (pos[i * 3 + 2] - cb[2]) ** 2;
			lab[t] = da <= db ? 0 : 1;
		}
		const s = [
			[0, 0, 0, 0],
			[0, 0, 0, 0]
		];
		for (let t = 0; t < idx.length; t++) {
			const i = idx[t];
			const r = s[lab[t]];
			r[0] += pos[i * 3];
			r[1] += pos[i * 3 + 1];
			r[2] += pos[i * 3 + 2];
			r[3]++;
		}
		if (!s[0][3] || !s[1][3]) return null;
		ca = [s[0][0] / s[0][3], s[0][1] / s[0][3], s[0][2] / s[0][3]];
		cb = [s[1][0] / s[1][3], s[1][1] / s[1][3], s[1][2] / s[1][3]];
	}
	return { lab, ca, cb };
}
const dist2 = (p, i, j) =>
	(p[i * 3] - p[j * 3]) ** 2 + (p[i * 3 + 1] - p[j * 3 + 1]) ** 2 + (p[i * 3 + 2] - p[j * 3 + 2]) ** 2;

function tearing(pos, members) {
	let measured = 0,
		torn = 0,
		severe = 0;
	const ratios = [];
	for (const idx of members) {
		if (idx.length < 12) continue;
		const r = twoMeans(pos, idx);
		if (!r) continue;
		const na = r.lab.reduce((s, v) => s + (v === 0 ? 1 : 0), 0);
		if (na < 3 || idx.length - na < 3) continue;
		const gap = Math.hypot(r.ca[0] - r.cb[0], r.ca[1] - r.cb[1], r.ca[2] - r.cb[2]);
		let sa = 0,
			sb = 0;
		for (let t = 0; t < idx.length; t++) {
			const i = idx[t];
			const c = r.lab[t] === 0 ? r.ca : r.cb;
			const d = Math.hypot(pos[i * 3] - c[0], pos[i * 3 + 1] - c[1], pos[i * 3 + 2] - c[2]);
			if (r.lab[t] === 0) sa += d;
			else sb += d;
		}
		const spread = 0.5 * (sa / na + sb / (idx.length - na));
		const ratio = gap / Math.max(spread, 1e-9);
		ratios.push(ratio);
		measured++;
		if (ratio > 5) torn++;
		if (ratio > 8) severe++;
	}
	ratios.sort((a, b) => a - b);
	return { measured, torn, severe, median: +(ratios[ratios.length >> 1] ?? 0).toFixed(3) };
}

const members = Array.from({ length: k }, () => []);
for (let i = 0; i < n; i++) if (clusterId[i] >= 0) members[clusterId[i]].push(i);

console.log('\n--- timing ------------------------------------------------------------');
let t0 = Date.now();
const off = buildLayout(assets, false);
const tOff = Date.now() - t0;
t0 = Date.now();
const on = buildLayout(assets, true);
const tOn = Date.now() - t0;
console.log(`buildLayout local=off ${tOff} ms   local=on ${tOn} ms   (local pass ${on.local.ms} ms)`);
console.log('report:', JSON.stringify(on.local));
console.log('non-finite positions:', on.positions.some((v) => !Number.isFinite(v)));

console.log('\n--- tearing -----------------------------------------------------------');
console.log('projected  :', JSON.stringify(tearing(off.positions, members)));
console.log('two-level  :', JSON.stringify(tearing(on.positions, members)));

console.log('\n--- knot extents ------------------------------------------------------');
function spreads(pos) {
	const out = [];
	for (const idx of members) {
		if (idx.length < 4) continue;
		let mx = 0,
			my = 0,
			mz = 0;
		for (const i of idx) {
			mx += pos[i * 3];
			my += pos[i * 3 + 1];
			mz += pos[i * 3 + 2];
		}
		mx /= idx.length;
		my /= idx.length;
		mz /= idx.length;
		let s = 0;
		for (const i of idx)
			s += Math.hypot(pos[i * 3] - mx, pos[i * 3 + 1] - my, pos[i * 3 + 2] - mz);
		out.push(s / idx.length);
	}
	out.sort((a, b) => a - b);
	return out;
}
const so = spreads(off.positions);
const sn = spreads(on.positions);
const q = (a, p) => +a[Math.floor(a.length * p)].toFixed(4);
console.log(`projected  median ${q(so, 0.5)}  p10 ${q(so, 0.1)}  p90 ${q(so, 0.9)}`);
console.log(`two-level  median ${q(sn, 0.5)}  p10 ${q(sn, 0.1)}  p90 ${q(sn, 0.9)}`);

console.log('\n--- the tag on nothing: centre to nearest member, in knot spreads ------');
function orphanAnchor(pos, cents) {
	const out = [];
	const abs = [];
	for (let c = 0; c < k; c++) {
		const idx = members[c];
		if (idx.length < 4) continue;
		let mx = 0, my = 0, mz = 0;
		for (const i of idx) { mx += pos[i*3]; my += pos[i*3+1]; mz += pos[i*3+2]; }
		mx /= idx.length; my /= idx.length; mz /= idx.length;
		let s = 0, near = Infinity;
		for (const i of idx) {
			s += Math.hypot(pos[i*3]-mx, pos[i*3+1]-my, pos[i*3+2]-mz);
			const dd = Math.hypot(pos[i*3]-cents[c*3], pos[i*3+1]-cents[c*3+1], pos[i*3+2]-cents[c*3+2]);
			if (dd < near) near = dd;
		}
		const spread = s / idx.length;
		abs.push(near);
		out.push(spread > 1e-9 ? near / spread : 0);
	}
	out.sort((a,b)=>a-b); abs.sort((a,b)=>a-b);
	return { rel: out, abs };
}
{
	const a = orphanAnchor(off.positions, off.centroids);
	const b = orphanAnchor(on.positions, on.centroids);
	console.log(`projected  median ${q(a.rel,0.5)}  p90 ${q(a.rel,0.9)}  p99 ${q(a.rel,0.99)}  max ${a.rel[a.rel.length-1].toFixed(3)}  (worst in box units ${a.abs[a.abs.length-1].toFixed(3)})`);
	console.log(`two-level  median ${q(b.rel,0.5)}  p90 ${q(b.rel,0.9)}  p99 ${q(b.rel,0.99)}  max ${b.rel[b.rel.length-1].toFixed(3)}  (worst in box units ${b.abs[b.abs.length-1].toFixed(3)})`);
}

console.log('\n--- widest split inside one knot, in box units ------------------------');
function gaps(pos) {
	const out = [];
	for (const idx of members) {
		if (idx.length < 12) continue;
		const r = twoMeans(pos, idx);
		if (!r) continue;
		out.push(Math.hypot(r.ca[0]-r.cb[0], r.ca[1]-r.cb[1], r.ca[2]-r.cb[2]));
	}
	out.sort((a,b)=>a-b);
	return out;
}
{
	const a = gaps(off.positions), b = gaps(on.positions);
	console.log(`projected  median ${q(a,0.5)}  p99 ${q(a,0.99)}  max ${a[a.length-1].toFixed(3)}   over ${a.filter(v=>v>0.5).length} knots split wider than 0.5 box units`);
	console.log(`two-level  median ${q(b,0.5)}  p99 ${q(b,0.99)}  max ${b[b.length-1].toFixed(3)}   over ${b.filter(v=>v>0.5).length} knots split wider than 0.5 box units`);
}

console.log('\n--- how far a knot moved ----------------------------------------------');
const moved = [];
for (let c = 0; c < k; c++) {
	if (!members[c].length) continue;
	moved.push(
		Math.hypot(
			off.centroids[c * 3] - on.centroids[c * 3],
			off.centroids[c * 3 + 1] - on.centroids[c * 3 + 1],
			off.centroids[c * 3 + 2] - on.centroids[c * 3 + 2]
		)
	);
}
moved.sort((a, b) => a - b);
console.log(`centre shift median ${q(moved, 0.5)}  p90 ${q(moved, 0.9)}  max ${moved[moved.length - 1].toFixed(4)}`);

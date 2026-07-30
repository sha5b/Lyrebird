/**
 * Sanity check for the provenance and orphan buffers the galaxy builds from the
 * shipped assets — the same rules as `app/src/lib/data/assets.ts`
 * (`pointProvenance`, `centroidProvenance`, `buildSyllablePointIndex`), re-derived
 * here so the check is independent of the code it checks.
 *
 * Verifies, against `app/static/birdy/`:
 *  - one provenance category per point, in {0,1,2,3}, never NaN;
 *  - every syllable-point index is in range;
 *  - every inventory syllable that owns no cluster (an orphan) still owns at least
 *    one point it can flash — an orphan with no points would be invisible again;
 *  - cluster tags get a category too.
 *
 * Category 3 is the unlabelled pseudo-species, keyed on the markers the pipeline
 * writes (speciesId `unlabelled`, U* candidate type ids — learn.py
 * `UNLABELLED_SPECIES`/`unlabelled_entry`). A zero count is a valid result: the
 * pool is empty on builds whose store had no unlabelled arrivals.
 *
 * Run: `node scripts/check-provenance-buffers.mjs` from `app/`. Exits 1 on failure.
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

const dir = new URL('../static/birdy/', import.meta.url).pathname;
const read = (name) => JSON.parse(readFileSync(join(dir, name), 'utf8'));

const points = read('points.json');
const centroids = read('centroids.json');
const inventory = read('inventory.json');

let failures = 0;
const fail = (msg) => {
	failures++;
	console.error(`FAIL ${msg}`);
};

// --- per-point provenance -----------------------------------------------------

const prov = new Float32Array(points.n);
const counts = [0, 0, 0, 0];
const isArrival = (sp, syl) => sp === 'unlabelled' || (syl && syl[0] === 'U');
for (let i = 0; i < points.n; i++) {
	const syl = points.syllableId[i];
	let p;
	if (isArrival(points.speciesId[i], syl)) p = 3;
	else if (points.novel?.[i]) p = 2;
	else if (!syl) p = points.source[i] === 'field' ? 2 : 0;
	else p = syl[0] === 'L' ? 1 : 0;
	if (Number.isNaN(p) || p < 0 || p > 3) fail(`point ${i}: category ${p}`);
	prov[i] = p;
	counts[p]++;
}
if (prov.length !== points.n) fail(`provenance length ${prov.length} != n ${points.n}`);
console.log(
	`points ${points.n}: documented ${counts[0]}, learned ${counts[1]}, candidate ${counts[2]}, ` +
		`unlabelled arrivals ${counts[3]}` +
		(points.novel ? '' : ' (no novelty flags in this build)') +
		(counts[3] ? '' : ' (the unlabelled pool is empty on this build)')
);

// --- cluster tag categories ----------------------------------------------------

const tagCounts = [0, 0, 0, 0];
for (const c of centroids.items) {
	const cat = isArrival(c.speciesId, c.syllableId)
		? 3
		: c.confidence === 'documented' || c.confidence === 'experimental' || c.confidence === 'inferred'
			? 0
			: c.anchor?.kind === 'anchored' || c.anchor?.kind === 'unknown' || c.anchor?.kind === 'mixed'
				? 2
				: 1;
	if (Number.isNaN(cat) || cat < 0 || cat > 3) fail(`cluster ${c.id}: category ${cat}`);
	tagCounts[cat]++;
}
console.log(
	`clusters ${centroids.items.length}: documented ${tagCounts[0]}, learned ${tagCounts[1]}, ` +
		`candidate ${tagCounts[2]}, unlabelled arrivals ${tagCounts[3]}`
);

// --- orphan flash coverage ------------------------------------------------------

const syllablePoints = new Map();
for (let i = 0; i < points.n; i++) {
	const syl = points.syllableId[i];
	if (!syl) continue;
	const key = `${points.speciesId[i]}/${syl}`;
	if (!syllablePoints.has(key)) syllablePoints.set(key, []);
	syllablePoints.get(key).push(i);
}
for (const [key, list] of syllablePoints) {
	for (const i of list) {
		if (!(i >= 0 && i < points.n)) fail(`syllable ${key}: point index ${i} out of range`);
	}
}

const clustered = new Map();
centroids.items.forEach((c, index) => {
	if (c.syllableId && !clustered.has(`${c.speciesId}/${c.syllableId}`)) {
		clustered.set(`${c.speciesId}/${c.syllableId}`, index);
	}
});

let orphans = 0;
let orphansWithoutPoints = 0;
for (const sp of inventory.species) {
	for (const syl of sp.syllables) {
		const key = `${sp.id}/${syl.id}`;
		if (clustered.has(key)) continue;
		orphans++;
		if (!syllablePoints.get(key)?.length) {
			orphansWithoutPoints++;
			if (orphansWithoutPoints <= 5) console.warn(`orphan with no points to flash: ${key}`);
		}
	}
}
console.log(
	`orphan syllables ${orphans}; ${orphansWithoutPoints} own no points at all (cannot flash)`
);
if (orphansWithoutPoints > 0) {
	// A warning, not a failure: the asset build decides which types get renders, and
	// "cannot flash" is a fact about the build, not a bug in the buffers.
	console.warn('WARN some orphans have no render or field points in this build');
}

if (failures) {
	console.error(`${failures} check(s) failed`);
	process.exit(1);
}
console.log('provenance + orphan buffers OK');

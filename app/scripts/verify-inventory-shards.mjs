/**
 * Verifies the per-species inventory shards against the whole-file checkpoint.
 *
 * The build writes `inventory.json` (canonical, untouched) plus `inventory/<id>.json`
 * per species and a tiny `inventory/index.json` — the app's lazy view. This script:
 *
 *  1. builds a fake two-species inventory in /tmp (syllables, songs, grammar with
 *     chunks/songTypes/gaps, refs/banks — the full entry shape),
 *  2. runs the pipeline's real shard writer on it (`galaxy._write_inventory_shards`,
 *     via `uv run python` in pipeline/),
 *  3. asserts every shard is semantically identical to its whole-file entry, that the
 *     index matches (header + per-species rows, order preserved), and that a re-run
 *     deletes the shard of a species the inventory no longer holds,
 *  4. serves the result over HTTP and replays the app's loading contract: shards
 *     present → index + one shard, no whole file; shards absent → index 404s once and
 *     the whole file loads instead.
 *
 * Everything lands in /tmp/birdy-shards-verify; app/static/birdy is never touched.
 * Run from the repo root: `node app/scripts/verify-inventory-shards.mjs`.
 */
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { createServer } from 'node:http';
import { mkdtempSync, readFileSync, rmSync, writeFileSync, existsSync } from 'node:fs';
import { readdir } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const REPO = new URL('../../', import.meta.url).pathname;

function fakeSpecies(id, common, bank) {
	return {
		id,
		common,
		scientific: `${common} us`,
		bank,
		summary: `Everything about the ${common}.`,
		syllables: [
			{
				id: `${id}_a`,
				label: `${common} A`,
				function: 'alarm, documented by playback',
				confidence: 'documented',
				refs: ['doe2020'],
				dur: 0.18,
				level: 0.9,
				timbre: 'pure',
				contour: [
					[0, 3200],
					[1, 2800]
				]
			},
			{
				id: `${id}_L01`,
				label: `${common} - learned L01`,
				function: '',
				confidence: 'unlabelled',
				refs: [],
				dur: 0.09,
				level: 0.7,
				timbre: 'buzz',
				contour: [
					[0, 1500],
					[0.5, 2100],
					[1, 1500]
				],
				learned: { members: 41, resynthesisCosine: 0.71 }
			}
		],
		songs: [
			{
				id: `${id}_song`,
				label: `${common} song`,
				gloss: 'a-a-L01',
				function: 'territorial advertisement',
				confidence: 'inferred',
				refs: ['doe2020'],
				sequence: [`${id}_a`, `${id}_a`, `${id}_L01`],
				gaps: [0.06, 0.12]
			}
		],
		grammar: {
			start: [`${id}_a`],
			transitions: { [`${id}_a`]: { [`${id}_L01`]: 0.7, end: 0.3 }, [`${id}_L01`]: { end: 1 } },
			chunks: [{ sequence: [`${id}_a`, `${id}_L01`], count: 9, species: [id], pmi: 3.1 }],
			songTypes: [{ id: 'T1', sequence: [`${id}_a`, `${id}_L01`], count: 9, share: 0.6 }],
			songTyping: {
				bouts: 15,
				short: 1,
				candidates: 14,
				types: 1,
				inTypes: 9,
				unplaced: 5,
				minClusterSize: 3
			}
		}
	};
}

const inventory = {
	version: 7,
	note: 'fake two-species inventory for shard verification',
	refs: { doe2020: 'Doe, J. (2020). Fake birds and how to hear them.' },
	banks: { XC: 'xeno-canto', INAT: 'iNaturalist' },
	species: [fakeSpecies('aves_alpha', 'alpha finch', 'XC'), fakeSpecies('aves_beta', 'beta owl', 'INAT')]
};

const work = mkdtempSync(join(tmpdir(), 'birdy-shards-verify-'));
const outDir = join(work, 'out');
const inventoryPath = join(work, 'inventory.json');
writeFileSync(inventoryPath, JSON.stringify(inventory, null, 1));

// The writer under test, exactly as build_galaxy calls it: whole-file copy + shards.
function runWriter(inv) {
	const invJson = join(work, 'inv-current.json');
	writeFileSync(invJson, JSON.stringify(inv));
	execFileSync(
		'uv',
		[
			'run',
			'python',
			'-c',
			'import json, shutil, sys; from pathlib import Path; ' +
				'from birdy_pipeline.galaxy import _write_inventory_shards; ' +
				'out, src = Path(sys.argv[1]), Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True); ' +
				'shutil.copyfile(src, out / "inventory.json"); ' +
				'_write_inventory_shards(out, json.loads(src.read_text(encoding="utf-8")))',
			outDir,
			invJson
		],
		{ cwd: join(REPO, 'pipeline'), stdio: 'pipe' }
	);
}
const readJson = (p) => JSON.parse(readFileSync(p, 'utf8'));

runWriter(inventory);

// --- 1. shards are the whole-file entries, semantically byte-for-byte ----------------
const whole = readJson(join(outDir, 'inventory.json'));
assert.deepStrictEqual(whole, inventory, 'whole-file copy is the inventory itself');
for (const sp of inventory.species) {
	const shard = readJson(join(outDir, 'inventory', `${sp.id}.json`));
	assert.deepStrictEqual(shard, sp, `shard ${sp.id} differs from the whole-file entry`);
}

// --- 2. the index is the header + one honest row per species --------------------------
const index = readJson(join(outDir, 'inventory', 'index.json'));
assert.equal(index.version, inventory.version);
assert.equal(index.note, inventory.note);
assert.deepStrictEqual(index.refs, inventory.refs);
assert.deepStrictEqual(index.banks, inventory.banks);
assert.deepStrictEqual(
	index.species,
	inventory.species.map((sp) => ({
		id: sp.id,
		common: sp.common,
		bank: sp.bank,
		types: sp.syllables.length,
		songs: sp.songs.length
	})),
	'index rows must mirror the whole file, in order'
);

// --- 3. idempotence: a removed species loses its shard, a stranger's file too ---------
writeFileSync(join(outDir, 'inventory', 'stray_file.json'), '{}');
const smaller = { ...inventory, species: [inventory.species[0]] };
runWriter(smaller);
const remaining = (await readdir(join(outDir, 'inventory'))).sort();
assert.deepStrictEqual(remaining, ['aves_alpha.json', 'index.json'], 'stale shards must be deleted');
const index2 = readJson(join(outDir, 'inventory', 'index.json'));
assert.equal(index2.species.length, 1, 'index shrinks with the inventory');
// …and re-running with the full inventory restores the shard (same content again).
runWriter(inventory);
assert.deepStrictEqual(
	readJson(join(outDir, 'inventory', 'aves_beta.json')),
	inventory.species[1],
	're-run restores a returning species'
);

// --- 4. the app's loading contract over HTTP ------------------------------------------
function serve(dir) {
	const server = createServer((req, res) => {
		const path = join(dir, decodeURIComponent(new URL(req.url, 'http://x').pathname));
		if (!existsSync(path)) {
			res.writeHead(404).end();
			return;
		}
		res.writeHead(200, { 'content-type': 'application/json' }).end(readFileSync(path));
	});
	return new Promise((resolve) => server.listen(0, '127.0.0.1', () => resolve(server)));
}
async function getJson(port, path) {
	const res = await fetch(`http://127.0.0.1:${port}/${path}`);
	if (!res.ok) return null; // mirrors assets.ts getJson's failure path
	return res.json();
}

// Shard build: index answers, one shard answers, and the whole file was never needed.
{
	const server = await serve(outDir);
	const port = server.address().port;
	const idx = await getJson(port, 'inventory/index.json');
	assert.ok(idx, 'index.json must answer on a sharded build');
	const shard = await getJson(port, 'inventory/aves_alpha.json');
	assert.deepStrictEqual(shard, inventory.species[0], 'fetched shard is the whole-file entry');
	server.close();
}

// Pre-shard build (whole file only): the index 404s once and the whole file loads.
{
	const flat = join(work, 'flat');
	execFileSync('mkdir', ['-p', flat]);
	writeFileSync(join(flat, 'inventory.json'), JSON.stringify(inventory));
	const server = await serve(flat);
	const port = server.address().port;
	const idx = await getJson(port, 'inventory/index.json');
	assert.equal(idx, null, 'older builds have no index — the fallback trigger');
	const fallback = await getJson(port, 'inventory.json');
	assert.equal(fallback.species.length, 2, 'fallback whole file carries every species');
	assert.deepStrictEqual(fallback.species[1], inventory.species[1]);
	server.close();
}

console.log('verify-inventory-shards: all assertions passed');
console.log(`  shards == whole-file entries: ${inventory.species.length}/${inventory.species.length}`);
console.log(`  index rows match (order, counts, refs, banks): yes`);
console.log(`  stale shard cleanup: aves_beta.json + stray_file.json removed on re-run`);
console.log(`  app contract: shard mode fetches index+shard; flat build falls back to whole file`);

rmSync(work, { recursive: true, force: true });

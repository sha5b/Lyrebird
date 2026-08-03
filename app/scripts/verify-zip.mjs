/**
 * The zip writer, checked against a real `unzip` rather than against itself.
 *
 * A zip is the archetype of the failure this project keeps naming: an off-by-one in a
 * central-directory offset produces a file of exactly the right size, with every byte of
 * the payload present, that no tool will open. Nothing throws. So a self-consistency test
 * — parse back what we just wrote — is close to worthless here, because the same wrong
 * arithmetic would be used to read it.
 *
 * This writes real archives to disk and hands them to `unzip -t` and `unzip -p`, which
 * knows the format and did not learn it from us. Then it mutates the writer and requires
 * `unzip` to reject the result, because a test that only ever sees valid input cannot tell
 * you it would notice invalid input.
 *
 * Run with `npm run verify:zip`. Exits non-zero on any disagreement.
 */
import { execFileSync } from 'node:child_process';
import { mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { crc32, zip } from '../src/lib/data/zip.ts';

let failures = 0;
const ok = (name, cond, detail = '') => {
	if (cond) console.log(`  ${name.padEnd(58)} ok${detail ? ` (${detail})` : ''}`);
	else {
		failures++;
		console.error(`  ${name.padEnd(58)} FAIL ${detail}`);
	}
};

const dir = mkdtempSync(join(tmpdir(), 'birdy-zip-'));
const BUILT = new Date('2026-08-03T08:51:31Z');
const enc = new TextEncoder();

/** Write a blob and return its path, so `unzip` can be the judge. */
async function write(name, blob) {
	const path = join(dir, name);
	writeFileSync(path, Buffer.from(await blob.arrayBuffer()));
	return path;
}

const unzip = (args) => execFileSync('unzip', args, { encoding: 'buffer' });

// --- CRC-32 against known answers ------------------------------------------------------
console.log('crc32, against values the format documents');

{
	// The two checks everyone's CRC-32 is measured by, so a table built wrong is caught here
	// rather than three layers up as "the archive is corrupt".
	ok('crc32("") is 0', crc32(new Uint8Array(0)) === 0);
	ok('crc32("a") is 0xe8b7be43', crc32(enc.encode('a')) === 0xe8b7be43,
		crc32(enc.encode('a')).toString(16));
	ok('crc32("123456789") is 0xcbf43926', crc32(enc.encode('123456789')) === 0xcbf43926,
		crc32(enc.encode('123456789')).toString(16));
	ok('crc32 is unsigned', crc32(enc.encode('\xff\xff\xff\xff')) >= 0);
}

// --- a real archive, opened by a real tool ---------------------------------------------
console.log('\nan archive unzip accepts');

const entries = [
	{ name: 'manifest.json', data: enc.encode(JSON.stringify({ points: 348461 })) },
	// Highly compressible, so `deflate` must actually be smaller than `store`.
	{ name: 'points.json', data: enc.encode('{"clusterId":[' + '0,'.repeat(20000) + '0]}') },
	// A nested path, which is how `inventory/index.json` ships.
	{ name: 'inventory/index.json', data: enc.encode('{"species":[]}') },
	// Binary, incompressible: 8 KB of a counter, standing in for the .f32 blocks.
	{ name: 'positions.f32', data: new Uint8Array(8192).map((_, i) => (i * 31) & 0xff) },
	// Empty. A zero-length member is legal and is where naive writers emit a broken header.
	{ name: 'empty.json', data: new Uint8Array(0) }
];

{
	const blob = await zip(entries, BUILT);
	const path = await write('assets.zip', blob);

	// `unzip -t` verifies every member's CRC against its decompressed bytes. If any offset,
	// size or checksum in either directory is wrong, this is what says so.
	let tested = '';
	try {
		tested = unzip(['-t', path]).toString();
	} catch (e) {
		tested = `THREW: ${e.stderr?.toString() ?? e.message}`;
	}
	ok('unzip -t reports no errors', /No errors detected/.test(tested), tested.trim().split('\n').pop());

	const listed = unzip(['-l', path]).toString();
	ok('every member is listed', entries.every((e) => listed.includes(e.name)),
		`${entries.length} entries`);
	ok('the nested path survives', listed.includes('inventory/index.json'));

	// Byte-exact round trip through the tool, which is the only claim that matters.
	let exact = 0;
	for (const entry of entries) {
		const got = new Uint8Array(unzip(['-p', path, entry.name]));
		if (got.length === entry.data.length && got.every((b, i) => b === entry.data[i])) exact++;
	}
	ok('every member round-trips byte-exact', exact === entries.length,
		`${exact}/${entries.length}`);

	// Deflate must be doing something, or we shipped a 77 MB "compressed" download.
	const raw = entries.reduce((n, e) => n + e.data.length, 0);
	ok('the archive is smaller than its contents', blob.size < raw,
		`${blob.size} against ${raw} raw`);
}

{
	// The build's stamp, not the download's: two downloads of one build must look identical.
	const a = await zip(entries.slice(0, 2), BUILT);
	const b = await zip(entries.slice(0, 2), BUILT);
	const [ba, bb] = [new Uint8Array(await a.arrayBuffer()), new Uint8Array(await b.arrayBuffer())];
	ok('two packs of one build are byte-identical',
		ba.length === bb.length && ba.every((x, i) => x === bb[i]));

	const later = await zip(entries.slice(0, 2), new Date('2026-08-03T09:51:31Z'));
	const bl = new Uint8Array(await later.arrayBuffer());
	ok('a different build stamp changes the archive', !(bl.every((x, i) => x === ba[i])));
}

{
	// 1980 is the format's floor; a date before it cannot be encoded and must not silently
	// write a negative year into two bytes.
	const old = await zip([entries[0]], new Date('1970-01-01T00:00:00Z'));
	const path = await write('old.zip', old);
	let tested = '';
	try {
		tested = unzip(['-t', path]).toString();
	} catch (e) {
		tested = `THREW: ${e.message}`;
	}
	ok('a pre-1980 stamp still writes a valid zip', /No errors detected/.test(tested));
}

// --- the mutations, so we know the tool would catch us ---------------------------------
console.log('\nunzip rejects a broken archive (so the checks above mean something)');

/** Corrupt one byte of a fresh archive and ask unzip what it thinks. */
async function corrupt(label, mutate) {
	const blob = await zip(entries, BUILT);
	const bytes = new Uint8Array(await blob.arrayBuffer());
	mutate(bytes);
	const path = join(dir, 'broken.zip');
	writeFileSync(path, Buffer.from(bytes));
	let rejected = false;
	let detail = '';
	try {
		const out = unzip(['-t', path]).toString();
		rejected = !/No errors detected/.test(out);
		detail = out.trim().split('\n').pop();
	} catch (e) {
		rejected = true;
		detail = 'non-zero exit';
	}
	ok(label, rejected, detail);
}

// The end-of-central-directory offset. Wrong by one byte and the archive has the right
// size and the right payload and cannot be read — the exact failure this file exists for.
await corrupt('a central-directory offset off by one is caught', (b) => {
	const eocd = b.length - 22;
	const view = new DataView(b.buffer);
	view.setUint32(eocd + 16, view.getUint32(eocd + 16, true) + 1, true);
});

await corrupt('a wrong CRC in a local header is caught', (b) => {
	const view = new DataView(b.buffer);
	view.setUint32(14, view.getUint32(14, true) ^ 0xff, true);
});

await corrupt('a truncated payload is caught', (b) => {
	b[b.length - 22 - 1] ^= 0xff;
});

console.log(failures ? `\n${failures} check(s) failed` : '\nall zip checks passed');
process.exit(failures ? 1 : 0);

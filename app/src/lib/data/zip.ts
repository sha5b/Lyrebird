/**
 * A zip file, assembled in the browser, so the whole build can leave as one download.
 *
 * Hand-rolled rather than a dependency, and the reason is small: a zip with no encryption,
 * no zip64 and known sizes is about sixty lines of header writing, and `CompressionStream`
 * has done the only hard part since Safari 16.4. A library for this would be more bytes
 * shipped to every visitor than the format costs to write.
 *
 * **Sizes are known before anything is written**, because each entry is compressed in full
 * first. That is what lets this emit ordinary local headers instead of the streaming
 * variant with data descriptors, and a plain zip is the one every tool opens.
 *
 * No zip64: it would be needed past 4 GB or 65 535 entries, and this packs eleven files
 * totalling about 77 MB. If a build ever outgrows that, the guard in `zip()` says so rather
 * than writing a file that unpacks wrong.
 */

/** The CRC-32 table, built once. Every zip entry carries this checksum of its raw bytes. */
const CRC_TABLE = (() => {
	const table = new Uint32Array(256);
	for (let i = 0; i < 256; i++) {
		let c = i;
		for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
		table[i] = c >>> 0;
	}
	return table;
})();

export function crc32(data: Uint8Array): number {
	let c = 0xffffffff;
	for (let i = 0; i < data.length; i++) c = CRC_TABLE[(c ^ data[i]) & 0xff] ^ (c >>> 8);
	return (c ^ 0xffffffff) >>> 0;
}

/** Deflate, or `null` where the browser has no `deflate-raw`, which means store instead. */
async function deflateRaw(data: Uint8Array): Promise<Uint8Array | null> {
	if (typeof CompressionStream === 'undefined') return null;
	try {
		const stream = new Blob([data as BlobPart]).stream().pipeThrough(
			new CompressionStream('deflate-raw')
		);
		return new Uint8Array(await new Response(stream).arrayBuffer());
	} catch {
		// An engine that has CompressionStream but not the raw variant. Storing is correct
		// and the only cost is size, so this must not fail the whole download.
		return null;
	}
}

/**
 * MS-DOS date and time, which is the only stamp the base format carries.
 *
 * Two-second resolution and no zone, so this is deliberately the *build's* time rather
 * than the download's: the archive describes a galaxy that was built once, and stamping it
 * "now" would make two downloads of one build look like two different things.
 */
function dosStamp(when: Date): { time: number; date: number } {
	const year = when.getFullYear();
	if (year < 1980) return { time: 0, date: 33 }; // 1980-01-01, the format's floor
	return {
		time: (when.getHours() << 11) | (when.getMinutes() << 5) | (when.getSeconds() >> 1),
		date: ((year - 1980) << 9) | ((when.getMonth() + 1) << 5) | when.getDate()
	};
}

export interface ZipEntry {
	/** Path inside the archive. Forward slashes, as the format requires. */
	name: string;
	data: Uint8Array;
}

const LOCAL_HEADER = 30;
const CENTRAL_HEADER = 46;
const EOCD = 22;
const MAX_U32 = 0xffffffff;

/**
 * Pack `entries` into one zip. `when` stamps every member — pass the build's own time.
 *
 * `onProgress` is called with the number of entries finished, because compressing 77 MB
 * takes long enough that a silent button reads as a broken one.
 */
export async function zip(
	entries: ZipEntry[],
	when: Date,
	onProgress?: (done: number, total: number) => void
): Promise<Blob> {
	if (entries.length > 0xffff) {
		throw new Error(`${entries.length} entries needs zip64; this writer emits plain zip`);
	}
	const stamp = dosStamp(when);
	const encoder = new TextEncoder();
	// Bit 11 declares the name is UTF-8, which is what `TextEncoder` emits. Set on every
	// entry rather than only the non-ASCII ones: ASCII *is* UTF-8, so the flag is accurate
	// either way, and a conditional here would be a branch that only ever tested itself.
	const FLAG_UTF8 = 0x800;

	const packed = [];
	for (const entry of entries) {
		const name = encoder.encode(entry.name);
		const deflated = await deflateRaw(entry.data);
		const body = deflated ?? entry.data;
		packed.push({
			name,
			body,
			method: deflated ? 8 : 0,
			crc: crc32(entry.data),
			raw: entry.data.length
		});
		onProgress?.(packed.length, entries.length);
	}

	const total =
		packed.reduce((n, p) => n + LOCAL_HEADER + p.name.length + p.body.length, 0) +
		packed.reduce((n, p) => n + CENTRAL_HEADER + p.name.length, 0) +
		EOCD;
	if (total > MAX_U32) {
		throw new Error(`${total} bytes needs zip64; this writer emits plain zip`);
	}

	const out = new Uint8Array(total);
	const view = new DataView(out.buffer);
	let at = 0;
	const offsets: number[] = [];

	for (const p of packed) {
		offsets.push(at);
		view.setUint32(at, 0x04034b50, true);
		view.setUint16(at + 4, 20, true);
		view.setUint16(at + 6, FLAG_UTF8, true);
		view.setUint16(at + 8, p.method, true);
		view.setUint16(at + 10, stamp.time, true);
		view.setUint16(at + 12, stamp.date, true);
		view.setUint32(at + 14, p.crc, true);
		view.setUint32(at + 18, p.body.length, true);
		view.setUint32(at + 22, p.raw, true);
		view.setUint16(at + 26, p.name.length, true);
		view.setUint16(at + 28, 0, true);
		at += LOCAL_HEADER;
		out.set(p.name, at);
		at += p.name.length;
		out.set(p.body, at);
		at += p.body.length;
	}

	const centralAt = at;
	for (let i = 0; i < packed.length; i++) {
		const p = packed[i];
		view.setUint32(at, 0x02014b50, true);
		view.setUint16(at + 4, 20, true);
		view.setUint16(at + 6, 20, true);
		view.setUint16(at + 8, FLAG_UTF8, true);
		view.setUint16(at + 10, p.method, true);
		view.setUint16(at + 12, stamp.time, true);
		view.setUint16(at + 14, stamp.date, true);
		view.setUint32(at + 16, p.crc, true);
		view.setUint32(at + 20, p.body.length, true);
		view.setUint32(at + 24, p.raw, true);
		view.setUint16(at + 28, p.name.length, true);
		view.setUint16(at + 30, 0, true);
		view.setUint16(at + 32, 0, true);
		view.setUint16(at + 34, 0, true);
		view.setUint16(at + 36, 0, true);
		view.setUint32(at + 38, 0, true);
		view.setUint32(at + 42, offsets[i], true);
		at += CENTRAL_HEADER;
		out.set(p.name, at);
		at += p.name.length;
	}

	view.setUint32(at, 0x06054b50, true);
	view.setUint16(at + 4, 0, true);
	view.setUint16(at + 6, 0, true);
	view.setUint16(at + 8, packed.length, true);
	view.setUint16(at + 10, packed.length, true);
	view.setUint32(at + 12, at - centralAt, true);
	view.setUint32(at + 16, centralAt, true);
	view.setUint16(at + 20, 0, true);

	return new Blob([out as BlobPart], { type: 'application/zip' });
}

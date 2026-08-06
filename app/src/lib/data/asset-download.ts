/**
 * The whole loaded build, packed into one zip the reader can keep.
 *
 * The info page's job is to say what this app does and does not claim, and every figure on
 * it is read from the build's own manifest. This is the end of that argument: the reader can
 * take the build away and check any of it. Nothing here is a summary or an export format —
 * it is the same bytes the browser loaded.
 *
 * **The file list comes from `manifest.files`**, which is the pipeline's own record of what
 * it wrote. A list kept here instead would drift the first time the pipeline wrote a twelfth
 * file, and the download would then quietly be a subset of the build while still calling
 * itself the build.
 *
 * `relations.json` is deliberately absent, because it is absent from `manifest.files`: it is
 * a sidecar the app reads three pairs of at a time, not part of the build's contract. One
 * production build wrote 760 MB of it.
 */

import { assetUrl } from './assets';
import type { GalaxyMap } from './assets';
import type { LyrebirdAssets } from './types';
import { zip, type ZipEntry } from './zip';

export interface PackProgress {
	/** `fetch` while files are coming down, `pack` while they are being compressed. */
	phase: 'fetch' | 'pack';
	done: number;
	total: number;
	/** The file in hand, for a caller that wants to name it. */
	name: string;
}

/** What a packed build is called: the stamp, so two downloads are never confused. */
export function buildFileName(builtAt: string): string {
	const day = /^\d{4}-\d{2}-\d{2}/.exec(builtAt)?.[0] ?? 'unknown';
	return `lyrebird-build-${day}.zip`;
}

/**
 * Fetch every file of the loaded build and return it as one zip.
 *
 * `mapDir` is the sub-build prefix of a `--clustering both` root, exactly as the loader uses
 * it — `''` for the ordinary single-map build. Passed in rather than guessed, because
 * packing the root's files while the reader is looking at `unknown/` would hand them a
 * different galaxy from the one on screen.
 *
 * Every request carries the manifest's `builtAt` as its cache-buster, which is the same rule
 * the loader follows and for the same reason: a cached `points.json` beside a fresh
 * `positions.f32` is a galaxy whose metadata describes someone else's points. Here it also
 * means the archive cannot be assembled from two builds.
 */
export async function packBuild(
	assets: LyrebirdAssets,
	mapDir: '' | GalaxyMap,
	fetcher: typeof fetch = fetch,
	onProgress?: (p: PackProgress) => void
): Promise<{ name: string; blob: Blob; bytes: number }> {
	const files = assets.manifest.files;
	if (!files?.length) {
		throw new Error('this build’s manifest lists no files, so there is nothing to pack');
	}
	const bust = assets.manifest.builtAt ?? '';
	const prefix = mapDir ? `${mapDir}/` : '';

	const entries: ZipEntry[] = [];
	let raw = 0;
	for (const path of files) {
		onProgress?.({ phase: 'fetch', done: entries.length, total: files.length, name: path });
		const res = await fetcher(assetUrl(`${prefix}${path}`, bust));
		if (!res.ok) throw new Error(`${path} answered ${res.status}`);
		const data = new Uint8Array(await res.arrayBuffer());
		raw += data.length;
		// Stored under the path the manifest names, so an unpacked archive is an asset root
		// the pipeline's own `verify` can be pointed at.
		entries.push({ name: path, data });
	}

	const blob = await zip(entries, new Date(bust), (done, total) =>
		onProgress?.({ phase: 'pack', done, total, name: files[done - 1] ?? '' })
	);
	return { name: buildFileName(bust), blob, bytes: raw };
}

/** Hand a blob to the browser as a download, then let go of the object URL. */
export function saveBlob(blob: Blob, name: string): void {
	const url = URL.createObjectURL(blob);
	const a = document.createElement('a');
	a.href = url;
	a.download = name;
	a.click();
	// Revoked on the next turn of the loop rather than immediately: the click is handled
	// asynchronously, and revoking in the same tick cancels the download in some browsers.
	setTimeout(() => URL.revokeObjectURL(url), 0);
}

/**
 * The per-cluster float arrays, which live beside `centroids.json` rather than inside it.
 *
 * `vector32`, `vector` and `featuresLo` were **64 % of centroids.json's bytes** (744 of
 * 1 159 per cluster, measured), and the file is fetched and parsed whole before the first
 * frame. At the production corpus's cluster count that is a 44 MB parse; as a binary
 * sidecar it is about 8 MB that never goes through `JSON.parse`. The pipeline writes
 * `centroid-vectors.f32` and describes its layout in centroids.json's own `vectors`
 * block, so nothing here has to know the field order in advance.
 *
 * The views handed back are **subarrays of one buffer**, not copies: attaching them to the
 * items costs nothing beyond the fetch, and every existing consumer keeps reading
 * `c.vector32` / `c.vector` / `c.featuresLo` as before.
 *
 * An asset set built before 2026-08-01 has no `vectors` block and carries the arrays
 * inline. That still loads — `hydrateCentroids` is a no-op on it.
 */
import type { Centroids } from './types';

/** How `centroids.json` describes its sidecar. */
export interface CentroidVectorBlock {
	file: string;
	order: string[];
	dims: Record<string, number>;
	rowFloats: number;
}

/**
 * Attach the sidecar's rows to `centroids.items`, in place.
 *
 * Returns whether the vectors are usable afterwards. A missing, short or unreadable
 * sidecar leaves the items without vectors and returns false rather than throwing: the
 * caller decides what a galaxy with no matcher vectors should do, and every current
 * caller already has a path for centroids whose vectors do not fit the space
 * (`SpectralMatcher` falls back, `ActivationTracker` drops to per-cluster response).
 */
export async function hydrateCentroids(
	centroids: Centroids,
	fetcher: typeof fetch,
	url: (file: string) => string
): Promise<boolean> {
	const block = centroids.vectors;
	if (!block) return centroids.items.some((c) => c.vector?.length || c.vector32?.length);
	const expected = centroids.k * block.rowFloats;
	let data: Float32Array;
	try {
		const res = await fetcher(url(block.file));
		if (!res.ok) return false;
		data = new Float32Array(await res.arrayBuffer());
	} catch {
		return false;
	}
	if (data.length !== expected) {
		console.warn(
			`${block.file} holds ${data.length} floats, centroids.json declares ` +
				`${centroids.k} x ${block.rowFloats} = ${expected}; ignoring it`
		);
		return false;
	}
	attach(centroids, block, data);
	return true;
}

/** The in-place half, shared with the node scripts, which read the file themselves. */
export function attach(
	centroids: Centroids,
	block: CentroidVectorBlock,
	data: Float32Array
): void {
	for (let i = 0; i < centroids.k; i++) {
		const item = centroids.items[i];
		if (!item) continue;
		let at = i * block.rowFloats;
		for (const name of block.order) {
			const width = block.dims[name] ?? 0;
			// A view, not a copy — one buffer backs every cluster's vectors.
			(item as unknown as Record<string, Float32Array>)[name] = data.subarray(at, at + width);
			at += width;
		}
	}
}

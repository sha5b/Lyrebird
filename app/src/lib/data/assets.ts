import { base } from '$app/paths';
import type { BirdyAssets, Centroids, EmbeddingSpace, FeatureSpace, Inventory, Manifest, PointCloudMeta, Species, SyrinxCalibration } from './types';

const ROOT = 'birdy';

export class AssetsMissingError extends Error {
	constructor(readonly file: string) {
		super(
			`Missing generated asset "${file}". Build it first:\n` +
				`  cd pipeline && uv sync && uv run birdy-pipeline build`
		);
		this.name = 'AssetsMissingError';
	}
}

/** Shape the pipeline may also use: the extractor spec nested for readability. */
interface NestedFeatureSpace {
	dims: number;
	dimNames: string[];
	mean: number[];
	std: number[];
	temperature?: number;
	embedding?: EmbeddingSpace;
	extractor?: {
		sampleRate?: number;
		frame?: number;
		hop?: number;
		window?: string;
		mel?: { bands?: number };
		mfcc?: { count?: number };
	};
	activation?: { softmaxTemperature?: number };
}

/**
 * Accepts either the flat schema of the contract or the nested `extractor` form, so a
 * documentation-shaped rewrite of the generated file cannot silently break the client.
 */
function normaliseFeatureSpace(raw: FeatureSpace & NestedFeatureSpace): FeatureSpace {
	const e = raw.extractor ?? {};
	const space: FeatureSpace = {
		sampleRate: raw.sampleRate ?? e.sampleRate ?? 48000,
		frameSize: raw.frameSize ?? e.frame ?? 1024,
		hopSize: raw.hopSize ?? e.hop ?? 512,
		window: raw.window ?? e.window ?? 'symmetric hann',
		melBands: raw.melBands ?? e.mel?.bands ?? 26,
		mfccCoeffs: raw.mfccCoeffs ?? e.mfcc?.count ?? 13,
		dims: raw.dims,
		dimNames: raw.dimNames,
		mean: raw.mean,
		std: raw.std,
		temperature: raw.temperature ?? raw.activation?.softmaxTemperature ?? 0.12
	};
	// The learned-space block is passed through as shipped: it is optional (descriptor
	// builds predate it) and self-gating (`mapQuality.accepted`), so there is nothing to
	// normalise, only something to not lose. A linear map must carry its weights inline;
	// an rff-ridge map declares them in a sidecar that loadAssets fetches next.
	const embedding = raw.embedding;
	const map = embedding?.map;
	const hasMap = Boolean(
		map && ('w' in map ? map.w?.length : map.kind === 'rff-ridge' && map.D > 0)
	);
	if (embedding && embedding.dims > 0 && hasMap) {
		space.embedding = embedding;
	}
	if (!(space.frameSize > 0) || (space.frameSize & (space.frameSize - 1)) !== 0) {
		throw new Error(`feature-space.json has an unusable frame size: ${space.frameSize}`);
	}
	if (space.mean.length !== space.dims || space.std.length !== space.dims) {
		throw new Error(
			`feature-space.json declares ${space.dims} dims but ships ${space.mean.length} means`
		);
	}
	return space;
}

/**
 * `bust` is appended as a query string so a rebuild can be picked up without a reload.
 * The files are written in place by the pipeline and every one of them has to come from
 * the *same* build — a cached `points.json` beside a fresh `positions.f32` is a galaxy
 * whose metadata describes someone else's points.
 */
function assetUrl(path: string, bust: string): string {
	return `${base}/${ROOT}/${path}${bust ? `?v=${encodeURIComponent(bust)}` : ''}`;
}

async function getJson<T>(path: string, fetcher: typeof fetch, bust = ''): Promise<T> {
	const res = await fetcher(assetUrl(path, bust));
	if (!res.ok) throw new AssetsMissingError(path);
	return (await res.json()) as T;
}

/**
 * Loads the generated galaxy + inventory. The pipeline is the only writer of these
 * files, so a missing one means the offline stage has not been run yet.
 */
export async function loadAssets(
	fetcher: typeof fetch = fetch,
	bust = ''
): Promise<BirdyAssets> {
	const manifest = await getJson<Manifest>('manifest.json', fetcher, bust);
	// Everything after the manifest is fetched under that build's own stamp, so a reload
	// triggered by a rebuild cannot mix two builds together.
	const stamp = bust || manifest.builtAt || '';
	const [inventory, rawFeatureSpace, points, centroids] = await Promise.all([
		getJson<Inventory>('inventory.json', fetcher, stamp),
		getJson<FeatureSpace & NestedFeatureSpace>('feature-space.json', fetcher, stamp),
		getJson<PointCloudMeta>('points.json', fetcher, stamp),
		getJson<Centroids>('centroids.json', fetcher, stamp)
	]);
	const featureSpace = normaliseFeatureSpace(rawFeatureSpace);

	// The rff-ridge map's weights ship in a binary sidecar (123 k floats are nobody's
	// JSON). Fetched under the same build stamp, checked against the declared layout,
	// and treated as absent on any mismatch — a wrong map is worse than no map, because
	// the 28-d fallback is honest and a mismatched one lights the wrong knots.
	const embMap = featureSpace.embedding?.map;
	if (embMap && 'kind' in embMap && embMap.kind === 'rff-ridge' && !embMap.rff) {
		try {
			const res = await fetcher(assetUrl(embMap.file, stamp));
			if (!res.ok) throw new Error(embMap.file);
			const raw = new Float32Array(await res.arrayBuffer());
			const D = embMap.D;
			const dims = featureSpace.embedding?.dims ?? 0;
			const want = 28 * D + D + D * dims + dims;
			if (raw.length !== want || dims <= 0) {
				throw new Error(`${embMap.file} holds ${raw.length} floats, expected ${want}`);
			}
			embMap.rff = {
				R: raw.subarray(0, 28 * D),
				phase: raw.subarray(28 * D, 28 * D + D),
				w: raw.subarray(28 * D + D, 28 * D + D + D * dims),
				b: raw.subarray(28 * D + D + D * dims, want)
			};
		} catch {
			delete featureSpace.embedding;
		}
	}

	// The calibration table only refines the synth; the analytic fallback covers its absence.
	let calibration: SyrinxCalibration | null = null;
	try {
		calibration = await getJson<SyrinxCalibration>('syrinx-calibration.json', fetcher, stamp);
	} catch {
		calibration = null;
	}

	const posRes = await fetcher(assetUrl('positions.f32', stamp));
	if (!posRes.ok) throw new AssetsMissingError('positions.f32');
	const positions = new Float32Array(await posRes.arrayBuffer());

	if (positions.length !== points.n * 3) {
		throw new Error(
			`positions.f32 holds ${positions.length / 3} points but points.json declares ${points.n}`
		);
	}

	const { pointFeatures, pointFeatureDims } = await loadPointFeatures(
		points.n,
		centroids,
		fetcher,
		stamp
	);

	return {
		manifest,
		inventory,
		calibration,
		featureSpace,
		positions,
		points,
		centroids,
		pointFeatures,
		pointFeatureDims
	};
}

/**
 * The per-point response space, if the pipeline wrote one.
 *
 * Optional on purpose: an asset set built before this existed still renders, it just
 * falls back to lighting whole clusters. A file that is present but inconsistent with
 * `points.json` or with the centroids is treated as absent rather than trusted, because
 * a mismatched projection would light the wrong points with total confidence.
 */
async function loadPointFeatures(
	n: number,
	centroids: Centroids,
	fetcher: typeof fetch,
	bust = ''
): Promise<{ pointFeatures: Float32Array | null; pointFeatureDims: number }> {
	const dims = centroids.items[0]?.featuresLo?.length ?? 0;
	if (!dims) return { pointFeatures: null, pointFeatureDims: 0 };
	try {
		const res = await fetcher(assetUrl('point-features.f32', bust));
		if (!res.ok) return { pointFeatures: null, pointFeatureDims: 0 };
		const data = new Float32Array(await res.arrayBuffer());
		if (data.length !== n * dims) {
			console.warn(
				`point-features.f32 holds ${data.length / dims} rows but points.json declares ${n}; ` +
					'falling back to per-cluster response'
			);
			return { pointFeatures: null, pointFeatureDims: 0 };
		}
		return { pointFeatures: data, pointFeatureDims: dims };
	} catch {
		return { pointFeatures: null, pointFeatureDims: 0 };
	}
}

/**
 * Stable species -> index map for the renderer, so a point can be dimmed when another
 * species is selected. The inventory sets the order; species that appear only in the
 * point cloud (harvested field recordings of something not in the inventory) are
 * appended, so no point is left without an index.
 */
export function buildSpeciesIndex(assets: BirdyAssets): Map<string, number> {
	const index = new Map<string, number>();
	assets.inventory.species.forEach((s) => index.set(s.id, index.size));
	for (const id of assets.points.speciesId) {
		if (!index.has(id)) index.set(id, index.size);
	}
	return index;
}

export function speciesById(inventory: Inventory, id: string): Species | undefined {
	return inventory.species.find((s) => s.id === id);
}

export function syllableById(species: Species, id: string) {
	return species.syllables.find((s) => s.id === id);
}

/** Resolves a song's syllable ids into the syllables themselves, dropping unknown ids. */
export function songSyllables(species: Species, songId: string) {
	const song = species.songs.find((s) => s.id === songId);
	if (!song) return null;
	const syllables = song.sequence
		.map((id) => syllableById(species, id))
		.filter((s): s is NonNullable<typeof s> => Boolean(s));
	return { song, syllables };
}

export function formatRefs(inventory: Inventory, refs: string[]): string[] {
	return refs.map((r) => inventory.refs[r] ?? r);
}

/**
 * Which galaxy cluster a syllable belongs to. Built once, because a phrase has to be
 * turned into a path through the cloud on every selection.
 */
export interface ClusterLookup {
	bySyllable: Map<string, number>;
}

export function buildClusterLookup(centroids: Centroids): ClusterLookup {
	const bySyllable = new Map<string, number>();
	centroids.items.forEach((item, index) => {
		if (item.syllableId && !bySyllable.has(`${item.speciesId}/${item.syllableId}`)) {
			bySyllable.set(`${item.speciesId}/${item.syllableId}`, index);
		}
	});
	return { bySyllable };
}

/**
 * Where a syllable sits in the galaxy, or -1 if it does not sit anywhere.
 *
 * **It used to fall back to "any cluster of the same species", and that was a placement
 * claim the corpus could not support.** Clustering is fitted over the whole point cloud
 * and a syllable only wins a cluster if enough of its renders land together; on the
 * shipped build 83 of the inventory's 176 syllables do not, so nearly half of them were
 * being resolved by that fallback. It returned `bySpecies`, which is the *first* cluster
 * of that bird in file order — an arbitrary knot, the same one for every unplaced
 * syllable the bird has. A phrase with three unplaced syllables therefore drew a
 * trajectory that kept returning to one node chosen by nothing, and it looked exactly
 * like a measured path.
 *
 * -1 propagates: `Listener.clean` drops the node and its scheduled time together, so the
 * thread joins the syllables whose position *is* known, at the times they actually sound,
 * and a phrase with fewer than two of those draws nothing. That silence is the honest
 * reading and it is not left silent — `syllableCoverage` below lets the interface say how
 * much of a call it can place, so a missing thread reads as a gap in the corpus rather
 * than as a rendering fault.
 */
export function clusterIndexFor(
	lookup: ClusterLookup,
	speciesId: string,
	syllableId: string
): number {
	return lookup.bySyllable.get(`${speciesId}/${syllableId}`) ?? -1;
}

/** How many of a sequence's syllables the galaxy can place, and how many there are. */
export interface Coverage {
	placed: number;
	total: number;
}

/**
 * Coverage for a run of syllable ids. Counts every occurrence rather than the distinct
 * ids, because a repeated syllable is repeated in the thread too.
 */
export function syllableCoverage(
	lookup: ClusterLookup,
	speciesId: string,
	syllableIds: string[]
): Coverage {
	let placed = 0;
	for (const id of syllableIds) {
		if (clusterIndexFor(lookup, speciesId, id) >= 0) placed++;
	}
	return { placed, total: syllableIds.length };
}

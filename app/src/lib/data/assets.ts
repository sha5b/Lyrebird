import { base } from '$app/paths';
import type { BirdyAssets, Centroids, FeatureSpace, Inventory, Manifest, PointCloudMeta, Species, SyrinxCalibration } from './types';

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

async function getJson<T>(path: string, fetcher: typeof fetch): Promise<T> {
	const url = `${base}/${ROOT}/${path}`;
	const res = await fetcher(url);
	if (!res.ok) throw new AssetsMissingError(path);
	return (await res.json()) as T;
}

/**
 * Loads the generated galaxy + inventory. The pipeline is the only writer of these
 * files, so a missing one means the offline stage has not been run yet.
 */
export async function loadAssets(fetcher: typeof fetch = fetch): Promise<BirdyAssets> {
	const manifest = await getJson<Manifest>('manifest.json', fetcher);
	const [inventory, rawFeatureSpace, points, centroids] = await Promise.all([
		getJson<Inventory>('inventory.json', fetcher),
		getJson<FeatureSpace & NestedFeatureSpace>('feature-space.json', fetcher),
		getJson<PointCloudMeta>('points.json', fetcher),
		getJson<Centroids>('centroids.json', fetcher)
	]);
	const featureSpace = normaliseFeatureSpace(rawFeatureSpace);

	// The calibration table only refines the synth; the analytic fallback covers its absence.
	let calibration: SyrinxCalibration | null = null;
	try {
		calibration = await getJson<SyrinxCalibration>('syrinx-calibration.json', fetcher);
	} catch {
		calibration = null;
	}

	const posRes = await fetcher(`${base}/${ROOT}/positions.f32`);
	if (!posRes.ok) throw new AssetsMissingError('positions.f32');
	const positions = new Float32Array(await posRes.arrayBuffer());

	if (positions.length !== points.n * 3) {
		throw new Error(
			`positions.f32 holds ${positions.length / 3} points but points.json declares ${points.n}`
		);
	}

	return { manifest, inventory, calibration, featureSpace, positions, points, centroids };
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
	bySpecies: Map<string, number>;
}

export function buildClusterLookup(centroids: Centroids): ClusterLookup {
	const bySyllable = new Map<string, number>();
	const bySpecies = new Map<string, number>();
	centroids.items.forEach((item, index) => {
		if (item.syllableId && !bySyllable.has(`${item.speciesId}/${item.syllableId}`)) {
			bySyllable.set(`${item.speciesId}/${item.syllableId}`, index);
		}
		if (!bySpecies.has(item.speciesId)) bySpecies.set(item.speciesId, index);
	});
	return { bySyllable, bySpecies };
}

/**
 * Cluster index for a syllable, falling back to any cluster of the same species. Returns
 * -1 when the corpus knows nothing about it — a syllable can be missing if the galaxy was
 * built from a different inventory.
 */
export function clusterIndexFor(
	lookup: ClusterLookup,
	speciesId: string,
	syllableId: string
): number {
	return lookup.bySyllable.get(`${speciesId}/${syllableId}`) ?? lookup.bySpecies.get(speciesId) ?? -1;
}

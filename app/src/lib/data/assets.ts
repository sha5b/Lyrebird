import { base } from '$app/paths';
import type { BirdyAssets, Centroid, Centroids, EmbeddingSpace, FeatureSpace, Inventory, InventoryIndex, Manifest, PointCloudMeta, RelationsDoc, Species, SpeciesIndexEntry, SyrinxCalibration } from './types';

const ROOT = 'birdy';

/**
 * The two maps a `build --clustering both` writes side by side: `known` is the kmeans
 * galaxy (every type owns a named knot — "Name everything"), `unknown` the hdbscan one
 * (dense regions only, the rest honestly unassigned — "Find the unknown"). Each ships a
 * complete asset set under its own subdirectory of the root.
 */
export type GalaxyMap = 'known' | 'unknown';

/**
 * Whether this asset root carries both clustering maps. Decided once at startup by the
 * two manifest probes; when either is absent the interface stays exactly the single-map
 * one — no toggle, and no further fetch mentions the subdirectories.
 */
export async function detectGalaxyMaps(fetcher: typeof fetch = fetch): Promise<boolean> {
	try {
		const [known, unknown] = await Promise.all([
			fetcher(assetUrl('known/manifest.json', '')),
			fetcher(assetUrl('unknown/manifest.json', ''))
		]);
		return known.ok && unknown.ok;
	} catch {
		return false;
	}
}

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
 *
 * The inventory loads lazily when the build ships per-species shards: the tiny
 * `inventory/index.json` fills the pickers up front, and a bird's full entry is
 * fetched from `inventory/<id>.json` only when one is actually selected, composed
 * with or sung. Whether shards exist is detected exactly once, here; an older build
 * without them answers 404 and the whole file loads instead, exactly as before.
 *
 * `map` selects one of the two clustering maps of a `--clustering both` build: every
 * path below resolves under `<root>/<map>/` instead of the root itself. The sub-build
 * is a complete asset set with its own manifest stamp, so everything downstream —
 * the stamp pinning, the shard view, the sidecar fetches — works unchanged. The
 * default `''` is byte-for-byte the historical single-map load.
 */
export async function loadAssets(
	fetcher: typeof fetch = fetch,
	bust = '',
	map: '' | GalaxyMap = ''
): Promise<BirdyAssets> {
	const dir = map ? `${map}/` : '';
	const manifest = await getJson<Manifest>(`${dir}manifest.json`, fetcher, bust);
	// Everything after the manifest is fetched under that build's own stamp, so a reload
	// triggered by a rebuild cannot mix two builds together.
	const stamp = bust || manifest.builtAt || '';
	let index: InventoryIndex | null = null;
	try {
		index = await getJson<InventoryIndex>(`${dir}inventory/index.json`, fetcher, stamp);
	} catch {
		index = null;
	}
	const [inventory, rawFeatureSpace, points, centroids] = await Promise.all([
		// In shard mode the inventory starts as the header alone; `loadSpecies` below is
		// how a bird joins it. The whole file is *not* fetched here — that is the point.
		index
			? Promise.resolve<Inventory>({
					version: index.version,
					note: index.note,
					refs: index.refs,
					banks: index.banks,
					species: []
				})
			: getJson<Inventory>(`${dir}inventory.json`, fetcher, stamp),
		getJson<FeatureSpace & NestedFeatureSpace>(`${dir}feature-space.json`, fetcher, stamp),
		getJson<PointCloudMeta>(`${dir}points.json`, fetcher, stamp),
		getJson<Centroids>(`${dir}centroids.json`, fetcher, stamp)
	]);
	const featureSpace = normaliseFeatureSpace(rawFeatureSpace);

	// The rff-ridge map's weights ship in a binary sidecar (123 k floats are nobody's
	// JSON). Fetched under the same build stamp, checked against the declared layout,
	// and treated as absent on any mismatch — a wrong map is worse than no map, because
	// the 28-d fallback is honest and a mismatched one lights the wrong knots.
	const embMap = featureSpace.embedding?.map;
	if (embMap && 'kind' in embMap && embMap.kind === 'rff-ridge' && !embMap.rff) {
		try {
			const res = await fetcher(assetUrl(`${dir}${embMap.file}`, stamp));
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
		calibration = await getJson<SyrinxCalibration>(`${dir}syrinx-calibration.json`, fetcher, stamp);
	} catch {
		calibration = null;
	}

	// Cross-species relations (relations.py): optional like every learned asset, and
	// candidates rather than facts even when present — the UI labels them that way.
	let relations: RelationsDoc | null = null;
	try {
		relations = await getJson<RelationsDoc>(`${dir}relations.json`, fetcher, stamp);
	} catch {
		relations = null;
	}

	const posRes = await fetcher(assetUrl(`${dir}positions.f32`, stamp));
	if (!posRes.ok) throw new AssetsMissingError(`${dir}positions.f32`);
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
		stamp,
		dir
	);

	// The lazy species view. In shard mode the index came from disk; without shards it
	// is derived from the whole file, so `inventoryIndex` is complete either way.
	const inventoryIndex: SpeciesIndexEntry[] =
		index?.species ??
		inventory.species.map((s) => ({
			id: s.id,
			common: s.common,
			bank: s.bank,
			types: s.syllables.length,
			songs: s.songs.length
		}));
	const commonById = new Map(inventoryIndex.map((s) => [s.id, s.common]));
	// Cache by promise, not by result: two selections of the same bird in the same tick
	// share one fetch, and a cached 404 stays answered rather than retried per lookup.
	const shardCache = new Map<string, Promise<Species | undefined>>();
	const loadSpecies = (id: string): Promise<Species | undefined> => {
		const held = inventory.species.find((s) => s.id === id);
		if (held) return Promise.resolve(held);
		if (!index) return Promise.resolve(undefined);
		let pending = shardCache.get(id);
		if (!pending) {
			pending = getJson<Species>(`${dir}inventory/${id}.json`, fetcher, stamp)
				.then((sp) => {
					// The shard is the whole file's entry for this bird, so once it is here
					// every sync reader (speciesById, the engine, the grammar) sees it.
					if (!inventory.species.some((s) => s.id === sp.id)) inventory.species.push(sp);
					return sp;
				})
				.catch(() => undefined);
			shardCache.set(id, pending);
		}
		return pending;
	};
	const ensureSpecies = async (ids?: string[]): Promise<void> => {
		if (!index) return; // whole-file mode: every species is already here
		if (ids) {
			await Promise.all(ids.map((id) => loadSpecies(id)));
			return;
		}
		// Every bird at once is the one case where the whole file is the lazy unit:
		// a single fetch beats one request per species.
		const whole = await getJson<Inventory>(`${dir}inventory.json`, fetcher, stamp);
		const held = new Set(inventory.species.map((s) => s.id));
		inventory.species.push(...whole.species.filter((s) => !held.has(s.id)));
	};
	const speciesCommon = (id: string): string => commonById.get(id) ?? id;

	return {
		manifest,
		inventory,
		inventoryIndex,
		loadSpecies,
		ensureSpecies,
		speciesCommon,
		calibration,
		featureSpace,
		positions,
		points,
		centroids,
		pointFeatures,
		pointFeatureDims,
		relations
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
	bust = '',
	dir = ''
): Promise<{ pointFeatures: Float32Array | null; pointFeatureDims: number }> {
	const dims = centroids.items[0]?.featuresLo?.length ?? 0;
	if (!dims) return { pointFeatures: null, pointFeatureDims: 0 };
	try {
		const res = await fetcher(assetUrl(`${dir}point-features.f32`, bust));
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
 * species is selected. The inventory index sets the order (it is the inventory's own
 * order, shards or not); species that appear only in the point cloud (harvested field
 * recordings of something not in the inventory) are appended, so no point is left
 * without an index.
 */
export function buildSpeciesIndex(assets: BirdyAssets): Map<string, number> {
	const index = new Map<string, number>();
	assets.inventoryIndex.forEach((s) => index.set(s.id, index.size));
	for (const id of assets.points.speciesId) {
		if (!index.has(id)) index.set(id, index.size);
	}
	return index;
}

/**
 * The full entry for one bird — present once its shard has landed (or always, on a
 * pre-shard build). Callers that cannot wait should go through `assets.loadSpecies`
 * first; name-only lookups belong to `assets.speciesCommon`, which needs no shard.
 */
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
 * Where a sound in the galaxy comes from, as the provenance categories the
 * provenance colour mode draws. Numeric because it crosses into a shader attribute.
 *
 * - `documented` (0) — a render of a call from the authored inventory: its identity
 *   was written down by a person, with a confidence the inventory states.
 * - `learned` (1) — *our synthesis* of a type the pipeline fitted (ids start with L).
 *   The type is measured; the sound at this point is one we generated from it.
 * - `field` (2) — *real recorded audio* carrying a fitted type. Same measured
 *   identity as `learned`, but the point is a recording rather than a render.
 * - `unlabelled` (3) — the pseudo-species: arrivals with no species label, typed by
 *   the label-free path (`learn_unlabelled`). Keyed on the markers the pipeline
 *   actually writes — speciesId `unlabelled` and the U-prefixed candidate type ids
 *   (learn.py `UNLABELLED_SPECIES` / `unlabelled_entry`) — not on a guess.
 * - `candidate` (4) — the honest remainder: harvested field audio with no identity at
 *   all. A per-point novelty flag would live here too, but no shipped build writes
 *   one yet, so unidentified field points are the whole of this category for now.
 *
 * **Why `learned` and `field` are two classes and not one.** They were one, and that
 * single class held 97.2 % of the shipped corpus (44 293 of 45 592 points) — so the
 * provenance mode painted the whole galaxy in one colour and told you nothing. It was
 * worse than nothing: the colour was the neutral grey, which at the resting wash is
 * ΔE 5.3 from the plain mode's neutral, i.e. indistinguishable, so switching the mode
 * on appeared to do nothing at all except tint the 2.8 % documented minority blue.
 * The class was hiding a real and nearly even division the assets already carry in
 * `source`: 24 100 of those points are renders we synthesized and 20 193 are actual
 * recordings. "Did a machine make this sound, or did a bird?" is the first question
 * provenance is asked, and it is now the one the mode answers most loudly.
 *
 * The ordering is by strength of claim, strongest first, and the neutral grey now sits
 * on `candidate` — the class that genuinely claims nothing — rather than on the
 * majority, which is what a neutral means everywhere else in this interface.
 */
export const PROVENANCE = {
	documented: 0,
	learned: 1,
	field: 2,
	unlabelled: 3,
	candidate: 4
} as const;

/** How many provenance classes there are; the shader's selector chain matches it. */
export const CLASS_COUNT = 5;

/** True for the unlabelled pool's own markers: the pseudo-species or a U* type id. */
function isUnlabelledArrival(speciesId: string, syllableId: string): boolean {
	return speciesId === 'unlabelled' || syllableId[0] === 'U';
}

/**
 * One provenance category per point, built once per asset load.
 *
 * The rule is deliberately a reading of fields the assets already carry, not a new
 * claim: `source` says whether a point is our render or real audio, `syllableId`
 * says whether anything named it, and the L/U prefix says whether that name was
 * fitted rather than authored — and whether it was fitted to a labelled bird at all.
 */
export function pointProvenance(assets: BirdyAssets): Float32Array {
	const { n, source, speciesId, syllableId, novel } = assets.points;
	const out = new Float32Array(n);
	for (let i = 0; i < n; i++) {
		const syl = syllableId[i] ?? '';
		// The pseudo-species outranks everything, novelty flags included: an arrival
		// with no species tag is that claim first, whatever else was measured about it.
		if (isUnlabelledArrival(speciesId[i] ?? '', syl)) {
			out[i] = PROVENANCE.unlabelled;
			continue;
		}
		// A novelty flag, when a build ships one, outranks the rest: that point was
		// measured as unlike every known type.
		if (novel?.[i]) {
			out[i] = PROVENANCE.candidate;
			continue;
		}
		if (!syl) {
			// Unlabelled field audio is the candidate pool — its `songId` names the
			// recording bout, not an authored song. A whole-song *render*
			// (synthetic-song) is still an authored phrase.
			out[i] = source[i] === 'field' ? PROVENANCE.candidate : PROVENANCE.documented;
			continue;
		}
		// A fitted type splits on where this particular point's audio came from: the
		// identity is the same measurement either way, but one is a recording of a bird
		// and the other is our synthesis of it, and the mode exists to say which.
		if (syl[0] === 'L') {
			out[i] = source[i] === 'field' ? PROVENANCE.field : PROVENANCE.learned;
			continue;
		}
		// An authored identity stays `documented` whatever the source: the class is
		// defined by who named the sound, and a person did.
		out[i] = PROVENANCE.documented;
	}
	return out;
}

/**
 * One provenance category per *knot*, so the tags and the trajectory threads can speak
 * the same colour language as the points while the provenance mode is on.
 *
 * The rule is a plurality of the knot's own member points, which is the only honest
 * summary available: a cluster is a region of the acoustic space, and nothing says its
 * members must share a provenance — a type fitted to field audio typically holds both
 * the recordings it was fitted to and our renders of it. The plurality names what the
 * knot is *mostly* made of, and it is a knot-level claim, not a promise about every
 * member. The points themselves keep telling the exact truth per point.
 *
 * Ties break toward the stronger claim (the lower PROVENANCE index), so a knot that is
 * half authored and half fitted is called authored rather than the reverse.
 */
export function clusterProvenance(assets: BirdyAssets, k?: number): Float32Array {
	const classes = pointProvenance(assets);
	const count = k ?? assets.centroids.items.length;
	const { clusterId } = assets.points;
	const tally = Array.from({ length: count }, () => new Uint32Array(CLASS_COUNT));
	for (let i = 0; i < classes.length; i++) {
		const c = clusterId[i];
		if (c >= 0 && c < count) tally[c][classes[i]]++;
	}
	const out = new Float32Array(count);
	for (let c = 0; c < count; c++) {
		let best = 0;
		let total = 0;
		// Strictly greater, walking upward from the strongest claim, is what makes a tie
		// fall to the stronger one.
		for (let cls = 0; cls < CLASS_COUNT; cls++) {
			total += tally[c][cls];
			if (cls > 0 && tally[c][cls] > tally[c][best]) best = cls;
		}
		// A knot with no members has nothing to summarise, and the all-zero tally would
		// otherwise tie its way to `documented` — the strongest claim in the set, asserted
		// about a knot that holds no sound at all. It gets the neutral, which is the class
		// that claims nothing. (No shipped build has one; the rest of the renderer already
		// refuses to launch waves or fronts from empty knots for the same reason.)
		out[c] = total ? best : PROVENANCE.candidate;
	}
	return out;
}

/**
 * Where each knot sits inside its own species, for the label hue's slight lightness
 * variation (speciesColourScaled). Same rule the point cloud's aHeat used before the
 * hue moved to the labels: the knot's true distance from its species' component-wise
 * median knot position, normalised by the species' own median knot distance and
 * capped at twice it. 0 is the species' core knot, 1 its far edge; a species with a
 * single knot — or all its knots on one spot — gets the flat mid value.
 */
export function knotHeat(assets: BirdyAssets): Float32Array {
	const items = assets.centroids.items;
	const out = new Float32Array(items.length).fill(0.5);
	const bySpecies = new Map<string, number[]>();
	items.forEach((c, i) => {
		const list = bySpecies.get(c.speciesId);
		if (list) list.push(i);
		else bySpecies.set(c.speciesId, [i]);
	});
	const medianOf = (values: number[]): number => {
		const sorted = [...values].sort((a, b) => a - b);
		return sorted[sorted.length >> 1] ?? 0;
	};
	for (const members of bySpecies.values()) {
		const mx = medianOf(members.map((i) => items[i].position[0] ?? 0));
		const my = medianOf(members.map((i) => items[i].position[1] ?? 0));
		const mz = medianOf(members.map((i) => items[i].position[2] ?? 0));
		const ds = members.map((i) =>
			Math.hypot(
				(items[i].position[0] ?? 0) - mx,
				(items[i].position[1] ?? 0) - my,
				(items[i].position[2] ?? 0) - mz
			)
		);
		const md = medianOf(ds);
		if (md < 1e-6) continue;
		members.forEach((i, j) => {
			out[i] = Math.min(1, ds[j] / (2 * md));
		});
	}
	return out;
}

/**
 * Every point a syllable type owns, keyed `speciesId/syllableId` — synthetic renders
 * and field members alike. This is what an *orphan* type (one that won no cluster,
 * so `clusterIndexFor` says -1) can still honestly show when it is sung: its own
 * points have positions, they just have no knot.
 */
export function buildSyllablePointIndex(assets: BirdyAssets): Map<string, number[]> {
	const map = new Map<string, number[]>();
	const { n, speciesId, syllableId } = assets.points;
	for (let i = 0; i < n; i++) {
		const syl = syllableId[i];
		if (!syl) continue;
		const key = `${speciesId[i]}/${syl}`;
		const list = map.get(key);
		if (list) list.push(i);
		else map.set(key, [i]);
	}
	return map;
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

/**
 * Types for the canonical inventory (`data/inventory.json`) and for the assets the
 * Python pipeline generates. Both are described in `docs/08-implementation.md`.
 */

export type Timbre = 'pure' | 'reed' | 'buzz';

/**
 * How well the stated function is supported by the literature. `unlabelled` is what a
 * harvested field cluster gets: real audio of a known species with no documented
 * function attached, which is a different claim from `invented`.
 */
export type Confidence =
	| 'experimental'
	| 'documented'
	| 'inferred'
	| 'invented'
	| 'unlabelled';

/** A pitch-contour breakpoint: [time fraction 0..1, frequency in Hz]. */
export type ContourPoint = [number, number];

export interface Syllable {
	id: string;
	label: string;
	function: string;
	confidence: Confidence;
	refs: string[];
	dur: number;
	level: number;
	timbre: Timbre;
	contour: ContourPoint[];
	attack?: number;
	hold?: boolean;
	harmonic?: number;
	two?: boolean;
	am?: number;
	amDepth?: number;
	vib?: { rate: number; depth: number };
	/**
	 * Tract resonances as `[hz, q, gain]`, at absolute frequencies that do **not** follow
	 * f0 — up to three (§8.1a).
	 *
	 * The tract of §8.1 is a bandpass retuned to the instantaneous f0, so its resonance is
	 * relative to pitch and the spectral envelope comes out pitch-invariant: transposing a
	 * syllable transposes its whole spectrum, and two species at the same pitch are the
	 * same instrument. A formant fixed in Hz is what lets a contour sweeping underneath it
	 * change timbre as it goes, the way a real trachea does.
	 */
	formants?: [number, number, number][];
	/** Turbulence at the labia, 0..1, gated by pressure. The only route to a real rasp:
	 *  the ODE limit cycle is periodic, so a "buzz" made by widening a bandpass is a tone. */
	noise?: number;
	/** Cycle-to-cycle tension irregularity, 0..1, which reaches the sound through the
	 *  oscillator as jitter, subharmonics and — at the top — aperiodicity. */
	rough?: number;
	/**
	 * Multiplier on the per-syllable gamma of §8.1, and the syllable's harmonic-richness
	 * control (§8.1a).
	 *
	 * gamma is a pure time-scale, so for a fixed target f0, raising it forces beta down —
	 * and the spectral content index (spectral centroid ÷ f0) is a function of beta alone.
	 * Low beta gives the pulse-like, harmonically dense solutions; high beta gives tonal
	 * ones. The §8.1 rule puts every syllable at beta ≈ 1, which is the tonal end, so
	 * without this the rich half of a repertoire is unreachable rather than merely
	 * mis-fitted.
	 */
	gammaScale?: number;
	/**
	 * Fit-quality record the learned inventory attaches to a fitted type. The one number
	 * the composer surfaces is `resynthesisCosine`: how close a render of this fit comes
	 * to the audio it was fitted from, so a low one means "this syllable is a rougher
	 * likeness", not "this bird sings worse".
	 */
	learned?: {
		members?: number;
		resynthesisCosine?: number;
		rivalCosine?: number;
		nearestOwn?: boolean;
		f0ErrorPercent?: number;
	};
	/**
	 * Q of the f0-tracking tract band, overriding the timbre class's default when set.
	 * The three classes offer 9, 5 and 3 — all broad next to the Q ≈ 30 measured for the
	 * oropharyngeal-esophageal resonance, and a broad band leaks the second harmonic.
	 */
	tractQ?: number;
	/**
	 * The species' respiratory set (docs/15 §1; Fainstein, Goller & Mindlin 2025, Table
	 * S2). When present, the designed envelope no longer drives `ps`: the two-state
	 * air-sac oscillator produces the pressure gesture, and the tract is driven by its
	 * square root at the injection point (Laje & Mindlin 2005's √ps · y). When absent
	 * the syllable renders exactly as it always has. `forcing` is the paper's F0 —
	 * the forcing amplitude, not a pitch.
	 */
	respiration?: {
		tauX: number;
		tauP: number;
		alphaI: number;
		alphaRel: number;
		forcing: number;
	};
	/**
	 * The second syringeal voice and its tracheal coupling (docs/15 §5; Laje & Mindlin
	 * 2005, docs/13 B2). When present, the syllable renders two independently-gestured
	 * sources — the syllable's contour drives the first voice, `contour`/`gamma` the
	 * second — coupled through the shared tracheal pressure: each source injects
	 * `betaInj · √ps · y/γ`, and the sum, plus one fractional-delay round trip
	 * (`tracheaCm` one-way, reflection `refl`), acts back on both sources' restitution.
	 * `level` is the second bronchus's share of the shared air-sac pressure; 0 is a
	 * closed right side (the paper's single-source-plus-feedback case). When absent
	 * the syllable renders exactly as it always has, and `two` stays the uncoupled
	 * 7-cent shimmer (ignored when this block exists).
	 */
	voices?: {
		contour: ContourPoint[];
		gamma: number;
		level: number;
		tracheaCm: number;
		refl: number;
		betaInj: number;
	};
}

export interface Song {
	id: string;
	label: string;
	gloss: string;
	function: string;
	confidence: Confidence;
	refs: string[];
	/** Syllable ids, in order. */
	sequence: string[];
	/** Silence in seconds between consecutive syllables; length = sequence.length - 1. */
	gaps: number[];
}

/** Finite-state song syntax (Bengalese finch); `end` terminates the bout. */
export interface Grammar {
	start: string[];
	transitions: Record<string, Record<string, number>>;
	/**
	 * Repeated subsequences mined from the observed bouts (docs/12). Present only in a
	 * learned inventory; `count` is how often the whole motif was heard, `pmi` how much
	 * more often than chance the sequence co-occurs.
	 */
	chunks?: Chunk[];
	/**
	 * Recurring song types, as run-collapsed medoid sequences: one entry per *act*, so a
	 * trill is a single token and playing a type means re-expanding runs (compose.ts).
	 */
	songTypes?: SongType[];
	/** The census behind `songTypes` — how many bouts were typed, and how many were not. */
	songTyping?: SongTyping;
}

export interface Chunk {
	sequence: string[];
	count: number;
	species: string[];
	pmi: number;
}

export interface SongType {
	/** Renumbered on every refit (docs/12 §12.5) — never persisted anywhere. */
	id: string;
	sequence: string[];
	count: number;
	share: number;
}

export interface SongTyping {
	bouts: number;
	short: number;
	candidates: number;
	types: number;
	inTypes: number;
	unplaced: number;
	minClusterSize: number;
}

export interface Species {
	id: string;
	common: string;
	scientific: string;
	bank: string;
	summary: string;
	syllables: Syllable[];
	songs: Song[];
	grammar?: Grammar;
}

export interface Inventory {
	version: number;
	note: string;
	refs: Record<string, string>;
	banks: Record<string, string>;
	species: Species[];
}

/**
 * One row of `inventory/index.json`: everything a picker needs without opening the
 * species' shard — the display name, the bank, and how much the bird has to sing.
 */
export interface SpeciesIndexEntry {
	id: string;
	common: string;
	bank: string;
	/** Syllable types (the shard's `syllables.length`). */
	types: number;
	songs: number;
}

/**
 * `inventory/index.json`: the inventory's header plus one row per species. The whole
 * file stays the checkpoint; this is the lazy view's front door. `refs` and `banks`
 * ride along because a citation must never require opening a shard.
 */
export interface InventoryIndex {
	version: number;
	note: string;
	refs: Record<string, string>;
	banks: Record<string, string>;
	species: SpeciesIndexEntry[];
}

/**
 * beta <-> f0 calibration measured offline from the syrinx ODE, at `gamma`. Because gamma
 * is a pure time-scale, a voice running at another gamma converts its target frequency
 * before indexing this table (docs/08-implementation.md §8.1).
 */
export interface SyrinxCalibration {
	gamma: number;
	oversample: number;
	sampleRate: number;
	pressureGrid: number[];
	betaGrid: number[];
	f0Hz: number[][];
	/** Peak-to-peak swing of y/gamma per [pressure][beta]; the source is divided by it. */
	ampPP?: number[][];
	inverse: { f0Grid: number[]; beta: number[][] };
	f0Range: [number, number];
	/** [min, max] beta the sweep covers, when the pipeline reports it. */
	betaClamp?: [number, number];
}

export interface FeatureSpace {
	sampleRate: number;
	frameSize: number;
	hopSize: number;
	window: string;
	melBands: number;
	mfccCoeffs: number;
	dims: number;
	dimNames: string[];
	mean: number[];
	std: number[];
	temperature: number;
	/**
	 * Present when the galaxy was built in the critic's learned 32-d embedding space
	 * (docs/09 phase 2). The browser cannot run the critic — no weights ship — so
	 * `map` is the offline-fitted ridge that carries its live standardised 28-d
	 * descriptor into the embedding space, and `mapQuality.accepted === false` means
	 * the map failed its held-out gate and the 28-d path stays in charge.
	 */
	embedding?: EmbeddingSpace;
}

/** The learned similarity space a `--space embed` build ships in feature-space.json. */
export interface EmbeddingSpace {
	dims: number;
	mean: number[];
	std: number[];
	map?: LinearSpaceMap | RffSpaceMap;
	mapQuality?: {
		accepted?: boolean;
		medianCosine?: number;
		centroidAgreement?: number;
		[key: string]: unknown;
	};
}

export interface LinearSpaceMap {
	kind?: 'linear';
	/** (28 x 32) ridge weights, applied to the standardised live descriptor. */
	w: number[][];
	/** (32) intercept. */
	b: number[];
	lambda?: number;
}

/**
 * The nonlinear map (spacemap.py): random Fourier features of the standardised live
 * descriptor, then ridge — `sqrt(2/D) * cos(x @ R + phase) @ w + b`. The 123 k floats
 * ship in the f32 sidecar `file` (layout `R (28 x D) | phase (D) | w (D x 32) | b (32)`,
 * row-major little-endian); `rff` is attached by loadAssets once the sidecar is parsed,
 * and the map is unusable until it is.
 */
export interface RffSpaceMap {
	kind: 'rff-ridge';
	file: string;
	sigma: number;
	D: number;
	lambda?: number;
	layout?: string;
	apply?: string;
	rff?: { R: Float32Array; phase: Float32Array; w: Float32Array; b: Float32Array };
}

export interface PointCloudMeta {
	n: number;
	speciesId: string[];
	syllableId: string[];
	songId: (string | null)[];
	clusterId: number[];
	/**
	 * Which build each point joined in. 0 for the original build, incremented by every
	 * `grow`, absent on an asset set built before growth existed. The renderer uses it to
	 * animate arrivals rather than having the whole cloud appear at once.
	 */
	generation?: number[];
	durations: number[];
	source: string[];
	/**
	 * One flag per point: the observation it came from was judged unlike every known
	 * type centroid at ingest (docs/09 §9.2b). Computed by the pipeline but **not yet
	 * written into points.json by any shipped build**, so this is absent in practice;
	 * the renderer treats absence as "unknown", never as "known not novel".
	 */
	novel?: boolean[];
}

export interface Centroid {
	id: number;
	label: string;
	speciesId: string;
	syllableId: string;
	function: string;
	confidence: Confidence;
	refs: string[];
	position: [number, number, number];
	vector: number[];
	/**
	 * The centroid in the critic's 32-d embedding space — the primary vector of a
	 * `--space embed` build, where `vector` is the 28-d member centroid kept for the
	 * fallback path. Absent in descriptor-space assets.
	 */
	vector32?: number[];
	count: number;
	/**
	 * The centroid in the reduced space of `point-features.f32`. Used only to decide how
	 * brightly each individual point responds; the reported match still uses `vector`.
	 */
	featuresLo?: number[];
	/**
	 * Behavioural class of the documented function — alarm, recruitment, courtship,
	 * territorial, contact, structural or unclassified. Derived by the pipeline from an
	 * auditable keyword table stored in the manifest.
	 */
	functionClass?: string;
	/** Per-cluster summary the node labels show. Absent in assets built before they existed. */
	meanDuration?: number;
	/** Mean 3D distance of members from the centroid: how tight the knot is on screen. */
	radius?: number;
	/** Mean 28-d cosine of members to the centroid: how tight it is in feature space. */
	cohesion?: number;
	speciesMix?: { speciesId: string; count: number }[];
	sources?: Record<string, number>;
	/**
	 * What the density clustering could say the cluster is, and on what evidence
	 * (pipeline `density.anchor`): `confirmed` when its labelled members agree and it
	 * holds nothing unlabelled, `anchored` when unlabelled field audio inherits the
	 * labelled majority's identity, `unknown` when a dense region of real audio holds
	 * nothing documented, and `mixed` when the labelled members disagree — i.e. the
	 * name it carries is contested rather than fitted.
	 */
	anchor?: {
		kind?: 'anchored' | 'confirmed' | 'unknown' | 'mixed' | 'empty';
		/** Share of the whole cluster backing the candidate identity. */
		support?: number;
		agreement?: number;
	};
}

export interface Centroids {
	k: number;
	dims: number;
	items: Centroid[];
}

/**
 * What the build wrote and how. Only the fields the client actually reads are named —
 * `builtAt` is the one that matters, because it is the stamp a rebuild changes and
 * therefore what tells a running app that its galaxy is out of date.
 */
export interface Manifest {
	builtAt: string;
	source: string;
	points: number;
	clusters: number;
	sourceMix?: Record<string, number>;
	projection?: string;
	/** Which clustering produced the knots: `kmeans` or `hdbscan`. */
	clustering?: string;
	/** Points the density clustering placed in no cluster at all. */
	unassigned?: number;
	/** Bumped by every `grow`; points carry the generation they joined in. */
	generation?: number;
	/**
	 * How many syllable types ended up with a cluster carrying their name. A type with none
	 * cannot light, be labelled or draw a trajectory, so this is the number that says whether
	 * the galaxy can respond to the repertoire it was built from.
	 */
	typeCoverage?: { types: number; withCluster: number; share: number; orphans: string[] };
	/**
	 * Which groupings the geometry actually corresponds to, each against its own label
	 * permutation. `headline` says whether the strongest one beats the recording-condition
	 * controls — the difference between structure about birds and structure about microphones.
	 */
	relations?: {
		headline: string;
		knnK: number;
		permutations: number;
		relations: {
			grouping: string;
			space: string;
			groups: number;
			coverage: number;
			knn: number | null;
			knnNull: number | null;
			knnP: number | null;
			silhouette: number | null;
			verdict: string;
		}[];
	};
	files?: Record<string, string>;
	[key: string]: unknown;
}

/** Everything the client needs, fetched once at startup. */
export interface BirdyAssets {
	manifest: Manifest;
	/**
	 * The canonical inventory. When the build ships per-species shards this starts as the
	 * header with an empty species list and gains a bird each time `loadSpecies` resolves
	 * — the shard *is* the whole file's entry for that bird, so a reader cannot tell the
	 * difference. When the build predates shards, this is the whole file, as it always was.
	 */
	inventory: Inventory;
	/**
	 * One row per species, complete from startup, in the inventory's own order: the
	 * pickers' and name lookups' data, no shard required.
	 */
	inventoryIndex: SpeciesIndexEntry[];
	/**
	 * Brings one bird's full entry into `inventory.species`, fetching its shard the first
	 * time and answering from the cache after. Resolves `undefined` for an id the
	 * inventory does not hold.
	 */
	loadSpecies(id: string): Promise<Species | undefined>;
	/**
	 * `loadSpecies` for several birds at once. With no ids it loads *every* species —
	 * which in shard mode fetches the whole file once, the cheapest way to have them all
	 * (the global chorus is the one caller that genuinely needs every bird).
	 */
	ensureSpecies(ids?: string[]): Promise<void>;
	/** A bird's display name from the index, or the id itself when nothing names it. */
	speciesCommon(id: string): string;
	calibration: SyrinxCalibration | null;
	featureSpace: FeatureSpace;
	positions: Float32Array;
	points: PointCloudMeta;
	centroids: Centroids;
	/**
	 * `n * pointFeatureDims` unit vectors, row-major, or null for an asset set built
	 * before the pipeline emitted them. When present, each point reacts to live audio on
	 * its own similarity rather than inheriting its cluster's.
	 */
	pointFeatures: Float32Array | null;
	pointFeatureDims: number;
}

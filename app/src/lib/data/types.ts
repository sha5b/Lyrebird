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
	/**
	 * The fricative routing of docs/16 §16.7: the turbulence bypasses the f0-tracking
	 * tract band and is shaped by this syllable's own formant set instead — a
	 * fricative is a noise burst filtered by the vocal tract and driven by the
	 * pressure gesture (whispered vowels, not static), not a tone with noise added.
	 * On the respiration path the √ps drive scales the burst exactly as it scales the
	 * tonal source; on the envelope path the existing output envelope drives it.
	 * A no-op when `noise` is 0; absent renders bit-identically to before.
	 */
	fricative?: boolean;
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
	 * the composer surfaces is `resynthesisCosine`: how close a render of this fit sits
	 * to the type's cluster in the descriptor space — a clustering match, not an
	 * audible-fidelity guarantee (docs/19 measured its correlation with audible
	 * distortion at ≈ 0.1; audible fidelity is measured separately, MCD on the bench) —
	 * so a low one means "this render sits off its type", not "this bird sings worse".
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
	 * Measured per-transition pauses in seconds, keyed `from>to` ("L100>L114"). The
	 * 2026-07-30 grammar.gaps work (26 897 measured gaps): no invented rhythm is left
	 * in a learned inventory. Optional because authored and older entries predate it.
	 */
	gaps?: Record<string, number>;
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
	/**
	 * The live session gate (docs/20 §20.3): 256 fit-side descriptor anchors and a
	 * calibrated threshold. A live session whose mean 5-NN euclidean distance to the
	 * anchors exceeds `threshold` sits off everything the map was fitted on, and the
	 * honest display is "positions are guesses", not a named call. The threshold is
	 * ship-time calibrated (cross-half over the fit sessions) and is never
	 * recalibrated in the browser. Absent on builds before 2026-07-31 — and when the
	 * embedding block itself is gone (a broken map sidecar deletes it), the gate goes
	 * with it: it was fitted alongside the map.
	 */
	sessionGate?: {
		/** 256 x 28 standardised fit-side descriptors — the reference cloud. */
		anchors: number[][];
		/** Neighbours per row of the statistic (5). */
		k: number;
		threshold: number;
		/** Human-readable statement of the statistic the pipeline calibrated. */
		aggregate?: string;
		/** The pipeline's own account of what a flag means, quoted verbatim in the UI. */
		calibration?: string;
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
	/**
	 * Ingest-measured signal-to-noise in dB per point, and `null` where no ratio exists —
	 * a synthetic render has no recording, and a row from a store predating the field was
	 * never measured. Both mean "no evidence", which must be drawn as unmeasured and never
	 * as poor. Absent on an asset set built before the channel existed.
	 *
	 * This is the corpus's real quality axis: median 11.96 dB, p10 2.62 on the v9 build.
	 */
	snr?: (number | null)[];
	/**
	 * Per point, the share of its 10 nearest neighbours *in the shipped 3D positions* that
	 * carry its own type. 1 means a point sits only among its own kind, 0 means it sits
	 * entirely among others — so it drives radius: agreement out on the rim, ambiguity
	 * sinking to the core (docs/25 §25.3).
	 *
	 * Its mean is the manifest's `knnAgreement` (0.4462 on the v9 build) by construction —
	 * the pipeline computes both from one code path on these exact positions. Absent on an
	 * asset set built before the channel existed.
	 */
	knnAgreement?: number[];
	/**
	 * Per point, 1 where a density clustering put this sound in **no dense region**.
	 *
	 * This is the one measurement the shipped map cannot make about itself. Its clustering
	 * is `label`, which gives every point a knot by construction — `manifest.unassigned`
	 * is 0 — so "none of these" is outside its output space. The verdict is joined in from
	 * a separate `--clustering hdbscan` build of the same `PointSet` by row index, which is
	 * valid because `cmd_build` builds that set once and never reorders it;
	 * `analysis/v10_unknown_join.py` re-derives the alignment from the five columns the
	 * clustering cannot touch before it writes anything.
	 *
	 * Absent on any build predating the join. Absent means unmeasured, and the renderer
	 * draws it as "not refused" — never as a discovery.
	 */
	unassigned?: number[];
	/**
	 * Per point, which dense region the density clustering put it in, or -1 for none.
	 *
	 * Joined from the same run as `unassigned`, and the reason it is worth carrying beside
	 * the flag: a *region* full of syllables no type claims is a candidate type, while a
	 * lone refused point is only a singleton. The queue in the join's report is ordered on
	 * this, and the ids index that build's regions, not this build's knots.
	 */
	densityRegion?: number[];
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
	vector: VectorRow;
	/**
	 * The centroid in the critic's 32-d embedding space — the primary vector of a
	 * `--space embed` build, where `vector` is the 28-d member centroid kept for the
	 * fallback path. Absent in descriptor-space assets.
	 */
	vector32?: VectorRow;
	count: number;
	/**
	 * Which of its type's knots this is, largest first, and how many there are.
	 *
	 * A type owns two when the build split it — the field/synthetic seam, or its own
	 * sounds forming two groups past `TYPE_SPLIT_SEPARATION`. Rank 0 is the type's main
	 * home: the one a song's thread runs through and the one a fly-to frames. Absent on
	 * builds before 2026-08-03, where a type never owned more than one.
	 */
	blobRank?: number;
	blobCount?: number;
	/**
	 * The centroid in the reduced space of `point-features.f32`. Used only to decide how
	 * brightly each individual point responds; the reported match still uses `vector`.
	 */
	featuresLo?: VectorRow;
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

/**
 * A per-cluster float array as the client sees it: a `Float32Array` view into the
 * `centroid-vectors.f32` sidecar on a current build, a plain array on one from before
 * 2026-08-01 that still carries its vectors inline. Every consumer only indexes, reads
 * `.length`, or copies with `Float32Array.from` / `Array.from`, all of which both do.
 */
export type VectorRow = number[] | Float32Array;

/** The sidecar's layout, as `centroids.json` declares it (see `centroid-vectors.ts`). */
export interface CentroidVectorBlock {
	file: string;
	format?: string;
	order: string[];
	dims: Record<string, number>;
	rowFloats: number;
	bytes?: number;
	note?: string;
}

export interface Centroids {
	k: number;
	dims: number;
	/**
	 * Where the per-cluster float arrays actually live: `centroid-vectors.f32`, because
	 * they were 64 % of this file's bytes and it is parsed whole before the first frame
	 * (see `centroid-vectors.ts`). Absent on builds from before 2026-08-01, which carry
	 * the arrays inline on each item.
	 */
	vectors?: CentroidVectorBlock;
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
	/**
	 * Which clustering produced the knots: `kmeans`, `hdbscan`, or `label` — the last
	 * being no clustering of the named points at all, each one going to the knot of the
	 * type it already carries (docs/22 §22.5).
	 */
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
	/**
	 * How much of the measured distance structure survived the projection to three
	 * dimensions: the correlation between 32-d cosine distance and drawn euclidean
	 * distance over `pairs` random point pairs. **The build has always written it and
	 * nothing read it**, so the interface asserted "closer is more alike" flatly while
	 * the number sat in the manifest saying "roughly" (0.667 on the shipped v6 build).
	 */
	faithfulness?: { pearson: number; spearman: number; pairs: number; definition?: string };
	/**
	 * The same question locally and much harsher: the share of a point's `k` nearest
	 * neighbours *on screen* that carry its own type. Measured 0.0849 against a
	 * 13 748-type inventory: far above the 1-in-13 748 a shuffle would give, and still
	 * nine neighbours in ten belonging to some other call. The value ships in the
	 * manifest, so read it from there rather than from this sentence.
	 */
	knnAgreement?: { k: number; value: number; definition?: string };
	/**
	 * The local half of the picture's honesty, which `faithfulness` cannot see.
	 *
	 * Faithfulness is a correlation over random pairs and is therefore dominated by far
	 * ones: it says whether the coarse map is right and is nearly blind to whether a
	 * point's own neighbours are its neighbours. **The projector was chosen on this pair**,
	 * so reading only faithfulness would say the current build got worse.
	 *
	 * `trustworthiness` — of the points drawn near a point, the share that belong near it;
	 * low means the picture invents neighbours, which is the failure that misleads, because
	 * two marks drawn together is a claim. `continuity` — of the points that belong near
	 * it, the share drawn near it; low means the picture hides them, a loss rather than a
	 * lie. 1 is perfect and about 0.5 is what a random arrangement scores. Absent on
	 * builds before 2026-08-03.
	 */
	neighbourhood?: {
		trustworthiness: number;
		continuity: number;
		sampled?: number;
		k?: number;
		definition?: string;
	};
	/**
	 * Knots this projection draws in two places at once, so their centroid — where the
	 * label, the thread and the wave all go — lands between two blobs instead of on
	 * the points. `median` ~2 is the null (splitting one blob scores about 2); `torn`
	 * counts above 5. This is the measured form of "the line goes to air".
	 */
	tearing?: {
		measured: number;
		torn: number;
		severe: number;
		median: number;
		worstGap: number;
		definition?: string;
	};
	/**
	 * Where the live match ramp sits for *this* asset set, measured by the build against
	 * the centroids it just wrote (`birdy-pipeline thresholds`, or the build's own pass).
	 *
	 * **The two numbers in `features.ts` are the fallback, not the answer.** They were
	 * hand-tuned against a 2026-07 corpus and went stale in silence: by v6 the whole
	 * distribution of real field syllables had moved up 0.07-0.14, which left the floor
	 * (0.62) below the *first* percentile — excluding nothing — and the ceiling (0.86)
	 * below the *median* real syllable, so most genuine birdsong pegged the ramp at full
	 * strength. The ramp is a property of the assets and now travels with them.
	 */
	matchRamp?: {
		floor: number;
		ceiling: number;
		/** e.g. `floor = p5, ceiling = p90` — the rule, so the numbers can be re-derived. */
		rule?: string;
		percentiles?: Record<string, number>;
		max?: number;
		sampled?: number;
		population?: number;
		store?: string;
		definition?: string;
	};
	/**
	 * Every file this build is made of, relative to the asset root — the pipeline's own
	 * list of what it wrote (`galaxy.py`, `"files": [...]`).
	 *
	 * Declared as a map until something first read it, which is when the mismatch showed:
	 * the pipeline writes an **array** of eleven paths. Nothing had used the field, so
	 * nothing had disagreed with it.
	 *
	 * It is the definitive answer to "what is this build", which is why the asset download
	 * packs exactly this and never a list of its own — a hand-kept copy would drift the
	 * first time the pipeline wrote a twelfth file.
	 */
	files?: string[];
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
	/**
	 * Cross-species relations measured in the critic's embedding (relations.json), or
	 * null when the build predates them. **Candidates, never documented
	 * relationships** — a shared call shape can be ancestry, convergence, or a
	 * recording artifact, and §8.5 says which of those the app may claim (none).
	 */
	relations: RelationsDoc | null;
}

/** One species pair in relations.json, strongest (smallest embedding distance) first. */
export interface SpeciesRelation {
	a: string;
	b: string;
	aCommon: string;
	bCommon: string;
	distance: number;
	sharedTypes: {
		a: { species: string; typeId: string };
		b: { species: string; typeId: string };
		distance: number;
	}[];
}

/** relations.json as the pipeline writes it beside the galaxy assets. */
export interface RelationsDoc {
	version: number;
	space?: string;
	sharedTypeThreshold?: number;
	sharedTypeDefinition?: string;
	speciesPairs: SpeciesRelation[];
	/**
	 * Present when this file is the browser's trimmed copy rather than the whole finding
	 * (`relations.shipped_relations`, since 2026-08-01). The complete document is every
	 * unordered pair of species, which is quadratic: 2 929 410 pairs and **760 MB** at the
	 * production build's species, fetched before the first frame. The shipped copy
	 * keeps each species' eight nearest partners — 14 425 pairs, 5.6 MB, and byte-identical
	 * answers to every query `relationsOf` makes — and records here what it dropped.
	 *
	 * **`sharedTypesKept` is not this corpus's shared-type total**; `sharedTypesComputed`
	 * is. Nothing in the UI reads either, and this exists so that a reader of the file
	 * cannot mistake the subset for the measurement.
	 */
	retention?: {
		rule: string;
		pairsKept: number;
		pairsComputed: number;
		sharedTypesKept: number;
		sharedTypesComputed: number;
		note?: string;
	};
	generatedAt?: string;
}

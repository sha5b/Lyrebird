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
	 * Q of the f0-tracking tract band, overriding the timbre class's default when set.
	 * The three classes offer 9, 5 and 3 — all broad next to the Q ≈ 30 measured for the
	 * oropharyngeal-esophageal resonance, and a broad band leaks the second harmonic.
	 */
	tractQ?: number;
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
	inventory: Inventory;
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

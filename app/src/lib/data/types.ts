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

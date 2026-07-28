/**
 * Types for the canonical inventory (`data/inventory.json`) and for the assets the
 * Python pipeline generates. Both are described in `docs/08-implementation.md`.
 */

export type Timbre = 'pure' | 'reed' | 'buzz';

/** How well the stated function is supported by the literature. */
export type Confidence = 'experimental' | 'documented' | 'inferred' | 'invented';

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
}

export interface Centroids {
	k: number;
	dims: number;
	items: Centroid[];
}

export interface Manifest {
	version: number;
	generated: string;
	source: string;
	counts: Record<string, number>;
	files: Record<string, string>;
	params: Record<string, unknown>;
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
}

import { RealFft } from './fft.ts';
import type { BirdyAssets, Centroids, FeatureSpace } from '$lib/data/types';

/**
 * The 28-dimensional clip/window descriptor of docs/08-implementation.md §8.2,
 * reimplemented here so live audio lands in the same space as the offline corpus.
 */

export interface FrameFeatures {
	mfcc: Float32Array;
	logCentroid: number;
	flatness: number;
	rms: number;
}

const MEL_SCALE = 1125;
/**
 * Normative. `feature-space.json` publishes this as `extractor.voiced.rmsFloor` and the
 * Python extractor uses the same value, so the two descriptors agree frame for frame.
 * Do not tune it to make the interface behave — `verify:features` will catch it, which
 * is what it is for.
 */
const CONTRACT_RMS_FLOOR = 1e-4;
/**
 * Not normative: how loud the input has to be before the client bothers matching at all.
 * Higher than the contract floor because room tone, fans and reverb tails all sit above
 * -80 dBFS, and promoting them to "voiced" is what used to leave a cluster lit between
 * songs. It gates the match, never the descriptor.
 */
const LISTEN_FLOOR = 5e-4;

function hzToMel(hz: number): number {
	return MEL_SCALE * Math.log(1 + hz / 700);
}

function melToHz(mel: number): number {
	return 700 * (Math.exp(mel / MEL_SCALE) - 1);
}

interface MelFilter {
	start: number;
	weights: Float32Array;
}

/** Triangular mel bank exactly as specified in §8.2 (shared with the Python side). */
function buildMelBank(bands: number, frameSize: number, sampleRate: number): MelFilter[] {
	const bins = frameSize / 2;
	const melMax = hzToMel(sampleRate / 2);
	const binPoints: number[] = [];
	for (let i = 0; i < bands + 2; i++) {
		const hz = melToHz((i / (bands + 1)) * melMax);
		binPoints.push((hz * frameSize) / sampleRate);
	}
	const filters: MelFilter[] = [];
	for (let j = 0; j < bands; j++) {
		const left = binPoints[j];
		const peak = binPoints[j + 1];
		const right = binPoints[j + 2];
		const from = Math.max(0, Math.ceil(left));
		const to = Math.min(bins - 1, Math.floor(right));
		const weights = new Float32Array(Math.max(0, to - from + 1));
		for (let k = from; k <= to; k++) {
			const w = k < peak ? (k - left) / Math.max(1e-9, peak - left) : (right - k) / Math.max(1e-9, right - peak);
			weights[k - from] = Math.max(0, w);
		}
		filters.push({ start: from, weights });
	}
	return filters;
}

export class FeatureExtractor {
	readonly spec: FeatureSpace;
	private readonly fft: RealFft;
	private readonly window: Float32Array;
	private readonly mag: Float32Array;
	private readonly mel: MelFilter[];
	private readonly dct: Float32Array[];
	private readonly windowed: Float32Array;
	private readonly binHz: Float32Array;
	/** Rolling history of recent frames; the descriptor is computed over the voiced ones. */
	private readonly history: FrameFeatures[] = [];
	private readonly historyLength: number;
	private maxRms = 0;

	constructor(spec: FeatureSpace, historyLength = 64) {
		this.spec = spec;
		this.historyLength = historyLength;
		const n = spec.frameSize;
		this.fft = new RealFft(n);
		// symmetric Hann, matching §8.2
		this.window = new Float32Array(n);
		for (let i = 0; i < n; i++) this.window[i] = 0.5 - 0.5 * Math.cos((2 * Math.PI * i) / (n - 1));
		this.windowed = new Float32Array(n);
		this.mag = new Float32Array(n / 2);
		this.mel = buildMelBank(spec.melBands, n, spec.sampleRate);
		this.dct = [];
		for (let i = 0; i < spec.mfccCoeffs; i++) {
			const row = new Float32Array(spec.melBands);
			for (let j = 0; j < spec.melBands; j++) {
				row[j] = Math.cos((Math.PI * i * (j + 0.5)) / spec.melBands);
			}
			this.dct.push(row);
		}
		this.binHz = new Float32Array(n / 2);
		for (let k = 0; k < n / 2; k++) this.binHz[k] = (k * spec.sampleRate) / n;
	}

	/** Analyses one frame of `frameSize` samples and pushes it into the rolling window. */
	push(frame: Float32Array): FrameFeatures {
		const n = this.spec.frameSize;
		let sumSq = 0;
		for (let i = 0; i < n; i++) {
			const s = frame[i] ?? 0;
			sumSq += s * s;
			this.windowed[i] = s * this.window[i];
		}
		const rms = Math.sqrt(sumSq / n);
		this.fft.magnitude(this.windowed, this.mag);

		// mel band energies from the power spectrum, natural log, DCT-II
		const bands = this.spec.melBands;
		const logE = new Float32Array(bands);
		for (let j = 0; j < bands; j++) {
			const f = this.mel[j];
			let e = 0;
			for (let w = 0; w < f.weights.length; w++) {
				const m = this.mag[f.start + w];
				e += f.weights[w] * m * m;
			}
			logE[j] = Math.log(Math.max(e, 1e-10));
		}
		const mfcc = new Float32Array(this.spec.mfccCoeffs);
		for (let i = 0; i < mfcc.length; i++) {
			const row = this.dct[i];
			let acc = 0;
			for (let j = 0; j < bands; j++) acc += logE[j] * row[j];
			mfcc[i] = acc;
		}

		let num = 0;
		let den = 0;
		let logSum = 0;
		let magSum = 0;
		for (let k = 0; k < this.mag.length; k++) {
			const m = this.mag[k];
			num += this.binHz[k] * m;
			den += m;
			logSum += Math.log(m + 1e-10);
			magSum += m;
		}
		const centroid = den > 1e-12 ? num / den : 0;
		const bins = this.mag.length;
		const flatness = Math.exp(logSum / bins) / (magSum / bins + 1e-10);

		const features: FrameFeatures = {
			mfcc,
			logCentroid: Math.log2(Math.max(centroid, 20)),
			flatness,
			rms
		};
		this.history.push(features);
		if (this.history.length > this.historyLength) this.history.shift();
		// decaying peak, so the voiced-frame gate adapts to input level
		this.maxRms = Math.max(rms, this.maxRms * 0.995);
		return features;
	}

	/**
	 * True while the input is loud enough to be worth projecting into the galaxy.
	 *
	 * The relative part of the gate adapts to how loud the source is, but on its own it
	 * lets a decaying `maxRms` promote room tone to "voiced" a few seconds after the last
	 * note — which is how a chorus used to leave one cluster lit indefinitely between
	 * songs. `LISTEN_FLOOR` is an absolute backstop at about -66 dBFS: below that nothing
	 * is a bird, however quiet the recent history has been.
	 */
	get active(): boolean {
		const last = this.history[this.history.length - 1];
		return Boolean(last && last.rms > LISTEN_FLOOR && last.rms > 0.05 * this.maxRms);
	}

	get level(): number {
		return this.history[this.history.length - 1]?.rms ?? 0;
	}

	/**
	 * 28-d descriptor over the voiced frames in the rolling window, or null if too quiet.
	 * Four frames is 43 ms at the shipped hop — low enough that a wren chip or a chickadee
	 * note still registers, which an eight-frame minimum silently dropped.
	 */
	descriptor(): Float32Array | null {
		const gate = Math.max(CONTRACT_RMS_FLOOR, 0.05 * this.maxRms);
		const voiced = this.history.filter((f) => f.rms > gate);
		if (voiced.length < 4) return null;
		const c = this.spec.mfccCoeffs;
		const out = new Float32Array(this.spec.dims);
		for (let i = 0; i < c; i++) {
			let mean = 0;
			for (const f of voiced) mean += f.mfcc[i];
			mean /= voiced.length;
			let variance = 0;
			for (const f of voiced) variance += (f.mfcc[i] - mean) ** 2;
			out[i] = mean;
			out[c + i] = Math.sqrt(variance / voiced.length);
		}
		let centroid = 0;
		let flatness = 0;
		for (const f of voiced) {
			centroid += f.logCentroid;
			flatness += f.flatness;
		}
		out[2 * c] = centroid / voiced.length;
		out[2 * c + 1] = flatness / voiced.length;
		return out;
	}

	reset(): void {
		this.history.length = 0;
		this.maxRms = 0;
	}
}

export function standardise(desc: Float32Array, spec: FeatureSpace): Float32Array {
	const out = new Float32Array(desc.length);
	for (let i = 0; i < desc.length; i++) {
		out[i] = (desc[i] - (spec.mean[i] ?? 0)) / Math.max(spec.std[i] ?? 1, 1e-6);
	}
	return out;
}

function cosine(a: Float32Array | number[], b: Float32Array | number[]): number {
	let dot = 0;
	let na = 0;
	let nb = 0;
	for (let i = 0; i < a.length; i++) {
		dot += a[i] * b[i];
		na += a[i] * a[i];
		nb += b[i] * b[i];
	}
	return dot / (Math.sqrt(na) * Math.sqrt(nb) + 1e-12);
}

/**
 * How well the best centroid has to match before anything is allowed to light up.
 *
 * Softmax is a *relative* measure: its outputs sum to 1, so whatever the input, some
 * cluster always wins. Fed room tone, a fan or a reverb tail, the matcher used to pin
 * 100 % on an arbitrary call and hold it there indefinitely — the galaxy hung on one
 * node while nothing was playing.
 *
 * These two numbers turn the relative measure into an absolute one, and they come from
 * the corpus rather than from taste. Re-measured against the shipped assets by
 * `birdy-pipeline thresholds`, on 2000 of the 31,653 harvested field syllables:
 *
 *   p1 0.509 · p5 0.605 · p10 0.654 · p25 0.728 · p50 0.801 · max 0.992
 *
 * The floor lets in about nine syllables in ten; between floor and ceiling the response
 * ramps, which is the honest behaviour for a live recording of a real bird — a partial
 * match should look partial, not certain.
 *
 * **The cosine alone can no longer carry this test, and the old comment claiming it
 * could was measuring a corpus that no longer exists.** Against 176 centroids fitted to
 * two thirds field audio, white noise scores 0.996 and room tone 0.996 — both above the
 * *median* real syllable. That is not a tuning failure: some of those clusters are bins
 * of wind and rain, and 59 noise-leaning syllables average into a centroid that is more
 * noise-like than any of its members (they score p99 0.941 individually, 0.996 pooled).
 * No floor separates the two, and dropping the worst clusters only promotes the next
 * ones. The tonality gate below is what actually does the work.
 */
const MATCH_FLOOR = 0.62;
const MATCH_CEILING = 0.86;

/**
 * Spectral flatness above which the input is broadband noise and not a bird, whatever it
 * happens to be nearest to.
 *
 * This is the test the cosine cannot do, and it separates cleanly where the cosine does
 * not: measured on the same corpus, white noise sits at 0.845 and room tone at 0.847,
 * while real harvested syllables reach 0.345 at p99. Ramping between 0.40 and 0.55
 * therefore touches under one percent of genuine birdsong and zeroes both noise probes.
 *
 * It says nothing about a *tonal* impostor, and cannot: a 1 kHz sine has flatness 0.000
 * and scores 0.917 against a tawny owl whose learned call sits at 907 Hz. Those two
 * sounds really are close in this feature space, so the honest report is a strong match,
 * not a rejection.
 */
const TONAL_FLOOR = 0.4;
const TONAL_CEILING = 0.55;

function smoothstep(edge0: number, edge1: number, x: number): number {
	const t = Math.min(1, Math.max(0, (x - edge0) / (edge1 - edge0)));
	return t * t * (3 - 2 * t);
}

/**
 * The live off-manifold session gate (docs/20 §20.3): is this *session* anything like
 * the recordings the 28-d -> 32-d map was fitted on?
 *
 * The statistic is exactly the one the pipeline calibrated: per standardised
 * descriptor, the mean euclidean distance to its `k` nearest fit-side anchors;
 * the session score is the running mean of that. Nothing is unit-normed — the
 * threshold (cross-half calibrated over the fit sessions, so it transfers to
 * genuinely unseen ones) is only valid against this exact statistic, which is why
 * it ships in the assets and is never recomputed here. On the debug build it
 * separated the pathological sessions at AUC 0.953; a session above the line is
 * not bad audio, it is audio the galaxy has no warrant to place — an unusual
 * recorder, heavy background, or a sound kind the corpus does not cover.
 *
 * The gate consumes the same `z` the tracker gets; it never filters it. The visual
 * decision stays in one place (the reading panel), matching how REPORT_STRENGTH
 * gates the claim without gating the math.
 */
export class SessionGate {
	readonly k: number;
	readonly threshold: number;
	private readonly anchors: Float32Array;
	private readonly dims: number;
	private sum = 0;
	/** Descriptors seen since the last reset — the session's size. */
	rows = 0;

	constructor(
		gate: { anchors: number[][]; k: number; threshold: number },
		dims: number
	) {
		this.k = gate.k || 5;
		this.threshold = gate.threshold;
		this.dims = dims;
		this.anchors = Float32Array.from(gate.anchors.flat());
	}

	push(z: Float32Array): void {
		// The k smallest squared distances, kept sorted by insertion. 256 anchors x
		// 28 dims is ~7 k multiply-adds per descriptor — brute force is the simple
		// answer at this size.
		const best = new Float64Array(this.k).fill(Infinity);
		for (let a = 0; a < this.anchors.length; a += this.dims) {
			let d2 = 0;
			for (let i = 0; i < this.dims; i++) {
				const d = z[i] - this.anchors[a + i];
				d2 += d * d;
			}
			for (let j = 0; j < this.k; j++) {
				if (d2 < best[j]) {
					best.copyWithin(j + 1, j);
					best[j] = d2;
					break;
				}
			}
		}
		let acc = 0;
		for (let j = 0; j < this.k; j++) acc += Math.sqrt(best[j]);
		this.sum += acc / this.k;
		this.rows += 1;
	}

	/** Mean per-row k-NN distance over the session; 0 before the first row. */
	get score(): number {
		return this.rows ? this.sum / this.rows : 0;
	}

	get flagged(): boolean {
		return this.rows > 0 && this.score > this.threshold;
	}

	reset(): void {
		this.sum = 0;
		this.rows = 0;
	}
}

/**
 * Turns a live descriptor into per-cluster activation weights (§8.2): cosine similarity
 * to each cluster centroid, softmax, then EMA smoothing so the galaxy does not flicker.
 *
 * The softmax distribution says *which* cluster is closest; `strength` says whether the
 * input resembles the corpus at all, and everything reported is scaled by it. Nothing
 * downstream has to re-derive that: an activation of zero means "this is not birdsong",
 * which the previous version had no way to express.
 */
export class ActivationTracker {
	readonly activations: Float32Array;
	readonly similarity: Float32Array;
	private readonly vectors: Float32Array[];
	private readonly temperature: number;
	/** The sparse-input smoothing rate: the flicker-killer the EMA exists for. */
	private readonly smoothingBase: number;
	/**
	 * Onsets per second the listener is seeing right now, written every frame. The EMA
	 * is pace-aware: at 0.82 per update the time constant is ~5.6 updates — about 93 ms
	 * at the 60 fps the listener runs at — which is what kills flicker on slow input but
	 * leaves note-dense passages visibly behind the audio ("at fastest tempo the
	 * animations don't keep up"). Measured on the harness, four onsets a second is where
	 * a fast chorus sits, so the rate eases from the base toward 0.5 (≈ 2 updates,
	 * ~33 ms) as the onset count climbs to that, and relaxes back when it thins. The
	 * floor is never removed: 0.5 still kills single-frame flicker.
	 */
	onsetRate = 0;
	/**
	 * The browser's bridge into the learned space (docs/09 phase 2): the offline-fitted
	 * map that carries a live standardised 28-d descriptor to the standardised 32-d
	 * embedding, or null when the assets predate it — or when the map failed its
	 * held-out gate, in which case the 28-d path below is the honest one and stays.
	 * Two kinds ship: the original linear ridge (inline `w`/`b`) and the rff-ridge
	 * (weights from the f32 sidecar, attached by loadAssets — spacemap.py chose it on
	 * held-out recordings when the 47 k critic's space stopped being linearly
	 * recoverable: 0.7997 < the 0.8 gate, rff measures 0.93).
	 */
	private readonly mapW: Float32Array | null;
	private readonly mapB: Float32Array | null;
	private readonly rff: { R: Float32Array; phase: Float32Array; w: Float32Array } | null;
	private readonly rffZ: Float32Array | null;
	private readonly zMapped: Float32Array | null;
	/** 0..1 confidence that the input matches anything in the corpus. EMA-smoothed. */
	strength = 0;

	constructor(centroids: Centroids, spec: FeatureSpace, smoothing = 0.82) {
		this.smoothingBase = smoothing;
		this.temperature = spec.temperature || 0.12;
		const embedding = spec.embedding;
		const map = embedding?.map;
		const mapReady = Boolean(
			map && ('w' in map ? map.w?.length : map.kind === 'rff-ridge' && map.rff)
		);
		const useEmbed = Boolean(
			embedding &&
				mapReady &&
				embedding.mapQuality?.accepted !== false &&
				embedding.dims > 0 &&
				centroids.items.length &&
				centroids.items.every((c) => c.vector32?.length === embedding.dims)
		);
		if (useEmbed && embedding?.map) {
			// The galaxy lives in the critic's 32-d space; the live descriptor lives in
			// the 28-d one. The map is how a sound gets from here to there. These
			// centroids are already standardised embedding vectors — there is no raw
			// form to detect, unlike the 28-d path below.
			if ('w' in embedding.map) {
				this.mapW = Float32Array.from(embedding.map.w.flat());
				this.mapB = Float32Array.from(embedding.map.b);
				this.rff = null;
				this.rffZ = null;
			} else {
				const rff = embedding.map.rff;
				if (!rff) throw new Error('rff-ridge map without its sidecar weights');
				this.mapW = null;
				this.mapB = Float32Array.from(rff.b);
				this.rff = { R: rff.R, phase: rff.phase, w: rff.w };
				this.rffZ = new Float32Array(embedding.map.D);
			}
			this.zMapped = new Float32Array(embedding.dims);
			this.vectors = centroids.items.map((c) => Float32Array.from(c.vector32 as number[]));
		} else {
			this.mapW = null;
			this.mapB = null;
			this.rff = null;
			this.rffZ = null;
			this.zMapped = null;
			// KMeans runs on standardised descriptors, but tolerate raw vectors too.
			//
			// Decided on the **median** component, not on whether any single one is large. The
			// old test asked whether *some* component exceeded 12, which one three-point
			// cluster of outliers satisfied on its own — its worst component reached 14.87 —
			// and every centroid was then standardised a second time. That inverts the whole
			// matcher silently: cosines go negative, the exact-match rate falls from 26/44 to
			// 1/44, and nothing anywhere reports an error. A median is unmoved by one bad
			// cluster, and the two cases it has to tell apart are nowhere near each other:
			// standardised vectors sit around 0.6, raw descriptors an order of magnitude up.
			// Array.from, not .map: a Float32Array's map returns a Float32Array, which
			// flatMap does not flatten (it only flattens real arrays), and the median
			// would then be taken over typed arrays instead of numbers.
			const magnitudes = centroids.items
				.flatMap((c) => Array.from(c.vector, Math.abs))
				.sort((a, b) => a - b);
			const median = magnitudes[magnitudes.length >> 1] ?? 0;
			const looksRaw = median > 4;
			this.vectors = centroids.items.map((c) =>
				looksRaw ? standardise(Float32Array.from(c.vector), spec) : Float32Array.from(c.vector)
			);
		}
		this.activations = new Float32Array(centroids.items.length);
		this.similarity = new Float32Array(centroids.items.length);
	}

	/**
	 * The smoothing rate for the input's current pace: the base rate when sparse,
	 * easing toward 0.5 as the onset rate climbs to four a second (see `onsetRate`).
	 */
	private effectiveSmoothing(): number {
		const pace = Math.min(1, this.onsetRate / 4);
		return this.smoothingBase + (0.5 - this.smoothingBase) * pace;
	}

	/**
	 * @param zLive standardised live descriptor
	 * @param flatness the same descriptor's raw spectral flatness, before standardising —
	 *   the noise test needs the physical quantity, not its z-score
	 */
	update(zLive: Float32Array, flatness = 0): Float32Array {
		// When the galaxy was built in the embedding space, first carry the live
		// descriptor into it, then the same cosine the 28-d path uses.
		let query = zLive;
		if (this.mapW && this.mapB && this.zMapped) {
			// Linear map: z32 = z28 @ W + b.
			const dims32 = this.zMapped.length;
			const dims28 = zLive.length;
			for (let j = 0; j < dims32; j++) {
				let acc = this.mapB[j];
				for (let i = 0; i < dims28; i++) acc += zLive[i] * this.mapW[i * dims32 + j];
				this.zMapped[j] = acc;
			}
			query = this.zMapped;
		} else if (this.rff && this.rffZ && this.mapB && this.zMapped) {
			// RFF map: f = sqrt(2/D) cos(z28 @ R + phase); z32 = f @ w + b.
			const D = this.rffZ.length;
			const dims32 = this.zMapped.length;
			const dims28 = zLive.length;
			const scale = Math.sqrt(2 / D);
			for (let j = 0; j < D; j++) {
				let acc = this.rff.phase[j];
				for (let i = 0; i < dims28; i++) acc += zLive[i] * this.rff.R[i * D + j];
				this.rffZ[j] = scale * Math.cos(acc);
			}
			for (let o = 0; o < dims32; o++) {
				let acc = this.mapB[o];
				for (let j = 0; j < D; j++) acc += this.rffZ[j] * this.rff.w[j * dims32 + o];
				this.zMapped[o] = acc;
			}
			query = this.zMapped;
		}
		const k = this.vectors.length;
		let max = -Infinity;
		for (let i = 0; i < k; i++) {
			this.similarity[i] = cosine(query, this.vectors[i]);
			if (this.similarity[i] > max) max = this.similarity[i];
		}
		// Two tests, and both have to pass: how close the nearest cluster is, and whether
		// the input is a tone at all. Either one alone lets noise through.
		const tonal = 1 - smoothstep(TONAL_FLOOR, TONAL_CEILING, flatness);
		const target = smoothstep(MATCH_FLOOR, MATCH_CEILING, max) * tonal;
		const smoothing = this.effectiveSmoothing();
		this.strength = smoothing * this.strength + (1 - smoothing) * target;

		let sum = 0;
		const exp = new Float32Array(k);
		for (let i = 0; i < k; i++) {
			exp[i] = Math.exp((this.similarity[i] - max) / this.temperature);
			sum += exp[i];
		}
		for (let i = 0; i < k; i++) {
			const scaled = (exp[i] / sum) * this.strength;
			this.activations[i] = smoothing * this.activations[i] + (1 - smoothing) * scaled;
		}
		return this.activations;
	}

	/**
	 * Pulls everything toward zero — used when the input goes quiet.
	 *
	 * The floor matters: an exponential decay never reaches zero, and a residual
	 * activation of 1e-7 is still enough to keep a node's label open and its points
	 * faintly lit. Below a thousandth it is snapped to nothing.
	 *
	 * The rate follows the pace like the attack does: in a dense passage the gaps
	 * between notes are short, and a slow release would smear one note's knot into the
	 * next — the same lag the pace-aware EMA fixes on the way up.
	 */
	decay(): Float32Array {
		const smoothing = this.effectiveSmoothing();
		this.strength *= smoothing;
		if (this.strength < 1e-3) this.strength = 0;
		for (let i = 0; i < this.activations.length; i++) {
			const v = this.activations[i] * smoothing;
			this.activations[i] = v < 1e-3 ? 0 : v;
		}
		// `similarity` is a measurement, not a level: it holds the last cosine actually
		// computed. Nothing displays it unless the reading is confident, and decaying it
		// would corrupt the ranking `best()` depends on.
		return this.activations;
	}

	/**
	 * Nearest centroid by raw cosine.
	 *
	 * Ranked on `similarity` rather than on `activations` because the activations are
	 * scaled by `strength`, and below the match floor every one of them is zero — an
	 * argmax over that returns cluster 0 for any unrecognised sound, which is a
	 * confident wrong answer rather than no answer. Softmax is monotonic in similarity,
	 * so above the floor the two rankings are identical. Callers that need "is this
	 * anything at all" read `strength`.
	 */
	best(): { index: number; similarity: number } {
		let index = 0;
		for (let i = 1; i < this.similarity.length; i++) {
			if (this.similarity[i] > this.similarity[index]) index = i;
		}
		return { index, similarity: this.similarity[index] ?? 0 };
	}
}

/**
 * How brightly each *individual* point responds, rather than each cluster.
 *
 * The reported match stays where the contract puts it: 28-d cosine against the cluster
 * centroids, in `ActivationTracker`. This is a second, cheaper pass whose only output is
 * a brightness. It projects the live descriptor into the reduced space the pipeline
 * shipped in `point-features.f32`, then takes the cosine of every point against it — at
 * the shipped corpus that is 4287 x 8 multiply-adds a frame, which is less work than the
 * FFT that produced the descriptor.
 *
 * Without that asset it degrades to a deterministic per-point offset of the cluster's
 * activation, which is not a measurement but does keep a knot from switching on as one
 * flat blob.
 */
export class PointTracker {
	readonly activation: Float32Array;
	private readonly affinity: Float32Array;
	private readonly features: Float32Array | null;
	private readonly dims: number;
	private readonly clusterOf: Int32Array;
	private readonly centroidsLo: Float32Array | null;
	private readonly zLo: Float32Array;
	private readonly smoothing: number;

	constructor(assets: BirdyAssets, smoothing = 0.7) {
		const n = assets.points.n;
		this.smoothing = smoothing;
		this.activation = new Float32Array(n);
		this.affinity = new Float32Array(n);
		this.dims = assets.pointFeatureDims;
		this.features = assets.pointFeatures;
		this.clusterOf = Int32Array.from(assets.points.clusterId);
		this.zLo = new Float32Array(this.dims);

		const lo = assets.centroids.items.map((c) => c.featuresLo);
		this.centroidsLo =
			this.features && lo.every((v) => v?.length === this.dims)
				? Float32Array.from(lo.flatMap((v) => Array.from(v as ArrayLike<number>)))
				: null;

		if (!this.centroidsLo) {
			// deterministic per-point offset, matching the shader's own seed
			for (let i = 0; i < n; i++) this.affinity[i] = ((i * 2654435761) % 1000) / 1000;
		}
	}

	get measured(): boolean {
		return this.centroidsLo !== null;
	}

	/**
	 * Projects the live descriptor into the reduced space by expressing it as the
	 * activation-weighted mix of the cluster centroids it matched. The pipeline's
	 * projection matrix is not shipped — only the projected vectors are — so this
	 * reconstructs the query from the same k anchors both sides already agree on.
	 */
	update(activations: Float32Array, strength = 1): Float32Array {
		const n = this.activation.length;
		const d = this.dims;
		const centroids = this.centroidsLo;
		// Below this there is nothing to show, and continuing would be actively wrong:
		// the query direction below is renormalised, so a vanishing activation still
		// yields a full-length unit vector and would keep the last matched knot glowing.
		if (strength < 1e-3) return this.decay();

		if (!centroids) {
			for (let i = 0; i < n; i++) {
				const act = activations[this.clusterOf[i]] ?? 0;
				const target = act * (0.35 + 0.65 * this.affinity[i]);
				this.activation[i] = this.smoothing * this.activation[i] + (1 - this.smoothing) * target;
			}
			return this.activation;
		}

		this.zLo.fill(0);
		const k = activations.length;
		for (let c = 0; c < k; c++) {
			const w = activations[c];
			if (w < 1e-4) continue;
			const off = c * d;
			for (let j = 0; j < d; j++) this.zLo[j] += w * centroids[off + j];
		}
		let norm = 0;
		for (let j = 0; j < d; j++) norm += this.zLo[j] * this.zLo[j];
		norm = Math.sqrt(norm);
		if (norm < 1e-6) return this.decay();
		for (let j = 0; j < d; j++) this.zLo[j] /= norm;

		// Both sides are unit vectors, so the dot product is the cosine directly. Mapped
		// through a steep ramp: below 0.9 a point is not really this sound, and without the
		// ramp the whole cloud glows dimly instead of the matched region standing out.
		const features = this.features as Float32Array;
		for (let i = 0; i < n; i++) {
			const off = i * d;
			let dot = 0;
			for (let j = 0; j < d; j++) dot += features[off + j] * this.zLo[j];
			const affinity = Math.max(0, (dot - 0.9) / 0.1);
			const clusterAct = activations[this.clusterOf[i]] ?? 0;
			// The cluster activation sets how loud the response is, the point's own
			// similarity sets which members of it actually light. Both are multiplied by
			// the match strength, so an input that resembles nothing lights nothing.
			// The `0.08` is what a point gets for resembling the sound while its own cluster
			// is not responding. It used to be 0.25, which on a 44-cluster galaxy read as a
			// faint sympathetic shimmer and on a 176-cluster one reads as half the sky
			// lighting up when one bird sings: the reduced space keeps 77 % of the variance,
			// so "close in 8-d" is a much weaker statement than "this is the same call".
			// The cluster floor went the other way: at 0.2 only the few members whose own
			// 8-d feature matched lit at all, and a responding knot showed as three bright
			// points inside a knot-sized patch of dark ones — "the inactive ones don't get
			// active". At 0.45 the knot answers as one region (its other knots sit at
			// clusterAct ≈ 0, so nothing else lights), and the affinity still ranks the
			// members inside it.
			const target = Math.min(
				1,
				Math.max(clusterAct * 0.45, affinity * affinity) * (0.08 + clusterAct * 3) * strength
			);
			this.activation[i] = this.smoothing * this.activation[i] + (1 - this.smoothing) * target;
		}
		return this.activation;
	}

	decay(): Float32Array {
		for (let i = 0; i < this.activation.length; i++) {
			const v = this.activation[i] * this.smoothing;
			this.activation[i] = v < 2e-3 ? 0 : v;
		}
		return this.activation;
	}

	/**
	 * Lights one whole cluster, for a scheduled note nothing is being matched against.
	 *
	 * The spread is wide on purpose. A scheduled note tells us the cluster and nothing
	 * about which of its members the rendition resembles, so lighting them evenly would
	 * assert a uniformity we have not measured — and would put a solid disc where the
	 * rest of the visualisation shows a spray of individual points.
	 */
	pulseCluster(cluster: number, strength: number): void {
		for (let i = 0; i < this.activation.length; i++) {
			if (this.clusterOf[i] !== cluster) continue;
			const jitter = 0.15 + 0.85 * (((i * 2654435761) % 1000) / 1000);
			this.activation[i] = Math.max(this.activation[i], strength * jitter);
		}
	}
}

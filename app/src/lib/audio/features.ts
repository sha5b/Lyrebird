import { RealFft } from './fft.ts';
import type { Centroids, FeatureSpace } from '$lib/data/types';

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

	/** True while the input is loud enough to be worth projecting into the galaxy. */
	get active(): boolean {
		const last = this.history[this.history.length - 1];
		return Boolean(last && last.rms > 1e-4 && last.rms > 0.05 * this.maxRms);
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
		const gate = Math.max(1e-4, 0.05 * this.maxRms);
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
 * Turns a live descriptor into per-cluster activation weights (§8.2): cosine similarity
 * to each cluster centroid, softmax, then EMA smoothing so the galaxy does not flicker.
 */
export class ActivationTracker {
	readonly activations: Float32Array;
	readonly similarity: Float32Array;
	private readonly vectors: Float32Array[];
	private readonly temperature: number;
	private readonly smoothing: number;

	constructor(centroids: Centroids, spec: FeatureSpace, smoothing = 0.82) {
		this.smoothing = smoothing;
		this.temperature = spec.temperature || 0.12;
		// KMeans runs on standardised descriptors, but tolerate raw vectors too.
		const looksRaw = centroids.items.some((c) => c.vector.some((v) => Math.abs(v) > 12));
		this.vectors = centroids.items.map((c) =>
			looksRaw ? standardise(Float32Array.from(c.vector), spec) : Float32Array.from(c.vector)
		);
		this.activations = new Float32Array(centroids.items.length);
		this.similarity = new Float32Array(centroids.items.length);
	}

	update(zLive: Float32Array): Float32Array {
		const k = this.vectors.length;
		let max = -Infinity;
		for (let i = 0; i < k; i++) {
			this.similarity[i] = cosine(zLive, this.vectors[i]);
			if (this.similarity[i] > max) max = this.similarity[i];
		}
		let sum = 0;
		const exp = new Float32Array(k);
		for (let i = 0; i < k; i++) {
			exp[i] = Math.exp((this.similarity[i] - max) / this.temperature);
			sum += exp[i];
		}
		for (let i = 0; i < k; i++) {
			const target = exp[i] / sum;
			this.activations[i] = this.smoothing * this.activations[i] + (1 - this.smoothing) * target;
		}
		return this.activations;
	}

	/** Pulls all activations toward zero — used when the input goes quiet. */
	decay(): Float32Array {
		for (let i = 0; i < this.activations.length; i++) this.activations[i] *= this.smoothing;
		return this.activations;
	}

	best(): { index: number; similarity: number } {
		let index = 0;
		for (let i = 1; i < this.activations.length; i++) {
			if (this.activations[i] > this.activations[index]) index = i;
		}
		return { index, similarity: this.similarity[index] ?? 0 };
	}
}

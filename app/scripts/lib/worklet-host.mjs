/**
 * Runs the real AudioWorklet processor outside a browser.
 *
 * `src/lib/audio/worklets/syrinx-processor.js` is loaded under stubbed
 * AudioWorkletGlobalScope globals and pumped block by block, so the browser DSP can be
 * measured and regression-tested from Node. Shared by scripts/render-syllable.mjs and
 * scripts/verify-features.mjs.
 */
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
export const APP_ROOT = resolve(here, '../..');
export const REPO_ROOT = resolve(APP_ROOT, '..');
export const SAMPLE_RATE = 48000;
const BLOCK = 128;

let ProcessorCtor = null;

/** Installs the worklet globals and loads the processor. Safe to call more than once. */
async function loadProcessor() {
	if (ProcessorCtor) return ProcessorCtor;

	globalThis.sampleRate = SAMPLE_RATE;
	globalThis.currentTime = 0;
	globalThis.currentFrame = 0;
	globalThis.registerProcessor = (_name, ctor) => {
		ProcessorCtor = ctor;
	};
	globalThis.AudioWorkletProcessor = class {
		constructor() {
			this.port = {
				onmessage: null,
				postMessage: () => {},
				/** test helper: deliver a message the way the main thread would */
				send(data) {
					this.onmessage?.({ data });
				}
			};
		}
	};

	await import('../../src/lib/audio/worklets/syrinx-processor.js');
	if (!ProcessorCtor) throw new Error('the worklet did not call registerProcessor');
	return ProcessorCtor;
}

export function loadInventory() {
	return JSON.parse(readFileSync(join(REPO_ROOT, 'data/inventory.json'), 'utf8'));
}

/** The generated asset, or null when the pipeline has not been run. */
export function loadGenerated(name) {
	const path = join(APP_ROOT, 'static/birdy', name);
	return existsSync(path) ? JSON.parse(readFileSync(path, 'utf8')) : null;
}

/**
 * Renders a syllable sequence through the worklet.
 * @returns {{signal: Float32Array, marks: {syllable: object, start: number}[]}}
 */
export async function render(syllables, gaps = [], { calibration = null, tail = 0.35, gain = 1 } = {}) {
	const Ctor = await loadProcessor();
	globalThis.currentTime = 0;
	globalThis.currentFrame = 0;
	const processor = new Ctor();
	if (calibration) processor.port.send({ type: 'calibration', calibration });

	let cursor = 0.02;
	const marks = [];
	syllables.forEach((syllable, i) => {
		processor.port.send({ type: 'note', when: cursor, syllable, gain });
		marks.push({ syllable, start: cursor });
		cursor += syllable.dur + (gaps[i] ?? 0.06);
	});

	const total = Math.ceil((cursor + tail) * SAMPLE_RATE);
	const signal = new Float32Array(total);
	const out = [[new Float32Array(BLOCK)]];
	for (let offset = 0; offset < total; offset += BLOCK) {
		out[0][0].fill(0);
		processor.process([], out, {});
		signal.set(out[0][0].subarray(0, Math.min(BLOCK, total - offset)), offset);
		globalThis.currentFrame += BLOCK;
		globalThis.currentTime = globalThis.currentFrame / SAMPLE_RATE;
	}
	return { signal, marks };
}

export function rms(signal, from = 0, to = signal.length) {
	const start = Math.max(0, Math.floor(from));
	const end = Math.min(signal.length, Math.floor(to));
	let acc = 0;
	for (let i = start; i < end; i++) acc += signal[i] * signal[i];
	return Math.sqrt(acc / Math.max(1, end - start));
}

/** Requested pitch at time fraction u, interpolated exactly as the worklet does. */
export function contourAt(syllable, u) {
	const c = syllable.contour;
	if (u <= c[0][0]) return c[0][1];
	if (u >= c[c.length - 1][0]) return c[c.length - 1][1];
	for (let i = 0; i < c.length - 1; i++) {
		const [t0, h0] = c[i];
		const [t1, h1] = c[i + 1];
		if (u <= t1) {
			const frac = (u - t0) / Math.max(1e-6, t1 - t0);
			return Math.exp(Math.log(h0) + (Math.log(h1) - Math.log(h0)) * frac);
		}
	}
	return c[c.length - 1][1];
}

/**
 * Frequency of a segment by counting rising zero crossings with hysteresis. Autocorrelation
 * was tried first and reported subharmonics on clean tones, which a near-sinusoid does not
 * have; the band follows a decaying peak so a fast amplitude decay is not undercounted.
 */
export function measureF0(signal, from, to) {
	const start = Math.max(0, Math.floor(from));
	const end = Math.min(signal.length, Math.floor(to));
	const n = end - start;
	if (n < 128) return 0;
	let mean = 0;
	let peak = 0;
	for (let i = start; i < end; i++) mean += signal[i];
	mean /= n;
	for (let i = start; i < end; i++) peak = Math.max(peak, Math.abs(signal[i] - mean));
	if (peak < 1e-5) return 0;

	let envelope = peak * 0.5;
	let armed = false;
	let crossings = 0;
	let first = -1;
	let last = -1;
	for (let i = start; i < end; i++) {
		const v = signal[i] - mean;
		envelope = Math.max(Math.abs(v), envelope * 0.9995);
		const band = envelope * 0.2;
		if (v < -band) armed = true;
		else if (armed && v > band) {
			armed = false;
			crossings++;
			if (first < 0) first = i;
			last = i;
		}
	}
	if (crossings < 2) return 0;
	return ((crossings - 1) * SAMPLE_RATE) / (last - first);
}

export function writeWav(path, signal) {
	const pcm = Buffer.alloc(signal.length * 2);
	let peak = 0;
	for (const s of signal) peak = Math.max(peak, Math.abs(s));
	const scale = peak > 0 ? 0.89 / peak : 1;
	for (let i = 0; i < signal.length; i++) {
		pcm.writeInt16LE(
			Math.max(-32768, Math.min(32767, Math.round(signal[i] * scale * 32767))),
			i * 2
		);
	}
	const header = Buffer.alloc(44);
	header.write('RIFF', 0);
	header.writeUInt32LE(36 + pcm.length, 4);
	header.write('WAVE', 8);
	header.write('fmt ', 12);
	header.writeUInt32LE(16, 16);
	header.writeUInt16LE(1, 20);
	header.writeUInt16LE(1, 22);
	header.writeUInt32LE(SAMPLE_RATE, 24);
	header.writeUInt32LE(SAMPLE_RATE * 2, 28);
	header.writeUInt16LE(2, 32);
	header.writeUInt16LE(16, 34);
	header.write('data', 36);
	header.writeUInt32LE(pcm.length, 40);
	writeFileSync(path, Buffer.concat([header, pcm]));
}

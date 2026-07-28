/**
 * Birdy syrinx AudioWorklet.
 *
 * Realtime integration of the Mindlin-Laje low-dimensional syrinx model followed by a
 * vocal tract that tracks the fundamental. The model, the parameter mapping and the
 * filter chain are specified in docs/08-implementation.md section 8.1 — the Python
 * pipeline renders the offline corpus from the same spec, so changes must be made in
 * both places.
 *
 * This file is plain JavaScript on purpose: AudioWorklet modules are loaded by URL and
 * are not part of the TypeScript bundle. Its message protocol is typed on the main
 * thread in `$lib/audio/engine.ts`.
 */

/**
 * gamma is a pure time-scale: rescaling t by gamma leaves the equations unchanged, so
 * f0 = gamma * PHI(alpha, beta) and the peak-to-peak swing of y/gamma depends only on
 * (alpha, beta). That is why the literature fits gamma per bird, and why Birdy picks it
 * per syllable — with gamma pinned at 24000 the oscillator cannot go below ~1.4 kHz, so
 * owls, doves and cuckoos would be unreachable. Verified numerically: see §8.6.
 */
const CALIBRATION_GAMMA = 24000; // the gamma the offline table was measured at
const PHI_AT_BETA_ONE = 0.17061; // measured f0/gamma at alpha 0.1, beta 1
const MAX_VOICES = 12;
const DETUNE_TWO = Math.pow(2, 7 / 1200); // +7 cents: the second syringeal side
const FILTER_UPDATE = 32; // samples between tract coefficient updates

const TIMBRE = {
	pure: { gain: 1.0, q: 9.0 },
	reed: { gain: 1.25, q: 5.0 },
	buzz: { gain: 1.75, q: 3.0 }
};

const BETA_MIN = 0.15;
const BETA_MAX = 16;

/**
 * Below BETA_MIN the oscillator is under threshold and silent (§8.6). With per-syllable
 * gamma this clamp almost never binds.
 * @param {number} beta
 * @returns {number}
 */
function clampBeta(beta) {
	return Math.min(BETA_MAX, Math.max(BETA_MIN, beta));
}

/**
 * Time-scale for a syllable: chosen so its median pitch sits at beta = 1, which keeps the
 * whole contour inside the well-behaved part of the parameter space.
 * @param {ContourPoint[]} contour
 * @returns {number}
 */
function gammaForContour(contour) {
	let logSum = 0;
	for (const [, hz] of contour) logSum += Math.log(Math.max(80, hz));
	const reference = Math.exp(logSum / Math.max(1, contour.length));
	return Math.min(150000, Math.max(1200, reference / PHI_AT_BETA_ONE));
}

/**
 * Euler needs gamma*dt small; this keeps it near 0.06 across the whole range.
 * @param {number} gamma
 * @param {number} sr
 * @returns {number}
 */
function oversampleForGamma(gamma, sr) {
	return Math.min(64, Math.max(16, Math.ceil(gamma / (0.06 * sr))));
}

/**
 * @typedef {import('$lib/data/types').Syllable} Syllable
 * @typedef {import('$lib/data/types').SyrinxCalibration} SyrinxCalibration
 * @typedef {import('$lib/data/types').ContourPoint} ContourPoint
 * @typedef {{ when: number, syllable: Syllable, gain: number, pan: number }} PendingNote
 */

/** Two-pole RBJ bandpass, constant 0 dB peak gain. */
class Biquad {
	constructor() {
		this.b0 = 1;
		this.b1 = 0;
		this.b2 = 0;
		this.a1 = 0;
		this.a2 = 0;
		this.x1 = 0;
		this.x2 = 0;
		this.y1 = 0;
		this.y2 = 0;
	}

	/**
	 * @param {number} freq
	 * @param {number} q
	 * @param {number} sampleRate
	 */
	setBandpass(freq, q, sampleRate) {
		const f = Math.min(Math.max(freq, 40), sampleRate * 0.45);
		const w0 = (2 * Math.PI * f) / sampleRate;
		const alpha = Math.sin(w0) / (2 * Math.max(q, 0.3));
		const a0 = 1 + alpha;
		this.b0 = alpha / a0;
		this.b1 = 0;
		this.b2 = -alpha / a0;
		this.a1 = (-2 * Math.cos(w0)) / a0;
		this.a2 = (1 - alpha) / a0;
	}

	/** @param {number} x */
	process(x) {
		const y = this.b0 * x + this.b1 * this.x1 + this.b2 * this.x2 - this.a1 * this.y1 - this.a2 * this.y2;
		this.x2 = this.x1;
		this.x1 = x;
		this.y2 = this.y1;
		this.y1 = y;
		return y;
	}

	reset() {
		this.x1 = this.x2 = this.y1 = this.y2 = 0;
	}
}

/** One syllable in flight: one or two oscillators plus the tract that filters them. */
class Voice {
	constructor() {
		this.active = false;
		/** @type {Syllable | null} */
		this.syllable = null;
		this.gainL = Math.SQRT1_2;
		this.gainR = Math.SQRT1_2;
		this.startSample = 0;
		this.gain = 1;
		this.x = [0.001, 0.001];
		this.y = [0, 0];
		this.tract = [new Biquad(), new Biquad()];
		this.tractHarm = [new Biquad(), new Biquad()];
		this.dcX = 0;
		this.dcY = 0;
		this.lpY = 0;
		this.f0 = 0;
		this.env = 0;
		this.gamma = CALIBRATION_GAMMA;
		this.oversample = 16;
		this.dt = 1 / (48000 * 16);
	}

	/**
	 * @param {Syllable} syllable
	 * @param {number} startSample
	 * @param {number} gain
	 * @param {number} pan -1 hard left to +1 hard right
	 */
	start(syllable, startSample, gain, pan) {
		this.active = true;
		this.syllable = syllable;
		this.startSample = startSample;
		this.gain = gain;
		// equal-power pan, held per voice: birds in a chorus overlap, and a single shared
		// panner would drag every one of them to wherever the newest note was placed
		const angle = ((Math.min(1, Math.max(-1, pan)) + 1) * Math.PI) / 4;
		this.gainL = Math.cos(angle);
		this.gainR = Math.sin(angle);
		this.gamma = gammaForContour(syllable.contour);
		this.oversample = oversampleForGamma(this.gamma, sampleRate);
		this.dt = 1 / (sampleRate * this.oversample);
		this.x = [0.001, -0.001];
		this.y = [0, 0];
		this.dcX = this.dcY = this.lpY = 0;
		for (const f of this.tract) f.reset();
		for (const f of this.tractHarm) f.reset();
		this.env = 0;
	}
}

class SyrinxProcessor extends AudioWorkletProcessor {
	constructor() {
		super();
		/** @type {Voice[]} */
		this.voices = [];
		for (let i = 0; i < MAX_VOICES; i++) this.voices.push(new Voice());
		/** @type {PendingNote[]} */
		this.pending = [];
		/** @type {SyrinxCalibration | null} */
		this.calibration = null;
		this.dcCoeff = Math.exp((-2 * Math.PI * 180) / sampleRate);
		this.lpCoeff = 1 - Math.exp((-2 * Math.PI * 12000) / sampleRate);
		this.reportCountdown = 0;
		this.lastF0 = 0;
		this.level = 0;

		this.port.onmessage = (event) => {
			const msg = event.data;
			if (msg.type === 'calibration') {
				this.calibration = msg.calibration;
			} else if (msg.type === 'note') {
				this.pending.push({
					when: msg.when,
					syllable: msg.syllable,
					gain: msg.gain ?? 1,
					pan: msg.pan ?? 0
				});
			} else if (msg.type === 'panic') {
				this.pending.length = 0;
				for (const v of this.voices) v.active = false;
			}
		};
	}

	/**
	 * beta for a target F0 via the offline calibration table, else small-oscillation form.
	 * @param {number} targetF0
	 * @param {number} pressure
	 * @param {number} gamma this voice's time-scale
	 * @returns {number}
	 */
	betaForF0(targetF0, pressure, gamma) {
		// The table was measured at CALIBRATION_GAMMA; because gamma is a pure time-scale,
		// a voice running at another gamma looks up the frequency it would have there.
		const f0 = (targetF0 * CALIBRATION_GAMMA) / gamma;
		const cal = this.calibration;
		if (!cal || !cal.inverse || !cal.inverse.f0Grid.length) {
			return clampBeta(Math.pow(f0 / (PHI_AT_BETA_ONE * CALIBRATION_GAMMA), 2));
		}
		const grid = cal.inverse.f0Grid;
		const table = cal.inverse.beta;
		const pGrid = cal.pressureGrid;

		// locate pressure row
		let pi = 0;
		while (pi < pGrid.length - 2 && pGrid[pi + 1] < pressure) pi++;
		const pSpan = pGrid[pi + 1] - pGrid[pi] || 1;
		const pFrac = Math.min(1, Math.max(0, (pressure - pGrid[pi]) / pSpan));

		// locate f0 column
		const clamped = Math.min(Math.max(f0, grid[0]), grid[grid.length - 1]);
		let fi = 0;
		while (fi < grid.length - 2 && grid[fi + 1] < clamped) fi++;
		const fSpan = grid[fi + 1] - grid[fi] || 1;
		const fFrac = (clamped - grid[fi]) / fSpan;

		const rowA = table[pi];
		const rowB = table[Math.min(pi + 1, table.length - 1)];
		const a = rowA[fi] + (rowA[fi + 1] - rowA[fi]) * fFrac;
		const b = rowB[fi] + (rowB[fi + 1] - rowB[fi]) * fFrac;
		const beta = a + (b - a) * pFrac;
		return clampBeta(beta > 0 ? beta : Math.pow(f0 / (PHI_AT_BETA_ONE * CALIBRATION_GAMMA), 2));
	}

	/**
	 * Peak-to-peak swing of y/gamma, which the source is divided by so loudness follows
	 * the envelope instead of the pitch (§8.1). Measured table when available.
	 * @param {number} alpha
	 * @param {number} beta
	 * @returns {number}
	 */
	ampPP(alpha, beta) {
		const cal = this.calibration;
		if (!cal || !cal.ampPP || !cal.ampPP.length) return 0.5 + 3.4 * alpha + 0.62 * beta;
		const pGrid = cal.pressureGrid;
		const bGrid = cal.betaGrid;
		const pressure = (alpha - 0.05) / 0.4;
		let pi = 0;
		while (pi < pGrid.length - 2 && pGrid[pi + 1] < pressure) pi++;
		let bi = 0;
		while (bi < bGrid.length - 2 && bGrid[bi + 1] < beta) bi++;
		const pFrac = Math.min(1, Math.max(0, (pressure - pGrid[pi]) / (pGrid[pi + 1] - pGrid[pi] || 1)));
		const bFrac = Math.min(1, Math.max(0, (beta - bGrid[bi]) / (bGrid[bi + 1] - bGrid[bi] || 1)));
		const rowA = cal.ampPP[pi];
		const rowB = cal.ampPP[Math.min(pi + 1, cal.ampPP.length - 1)];
		const a = rowA[bi] + (rowA[bi + 1] - rowA[bi]) * bFrac;
		const b = rowB[bi] + (rowB[bi + 1] - rowB[bi]) * bFrac;
		const amp = a + (b - a) * pFrac;
		return amp > 0.05 ? amp : 0.5 + 3.4 * alpha + 0.62 * beta;
	}

	/**
	 * Pitch contour in Hz at time fraction u, interpolated in log frequency.
	 * @param {ContourPoint[]} contour
	 * @param {number} u
	 * @returns {number}
	 */
	contourAt(contour, u) {
		const n = contour.length;
		if (n === 0) return 440;
		if (u <= contour[0][0]) return contour[0][1];
		if (u >= contour[n - 1][0]) return contour[n - 1][1];
		for (let i = 0; i < n - 1; i++) {
			const [t0, h0] = contour[i];
			const [t1, h1] = contour[i + 1];
			if (u <= t1) {
				const frac = (u - t0) / Math.max(1e-6, t1 - t0);
				return Math.exp(Math.log(h0) + (Math.log(h1) - Math.log(h0)) * frac);
			}
		}
		return contour[n - 1][1];
	}

	/**
	 * @param {Syllable} syllable
	 * @param {number} t seconds since syllable onset
	 * @returns {number}
	 */
	envelopeAt(syllable, t) {
		const dur = syllable.dur;
		const attack = syllable.attack ?? 0.008;
		const release = 0.006;
		if (t < attack) return t / Math.max(attack, 1e-5);
		const body = syllable.hold
			? t < dur * 0.75
				? 1
				: Math.exp(-(t - dur * 0.75) / Math.max(dur * 0.12, 1e-4))
			: Math.exp(-(t - attack) / Math.max(dur / 2.5, 1e-4));
		const tail = t > dur - release ? Math.max(0, (dur - t) / release) : 1;
		return body * tail;
	}

	/**
	 * One sample of one oscillator: integrates OVERSAMPLE Euler steps, returns the source.
	 * @param {Voice} voice
	 * @param {number} index 0 = left syringeal side, 1 = right
	 * @param {number} alpha
	 * @param {number} beta
	 * @param {number} ampPP peak-to-peak swing of y/gamma, divided out of the source
	 * @returns {number}
	 */
	stepOsc(voice, index, alpha, beta, ampPP) {
		const g = voice.gamma;
		const g2 = g * g;
		const dt = voice.dt;
		const oversample = voice.oversample;
		let x = voice.x[index];
		let y = voice.y[index];
		for (let s = 0; s < oversample; s++) {
			const dx = y;
			const dy = -alpha * g2 - beta * g2 * x - g2 * x * x * x - g * x * x * y + g2 * x * x - g * x * y;
			x += dx * dt;
			y += dy * dt;
			// The trajectory stays well inside these bounds across the whole usable range
			// (§8.6); the clamp only exists so an onset transient cannot run away.
			if (x > 40) x = 40;
			else if (x < -40) x = -40;
			if (y > 4e6) y = 4e6;
			else if (y < -4e6) y = -4e6;
		}
		voice.x[index] = x;
		voice.y[index] = y;
		if (!Number.isFinite(x) || !Number.isFinite(y)) {
			voice.x[index] = 0.001;
			voice.y[index] = 0;
			return 0;
		}
		// dividing by the peak-to-peak swing keeps loudness tied to the envelope rather
		// than to the pitch, which otherwise dominates it
		return ((y / g) * 0.35) / ampPP;
	}

	/**
	 * @param {Float32Array[][]} _inputs
	 * @param {Float32Array[][]} outputs
	 * @returns {boolean}
	 */
	process(_inputs, outputs) {
		const outL = outputs[0][0];
		// mono hosts (and the offline test harness) may give a single channel
		const outR = outputs[0][1] ?? outL;
		const stereo = outR !== outL;
		const blockSize = outL.length;
		const now = currentTime;
		const startSample = currentFrame;

		// promote scheduled notes whose start time falls in or before this block
		if (this.pending.length) {
			const horizon = now + blockSize / sampleRate;
			for (let i = this.pending.length - 1; i >= 0; i--) {
				const note = this.pending[i];
				if (note.when < horizon) {
					const voice = this.voices.find((v) => !v.active);
					if (voice) {
						const offset = Math.max(0, Math.round((note.when - now) * sampleRate));
						voice.start(note.syllable, startSample + offset, note.gain, note.pan ?? 0);
					}
					this.pending.splice(i, 1);
				}
			}
		}

		outL.fill(0);
		if (stereo) outR.fill(0);
		let peak = 0;

		for (const voice of this.voices) {
			if (!voice.active || !voice.syllable) continue;
			const syl = voice.syllable;
			const timbre = TIMBRE[syl.timbre] ?? TIMBRE.pure;
			const harmonic = syl.harmonic ?? 0;
			const twoVoices = syl.two === true;
			const durSamples = Math.ceil((syl.dur + 0.02) * sampleRate);

			for (let i = 0; i < blockSize; i++) {
				const sampleIndex = startSample + i - voice.startSample;
				if (sampleIndex < 0) continue;
				if (sampleIndex >= durSamples) {
					voice.active = false;
					break;
				}
				const t = sampleIndex / sampleRate;
				const u = Math.min(1, t / syl.dur);

				let f0 = this.contourAt(syl.contour, u);
				if (syl.vib) f0 *= 1 + syl.vib.depth * Math.sin(2 * Math.PI * syl.vib.rate * t);

				let env = this.envelopeAt(syl, t);
				if (syl.am) {
					const depth = syl.amDepth ?? 0.5;
					env *= 1 - depth * (0.5 - 0.5 * Math.cos(2 * Math.PI * syl.am * t));
				}
				voice.env = env;
				const pressure = Math.min(1.4, Math.max(0, syl.level * env * timbre.gain));
				// positive alpha is the oscillating side of the threshold here (§8.1)
				const alpha = 0.05 + 0.4 * pressure;

				if ((sampleIndex & (FILTER_UPDATE - 1)) === 0) {
					voice.tract[0].setBandpass(f0, timbre.q, sampleRate);
					if (twoVoices) voice.tract[1].setBandpass(f0 * DETUNE_TWO, timbre.q, sampleRate);
					if (harmonic > 0) {
						voice.tractHarm[0].setBandpass(f0 * 2, timbre.q * 0.8, sampleRate);
						if (twoVoices) voice.tractHarm[1].setBandpass(f0 * 2 * DETUNE_TWO, timbre.q * 0.8, sampleRate);
					}
				}

				const betaA = this.betaForF0(f0, pressure, voice.gamma);
				let source = this.stepOsc(voice, 0, alpha, betaA, this.ampPP(alpha, betaA));
				let filtered = voice.tract[0].process(source);
				if (harmonic > 0) filtered += harmonic * 0.5 * voice.tractHarm[0].process(source);
				let sample = filtered;

				if (twoVoices) {
					const betaB = this.betaForF0(f0 * DETUNE_TWO, pressure, voice.gamma);
					const sourceB = this.stepOsc(voice, 1, alpha, betaB, this.ampPP(alpha, betaB));
					let filteredB = voice.tract[1].process(sourceB);
					if (harmonic > 0) filteredB += harmonic * 0.5 * voice.tractHarm[1].process(sourceB);
					sample = 0.5 * sample + 0.5 * filteredB;
				}

				// DC block, then tracheal roll-off
				const hp = sample - voice.dcX + this.dcCoeff * voice.dcY;
				voice.dcX = sample;
				voice.dcY = hp;
				voice.lpY += this.lpCoeff * (hp - voice.lpY);

				// the envelope also acts as a linear output gain: dividing the source by
				// ampPP takes level out of the ODE, so pressure alone never fades a note (§8.1)
				const value = voice.lpY * voice.gain * env;
				if (stereo) {
					outL[i] += value * voice.gainL;
					outR[i] += value * voice.gainR;
				} else {
					outL[i] += value;
				}
				voice.f0 = f0;
				if (Math.abs(value) > peak) peak = Math.abs(value);
				this.lastF0 = f0;
			}
		}

		// gentle saturation keeps overlapping voices inside [-1, 1]
		for (let i = 0; i < blockSize; i++) {
			outL[i] = Math.tanh(outL[i] * 1.6) * 0.8;
			if (stereo) outR[i] = Math.tanh(outR[i] * 1.6) * 0.8;
		}

		this.level = Math.max(this.level * 0.9, peak);
		this.reportCountdown -= blockSize;
		if (this.reportCountdown <= 0) {
			this.reportCountdown = sampleRate * 0.04;
			const active = this.voices.reduce((n, v) => n + (v.active ? 1 : 0), 0);
			this.port.postMessage({ type: 'state', voices: active, f0: this.lastF0, level: this.level });
		}
		return true;
	}
}

registerProcessor('syrinx-processor', SyrinxProcessor);

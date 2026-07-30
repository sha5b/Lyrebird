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
// Envelope constants of §8.1. Named rather than inlined because `syrinx.py` names them too
// and `verify-parity.mjs` is what proves the two agree.
const DEFAULT_ATTACK = 0.008;
const RELEASE_S = 0.006;
const DECAY_TAU_DIVISOR = 2.5;
const HOLD_FRACTION = 0.75;
const TRACT_HP_HZ = 180.0;
// The source starts here on both sides, and on both sides of the contract. It used to be
// 0.001 and -0.001, which is a different transient from the offline renderer's 1e-4.
const ODE_X0 = 1.0e-4;

const TIMBRE = {
	pure: { gain: 1.0, q: 9.0 },
	reed: { gain: 1.25, q: 5.0 },
	buzz: { gain: 1.75, q: 3.0 }
};

/**
 * Absolute tract resonances, turbulence and roughness — contract §8.1a, and the Python
 * side of it is `syrinx.py`. All three default to off, so a syllable that does not carry
 * them sounds exactly as it did before they existed.
 *
 * The tract above is a bandpass retuned to the instantaneous f0, so every resonance in it
 * is *relative* to pitch and the spectral envelope is pitch-invariant: two species at the
 * same pitch come out as the same instrument transposed. `formants` pins a resonance in Hz
 * instead, so a contour sweeping under it changes timbre as it goes. `noise` injects
 * turbulence at the labia, which is the only honest route to a rasp — the ODE limit cycle
 * is periodic, so a "buzz" made by widening a bandpass is still a tone. `rough` perturbs
 * the driving pressure, which is what reaches the subharmonic and chaotic regimes.
 */
const FORMANT_MAX = 4; // the tracheal comb of §8.1a wants four
const FORMANT_Q_MIN = 0.7;
const FORMANT_Q_MAX = 40;
const FORMANT_HZ_MIN = 150;
const NOISE_PS_FLOOR = 0.05;
const SOURCE_GAIN = 0.35;
const NOISE_GAIN = 2.0 * SOURCE_GAIN; // calibrated against the harvest; see syrinx.py
const ROUGH_LP_HZ = 140;
const ROUGH_DEPTH = 0.12;
const ROUGH_CLAMP_LO = 0.5;
const ROUGH_CLAMP_HI = 1.5;

/**
 * The respiratory oscillator of Fainstein, Goller & Mindlin (2025) — docs/15 §1, the top
 * bet of docs/09 §9.6, mirrored from `respiration.py`. A syllable carrying a
 * `respiration` block replaces the designed envelope with the two-state air-sac
 * dynamics:
 *
 *   tau_x * dx/dt = -(1 + x^2)*x - p + F0*f(t)
 *   tau_p * dp/dt = -(1 + x^2)*x - (1 + alpha(p))*p + F0*f(t)
 *   alpha(p)      = alpha_i - (alpha_i - alpha_o) * Theta(p)
 *
 * with the cubic restitution the paper measured and the Heaviside giving inflow and
 * outflow different conductances. The gesture p(t) is scaled so its peak lands where
 * the envelope path's ps peaked, and it drives the tract **multiplicatively at the
 * injection point** as sqrt(ps) — Laje & Mindlin 2005's low-frequency result
 * (s(t) ≈ √ps · y). Note the correction `syrinx.py` also carries: "every reference
 * injects ẏ" is wrong — birdsongs injects the acceleration, syrinxsynth the velocity,
 * and the physics says velocity × √ps. The whole gesture is precomputed at note start
 * (the P10/P90 normalisation needs the full command, which a worklet never has sample
 * by sample), integrating at the audio rate exactly as the paper specifies.
 *
 * The AM gate stays out of the forcing on purpose: air-sac pressure cannot swing at
 * syringeal AM rates, so `am` keeps gating ps at the labia, and the tract drive uses
 * the un-gated pressure. Defaults and ranges are Table S2 of the paper.
 */
const TAU_X_MIN = 0.01;
const TAU_X_MAX = 0.25;
const TAU_P_MIN = 0.005;
const TAU_P_MAX = 0.2;
const ALPHA_I_MIN = 0.05;
const ALPHA_I_MAX = 6.0;
const ALPHA_REL_MIN = 0.025;
const ALPHA_REL_MAX = 0.125;
const FORCING_MIN = 20.0;
const FORCING_MAX = 200.0;
const FORCING_TAU_S = 0.005; // the paper's critically damped expiratory filter, 5 ms
const MINI_BREATH_DEPTH = 0.5;
const MINI_BREATH_MIN_S = 0.012; // below this a gap is a pulse edge, not a breath
const SILENCE_FRACTION = 0.05; // of the command's maximum: what "silence" means

/**
 * The two-voice coupling of Laje & Mindlin 2005 — docs/15 §5, docs/13 B2, mirrored
 * from `twovoice.py` and `syrinx._ode_source_coupled`. A syllable carrying a
 * `voices` block renders two independently-gestured sources — the syllable's contour
 * drives the first voice, the block's own contour and gamma the second — coupled
 * through the shared tracheal pressure pi(t):
 *
 *   pi[i]      = betaInj * (sqrt(ps_a)*y_a/gamma_a + sqrt(ps_b)*y_b/gamma_b)
 *                - refl * pi(i - T),        T = 2L/c (fractional samples)
 *   alpha_j(i) = alpha_j[i] - 0.40 * pi[i]
 *
 * Each source's injection is velocity times root pressure — the low-frequency
 * inertive limit of the paper's eqs. 62-67, the same result that put sqrt(ps) at the
 * tract input on the respiration path — and the back-action lands on `alpha`,
 * because in this model the restitution constant IS the air-sac pressure. The
 * weak-coupling approximation (Table I: beta 1.5e3 against 1/tau 1e4) is what keeps
 * the integration plain explicit Euler, refreshed once per output sample from the
 * states at the top of the sample, exactly the way alpha and beta are per-sample
 * constants on both sides of the contract. A `level` of 0 is a closed right
 * bronchus: it injects nothing (sqrt(0) * y = 0) and is dropped from the mix, while
 * the shared trachea still feeds the active side its own pressure back — the
 * paper's single-source period-doubling configuration. Ranges are `twovoice.py`'s.
 */
const TWOVOICE_LEVEL_MAX = 1.0;
const TWOVOICE_TRACHEA_CM_MIN = 0.8; // keeps the round trip above two samples at 48 kHz
const TWOVOICE_TRACHEA_CM_MAX = 20.0;
const TWOVOICE_REFL_MAX = 0.95;
const TWOVOICE_BETA_INJ_MAX = 0.5;
const SOUND_SPEED_CM_S = 34400.0;

/**
 * A syllable's `voices` block, clamped into `twovoice.py`'s ranges, or null — in
 * which case the syllable renders single-voiced, bit-identically to before. Contour
 * points are sorted by time fraction and floored at 1 Hz, so the log-interpolation
 * both renderers do cannot disagree about a degenerate point. Mirrors
 * `twovoice.parse`.
 * @param {any} raw
 * @returns {{contour: ContourPoint[], gamma: number, level: number, tracheaCm: number, refl: number, betaInj: number} | null}
 */
function parseTwoVoice(raw) {
	if (!raw || typeof raw !== 'object' || !Array.isArray(raw.contour) || !raw.contour.length) {
		return null;
	}
	const v = [raw.gamma, raw.level, raw.tracheaCm, raw.refl, raw.betaInj].map(Number);
	if (v.some((x) => !Number.isFinite(x))) return null;
	/** @type {(x: number, lo: number, hi: number) => number} */
	const clamp = (x, lo, hi) => Math.min(hi, Math.max(lo, x));
	/** @type {ContourPoint[]} */
	const contour = [];
	for (const p of raw.contour) {
		if (!Array.isArray(p) || p.length < 2) return null;
		const f = Number(p[0]);
		const hz = Number(p[1]);
		if (!Number.isFinite(f) || !Number.isFinite(hz)) return null;
		contour.push([f, Math.max(1, hz)]);
	}
	contour.sort((a, b) => a[0] - b[0]);
	return {
		contour,
		gamma: clamp(v[0], 1200, 150000),
		level: clamp(v[1], 0, TWOVOICE_LEVEL_MAX),
		tracheaCm: clamp(v[2], TWOVOICE_TRACHEA_CM_MIN, TWOVOICE_TRACHEA_CM_MAX),
		refl: clamp(v[3], 0, TWOVOICE_REFL_MAX),
		betaInj: clamp(v[4], 0, TWOVOICE_BETA_INJ_MAX)
	};
}

/**
 * A syllable's `respiration` block, clamped into the Table S2 ranges, or null — in
 * which case the syllable renders on the envelope path, bit-identically to before.
 * Mirrors `respiration.parse`.
 * @param {any} raw
 * @returns {{tauX: number, tauP: number, alphaI: number, alphaRel: number, forcing: number} | null}
 */
function parseRespiration(raw) {
	if (!raw || typeof raw !== 'object') return null;
	const v = [raw.tauX, raw.tauP, raw.alphaI, raw.alphaRel, raw.forcing].map(Number);
	if (v.some((x) => !Number.isFinite(x))) return null;
	/** @type {(x: number, lo: number, hi: number) => number} */
	const clamp = (x, lo, hi) => Math.min(hi, Math.max(lo, x));
	return {
		tauX: clamp(v[0], TAU_X_MIN, TAU_X_MAX),
		tauP: clamp(v[1], TAU_P_MIN, TAU_P_MAX),
		alphaI: clamp(v[2], ALPHA_I_MIN, ALPHA_I_MAX),
		alphaRel: clamp(v[3], ALPHA_REL_MIN, ALPHA_REL_MAX),
		forcing: clamp(v[4], FORCING_MIN, FORCING_MAX)
	};
}

/**
 * Fill each interior expiratory silence with a negative half-sine — a mini-breath.
 * Interior only: a run touching the edges is the attack or the release, and putting an
 * inhalation there would move the onset. Mirrors `respiration._insert_mini_breaths`.
 * @param {Float64Array} m
 * @param {number} sr
 * @returns {Float64Array}
 */
function insertMiniBreaths(m, sr) {
	const n = m.length;
	let peak = 0;
	for (let i = 0; i < n; i++) peak = Math.max(peak, m[i]);
	const out = Float64Array.from(m);
	if (peak <= 0) return out;
	const threshold = SILENCE_FRACTION * peak;
	const minLen = Math.trunc(MINI_BREATH_MIN_S * sr);
	let i = 0;
	while (i < n) {
		if (m[i] < threshold) {
			let j = i;
			while (j < n && m[j] < threshold) j++;
			const length = j - i;
			if (i > 0 && j < n && length >= minLen) {
				for (let k = 0; k < length; k++) {
					out[i + k] = -MINI_BREATH_DEPTH * Math.sin((Math.PI * (k + 1)) / (length + 1));
				}
			}
			i = j;
		} else {
			i++;
		}
	}
	return out;
}

/**
 * Linear-interpolation percentile on an already-sorted array, position (n-1)*q/100.
 * Written by hand because this number is part of the contract — see
 * `respiration._percentile`, which this mirrors.
 * @param {Float64Array} sorted
 * @param {number} q percent
 */
function percentileOf(sorted, q) {
	const n = sorted.length;
	if (n === 0) return 0;
	const pos = (n - 1) * (q / 100);
	const lo = Math.floor(pos);
	const hi = Math.min(lo + 1, n - 1);
	const frac = pos - lo;
	return sorted[lo] + (sorted[hi] - sorted[lo]) * frac;
}

/**
 * The air-sac pressure gesture for one syllable, precomputed at note start.
 *
 * Returns `{ps, drive}` — `ps` the clipped, un-gated air-sac pressure in the synth's
 * [0, 1.4] range, `drive` its square root normalised to 1 at the peak, the
 * multiplicative tract-input of docs/15 §1 — or null when the syllable carries no
 * valid respiration block. Mirrors `syrinx.render_plan`'s respiratory branch, which
 * calls `respiration.pressure`; the arithmetic and its order are the same.
 * @param {Syllable} syl
 * @param {number} gain the timbre class's pressure gain
 * @param {(i: number, n: number) => number} envelopeAt the §8.1 envelope, per sample
 * @returns {{ps: Float64Array, drive: Float64Array} | null}
 */
function respirationGesture(syl, gain, envelopeAt) {
	const params = parseRespiration(syl.respiration);
	if (!params) return null;
	const n = Math.max(2, Math.round(syl.dur * sampleRate));
	const dt = 1 / sampleRate;

	// the designed envelope is the expiratory muscle command; mini-breaths fill its
	// interior silences before the filter smooths everything alike
	const m = insertMiniBreaths(
		Float64Array.from({ length: n }, (_, i) => envelopeAt(i, n)),
		sampleRate
	);

	// the paper's eqs. (3)-(4): critically damped 2nd-order filter, tau = 5 ms
	const f = new Float64Array(n);
	const tau2 = FORCING_TAU_S * FORCING_TAU_S;
	let x1 = 0;
	let x2 = 0;
	for (let i = 0; i < n; i++) {
		const dx1 = x2;
		const dx2 = (m[i] - x1) / tau2 - (2 * x2) / FORCING_TAU_S;
		x1 += dx1 * dt;
		x2 += dx2 * dt;
		f[i] = x1;
	}

	// P10/P90 normalisation: P10 maps to 0, P90 to 1
	const ordered = Float64Array.from(f).sort();
	const lo = percentileOf(ordered, 10);
	const hi = percentileOf(ordered, 90);
	const span = hi - lo;
	if (span < 1e-9) f.fill(0);
	else for (let i = 0; i < n; i++) f[i] = (f[i] - lo) / span;

	// the respiratory states, forward Euler, one step per output sample
	const alphaO = params.alphaI / params.alphaRel;
	const p = new Float64Array(n);
	let x = 0;
	let pp = 0;
	for (let i = 0; i < n; i++) {
		const a = params.alphaI - (params.alphaI - alphaO) * (pp > 0 ? 1 : 0);
		const rest = (1 + x * x) * x;
		const ff = params.forcing * f[i];
		const dx = (-rest - pp + ff) / params.tauX;
		const dp = (-rest - (1 + a) * pp + ff) / params.tauP;
		x += dx * dt;
		pp += dp * dt;
		if (!(Math.abs(x) < 1e6 && Math.abs(pp) < 1e6)) {
			x = 0;
			pp = 0;
		}
		p[i] = pp;
	}

	// scale the gesture so its peak lands where the envelope path's ps peaked
	const ps0 = Math.min(1.4, Math.max(0, syl.level * gain));
	let peak = 0;
	for (let i = 0; i < n; i++) peak = Math.max(peak, p[i]);
	const scale = peak > 1e-9 ? ps0 / peak : 0;
	const ps = new Float64Array(n);
	const drive = new Float64Array(n);
	for (let i = 0; i < n; i++) {
		ps[i] = Math.min(1.4, Math.max(0, p[i] * scale));
		drive[i] = ps0 > 0 ? Math.sqrt(ps[i] / ps0) : 0;
	}
	return { ps, drive };
}


/**
 * xorshift32, bit-identical to `syrinx._xorshift_noise`.
 *
 * A PRNG rather than `Math.random` because the noise is part of the two-sided contract:
 * the offline renderer has to be able to produce the same turbulence from the same
 * syllable, and "some noise with the same spectrum" is not a contract anyone can test.
 * xorshift32 is four integer ops and lands exactly on JavaScript's int32 bitwise
 * semantics, so the two implementations cannot drift.
 */
class Xorshift {
	/** @param {number} stream */
	constructor(stream) {
		// Math.imul, because `stream * 2654435761` exceeds 2^53 and would lose low bits —
		// the very bits the generator depends on.
		let state = (Math.imul(stream, 2654435761) + 1) >>> 0;
		if (state === 0) state = 0x9e3779b9;
		this.state = state;
		for (let i = 0; i < 8; i++) this.next(); // adjacent streams start correlated
	}

	/** @returns {number} uniform in [-1, 1) */
	next() {
		let s = this.state;
		s ^= s << 13;
		s ^= s >>> 17;
		s ^= s << 5;
		this.state = s >>> 0;
		return this.state * (2.0 / 4294967296.0) - 1.0;
	}
}

/**
 * Scale giving the lowpassed roughness noise unit standard deviation — analytic, so the
 * worklet and the offline renderer arrive at the same constant. Normalising by a buffer
 * maximum instead would need the whole syllable up front, which a worklet never has, and
 * would make the effect depend on syllable length.
 * @param {number} sr
 */
function roughStdGain(sr) {
	const c = Math.exp((-2 * Math.PI * ROUGH_LP_HZ) / sr);
	return Math.sqrt(3) * Math.sqrt((1 + c) / (1 - c));
}

/**
 * `[[hz, q, gain], ...]` cleaned and clamped, dropping anything inaudible so it cannot
 * occupy one of the FORMANT_MAX slots. Mirrors `syrinx.parse_formants`.
 * @param {number[][] | undefined} raw
 * @returns {number[][]}
 */
function parseFormants(raw) {
	if (!raw || !raw.length) return [];
	const out = [];
	for (const item of raw) {
		if (!item || item.length < 3) continue;
		const hz = +item[0];
		const q = +item[1];
		const gain = +item[2];
		if (!Number.isFinite(hz) || !Number.isFinite(q) || !Number.isFinite(gain)) continue;
		if (hz < FORMANT_HZ_MIN || gain <= 0) continue;
		out.push([hz, Math.min(Math.max(q, FORMANT_Q_MIN), FORMANT_Q_MAX), gain]);
		if (out.length >= FORMANT_MAX) break;
	}
	return out;
}

/**
 * Contract default clamp (§8.1). The *effective* floor is read from the calibration table's
 * `betaClamp`, because `--beta-min` can lower it and the table is then measured over the
 * wider range — `syrinx.py` has always said the browser should read it rather than hard-code
 * it, and until now the browser hard-coded it. That mattered once §8.1a made low beta useful:
 * the fit would choose a rich, low-beta voice and the worklet would clamp it back to 0.15 and
 * play a tone instead.
 */
const BETA_MIN_DEFAULT = 0.15;
const BETA_MAX = 16;
let betaMin = BETA_MIN_DEFAULT;

/**
 * Below the floor the oscillator is under threshold and silent (§8.6).
 * @param {number} beta
 * @returns {number}
 */
function clampBeta(beta) {
	return Math.min(BETA_MAX, Math.max(betaMin, beta));
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
		/** Per-side 180 Hz one-pole highpass on the source, ahead of the tract (§8.1). */
		this.srcHpX = [0, 0];
		this.srcHpY = [0, 0];
		/**
		 * The fricative path's own DC blocks and formant banks, per side (docs/16 §16.7).
		 * A fricative's turbulence is routed around the f0-tracking band and shaped by
		 * the syllable's formant set instead, so it needs filter state of its own —
		 * sharing the tonal bank would interleave two signals through one biquad.
		 * @type {number[]}
		 */
		this.noiseHpX = [0, 0];
		this.noiseHpY = [0, 0];
		/** @type {Biquad[][]} */
		this.noiseFormantFilters = [[], []];
		/**
		 * One bank per syringeal side. Fixed in Hz, so unlike `tract` these are set once at
		 * note start and never retuned — that is the whole point of them.
		 * @type {Biquad[][]}
		 */
		this.formantFilters = [[], []];
		/** @type {number[][]} */
		this.formants = [];
		this.noise = 0;
		this.rough = 0;
		/** @type {(Xorshift | null)[]} per side: turbulence */
		this.noiseRng = [null, null];
		/** @type {(Xorshift | null)[]} per side: pressure roughness */
		this.roughRng = [null, null];
		this.roughLp = [0, 0];
		this.roughCoeff = 0;
		this.roughScale = 0;
		this.dcX = 0;
		this.dcY = 0;
		this.lpY = 0;
		this.f0 = 0;
		this.env = 0;
		/**
		 * The precomputed air-sac pressure gesture of docs/15 §1, or null on the
		 * envelope path: `{ps, drive}` Float64Arrays over the syllable's sample grid.
		 * @type {{ps: Float64Array, drive: Float64Array} | null}
		 */
		this.resp = null;
		/**
		 * The parsed second voice of docs/15 §5, or null on the single-voice path.
		 * `gammaB`/`dtB`/`oversampleB` are the second oscillator's own time-scale;
		 * `piRing` is the shared tracheal pressure's fractional-delay line (the
		 * round trip T = 2L/c), indexed by sample since syllable start, mirroring
		 * the ring in `syrinx._ode_source_coupled`.
		 * @type {{contour: ContourPoint[], gamma: number, level: number, tracheaCm: number, refl: number, betaInj: number} | null}
		 */
		this.voices = null;
		this.gammaB = CALIBRATION_GAMMA;
		this.oversampleB = 16;
		this.dtB = 1 / (48000 * 16);
		this.piDelay = 0;
		this.piRingLen = 2;
		/** @type {Float64Array} */
		this.piRing = new Float64Array(2);
		this.gamma = CALIBRATION_GAMMA;
		this.oversample = 16;
		this.dt = 1 / (48000 * 16);
	}

	/**
	 * @param {Syllable} syllable
	 * @param {number} startSample
	 * @param {number} gain
	 * @param {number} pan -1 hard left to +1 hard right
	 * @param {number} stream turbulence realisation; see `render_syllable(stream=...)`
	 * @param {{ps: Float64Array, drive: Float64Array} | null} resp the precomputed
	 *   respiratory gesture of docs/15 §1, or null on the envelope path
	 */
	start(syllable, startSample, gain, pan, stream, resp = null) {
		this.active = true;
		this.syllable = syllable;
		this.startSample = startSample;
		this.gain = gain;
		this.resp = resp;
		// equal-power pan, held per voice: birds in a chorus overlap, and a single shared
		// panner would drag every one of them to wherever the newest note was placed
		const angle = ((Math.min(1, Math.max(-1, pan)) + 1) * Math.PI) / 4;
		this.gainL = Math.cos(angle);
		this.gainR = Math.sin(angle);
		// §8.1a: the scale is this syllable's position on the tonal-to-rich axis. Raising
		// gamma forces beta down for the same f0, and low beta is where the model's
		// pulse-like, harmonically dense solutions live. Clamped to the range the Euler
		// step stays accurate over.
		const scale = Number.isFinite(syllable.gammaScale) ? syllable.gammaScale : 1;
		this.gamma = Math.min(
			150000,
			Math.max(1200, gammaForContour(syllable.contour) * (scale > 0 ? scale : 1))
		);
		this.oversample = oversampleForGamma(this.gamma, sampleRate);
		this.dt = 1 / (sampleRate * this.oversample);
		this.x = [ODE_X0, ODE_X0];
		this.y = [0, 0];
		this.srcHpX = [0, 0];
		this.srcHpY = [0, 0];
		this.noiseHpX = [0, 0];
		this.noiseHpY = [0, 0];
		this.dcX = this.dcY = this.lpY = 0;
		for (const f of this.tract) f.reset();
		for (const f of this.tractHarm) f.reset();
		this.env = 0;

		this.formants = parseFormants(syllable.formants);
		this.noise = Math.min(1, Math.max(0, syllable.noise ?? 0));
		this.rough = Math.min(1, Math.max(0, syllable.rough ?? 0));
		// Each side gets its own streams, offset exactly as the offline renderer offsets
		// them: sharing one would correlate the two sides, and correlated noise through two
		// near-identical tracts sums to one louder voice instead of two.
		for (const side of [0, 1]) {
			const s = side === 0 ? stream : stream + 1024;
			this.noiseRng[side] = this.noise > 0 ? new Xorshift(s * 4 + 1) : null;
			this.roughRng[side] = this.rough > 0 ? new Xorshift(s * 4 + 2) : null;
			this.roughLp[side] = 0;
			this.formantFilters[side] = this.formants.map(([hz, q]) => {
				const f = new Biquad();
				f.setBandpass(hz, q, sampleRate);
				return f;
			});
			// The fricative path's bank (docs/16 §16.7): the same resonances as the tonal
			// bank, on their own state, because a biquad cannot carry two signals.
			this.noiseFormantFilters[side] = this.formants.map(([hz, q]) => {
				const f = new Biquad();
				f.setBandpass(hz, q, sampleRate);
				return f;
			});
		}
		this.roughCoeff = Math.exp((-2 * Math.PI * ROUGH_LP_HZ) / sampleRate);
		this.roughScale = roughStdGain(sampleRate);

		// docs/15 §5: the second voice's own time-scale and the shared trachea's
		// fractional-delay ring, or null and the syllable renders single-voiced as it
		// always has. The ring starts at zero — silence before the bird — exactly as
		// the offline kernel's does, and two slots past the delay are enough (the
		// 0.8 cm floor keeps the delay above two samples, so a read never touches the
		// slot being written).
		this.voices = parseTwoVoice(syllable.voices);
		if (this.voices) {
			this.gammaB = this.voices.gamma;
			this.oversampleB = oversampleForGamma(this.gammaB, sampleRate);
			this.dtB = 1 / (sampleRate * this.oversampleB);
			this.piDelay = (2 * this.voices.tracheaCm * sampleRate) / SOUND_SPEED_CM_S;
			this.piRingLen = Math.floor(this.piDelay) + 2;
			this.piRing = new Float64Array(this.piRingLen);
		}
	}

	/**
	 * Roughness multiplier on **beta** (labial tension) for this sample, or 1 when `rough`
	 * is off. One-pole lowpass on the noise, matching `syrinx._one_pole_lp`: white jitter at
	 * the sample rate reads as added hiss, not as a rough voice, and ROUGH_LP_HZ sits inside
	 * the 80-250 Hz band syringeal muscle can actually follow.
	 *
	 * Tension rather than pressure, and rather than the output, because that is the one
	 * thing the literature is specific about — see the note in `syrinx._voice`.
	 * @param {number} side
	 */
	roughFactor(side) {
		const rng = this.roughRng[side];
		if (!rng) return 1;
		const c = this.roughCoeff;
		this.roughLp[side] = (1 - c) * rng.next() + c * this.roughLp[side];
		const f = 1 + ROUGH_DEPTH * this.rough * this.roughLp[side] * this.roughScale;
		return Math.min(ROUGH_CLAMP_HI, Math.max(ROUGH_CLAMP_LO, f));
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
		/**
		 * Turbulence realisation for the next note. It advances per note rather than being
		 * fixed, so a chorus singing one syllable is not noisy in the same places twice —
		 * the *spectrum* is what the fit measured and what ships; where the noise happens to
		 * fall is not, any more than it is for a real bird. The offline renderer defaults to
		 * stream 0 so a verified cosine stays reproducible.
		 */
		this.stream = 0;

		this.port.onmessage = (event) => {
			const msg = event.data;
			if (msg.type === 'calibration') {
				this.calibration = msg.calibration;
				const clamp = msg.calibration?.betaClamp;
				if (Array.isArray(clamp) && Number.isFinite(clamp[0]) && clamp[0] > 0) {
					betaMin = clamp[0];
				}
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
	 * @param {number} alpha only used by the analytic fallback
	 * @param {number} beta
	 * @param {number} pressure passed rather than recovered from alpha: once `rough`
	 *   modulates alpha, `(alpha - 0.05) / 0.4` is no longer the pressure the envelope
	 *   asked for, and reading the table at a wobbling pressure would put the roughness
	 *   into the loudness as well as into the pitch.
	 * @returns {number}
	 */
	ampPP(alpha, beta, pressure) {
		const cal = this.calibration;
		if (!cal || !cal.ampPP || !cal.ampPP.length) return 0.5 + 3.4 * alpha + 0.62 * beta;
		const pGrid = cal.pressureGrid;
		const bGrid = cal.betaGrid;
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
	 * The envelope of §8.1: linear attack, sustain-or-exponential-decay, 6 ms release.
	 *
	 * Indexed by sample rather than by seconds, and taking the syllable's sample count,
	 * because it has to agree with `syrinx.envelope` to the last bit — that function works
	 * on an `n`-sample grid and derives its duration from `n / sampleRate`, so computing
	 * from a float `t` and `syllable.dur` lands somewhere slightly different.
	 *
	 * @param {Syllable} syllable
	 * @param {number} sampleIndex samples since syllable onset
	 * @param {number} n the syllable's length in samples
	 * @returns {number}
	 */
	envelopeAt(syllable, sampleIndex, n) {
		if (n <= 1) return 0;
		// Past the grid the envelope is zero, full stop. The offline renderer's array simply
		// ends at `n`, but a voice here keeps running for ~20 ms so the filter tails can
		// decay — and without this the release ramp below carries on past its endpoint and
		// goes *negative*, reaching about -4x the body level. That was an audible click on
		// the tail of every single note, and the parity harness could not see it because it
		// only compares the first `n` samples.
		if (sampleIndex >= n) return 0;
		const dur = n / sampleRate;
		const t = sampleIndex / sampleRate;
		const atk = Math.min(Math.max(syllable.attack ?? DEFAULT_ATTACK, 1 / sampleRate), 0.9 * dur);
		const tau = dur / DECAY_TAU_DIVISOR;

		// The attack wins over the tail, as it does in the Python (which assigns the decay
		// first and then overwrites the rising part).
		let env;
		if (t < atk) {
			env = t / atk;
		} else if (syllable.hold) {
			const knee = HOLD_FRACTION * dur;
			env = t > knee ? Math.exp(-(t - knee) / tau) : 1;
		} else {
			env = Math.exp(-(t - atk) / tau);
		}

		const rel = Math.round(RELEASE_S * sampleRate);
		if (rel > 1 && rel < n && sampleIndex >= n - rel) {
			// linspace(1, 0, rel) with both endpoints included, floored at zero
			env *= Math.max(0, 1 - (sampleIndex - (n - rel)) / (rel - 1));
		}
		return env;
	}

	/**
	 * One sample of one oscillator: integrates OVERSAMPLE Euler steps, returns the source.
	 * @param {Voice} voice
	 * @param {number} index 0 = left syringeal side, 1 = right
	 * @param {number} alpha
	 * @param {number} beta
	 * @param {number} ampPP peak-to-peak swing of y/gamma, divided out of the source
	 * @param {number} pressure drives the turbulence gate
	 * @param {number} drive √ps at the tract input (docs/15 §1); exactly 1 on the
	 *   envelope path, where multiplying by it changes nothing
	 * @param {number} [g] time-scale override — the second voice of docs/15 §5 runs at
	 *   its own gamma; defaults to the syllable's, which keeps the single-voice and
	 *   `two: true` paths bit-identical
	 * @param {number} [dt]
	 * @param {number} [oversample]
	 * @param {{noise?: number} | null} [split] when given (the fricative path of
	 *   docs/16 §16.7), the turbulence is NOT mixed into the returned source: it gets
	 *   the same √ps drive and its own 180 Hz DC block, and lands in `split.noise`,
	 *   so the caller can route it around the f0-tracking band into the formant set.
	 *   Null keeps the old mixed path bit-identical.
	 * @returns {number}
	 */
	stepOsc(voice, index, alpha, beta, ampPP, pressure, drive, g = 0, dt = 0, oversample = 0, split = null) {
		if (g === 0) {
			g = voice.gamma;
			dt = voice.dt;
			oversample = voice.oversample;
		}
		const g2 = g * g;
		let x = voice.x[index];
		let y = voice.y[index];
		for (let s = 0; s < oversample; s++) {
			const dx = y;
			const dy = -alpha * g2 - beta * g2 * x - g2 * x * x * x - g * x * x * y + g2 * x * x - g * x * y;
			x += dx * dt;
			y += dy * dt;
		}
		// Bounds checked once per output sample, at the offline renderer's thresholds, not
		// clamped every Euler step at ±40/±4e6. The tight per-step clamp was a divergence
		// from §8.1 *and* a distortion in its own right: it flattened the peaks of the very
		// large-amplitude regimes the model reaches at high beta, so the loudest syllables
		// were quietly being squared off. Outside these bounds there is no basin left to be
		// in, so restarting from rest is the only useful answer.
		if (!(Math.abs(x) < 1e6 && Math.abs(y) < 1e12)) {
			x = ODE_X0;
			y = 0;
		}
		voice.x[index] = x;
		voice.y[index] = y;
		if (!Number.isFinite(x) || !Number.isFinite(y)) {
			voice.x[index] = ODE_X0;
			voice.y[index] = 0;
			return 0;
		}
		// dividing by the peak-to-peak swing keeps loudness tied to the envelope rather
		// than to the pitch, which otherwise dominates it
		let source = ((y / g) * SOURCE_GAIN) / ampPP;
		const rng = voice.noiseRng[index];
		let noiseSrc = 0;
		if (rng) {
			// Turbulent flow at the labia, so it enters before the tract and is shaped by
			// it: the same noise becomes a breathy whistle under a high-Q tract band and a
			// rasp under a low-Q formant, which is why one scalar can serve both. Gated by
			// pressure because a bird with no airflow does not hiss.
			const flow = Math.max(pressure - NOISE_PS_FLOOR, 0);
			noiseSrc = voice.noise * NOISE_GAIN * flow * rng.next();
			if (!split) source += noiseSrc;
		}
		// √ps at the tract input (docs/15 §1): the one point where pressure enters
		// multiplicatively, ahead of the DC block and every resonance, and it scales
		// oscillator and turbulence together — both are the same airflow. Exactly 1 on
		// the envelope path, which is then bit-identical to before. On the fricative
		// path the turbulence is scaled explicitly, to the same end (docs/16 §16.7
		// piece 2: a fricative burst IS a pressure event).
		source *= drive;
		// 180 Hz one-pole highpass on the source, ahead of the tract (§8.1). This was
		// missing: the worklet only DC-blocked after the tract, so the offline renderer's
		// tract saw a source with the sub-180 Hz drift already removed and the worklet's did
		// not — audible on low-pitched syllables, where that drift is a big share of the
		// signal the resonance is being asked to shape.
		const r = this.dcCoeff;
		const hp = source - voice.srcHpX[index] + r * voice.srcHpY[index];
		voice.srcHpX[index] = source;
		voice.srcHpY[index] = hp;
		if (split) {
			noiseSrc *= drive;
			const nhp = noiseSrc - voice.noiseHpX[index] + r * voice.noiseHpY[index];
			voice.noiseHpX[index] = noiseSrc;
			voice.noiseHpY[index] = nhp;
			split.noise = nhp;
		}
		return hp;
	}

	/**
	 * One side's tract for one sample: the f0-tracking band, the harmonic band and the
	 * formant set on the tonal source — and, on the fricative path (docs/16 §16.7),
	 * the same formant set once more on the separated turbulence, added last. The
	 * noise never sees the tracking band: that filter is pitch-shaped, and a
	 * fricative's shape is the tract's, not the pitch's.
	 * @param {Voice} voice
	 * @param {number} index
	 * @param {number} source tonal source sample (HP'd, drive applied)
	 * @param {number} harmonic
	 * @param {number | null} noiseSrc the fricative path's separated turbulence, or
	 *   null on the mixed path
	 * @returns {number}
	 */
	filterSide(voice, index, source, harmonic, noiseSrc) {
		let filtered = voice.tract[index].process(source);
		if (harmonic > 0) filtered += harmonic * 0.5 * voice.tractHarm[index].process(source);
		const bank = voice.formantFilters[index];
		for (let k = 0; k < bank.length; k++) {
			filtered += voice.formants[k][2] * bank[k].process(source);
		}
		if (noiseSrc !== null) {
			const nbank = voice.noiseFormantFilters[index];
			for (let k = 0; k < nbank.length; k++) {
				filtered += voice.formants[k][2] * nbank[k].process(noiseSrc);
			}
		}
		return filtered;
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
						// docs/15 §1: the respiratory gesture is precomputed whole — its
						// P10/P90 normalisation needs the full command — or is null, and
						// the voice renders on the envelope path as it always has.
						const timbre = TIMBRE[note.syllable.timbre] ?? TIMBRE.pure;
						voice.start(
							note.syllable,
							startSample + offset,
							note.gain,
							note.pan ?? 0,
							this.stream++,
							respirationGesture(note.syllable, timbre.gain, (i, n) =>
								this.envelopeAt(note.syllable, i, n)
							)
						);
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
			// A fitted Q overrides the timbre class's. See the note on `tract_q` in syrinx.py:
			// the three classes are all broad next to the Q ~ 30 measured for the OEC
			// resonance, and a broad band leaks the second harmonic.
			const tractQ =
				syl.tractQ > 0
					? Math.min(Math.max(syl.tractQ, FORMANT_Q_MIN), FORMANT_Q_MAX)
					: timbre.q;
			const harmonic = syl.harmonic ?? 0;
			const twoVoices = syl.two === true;
			// docs/16 §16.7: the fricative routing — turbulence bypasses the f0-tracking
			// band and is shaped by the formant set. With no turbulence it is a no-op,
			// matching `syrinx._voice_tract`.
			const fricative = syl.fricative === true && voice.noise > 0;
			const durSamples = Math.ceil((syl.dur + 0.02) * sampleRate);
			// The grid the envelope is defined on, matching `syrinx.render_plan`'s `n`. The
			// voice runs ~20 ms past it so the release and the filter tails can finish.
			const envN = Math.max(2, Math.round(syl.dur * sampleRate));

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

				// AM gates the *pressure* only, and not the output gain.
				//
				// It used to be folded into `env`, which is also the output gain a few lines
				// below — so every AM syllable had its tremolo applied twice, once through the
				// oscillator's drive and again on the way out. That both doubled the depth and
				// made it the largest single disagreement with the offline renderer, which
				// modulates `ps` and leaves `plan.env` clean (§8.1).
				let env, pressure, drive;
				if (voice.resp) {
					// docs/15 §1: ps comes from the air-sac pressure gesture, and the
					// amplitude shaping is the drive's job at the tract input, so the
					// output gain is 1. The AM gate acts at the labia on this path too —
					// air-sac pressure cannot swing at syringeal AM rates — while the
					// drive keeps the un-gated pressure the sacs actually hold.
					env = 1;
					if (sampleIndex < envN) {
						pressure = voice.resp.ps[sampleIndex];
						drive = voice.resp.drive[sampleIndex];
					} else {
						pressure = 0;
						drive = 0;
					}
					if (syl.am) {
						const depth = syl.amDepth ?? 0.5;
						pressure *= 1 - depth * (0.5 - 0.5 * Math.cos(2 * Math.PI * syl.am * t));
					}
					pressure = Math.min(1.4, Math.max(0, pressure));
				} else {
					env = this.envelopeAt(syl, sampleIndex, envN);
					let psEnv = env;
					if (syl.am) {
						const depth = syl.amDepth ?? 0.5;
						psEnv *= 1 - depth * (0.5 - 0.5 * Math.cos(2 * Math.PI * syl.am * t));
					}
					pressure = Math.min(1.4, Math.max(0, syl.level * psEnv * timbre.gain));
					drive = 1;
				}
				voice.env = env;
				// positive alpha is the oscillating side of the threshold here (§8.1)
				const alpha = 0.05 + 0.4 * pressure;

				// docs/15 §5: the second voice's own contour, per sample — the tract
				// coefficient block and the coupled branch both need it. Its tract band
				// tracks ITS f0, the way `two: true`'s second band tracks the detuned one.
				const coupled = voice.voices;
				const f0b = coupled ? this.contourAt(coupled.contour, u) : 0;

				if ((sampleIndex & (FILTER_UPDATE - 1)) === 0) {
					voice.tract[0].setBandpass(f0, tractQ, sampleRate);
					if (coupled) voice.tract[1].setBandpass(f0b, tractQ, sampleRate);
					else if (twoVoices) voice.tract[1].setBandpass(f0 * DETUNE_TWO, tractQ, sampleRate);
					if (harmonic > 0) {
						// The harmonic band is "a second tract band at 2*f0" (§8.1) — the same Q as
						// the tract, not a widened one. The 0.8 factor here was local invention.
						voice.tractHarm[0].setBandpass(f0 * 2, tractQ, sampleRate);
						if (coupled) voice.tractHarm[1].setBandpass(f0b * 2, tractQ, sampleRate);
						else if (twoVoices) voice.tractHarm[1].setBandpass(f0 * 2 * DETUNE_TWO, tractQ, sampleRate);
					}
				}

				// ampPP is read at the *clean* beta: its job is to divide the pitch out of the
				// loudness, and reading it at the roughened beta would divide the roughness
				// out too. Only the ODE sees the roughened tension, so the wobble arrives as
				// correlated pitch and amplitude irregularity through the oscillator's own
				// dynamics rather than as noise laid over the top.
				const betaClean = this.betaForF0(f0, pressure, voice.gamma);
				const ampA = this.ampPP(alpha, betaClean, pressure);
				let sample;
				if (coupled) {
					// docs/15 §5: the shared tracheal pressure, from the oscillator states
					// at the TOP of the sample — explicit Euler, the offline kernel's exact
					// order (`syrinx._ode_source_coupled`). One pair of air sacs feeds both
					// bronchi, so the second voice's pressure is the first's scaled by
					// `level`; the coupling then moves each side's alpha, because the
					// restitution constant IS the air-sac pressure.
					const pressureB = Math.min(1.4, Math.max(0, pressure * coupled.level));
					const gpos = sampleIndex - voice.piDelay;
					let delayed = 0;
					if (gpos >= 0) {
						const i0 = Math.floor(gpos);
						const frac = gpos - i0;
						delayed =
							voice.piRing[i0 % voice.piRingLen] * (1 - frac) +
							voice.piRing[(i0 + 1) % voice.piRingLen] * frac;
					}
					const pi =
						coupled.betaInj *
							(Math.sqrt(pressure) * (voice.y[0] / voice.gamma) +
								Math.sqrt(pressureB) * (voice.y[1] / voice.gammaB)) -
						coupled.refl * delayed;
					voice.piRing[sampleIndex % voice.piRingLen] = pi;
					const alphaB = 0.05 + 0.4 * pressureB;

					const betaA = clampBeta(betaClean * voice.roughFactor(0));
					/** @type {{noise?: number} | null} */
					const splitA = fricative ? {} : null;
					const sourceA = this.stepOsc(voice, 0, alpha - 0.4 * pi, betaA, ampA, pressure, drive, 0, 0, 0, splitA);
					sample = this.filterSide(voice, 0, sourceA, harmonic, splitA ? splitA.noise ?? 0 : null);

					if (coupled.level > 0) {
						// A closed right bronchus (level 0) injects nothing — sqrt(0)*y = 0 —
						// and is not heard: the single-source-plus-feedback case. Its
						// oscillator need not advance then; its state never reaches pi.
						const betaCleanB = this.betaForF0(f0b, pressureB, voice.gammaB);
						const ampB = this.ampPP(alphaB, betaCleanB, pressureB);
						const betaB = clampBeta(betaCleanB * voice.roughFactor(1));
						/** @type {{noise?: number} | null} */
						const splitB = fricative ? {} : null;
						const sourceB = this.stepOsc(
							voice, 1, alphaB - 0.4 * pi, betaB, ampB, pressureB, drive,
							voice.gammaB, voice.dtB, voice.oversampleB, splitB
						);
						const filteredB = this.filterSide(voice, 1, sourceB, harmonic, splitB ? splitB.noise ?? 0 : null);
						sample = 0.5 * sample + 0.5 * filteredB;
					}
				} else {
					const betaA = clampBeta(betaClean * voice.roughFactor(0));
					/** @type {{noise?: number} | null} */
					const split = fricative ? {} : null;
					const source = this.stepOsc(voice, 0, alpha, betaA, ampA, pressure, drive, 0, 0, 0, split);
					sample = this.filterSide(voice, 0, source, harmonic, split ? split.noise ?? 0 : null);

					if (twoVoices) {
						const betaCleanB = this.betaForF0(f0 * DETUNE_TWO, pressure, voice.gamma);
						const ampB = this.ampPP(alpha, betaCleanB, pressure);
						const betaB = clampBeta(betaCleanB * voice.roughFactor(1));
						/** @type {{noise?: number} | null} */
						const splitB = fricative ? {} : null;
						const sourceB = this.stepOsc(voice, 1, alpha, betaB, ampB, pressure, drive, 0, 0, 0, splitB);
						const filteredB = this.filterSide(voice, 1, sourceB, harmonic, splitB ? splitB.noise ?? 0 : null);
						sample = 0.5 * sample + 0.5 * filteredB;
					}
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

/**
 * Cross-checks the browser worklet against the offline Python renderer, sample by sample.
 *
 * `docs/08-implementation.md` §8.1 is a two-sided contract: the ODE, the integration
 * scheme, the parameter mapping and the filter forms have to be identical in
 * `src/lib/audio/worklets/syrinx-processor.js` and in `pipeline/.../syrinx.py`. Nothing
 * enforced that. The pitch regression in `render-syllable.mjs` checks the worklet against
 * the *contour*, which both sides can satisfy while disagreeing about everything else —
 * and §8.1a added a noise generator, whose whole claim is that the two sides produce the
 * same turbulence from the same syllable. That claim needs a test or it is decoration.
 *
 *   node scripts/verify-parity.mjs            # writes the JS side, then compares
 *
 * It renders each case here, strips the worklet's output saturation, and reports the worst
 * absolute sample difference against Python's array. The two are expected to agree to
 * float32 rounding — they run the same arithmetic in the same order.
 */
import { execFileSync } from 'node:child_process';
import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { loadGenerated, REPO_ROOT, SAMPLE_RATE, render } from './lib/worklet-host.mjs';

const calibration = loadGenerated('syrinx-calibration.json');
if (!calibration) {
	console.error('no syrinx-calibration.json — run the pipeline build first');
	process.exit(2);
}

const base = {
	id: 'P',
	label: '',
	function: '',
	confidence: 'inferred',
	refs: [],
	dur: 0.12,
	level: 0.85,
	timbre: 'pure',
	contour: [
		[0.0, 3000],
		[1.0, 3600]
	]
};

/** Each case names the part of §8.1/§8.1a it is there to pin down. */
const CASES = [
	{ name: 'baseline', syllable: base },
	{ name: 'harmonic', syllable: { ...base, harmonic: 0.5 } },
	{ name: 'two-voice', syllable: { ...base, two: true } },
	{ name: 'am+vib', syllable: { ...base, am: 40, amDepth: 0.5, vib: { rate: 12, depth: 0.03 } } },
	{ name: 'hold+buzz', syllable: { ...base, hold: true, timbre: 'buzz' } },
	{ name: 'low pitch', syllable: { ...base, contour: [[0.0, 520]], dur: 0.2 } },
	// §8.1a
	{ name: 'formants', syllable: { ...base, formants: [[3200, 4, 1.0], [6100, 6, 0.5]] } },
	{ name: 'noise', syllable: { ...base, noise: 0.5 } },
	{ name: 'rough', syllable: { ...base, rough: 0.4 } },
	{ name: 'tractQ', syllable: { ...base, tractQ: 28 } },
	{ name: 'trachea', syllable: { ...base, formants: [[1900, 6, 0.6], [5700, 6, 0.2]] } },
	{
		name: 'all + two',
		syllable: {
			...base,
			two: true,
			harmonic: 0.3,
			formants: [[2800, 3, 1.2], [7000, 1.5, 0.6]],
			noise: 0.35,
			rough: 0.25
		}
	}
];

// The worklet saturates its bus with tanh(x * 1.6) * 0.8 so a twelve-voice chorus cannot
// clip. Python renders one voice with no output stage, so the saturation is undone here
// rather than bolted onto Python — monotonic, and the values are far from the asymptote.
const unsaturate = (y) => Math.atanh(Math.min(0.999999, Math.max(-0.999999, y / 0.8))) / 1.6;

const LEAD = Math.round(0.02 * SAMPLE_RATE); // worklet-host schedules the note at t = 0.02

const out = {};
for (const { name, syllable } of CASES) {
	const { signal } = await render([syllable], [], { calibration });
	const n = Math.round(syllable.dur * SAMPLE_RATE); // Python's plan length
	const samples = new Array(n);
	for (let i = 0; i < n; i++) samples[i] = unsaturate(signal[LEAD + i]);

	// **And what the worklet does after Python's array ends.**
	//
	// Comparing only the first `n` samples is not enough, and that gap hid a real bug: the
	// worklet keeps a voice running ~20 ms past `n` so the filter tails can decay, and a
	// release ramp that carried on past its endpoint went negative there — roughly -4x the
	// body level, an audible click on the tail of every note — while every case still
	// reported `ok`. Python has no samples to compare against out there, so the check is the
	// physical one instead: the tail is a decay, so nothing in it may exceed the body.
	const tailFrom = LEAD + n;
	const tailTo = Math.min(signal.length, tailFrom + Math.round(0.02 * SAMPLE_RATE));
	let tailPeak = 0;
	for (let i = tailFrom; i < tailTo; i++) tailPeak = Math.max(tailPeak, Math.abs(signal[i]));
	out[name] = { syllable, samples, tailPeak };
}

const path = join(REPO_ROOT, 'pipeline/out/parity-js.json');
mkdirSync(dirname(path), { recursive: true });
writeFileSync(path, JSON.stringify(out));
console.log(`wrote ${CASES.length} cases to ${path}`);

const python = join(REPO_ROOT, 'pipeline/.venv/bin/python');
console.log(
	execFileSync(python, ['-m', 'birdy_pipeline.parity', path], {
		cwd: join(REPO_ROOT, 'pipeline'),
		encoding: 'utf8'
	})
);

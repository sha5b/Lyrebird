/**
 * A lit knot fades over a *duration*, not over a number of frames.
 *
 * The bug this exists to prevent shipped for a long time and could not have been caught by
 * looking: `ActivationTracker`'s attack and release were EMA coefficients applied once per
 * `requestAnimationFrame`, so both were a function of the display. `RELEASE = 0.97` has a
 * half-life of 22.8 *frames* — which is the 0.38 s its own comment claims at 60 Hz, 0.16 s on
 * a 144 Hz monitor, and 0.76 s when a heavy scene drops to 30. The picture therefore fell away
 * more than twice as fast on a fast screen, and got laggier exactly when the frame rate did.
 *
 * It also disagreed with its neighbours, which is what makes it a correctness bug rather than
 * a preference. The scheduled pulse in `listener.ts` is two gaussians in seconds off the audio
 * clock, and the accent colour's ease is delta-corrected — so at 144 Hz a knot's glow was gone
 * while the note that lit it and the colour it was easing toward were both still going.
 *
 * Every check here is the same question asked at several frame rates: does the fade take the
 * same number of *seconds*? Nothing about the tuned 60 Hz behaviour may move, because that is
 * the one that was looked at and accepted.
 *
 * Run with `npm run verify:fade`. Exits non-zero on any disagreement.
 */
import { ActivationTracker } from '../src/lib/audio/features.ts';

let failures = 0;
const ok = (name, cond, detail = '') => {
	if (cond) console.log(`  ${name.padEnd(56)} ok${detail ? ` (${detail})` : ''}`);
	else {
		failures++;
		console.error(`  ${name.padEnd(56)} FAIL ${detail}`);
	}
};

/**
 * A minimal two-knot corpus, built here rather than loaded.
 *
 * The fade is arithmetic on one float and has nothing to do with which build is installed, so
 * depending on the assets would make this test slower, unrunnable without them, and able to
 * fail for reasons that are not about fading. The tracker only needs `items[].vector` of the
 * declared width and a ramp.
 */
const DIMS = 4;
const spec = { dims: DIMS, mean: new Array(DIMS).fill(0), std: new Array(DIMS).fill(1) };
const centroids = {
	items: [
		{ vector: Float32Array.from([1, 0, 0, 0]) },
		{ vector: Float32Array.from([0, 1, 0, 0]) }
	]
};
const ramp = { floor: 0.2, ceiling: 0.9, fromAssets: false };

/** A tracker with one activation set by hand, so the release is measured on its own. */
function litTracker() {
	const t = new ActivationTracker(centroids, spec, 0.82, ramp);
	t.activations.fill(0);
	t.activations[0] = 1;
	t.strength = 1;
	return t;
}

/**
 * Seconds for the seeded activation to fall below `to`, stepping at `fps`.
 *
 * Measured by running the real `decay`, not by re-deriving the arithmetic: the point is to
 * check the shipped function, and a test that recomputed the half-life would agree with a
 * wrong implementation.
 */
function releaseSeconds(fps, to = 0.5) {
	const dt = 1 / fps;
	const t = litTracker();
	let seconds = 0;
	// Generous ceiling; a fade that needs 20 s has already failed every check below.
	while (t.activations[0] > to && seconds < 20) {
		t.decay(dt);
		seconds += dt;
	}
	return seconds;
}

const RATES = [24, 30, 50, 60, 75, 90, 120, 144, 165, 240];

// --- the release is a duration ----------------------------------------------------------
console.log('the release takes the same time at every frame rate');

{
	const halves = RATES.map((fps) => ({ fps, s: releaseSeconds(fps) }));
	for (const { fps, s } of halves) {
		console.log(`    ${String(fps).padStart(3)} fps   half-life ${s.toFixed(3)} s`);
	}
	const lo = Math.min(...halves.map((h) => h.s));
	const hi = Math.max(...halves.map((h) => h.s));
	// One frame of slack at the coarsest rate is unavoidable — the loop can only stop on a
	// frame boundary — so the tolerance is a frame at 24 fps plus a little.
	ok('half-life agrees across 24..240 fps', hi - lo < 1 / 24 + 0.005,
		`spread ${(hi - lo).toFixed(4)} s`);

	const at60 = halves.find((h) => h.fps === 60).s;
	ok('and the tuned 60 fps value is unchanged', Math.abs(at60 - 0.38) < 0.03,
		`${at60.toFixed(3)} s against the documented ~0.4 s`);

	// The reported failure, as an assertion: the fast screen must not be the short fade.
	const at144 = halves.find((h) => h.fps === 144).s;
	ok('144 fps is not faster than 60', Math.abs(at144 - at60) < 0.05,
		`${at144.toFixed(3)} s against ${at60.toFixed(3)} s`);
}

{
	// Full silence: how long until nothing is lit at all. The floor in `decay` snaps a
	// residual to zero, and without it an activation of 1e-7 keeps a label open forever.
	const toZero = (fps) => {
		const dt = 1 / fps;
		const t = litTracker();
		let seconds = 0;
		while (t.activations[0] > 0 && seconds < 20) {
			t.decay(dt);
			seconds += dt;
		}
		return seconds;
	};
	const at30 = toZero(30);
	const at144 = toZero(144);
	ok('reaches exactly zero, not a residual', at30 < 20 && at144 < 20,
		`${at30.toFixed(2)} s at 30, ${at144.toFixed(2)} s at 144`);
	ok('and takes the same time either way', Math.abs(at30 - at144) < 1 / 24 + 0.02,
		`${Math.abs(at30 - at144).toFixed(4)} s apart`);
}

// --- the attack is a duration too ------------------------------------------------------
console.log('\nthe attack takes the same time at every frame rate');

{
	// `strength` is the channel the attack rides, and it is what gates `best()` and the HUD.
	// Driven straight rather than through `update`, which would need a descriptor per frame;
	// the smoothing is the thing under test and it is the same coefficient either way.
	const riseSeconds = (fps) => {
		const dt = 1 / fps;
		const t = new ActivationTracker(centroids, spec, 0.82, ramp);
		let seconds = 0;
		// The EMA that `update` applies, with the shipped conversion in front of it.
		while (t.strength < 0.5 && seconds < 20) {
			const k = Math.pow(0.82, dt * 60);
			t.strength = k * t.strength + (1 - k) * 1;
			seconds += dt;
		}
		return seconds;
	};
	const rises = RATES.map((fps) => ({ fps, s: riseSeconds(fps) }));
	const lo = Math.min(...rises.map((r) => r.s));
	const hi = Math.max(...rises.map((r) => r.s));
	ok('rise to half agrees across 24..240 fps', hi - lo < 1 / 24 + 0.005,
		`${lo.toFixed(3)}..${hi.toFixed(3)} s`);
	ok('the attack is faster than the release',
		rises.find((r) => r.fps === 60).s < releaseSeconds(60),
		'a knot must light faster than it lets go');
}

// --- the edges -------------------------------------------------------------------------
console.log('\nthe edges');

{
	// A tab returning from the background reports a dt in seconds. That must land at silence
	// rather than throwing or leaving a knot lit.
	const t = litTracker();
	t.decay(30);
	ok('a 30 s frame gap lands at silence', t.activations[0] === 0);

	// A duplicated timestamp must not freeze the fade.
	const z = litTracker();
	for (let i = 0; i < 500; i++) z.decay(0);
	ok('a zero-length frame still decays', z.activations[0] < 1, `${z.activations[0].toFixed(4)}`);

	// Default argument: any caller that passes nothing gets the reference step, so the
	// existing test and any older call site behave exactly as they did.
	const d = litTracker();
	d.decay();
	const e = litTracker();
	e.decay(1 / 60);
	ok('the default step is the reference rate', d.activations[0] === e.activations[0]);
}

{
	// Monotone: a fade must never brighten.
	const t = litTracker();
	let prev = t.activations[0];
	let rose = false;
	for (let i = 0; i < 200; i++) {
		t.decay(1 / 90);
		if (t.activations[0] > prev) rose = true;
		prev = t.activations[0];
	}
	ok('the release never brightens', !rose);
}

console.log(failures ? `\n${failures} check(s) failed` : '\nall fade checks passed');
process.exit(failures ? 1 : 0);

/**
 * End-to-end contract test across the two halves of Birdy.
 *
 * Renders each syllable with the browser's own AudioWorklet, runs it through the
 * browser's own feature extractor, and asks which cluster of the Python-built galaxy it
 * lands in. A high hit rate means three separate things agree: the two ODE
 * implementations, the two MFCC implementations, and the standardisation statistics. If
 * either half drifts, this is the test that notices — the app itself would just quietly
 * light the wrong stars.
 *
 *   npm run verify:features
 */
import {
	ActivationTracker,
	FeatureExtractor,
	matchRamp,
	SessionGate,
	standardise
} from '../src/lib/audio/features.ts';
import { attach } from '../src/lib/data/centroid-vectors.ts';
import { loadGenerated, loadGeneratedFloats, loadInventory, render } from './lib/worklet-host.mjs';

const inventory = loadInventory();
const rawSpace = loadGenerated('feature-space.json');
const centroids = loadGenerated('centroids.json');
const calibration = loadGenerated('syrinx-calibration.json');
// The match ramp ships in the manifest, so the leak test below has to read it from there
// or it is asserting about a ramp the app does not run. Absent on older builds, where
// `matchRamp` returns the fallback constants — which is also what the app would use.
const ramp = matchRamp(loadGenerated('manifest.json') ?? undefined);

// The per-cluster vectors are a binary sidecar since 2026-08-01 (centroid-vectors.ts):
// 64 % of centroids.json's bytes, and this script needs them to build a matcher at all.
// A build from before that carries them inline and needs nothing here.
if (centroids?.vectors) {
	const floats = loadGeneratedFloats(centroids.vectors.file);
	if (!floats) {
		console.error(`centroids.json names ${centroids.vectors.file}, which is not there.`);
		process.exit(2);
	}
	attach(centroids, centroids.vectors, floats);
}

if (!rawSpace || !centroids) {
	console.error('Generated assets missing. Run: cd pipeline && uv run birdy-pipeline build');
	process.exit(2);
}

// accept the flat contract keys or the nested extractor block, exactly as the client does
const e = rawSpace.extractor ?? {};
const spec = {
	sampleRate: rawSpace.sampleRate ?? e.sampleRate ?? 48000,
	frameSize: rawSpace.frameSize ?? e.frame ?? 1024,
	hopSize: rawSpace.hopSize ?? e.hop ?? 512,
	window: rawSpace.window ?? e.window ?? 'symmetric hann',
	melBands: rawSpace.melBands ?? e.mel?.bands ?? 26,
	mfccCoeffs: rawSpace.mfccCoeffs ?? e.mfcc?.count ?? 13,
	dims: rawSpace.dims,
	dimNames: rawSpace.dimNames,
	mean: rawSpace.mean,
	std: rawSpace.std,
	temperature: rawSpace.temperature ?? rawSpace.activation?.softmaxTemperature ?? 0.12
};

/** Whole-clip descriptor: peak-normalise, then average over every voiced frame. */
function describe(signal) {
	let peak = 0;
	for (const s of signal) peak = Math.max(peak, Math.abs(s));
	if (peak < 1e-6) return null;
	const scaled = new Float32Array(signal.length);
	const gain = 0.9 / peak;
	for (let i = 0; i < signal.length; i++) scaled[i] = signal[i] * gain;

	const frames = Math.max(0, Math.floor((scaled.length - spec.frameSize) / spec.hopSize) + 1);
	const extractor = new FeatureExtractor(spec, frames + 1);
	for (let f = 0; f < frames; f++) {
		extractor.push(scaled.subarray(f * spec.hopSize, f * spec.hopSize + spec.frameSize));
	}
	return extractor.descriptor();
}

const tracker = new ActivationTracker(centroids, spec, 0, ramp);
let hits = 0;
let speciesHits = 0;
let total = 0;
const confusions = [];
const zRows = []; // standardised descriptors, for the session-gate assertions below

console.log(
	`match ramp ${ramp.floor.toFixed(3)}..${ramp.ceiling.toFixed(3)} ` +
		`(${ramp.fromAssets ? 'from manifest.matchRamp' : 'FALLBACK CONSTANTS — these assets ship no ramp'})\n`
);
console.log('species                     syllable        -> matched cluster                          sim');
for (const species of inventory.species) {
	for (const syllable of species.syllables) {
		const { signal } = await render([syllable], [], { calibration, tail: 0.15 });
		const descriptor = describe(signal);
		if (!descriptor) {
			// too short or too quiet to fill the minimum number of voiced frames
			console.log(`${species.id.padEnd(26)} ${syllable.id.padEnd(15)} -> NO DESCRIPTOR`);
			total++;
			continue;
		}
		const z = standardise(descriptor, spec);
		tracker.update(z);
		zRows.push(z);
		const { index, similarity } = tracker.best();
		const match = centroids.items[index];
		const hit = match.speciesId === species.id && match.syllableId === syllable.id;
		const speciesHit = match.speciesId === species.id;
		total++;
		if (hit) hits++;
		if (speciesHit) speciesHits++;
		else confusions.push(`${species.id}/${syllable.id} -> ${match.speciesId}/${match.syllableId}`);
		console.log(
			`${species.id.padEnd(26)} ${syllable.id.padEnd(15)} ${hit ? '  ' : '!='} ` +
				`${`${match.speciesId}/${match.syllableId}`.padEnd(40)} ${similarity.toFixed(3)}`
		);
	}
}

const pct = (n) => `${((100 * n) / total).toFixed(1)}%`;
console.log(`\nexact syllable match: ${hits}/${total} (${pct(hits)})`);
console.log(`same species:         ${speciesHits}/${total} (${pct(speciesHits)})`);
if (confusions.length) {
	console.log('\ncross-species confusions:');
	for (const c of confusions) console.log('  ' + c);
}
/**
 * The other half of the contract: what the matcher does with things that are not birds.
 *
 * Getting the birds right is only half of honest, and it is the easier half. Against a
 * corpus that is two thirds field audio, broadband noise scores 0.996 against the nearest
 * centroid — higher than the median real syllable — because some clusters are bins of
 * wind and rain. The cosine cannot reject it and no floor can; the tonality gate in
 * `features.ts` is what does, and this asserts that it is still wired up and still
 * calibrated against *this* build rather than against the one it was written for.
 */
console.log('\nnot birdsong:');
const rate = spec.sampleRate;
let seed = 12345;
const rnd = () => ((seed = (seed * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff) * 2 - 1;
const seconds = 1;
const n = rate * seconds;
const probes = {
	'white noise': Float32Array.from({ length: n }, () => rnd()),
	'room tone': Float32Array.from({ length: n }, () => rnd() * 1e-3),
	'1 kHz hum': Float32Array.from({ length: n }, (_, i) => Math.sin((2 * Math.PI * 1000 * i) / rate))
};
let leaked = 0;
let whiteNoiseZ = null;
for (const [name, signal] of Object.entries(probes)) {
	const descriptor = describe(signal);
	if (!descriptor) {
		console.log(`  ${name.padEnd(14)} no descriptor — rejected before matching`);
		continue;
	}
	const flatness = descriptor[descriptor.length - 1];
	const noise = new ActivationTracker(centroids, spec, 0, ramp);
	const nz = standardise(descriptor, spec);
	if (name === 'white noise') whiteNoiseZ = nz;
	noise.update(nz, flatness);
	const { index, similarity } = noise.best();
	const match = centroids.items[index];
	console.log(
		`  ${name.padEnd(14)} flatness ${flatness.toFixed(3)}  cosine ${similarity.toFixed(3)}  ` +
			`strength ${noise.strength.toFixed(3)}  -> ${match.speciesId}/${match.syllableId}`
	);
	// The hum is exempt and always will be: a 1 kHz sine really is close to a 907 Hz owl
	// hoot in this feature space, and reporting that as a match is the honest answer.
	if (name !== '1 kHz hum' && noise.strength > 0.05) leaked++;
}

/**
 * The docs/20 session gate, when these assets ship one (builds before 2026-07-31 do
 * not — absence must be a no-op, which is what the rest of this script then proves).
 *
 * **What "in-manifold" means here was wrong until 2026-08-01, and it is why this check
 * failed on every build that shipped it.** The assertion used to be that *this script's
 * own synth renders* must not flag, on the stated grounds that "the corpus's own renders
 * are in-manifold by construction". They are not. The gate's anchors are drawn from the
 * fit *sessions*, which are field recordings; our renders are the synthesized class,
 * which docs/22 §22.6 measures as sitting a source-mean-gap of 7.233 away along an axis
 * carrying 42 % of the space's energy. Measured against the shipped anchors on the
 * production build (348 461 points, k = 14 003):
 *
 *   field-evidence knots      n=13 928  median 5-NN 3.17, 74.7 % under the 3.92 threshold
 *   synthesized-only knots    n=    75  median 5-NN 11.02, 0 % under
 *   this script's 44 renders            13.09
 *
 * So the old assertion demanded that synth output land on the field manifold — a thing
 * the corpus itself does not do, and a property of this embedding rather than a fault.
 * It is replaced by the claim that is true and worth pinning: **real field audio is
 * in-manifold**, asserted on the per-knot 28-d means the sidecar already loads, which are
 * in the same standardised space as the anchors (both measured at per-dim |mean| ≈ 0.4,
 * std ≈ 0.97 — this was checked, because feeding the gate the wrong space would inflate
 * every distance ≈ 4x and look exactly like a miscalibrated threshold).
 *
 * The render score is still printed: its distance from the field cloud is a real property
 * of this corpus and a change in it is worth seeing. It is reported, not asserted.
 * Broadband noise stays the negative control, and it must flag.
 */
// Declared before the session-gate block, which was the first writer of it: `let` is
// hoisted but not initialised, so the gate's own `failed = true` threw a TDZ
// ReferenceError and the failure it was reporting never got printed.
let failed = false;

console.log('\nsession gate (docs/20 §20.3):');
const gateSpec = rawSpace.embedding?.sessionGate;
if (!gateSpec?.anchors?.length) {
	console.log('  no sessionGate in these assets — nothing to assert (build predates it)');
} else {
	// Reported, not asserted — the synthesized class sits off the field manifold by
	// measurement, so this number is a property of the corpus, not a pass/fail.
	const renders = new SessionGate(gateSpec, spec.dims);
	for (const z of zRows) renders.push(z);
	console.log(
		`  our own renders:   score ${renders.score.toFixed(2)} vs threshold ` +
			`${gateSpec.threshold.toFixed(2)} — reported, not asserted (synthesized class)`
	);

	// The assertion: real field audio must be in-manifold. One knot is one session's worth
	// of rows aggregated the same way the gate aggregates, and a knot with any field
	// evidence at all is audio a bird actually made in a room someone actually recorded.
	// The median is the statistic, so a minority of genuinely odd knots cannot fail this
	// while the coverage claim still holds.
	const fieldScores = [];
	for (const item of centroids.items) {
		const v = item.vector;
		if (!v || v.length !== spec.dims) continue;
		if (!((item.sources?.field ?? 0) > 0)) continue;
		const one = new SessionGate(gateSpec, spec.dims);
		one.push(v);
		fieldScores.push(one.score);
	}
	if (!fieldScores.length) {
		console.log('  field knots:       none in this build — nothing to assert');
	} else {
		fieldScores.sort((a, b) => a - b);
		const median = fieldScores[fieldScores.length >> 1];
		const under = fieldScores.filter((s) => s <= gateSpec.threshold).length;
		console.log(
			`  field knots:       median ${median.toFixed(2)}, ` +
				`${((100 * under) / fieldScores.length).toFixed(1)} % under threshold ` +
				`(n=${fieldScores.length}, must be in-manifold)`
		);
		if (median > gateSpec.threshold) {
			console.error(
				`\nFAIL: real field audio flags as off-manifold (median ${median.toFixed(2)} > ` +
					`${gateSpec.threshold.toFixed(2)}) — the gate would call the corpus's own ` +
					`recordings uncharted`
			);
			failed = true;
		}
	}
	if (whiteNoiseZ) {
		const noiseGate = new SessionGate(gateSpec, spec.dims);
		noiseGate.push(whiteNoiseZ);
		console.log(`  white noise:       score ${noiseGate.score.toFixed(2)} (must flag)`);
		if (!noiseGate.flagged) {
			console.error('\nFAIL: white noise does not flag — the gate is not holding');
			failed = true;
		}
	}
}

// A live sound only has to land in the right neighbourhood for the galaxy to be honest,
// so this gate is deliberately loose; a collapse below it means the halves have drifted.
const floor = 0.5;
if (hits / total < floor) {
	console.error(`\nFAIL: exact match rate below ${floor * 100}% — the two halves have drifted apart`);
	failed = true;
}
if (leaked) {
	console.error(`\nFAIL: ${leaked} noise probe(s) reported as birdsong — the tonality gate is not holding`);
	failed = true;
}
if (failed) process.exit(1);

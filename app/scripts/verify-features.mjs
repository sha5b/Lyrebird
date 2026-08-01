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
import { ActivationTracker, FeatureExtractor, SessionGate, standardise } from '../src/lib/audio/features.ts';
import { attach } from '../src/lib/data/centroid-vectors.ts';
import { loadGenerated, loadGeneratedFloats, loadInventory, render } from './lib/worklet-host.mjs';

const inventory = loadInventory();
const rawSpace = loadGenerated('feature-space.json');
const centroids = loadGenerated('centroids.json');
const calibration = loadGenerated('syrinx-calibration.json');

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

const tracker = new ActivationTracker(centroids, spec, 0);
let hits = 0;
let speciesHits = 0;
let total = 0;
const confusions = [];
const zRows = []; // standardised descriptors, for the session-gate assertions below

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
	const noise = new ActivationTracker(centroids, spec, 0);
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
 * The corpus's own renders are in-manifold by construction, so they must not flag;
 * broadband noise is the negative control, and it must.
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
	const corpus = new SessionGate(gateSpec, spec.dims);
	for (const z of zRows) corpus.push(z);
	console.log(
		`  in-corpus renders: score ${corpus.score.toFixed(2)} vs threshold ${gateSpec.threshold.toFixed(2)}`
	);
	if (corpus.flagged) {
		console.error("\nFAIL: the corpus's own renders flag as off-manifold");
		failed = true;
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

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
import { ActivationTracker, FeatureExtractor, standardise } from '../src/lib/audio/features.ts';
import { loadGenerated, loadInventory, render } from './lib/worklet-host.mjs';

const inventory = loadInventory();
const rawSpace = loadGenerated('feature-space.json');
const centroids = loadGenerated('centroids.json');
const calibration = loadGenerated('syrinx-calibration.json');

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
		tracker.update(standardise(descriptor, spec));
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
// A live sound only has to land in the right neighbourhood for the galaxy to be honest,
// so this gate is deliberately loose; a collapse below it means the halves have drifted.
const floor = 0.5;
if (hits / total < floor) {
	console.error(`\nFAIL: exact match rate below ${floor * 100}% — the two halves have drifted apart`);
	process.exit(1);
}

/**
 * Pitch regression for the browser synth.
 *
 * Renders every syllable in data/inventory.json through the real AudioWorklet processor
 * and checks that the measured F0 matches the requested contour. Run it after touching
 * the worklet, the contract, or the calibration table.
 *
 *   npm run verify:synth
 *   npm run demo:wav          # also writes listenable wavs to out/wav
 */
import { mkdirSync } from 'node:fs';
import { join, resolve } from 'node:path';
import {
	APP_ROOT,
	SAMPLE_RATE,
	contourAt,
	loadGenerated,
	loadInventory,
	measureF0,
	render,
	rms,
	writeWav
} from './lib/worklet-host.mjs';

const args = process.argv.slice(2);
const wavIndex = args.indexOf('--wav');
const wavDir = wavIndex >= 0 ? resolve(APP_ROOT, args[wavIndex + 1] ?? 'out/wav') : null;

const inventory = loadInventory();
const calibration = loadGenerated('syrinx-calibration.json');
if (wavDir) mkdirSync(wavDir, { recursive: true });

console.log(
	`syrinx worklet harness — ${calibration ? 'using calibration table' : 'analytic beta fallback'}`
);
console.log('species                     syllable        want Hz   got Hz   err    rms   verdict');

let failures = 0;
let checked = 0;
const errors = [];

for (const species of inventory.species) {
	for (const syllable of species.syllables) {
		const { signal } = await render([syllable], [], { calibration });
		const want = contourAt(syllable, 0.5);
		// Centre the window on the midpoint and keep it as narrow as the contour allows,
		// but never shorter than ~8 periods, or there is nothing to count.
		const half = Math.min(syllable.dur * 0.2, Math.max(syllable.dur * 0.06, 8 / want));
		const from = (0.02 + syllable.dur * 0.5 - half) * SAMPLE_RATE;
		const to = (0.02 + syllable.dur * 0.5 + half) * SAMPLE_RATE;
		const measured = measureF0(signal, from, to);
		const level = rms(signal, from, to);
		const err = measured > 0 ? Math.abs(measured - want) / want : 1;
		// Buzz syllables are deliberately driven into the nonlinear regime, where the
		// perceived pitch may be a subharmonic — only require them to make sound.
		const tolerance = syllable.timbre === 'buzz' ? 0.55 : 0.2;
		const silent = level < 2e-3;
		const ok = !silent && err <= tolerance;
		checked++;
		if (!ok) failures++;
		else errors.push(err);
		console.log(
			`${species.id.padEnd(26)} ${syllable.id.padEnd(15)} ${String(Math.round(want)).padStart(7)} ` +
				`${String(Math.round(measured)).padStart(8)} ${(err * 100).toFixed(0).padStart(4)}% ` +
				`${level.toFixed(3).padStart(6)}  ${ok ? 'ok' : silent ? 'SILENT' : 'PITCH'}`
		);
		if (wavDir) writeWav(join(wavDir, `${species.id}-${syllable.id}.wav`), signal);
	}

	if (wavDir) {
		for (const song of species.songs) {
			const syllables = song.sequence
				.map((id) => species.syllables.find((s) => s.id === id))
				.filter(Boolean);
			if (!syllables.length) continue;
			const { signal } = await render(syllables, song.gaps, { calibration });
			writeWav(join(wavDir, `song-${species.id}-${song.id}.wav`), signal);
		}
	}
}

const median = errors.sort((a, b) => a - b)[Math.floor(errors.length / 2)] ?? 0;
console.log(`\n${checked - failures}/${checked} syllables ok, median pitch error ${(median * 100).toFixed(1)}%`);
if (wavDir) console.log(`wavs written to ${wavDir}`);
process.exit(failures > 0 ? 1 : 0);

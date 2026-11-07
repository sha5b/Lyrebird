/**
 * The page accent's rules, swept over every species the build ships.
 *
 * Black means nothing is chosen and nothing is sounding, so it has to be exactly black. A bird's
 * accent is also text on white and a fill behind white labels, so it has to stay legible at every
 * loudness and pitch, on every hue the hash can produce, and that fails quietly: a yellow reads as
 * "a bit pale" rather than as anything broken.
 *
 * Run with `npm run verify:accent`. Exits non-zero on any disagreement.
 */
import { readFileSync } from 'node:fs';
import { accentRgb, contrastOnWhite, hslToRgb, pitchPosition } from '../src/lib/accent.ts';

let failures = 0;
const ok = (name, cond, detail = '') => {
	if (cond) console.log(`  ${name.padEnd(58)} ok${detail ? ` (${detail})` : ''}`);
	else {
		failures++;
		console.error(`  ${name.padEnd(58)} FAIL ${detail}`);
	}
};
const hex = (rgb) => `#${rgb.toString(16).padStart(6, '0')}`;

const index = JSON.parse(readFileSync('static/lyrebird/inventory/index.json', 'utf8'));
const ids = (index.species ?? index).map((s) => s.id);
console.log(`species swept: ${ids.length}`);

// --- black at rest
ok('no bird, silence: exactly black', accentRgb('', '', 0, 0.5) === 0);
ok('no bird, singer known, silence: exactly black', accentRgb('', ids[0], 0, 0.5) === 0);
ok('no bird, loud, nobody known: black', accentRgb('', '', 1, 0.5) === 0);

// --- contrast, everywhere
let worst = Infinity;
let worstAt = '';
const LEVELS = [0, 0.02, 0.1, 0.3, 0.6, 1];
const PITCHES = [0, 0.25, 0.5, 0.75, 1];
for (const id of ids) {
	for (const level of LEVELS) {
		for (const pitch of PITCHES) {
			for (const [bird, singer] of [
				[id, ''],
				['', id]
			]) {
				const c = contrastOnWhite(accentRgb(bird, singer, level, pitch));
				if (c < worst) {
					worst = c;
					worstAt = `${id} level ${level} pitch ${pitch}`;
				}
			}
		}
	}
}
ok('every accent holds 4.5:1 on white', worst >= 4.5, `worst ${worst.toFixed(2)}, ${worstAt}`);

// --- a chosen bird shows at rest, and differs from others
const a = ids[0];
ok('bird chosen, silence: not black', accentRgb(a, '', 0, 0.5) !== 0, hex(accentRgb(a, '', 0, 0.5)));
const rests = new Set(ids.map((id) => accentRgb(id, '', 0, 0.5)));
ok('birds get distinct resting colours', rests.size > ids.length * 0.5, `${rests.size} of ${ids.length}`);

// --- the chosen bird wins over whoever else is singing
ok(
	'a chosen bird ignores another singer',
	accentRgb(a, ids[1], 0.5, 0.5) === accentRgb(a, '', 0.5, 0.5)
);

// --- it reacts
const quiet = accentRgb(a, '', 0, 0.5);
const loud = accentRgb(a, '', 1, 0.5);
ok('loudness changes a chosen bird', quiet !== loud, `${hex(quiet)} -> ${hex(loud)}`);
const low = accentRgb(a, '', 0.5, 0);
const high = accentRgb(a, '', 0.5, 1);
ok('pitch changes a chosen bird', low !== high, `${hex(low)} -> ${hex(high)}`);
ok(
	'pitch has no effect in silence',
	accentRgb(a, '', 0, 0) === accentRgb(a, '', 0, 1),
	'the hue must not wander on a stale pitch'
);
const lum = (rgb) => ((rgb >> 16) & 255) + ((rgb >> 8) & 255) + (rgb & 255);
ok(
	'no bird: rises out of black with loudness',
	lum(accentRgb('', a, 0.1, 0.5)) < lum(accentRgb('', a, 0.5, 0.5)) &&
		lum(accentRgb('', a, 0.5, 0.5)) < lum(accentRgb('', a, 1, 0.5))
);

// --- units and edge values
ok('pitch 0 Hz sits mid-range', pitchPosition(0) === 0.5);
ok('pitch NaN sits mid-range', pitchPosition(NaN) === 0.5);
ok('pitch below range clamps', pitchPosition(10) === 0);
ok('pitch above range clamps', pitchPosition(40000) === 1);
ok('pitch is monotonic', pitchPosition(1000) < pitchPosition(4000));
ok('hsl pure red', hslToRgb(0, 100, 50) === 0xff0000, hex(hslToRgb(0, 100, 50)));
ok('hsl wraps negative hue', hslToRgb(-120, 100, 50) === hslToRgb(240, 100, 50));
ok('overdriven level is clamped', accentRgb(a, '', 5, 0.5) === accentRgb(a, '', 1, 0.5));

if (failures) {
	console.error(`\n${failures} check(s) failed`);
	process.exit(1);
}
console.log('\nall checks passed');

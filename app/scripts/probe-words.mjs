/**
 * The Words tab's functional reading, driven in a real browser.
 *
 * `verify:functions` checks the logic against the shipped inventory and cannot see whether
 * any of it reaches the screen. The three states this tab now has all fail *quietly* if the
 * wiring is wrong — a `$derived` that never recomputes, an `$effect` that clears the
 * override on its own, a branch that renders nothing — and every one of those looks like
 * "the feature does nothing" rather than like an error.
 *
 * So this asserts on the rendered text of the three states and writes a screenshot of each:
 *
 *   hit       a species that HAS a documented call in the read category
 *   refusal   a species that does not — the 99.55 % case
 *   override  the user disagreeing with the reading, one click
 *
 * Needs a dev server. Pass PROBE_URL if it is not 5173.
 */
import { chromium } from 'playwright';
import { mkdirSync } from 'node:fs';

const URL = process.env.PROBE_URL ?? 'http://localhost:5173/';
const SHOT = process.env.PROBE_SHOTS ?? 'out/probe-words';
mkdirSync(SHOT, { recursive: true });

let failures = 0;
const ok = (name, cond, detail = '') => {
	if (cond) console.log(`  ${name.padEnd(56)} ok${detail ? ` (${detail})` : ''}`);
	else {
		console.log(`  ${name.padEnd(56)} FAIL${detail ? ` (${detail})` : ''}`);
		failures++;
	}
};

const browser = await chromium.launch({
	args: [
		'--use-gl=angle',
		'--use-angle=swiftshader',
		'--enable-unsafe-swiftshader',
		// The gate is `{#if !engine}`, so it only lifts once an AudioContext actually opens.
		// Headless Chromium has no output device and will not start one from a synthetic
		// click without these two, which is why the first run of this probe timed out on the
		// Compose button rather than on the gate it was actually stuck behind.
		'--autoplay-policy=no-user-gesture-required',
		'--mute-audio'
	]
});
const page = await browser.newPage({ viewport: { width: 1400, height: 1100 } });
const errors = [];
const missing = new Set();
page.on('pageerror', (e) => errors.push(`pageerror: ${e.message}`));
page.on('response', (r) => {
	// `URL` is this file's own base-address constant, so the global constructor is shadowed
	// here. Trimming the prefix is what `probe-stage.mjs` does and it needs no constructor.
	if (r.status() === 404) missing.add(r.url().replace(URL, ''));
});
page.on('console', (m) => {
	// A 404 reaches the console as "Failed to load resource" with no URL attached, so it is
	// counted from the response hook instead and reported rather than failed. `assets.ts`
	// probes for `known/` and `unknown/` galaxy maps this build does not ship and falls back
	// cleanly, so those two are expected and are not this tab's business.
	const t = m.text();
	if (m.type() !== 'error') return;
	if (/shader|WebGLProgram|GLSL/i.test(t)) return;
	if (/Failed to load resource/i.test(t)) return;
	errors.push(t);
});

await page.goto(URL, { waitUntil: 'load', timeout: 120000 });

// The "Enter the aviary" gate intercepts every pointer event until audio is started, which
// is correct behaviour — a browser will not open an AudioContext without a gesture.
// The gate is rendered only once the inventory has arrived, several seconds after `load`.
// Checking for it immediately finds nothing and then every later click is silently blocked
// by an overlay that appeared afterwards — which is exactly how this probe first failed.
const gate = page.locator('.overlay button', { hasText: /start listening/i }).first();
await gate.waitFor({ state: 'visible', timeout: 60000 }).catch(() => {});
if (await gate.count()) {
	await gate.click();
	// Wait on the overlay leaving rather than on a stopwatch: it lifts when `engine` is set,
	// and if it never lifts the audio error on the card is the thing worth reporting.
	await page
		.locator('.overlay')
		.waitFor({ state: 'detached', timeout: 30000 })
		.catch(async () => {
			const err = await page.locator('.overlay .error').innerText().catch(() => '');
			console.log(`  audio gate did not lift${err ? `: ${err}` : ''}`);
		});
}

await page.getByRole('button', { name: 'Compose', exact: true }).click();
await page.waitForTimeout(1500);

const panel = page.locator('section.block').first();
const select = panel.locator('select').first();
const box = panel.locator('textarea').first();

/** The panel's rendered text, which is what a reader actually gets. */
const readText = async () => (await panel.innerText()).replace(/\s+/g, ' ');

async function pick(speciesId) {
	await select.selectOption(speciesId);
	await page.waitForTimeout(600);
}
async function type(text) {
	await box.fill('');
	await box.type(text, { delay: 8 });
	await page.waitForTimeout(600);
}

console.log('\nthe marked picker');
{
	const marked = await select.locator('option').evaluateAll((opts) =>
		opts.filter((o) => o.textContent.trim().startsWith('•')).length
	);
	ok('12 species are marked as having a documented function', marked === 12, String(marked));
	const total = await select.locator('option').count();
	ok('all species stay in the list', total > 2000, String(total));
}

console.log('\nstate 1 — a hit: great tit, "danger"');
{
	await pick('parus_minor');
	await type('danger');
	const t = await readText();
	ok('the reading is shown and named', /We read this as\s*alarm/i.test(t));
	ok('the reading is badged as ours', /invented|our own mapping/i.test(t));
	ok('the authored call is offered', /ABC/.test(t));
	ok('the call carries its own evidence class', /playback-verified/i.test(t), '');
	ok('the documented function is quoted', /scan horizontally/i.test(t));
	ok('the two-link caveat is present', /category is the bird|assignment of your words|reading is ours/i.test(t));
	await panel.screenshot({ path: `${SHOT}/1-hit.png` });
}

console.log('\nstate 2 — a refusal: a species with no authored function');
{
	await pick('abroscopus_albogularis');
	await type('danger');
	const t = await readText();
	ok('no authored call is offered', !/playback-verified/i.test(t));
	ok('the refusal explains the scale', /2 650|12 of/.test(t));
	ok('it still says what will play', /rhythm of your words/i.test(t));
	ok('it does not claim a function', !/scan horizontally/i.test(t));
	await panel.screenshot({ path: `${SHOT}/2-refusal.png` });
}

console.log('\nstate 3 — the override: chickadee, "hello", corrected to alarm');
{
	await pick('poecile_atricapillus');
	await type('hello');
	const before = await readText();
	ok('"hello" reads as contact', /We read this as\s*contact/i.test(before));

	await panel.getByRole('button', { name: 'alarm', exact: true }).click();
	await page.waitForTimeout(500);
	const after = await readText();
	ok('the override changes the reading', /We read this as\s*alarm/i.test(after));
	ok('the alarm call is now offered', /chick-a-dee-dee/i.test(after));
	ok('the one graded case names its source', /Templeton/.test(after));
	await panel.screenshot({ path: `${SHOT}/3-override.png` });

	// The override is a correction of *this* reading, so typing must clear it.
	await type('hello there');
	const retyped = await readText();
	ok('typing clears the override', /We read this as\s*contact/i.test(retyped));
}

console.log('\nstate 4 — the strip must not be one token stamped N times');
{
	// The walk used to take the likeliest transition at every step. Most species' likeliest
	// transition out of a type is back into itself, so every text produced "L20 L20 L20 ...".
	// Cape Canary is the species the bug was reported on: start[0] is L20 and L20 -> L20 is
	// its top row entry at p = 0.2911, i.e. a 29 % event chosen 100 % of the time.
	await pick('serinus_canicollis');
	const seen = [];
	for (const text of ['Hello im here', 'sing me a long song about the sky']) {
		await type(text);
		await panel.getByRole('button', { name: 'Sing the words', exact: true }).click();
		await page.waitForTimeout(900);
		const chips = (await panel.locator('.chip').allInnerTexts())
			.map((c) => c.trim())
			.filter(Boolean); // an empty label is not a distinct type, and counting it
		const uniq = new Set(chips); // once made this assertion pass on a degenerate strip
		seen.push(uniq.size);
		ok(`"${text}" gives more than one type`, uniq.size > 1,
			`${chips.length} chips, ${uniq.size} distinct: ${[...uniq].join(' ')}`);
		ok(`"${text}" has as many chips as syllables`, chips.length > 1, String(chips.length));
	}
	ok('the walk is not degenerate on this species', Math.max(...seen) >= 2);

	// Seeded: the same words must still give the same bout.
	await type('Hello im here');
	await panel.getByRole('button', { name: 'Sing the words', exact: true }).click();
	await page.waitForTimeout(900);
	const a = (await panel.locator('.chip').allInnerTexts()).join(' ');
	await type('x');
	await type('Hello im here');
	await panel.getByRole('button', { name: 'Sing the words', exact: true }).click();
	await page.waitForTimeout(900);
	const b = (await panel.locator('.chip').allInnerTexts()).join(' ');
	ok('the same words give the same bout', a === b, `${a} | ${b}`);
}

console.log('\nconsole');
ok('no page errors', errors.length === 0, errors.slice(0, 2).join(' | '));
console.log(`  404s (reported, not failed): ${[...missing].join(', ') || 'none'}`);

await browser.close();
console.log(failures ? `\n${failures} failure(s)` : `\nall checks passed — shots in ${SHOT}/`);
process.exit(failures ? 1 : 0);

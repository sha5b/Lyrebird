/**
 * The browser probe: what only a running app can answer.
 *
 * Three classes of change on this stage are invisible to `npm run check`, and each one fails
 * by drawing *nothing* rather than by erroring:
 *
 *   1. **A shader that will not link.** three.js logs "THREE.WebGLProgram: Shader Error" to
 *      console.error and then draws an empty scene. TypeScript never sees GLSL.
 *   2. **A CSS value the browser discards.** `max()` inside a custom property consumed by
 *      `calc()`, `color-mix`, a mistyped variable — all resolve to nothing and leave the mark
 *      at its rest state, which looks like "it does not react" and not like a fault.
 *   3. **A computed style that moved.** The kind the earlier rounds caught with a
 *      computed-style probe: `:global()` in a plain stylesheet, `.stagepage` left behind.
 *
 * So this asserts on console errors, computed styles and element counts rather than on
 * screenshots — pixel diffing was tried on this app and could not localise anything, because
 * the live cloud and the font rasterisation differ on every frame.
 *
 * Needs a dev server. `npm run probe:stage` starts nothing; pass PROBE_URL if it is not 5173.
 */
import { chromium } from 'playwright';

const URL = process.env.PROBE_URL ?? 'http://localhost:5173/';
const SHOT = process.env.PROBE_SHOTS ?? 'out/probe';

const browser = await chromium.launch({
	args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader']
});
const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });

const errors = [];
const shaderErrors = [];
page.on('console', (m) => {
	const t = m.text();
	if (/shader|WebGLProgram|GLSL|compile/i.test(t)) shaderErrors.push(`[${m.type()}] ${t}`);
	else if (m.type() === 'error') errors.push(t);
});
page.on('pageerror', (e) => errors.push(`pageerror: ${e.message}`));
const missing = [];
page.on('response', (r) => {
	if (r.status() === 404) missing.push(r.url().replace(URL, ''));
});

await page.goto(URL, { waitUntil: 'load', timeout: 120000 });

// The galaxy loads 77 MB of assets; wait for the readings row to report a point count.
await page.waitForFunction(
	() => /\d/.test(document.body.innerText) && !/loading/i.test(document.body.innerText),
	null,
	{ timeout: 180000 }
).catch(() => {});
await page.waitForTimeout(12000);

const say = (k, v) => console.log(`${k.padEnd(42)} ${v}`);

// --- the shader ------------------------------------------------------------------------
say('shader errors', shaderErrors.length ? `*** ${shaderErrors.length} ***` : 'none');
for (const e of shaderErrors.slice(0, 6)) console.log('   ', e.slice(0, 300));
say('other console errors', errors.length);
for (const e of errors.slice(0, 6)) console.log('   ', e.slice(0, 200));
say('404s', missing.length ? missing.join(', ').slice(0, 200) : 'none');

// **The audio gate.** Nothing on the stage is reachable until "Start listening" is clicked —
// the overlay intercepts every pointer event, which is correct behaviour and is what made the
// first run of this probe time out on the Display button.
const gate = page.locator('.overlay button', { hasText: /start listening/i }).first();
if (await gate.count()) {
	await gate.click();
	await page.waitForTimeout(2500);
	say('audio gate', 'entered');
}

// A tag only exists for a knot that is sounding, selected or pinned. Choosing a bird is the
// way to make one appear without any audio: NodeProjector gives a chosen bird's knots a tag
// whether or not they are active.
//
// **This block looked for a `<select>` and the species picker is not one.** It is a custom
// combobox — `button.picker-btn[aria-haspopup="listbox"]` — so `page.locator('select')`
// counted 0, the `if` skipped the whole pick, and every assertion downstream that needs a tag
// reported the *absence* of one as a pass: "tags on screen 0", "ring size (no tag visible)",
// and four `undefined` computed styles. A probe whose subject never appears is worse than no
// probe, so the pick is now asserted rather than guarded, and `say('chose a bird', ...)`
// reports the failure instead of falling silent.
const picker = page.locator('button.picker-btn').first();
if (await picker.count()) {
	await picker.click({ force: true });
	await page.waitForTimeout(600);
	// The list is filterable; typing narrows it to one row, which is more robust than
	// indexing into 2 489 options whose order is the inventory's.
	const search = page.locator('input[type="text"], input[type="search"]').first();
	const want = 'Chinese Barbet';
	if (await search.count()) {
		await search.fill(want);
		await page.waitForTimeout(800);
	}
	const option = page.locator('li, [role="option"], button').filter({ hasText: want }).first();
	if (await option.count()) {
		await option.click({ force: true });
		// The bird's shard has to arrive before its knots can be tagged, and that is a network
		// fetch — the run where this was given four seconds produced tags and the run where the
		// chorus was started instead produced none. Wait on the tag, not on a stopwatch.
		await page
			.waitForFunction(() => document.querySelectorAll('.tag .dot').length > 0, null, {
				timeout: 45000
			})
			.catch(() => {});
		const now = await page.locator('.picker-current').first().innerText().catch(() => '');
		say('chose a bird', now.includes(want) ? `${want} (picker reads "${now}")` : `*** wanted ${want}, picker reads "${now}" ***`);
	} else {
		say('chose a bird', `*** no option matching "${want}" in the picker ***`);
	}
} else {
	say('chose a bird', '*** no picker found: button.picker-btn is absent ***');
}

// A tag exists only for a knot that is sounding, selected or pinned, so the ring cannot be
// measured on a resting stage. The whole-aviary chorus is the reliable way to light some:
// selecting a bird from the picker did it on one run and not the next, which is a race with
// the shard fetch rather than a fact about the ring.
const chorus = page.locator('button', { hasText: /^Chorus$/i }).first();
if (await chorus.count()) {
	await chorus.click();
	await page.waitForTimeout(9000);
	say('chorus started', 'yes');
}

// Points actually drawing: the readings row prints the corpus size.
const readings = await page.locator('.readings').first().innerText().catch(() => '');
say('readings row', JSON.stringify(readings.replace(/\s+/g, ' ').slice(0, 120)));

// --- the grid --------------------------------------------------------------------------
const grid = await page.evaluate(() => {
	const stage = document.querySelector('.stage');
	if (!stage) return null;
	const cs = getComputedStyle(stage);
	return {
		size: cs.backgroundSize,
		position: cs.backgroundPosition,
		layers: cs.backgroundImage.split(/,(?![^(]*\))/).length,
		coarsePx: cs.getPropertyValue('--grid-coarse-px').trim(),
		at: cs.getPropertyValue('--grid-coarse-at').trim()
	};
});
say('grid layers (vignette + 2 lines)', grid?.layers);
say('grid tile', `${grid?.coarsePx} (offset ${grid?.at})`);
say('grid background-size', grid?.size);
const caption = await page.locator('.ruler-caption').first().innerText().catch(() => '');
say('ruler caption', JSON.stringify(caption.trim()));

// Grid tile must equal step * pxPerKnot, i.e. the caption's tick. Cross-check the numbers.
const tickMatch = /=\s*([\d.]+)\s*knot/.exec(caption);
say('caption tick value', tickMatch?.[1] ?? '(none)');

// --- the label dots --------------------------------------------------------------------
const dot = await page.evaluate(() => {
	const d = document.querySelector('.tag .dot');
	if (!d) return null;
	const cs = getComputedStyle(d);
	const tag = getComputedStyle(d.parentElement);
	return {
		w: cs.width,
		h: cs.height,
		background: cs.backgroundColor,
		border: `${cs.borderTopWidth} ${cs.borderTopColor}`,
		transform: cs.transform,
		blend: cs.mixBlendMode,
		ringOn: cs.getPropertyValue('--ring-on').trim(),
		act: tag.getPropertyValue('--act').trim(),
		hot: tag.getPropertyValue('--hot').trim(),
		tagFont: tag.fontSize,
		tags: document.querySelectorAll('.tag .dot').length,
		visibleTags: [...document.querySelectorAll('.tag')].filter(
			(t) => getComputedStyle(t).opacity !== '0'
		).length
	};
});
say('tags on screen', dot?.tags ?? 0);
say('ring size', dot ? `${dot.w} x ${dot.h} (tag font ${dot.tagFont})` : '(no tag visible)');
say('ring fill (must be none)', dot?.background);
say('ring border', dot?.border);
say('ring blend mode', dot?.blend);
say('ring --act / --hot', dot ? `${dot.act || '(unset)'} / ${dot.hot || '(unset)'}` : '-');
say('ring transform (scale)', dot?.transform);

// --- Display panel: the toggles --------------------------------------------------------
const viewBtn = page.locator('.viewbtn').first();
if (await viewBtn.count()) {
	await viewBtn.click();
	await page.waitForTimeout(600);
}
const checks = await page.evaluate(() =>
	[...document.querySelectorAll('label.check')].map((l) => l.innerText.trim())
);
say('display checkboxes', JSON.stringify(checks));
const provOrder = await page.evaluate(() => {
	const rows = [...document.querySelectorAll('label.check')]
		.map((l) => l.innerText.replace(/\s+/g, ' ').trim())
		.filter((t) => /%|none/.test(t));
	return rows;
});
say('provenance key order', JSON.stringify(provOrder));
say('"Local knot shape" gone', !checks.some((c) => /local knot/i.test(c)));
say('"Bird colours" present', checks.some((c) => /bird colour/i.test(c)));

// Toggle bird colours on and confirm no shader error follows.
const before = shaderErrors.length;
const birdBox = page.locator('label.check', { hasText: /bird colour/i }).locator('input');
if (await birdBox.count()) {
	await birdBox.check();
	await page.waitForTimeout(3000);
	say('bird colours: new shader errors', shaderErrors.length - before);
	await page.screenshot({ path: `${SHOT}/probe-bird-colours.png` });
	// mutual exclusion
	const prov = page.locator('label.check', { hasText: /provenance colour/i }).locator('input');
	await prov.check();
	await page.waitForTimeout(1200);
	say('bird cleared when prov chosen', !(await birdBox.isChecked()));
	await birdBox.check();
	await page.waitForTimeout(1200);
	say('prov cleared when bird chosen', !(await prov.isChecked()));
	await birdBox.uncheck();
	await page.waitForTimeout(800);
}

await page.screenshot({ path: `${SHOT}/probe-stage.png` });

// --- the info page ---------------------------------------------------------------------
const infoOpen = page.locator('.reading-open', { hasText: /info/i }).first();
if (await infoOpen.count()) {
	await infoOpen.click();
	await page.waitForTimeout(1500);
	const dl = await page.evaluate(() => {
		const row = document.querySelector('.downloads');
		if (!row) return null;
		const kids = [...row.children].map((k) => {
			const cs = getComputedStyle(k);
			const r = k.getBoundingClientRect();
			return {
				text: k.innerText.replace(/\s+/g, ' ').trim().slice(0, 48),
				h: Math.round(r.height),
				border: cs.borderTopWidth,
				bg: cs.backgroundColor
			};
		});
		const fig = document.querySelector('.figure img');
		const figBox = fig?.getBoundingClientRect();
		const col = fig?.closest('.pagecol, .pagesection, div')?.getBoundingClientRect();
		return { kids, figW: Math.round(figBox?.width ?? 0), colW: Math.round(col?.width ?? 0) };
	});
	say('downloads row', JSON.stringify(dl?.kids));
	say('figure width vs container', `${dl?.figW} / ${dl?.colW}`);
	await page.screenshot({ path: `${SHOT}/probe-info.png`, fullPage: false });
	await page.locator('.pageclose').first().click().catch(() => {});
	await page.waitForTimeout(800);
}

// --- the learn page --------------------------------------------------------------------
const learnOpen = page.locator('.reading-open', { hasText: /learn/i }).first();
if (await learnOpen.count()) {
	await learnOpen.click();
	await page.waitForTimeout(1500);
	const order = await page.evaluate(() => {
		const titles = [...document.querySelectorAll('.blocktitle')].map((h) => h.innerText.trim());
		const drawer = document.querySelector('details.rollup.block > summary')?.innerText.trim();
		const inDrawer = [
			...(document.querySelector('details.rollup.block')?.querySelectorAll('.blocktitle') ?? [])
		].map((h) => h.innerText.trim());
		return { titles, drawer, inDrawer };
	});
	say('learn section order', JSON.stringify(order.titles));
	say('drawer summary', JSON.stringify(order.drawer));
	say('inside the drawer', JSON.stringify(order.inDrawer));
	await page.screenshot({ path: `${SHOT}/probe-learn.png`, fullPage: false });
}

say('TOTAL shader errors', shaderErrors.length);
await browser.close();

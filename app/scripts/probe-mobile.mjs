/**
 * The phone probe: does this instrument fit in a hand?
 *
 * The stage was laid out for a 1600 px bench — a 20 rem control column pinned top-left, a
 * reading card under it, a display panel hanging off the top-right corner and a history strip
 * running between them. None of that survives a 390 px viewport on its own, and every way it
 * fails is silent: a panel wider than the screen simply clips, a strip whose left edge is
 * computed as `20rem + 3rem` from the left and `1rem` from the right becomes a negative width,
 * and a control that lands under another control is still in the DOM and still passes every
 * check we have.
 *
 * So this asserts the four things a phone layout has to be true about, at three viewports:
 *
 *   1. **Nothing overflows the viewport.** Every panel, the dock and the history strip are
 *      measured against the window box; anything sticking out is named with its overhang.
 *   2. **Every control is reachable.** The dock's sheets open, one at a time, and the sheet
 *      that opens is the one that was asked for.
 *   3. **Touch targets are big enough.** 44 px is Apple's floor and Google's is 48; the
 *      smallest interactive box in each open sheet is reported against 44.
 *   4. **The stage keeps its share.** A sheet may not cover more of the screen than it is
 *      allowed to, because the galaxy is the subject and a sheet is a drawer over it.
 *
 * Needs a dev server. Pass PROBE_URL if it is not on 5173.
 */
import { chromium } from 'playwright';

const URL = process.env.PROBE_URL ?? 'http://localhost:5173/';
const SHOT = process.env.PROBE_SHOTS ?? 'out/probe';
/** How much of the screen a sheet may take before it stops being a drawer over the stage. */
const SHEET_MAX_SHARE = 0.72;
/** The touch-target floor, in CSS pixels. */
const TOUCH_MIN = 44;
/** What a word inside a sentence gets instead. See the note at the measurement. */
const INLINE_MIN = 28;

const VIEWPORTS = [
	{ name: 'iphone-se', width: 375, height: 667 },
	{ name: 'iphone-14', width: 390, height: 844 },
	{ name: 'pixel-landscape', width: 844, height: 390 }
];

const browser = await chromium.launch({
	args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader']
});

const say = (k, v) => console.log(`${k.padEnd(44)} ${v}`);
const fails = [];
const fail = (msg) => {
	fails.push(msg);
	console.log(`   *** ${msg}`);
};

for (const vp of VIEWPORTS) {
	console.log(`\n=== ${vp.name} ${vp.width}x${vp.height} ==============================`);
	const page = await browser.newPage({
		viewport: { width: vp.width, height: vp.height },
		deviceScaleFactor: 2,
		isMobile: true,
		hasTouch: true
	});
	const errors = [];
	page.on('console', (m) => {
		if (m.type() === 'error') errors.push(m.text());
	});
	page.on('pageerror', (e) => errors.push(`pageerror: ${e.message}`));

	await page.goto(URL, { waitUntil: 'load', timeout: 120000 });
	await page
		.waitForFunction(() => document.querySelector('.bench') !== null, null, { timeout: 240000 })
		.catch(() => fail(`${vp.name}: the bench never mounted (assets still loading?)`));
	await page.waitForTimeout(3000);

	// The audio gate covers everything until it is dismissed, and on a phone it is the first
	// thing that has to fit.
	const gateBox = await page
		.locator('.overlay .card')
		.first()
		.boundingBox()
		.catch(() => null);
	if (gateBox) {
		say('audio gate card', `${Math.round(gateBox.width)}x${Math.round(gateBox.height)}`);
		if (gateBox.width > vp.width) fail(`${vp.name}: the audio gate is wider than the screen`);
		if (gateBox.height > vp.height) fail(`${vp.name}: the audio gate is taller than the screen`);
		await page.locator('.overlay button', { hasText: /start listening/i }).first().click();
		await page.waitForTimeout(2500);
	}

	// --- 1. the marks on the stage ------------------------------------------------------------
	//
	// **The knot rings, and this check exists because the first phone pass broke them.** A ring
	// is a `<button>`, so the 44 px touch floor written for the panels reached it too and every
	// one of them became a 5 × 44 capsule standing on the cloud. Nothing failed: the drawers
	// were measured, the overflow was measured, and the mark the whole galaxy is annotated with
	// was drawn as an oval for a round of probing. Three things are true of a ring or it is
	// wrong — it is round, it is the size the zoom says, and its centre is on its knot.
	//
	// Tags only exist for knots that are sounding, selected or pinned, so this samples across
	// the chorus rather than reading one frame — and it runs **before** the dock loop below,
	// which is not tidiness. Opening the Compose drawer silences the aviary and returning to
	// Sing deliberately stays silent (`state/performance.ts`'s `stop` contract, asserted in
	// verify:performance), so a ring check placed after the loop measures a stage where nothing
	// can sound. It reported "no knot tag ever appeared" for three viewports, which is exactly
	// the shape of a probe whose subject never arrives: it says nothing and looks like a pass.
	const rings = { seen: 0, oval: 0, offKnot: 0, worstOff: 0, overhang: 0, flipped: 0 };
	// The whole-aviary chorus starts itself when the gate is entered, but the first song has to
	// wait for a species shard to arrive and for the scheduler's own gap — tens of seconds on a
	// cold cache, and none of it under this probe's control. Waiting on the tag rather than on a
	// stopwatch is the difference between measuring the rings and reporting that there were none.
	await page
		.waitForFunction(
			() =>
				[...document.querySelectorAll('.tag')].some(
					(t) => getComputedStyle(t).visibility !== 'hidden' && getComputedStyle(t).opacity !== '0'
				),
			null,
			{ timeout: 90000 }
		)
		.catch(() => {});
	for (let i = 0; i < 12; i++) {
		const frame = await page.evaluate(() => {
			const w = window.innerWidth;
			const out = [];
			for (const tag of document.querySelectorAll('.tag')) {
				const cs = getComputedStyle(tag);
				if (cs.visibility === 'hidden' || cs.opacity === '0') continue;
				const r = tag.getBoundingClientRect();
				const dot = tag.querySelector('.dot');
				if (!dot) continue;
				const d = dot.getBoundingClientRect();
				const flip = tag.classList.contains('flip');
				// The knot is the box's origin before the flip's own translate: its right edge
				// when flipped, its left edge otherwise.
				const knot = flip ? r.right : r.x;
				out.push({
					flip,
					round: Math.abs(d.width - d.height) < 0.5,
					off: Math.abs(d.x + d.width / 2 - knot),
					over: Math.max(0, r.right - w, -r.x)
				});
			}
			return out;
		});
		for (const t of frame) {
			rings.seen++;
			if (t.flip) rings.flipped++;
			if (!t.round) rings.oval++;
			if (t.off > 2) rings.offKnot++;
			rings.worstOff = Math.max(rings.worstOff, t.off);
			rings.overhang = Math.max(rings.overhang, t.over);
		}
		if (rings.seen > 8) break;
		await page.waitForTimeout(900);
	}
	say(
		'knot rings',
		`${rings.seen} seen, ${rings.flipped} with the card flipped left, worst overhang ${Math.round(rings.overhang)} px`
	);
	if (!rings.seen) {
		fail(`${vp.name}: no knot tag ever appeared, so none of the ring checks ran`);
	} else {
		if (rings.oval) fail(`${vp.name}: ${rings.oval} of ${rings.seen} knot rings are not round`);
		if (rings.offKnot)
			fail(
				`${vp.name}: ${rings.offKnot} of ${rings.seen} knot rings sit off their knot (worst ${rings.worstOff.toFixed(1)} px)`
			);
		if (rings.overhang > 4)
			fail(`${vp.name}: a tag hangs ${Math.round(rings.overhang)} px off the edge of the stage`);
	}

	// --- 2. the dock -----------------------------------------------------------------------
	const dock = page.locator('.dock').first();
	const hasDock = (await dock.count()) > 0;
	const wide = vp.width >= 860;
	say('dock present', hasDock ? 'yes' : 'no');
	if (!hasDock && !wide) fail(`${vp.name}: no dock, so the panels have no opener`);

	// --- 3. every sheet opens, one at a time -------------------------------------------------
	if (hasDock) {
		const items = await dock.locator('button').all();
		say('dock buttons', items.length);
		for (const item of items) {
			const label = (await item.innerText()).replace(/\s+/g, ' ').trim();
			const box = await item.boundingBox();
			if (box && Math.min(box.width, box.height) < TOUCH_MIN - 1) {
				fail(
					`${vp.name}: dock "${label}" is ${Math.round(box.width)}x${Math.round(box.height)}, under the ${TOUCH_MIN} px floor`
				);
			}
			await item.click();
			await page.waitForTimeout(500);
			const open = await page.locator('.sheet, .panel:visible').count();
			const sheet = page.locator('.panel:visible').first();
			const sb = await sheet.boundingBox().catch(() => null);
			if (!sb) {
				fail(`${vp.name}: "${label}" opened nothing`);
				continue;
			}
			// **Area, not height.** A drawer comes up from the bottom in portrait and in from
			// the side in landscape — a phone lying down has 390 px of height, and a bottom
			// drawer worth opening would leave the galaxy a centimetre. Measuring height alone
			// called the side drawer an 87 % failure when it covers a third of the screen.
			const share = (sb.width * sb.height) / (vp.width * vp.height);
			say(
				`  ${label.padEnd(12)} sheet`,
				`${Math.round(sb.width)}x${Math.round(sb.height)} · ${Math.round(share * 100)} % of the screen · ${open} panel(s)`
			);
			if (sb.x < -1 || sb.x + sb.width > vp.width + 1) {
				fail(`${vp.name}: the "${label}" sheet runs off the side`);
			}
			if (sb.y + sb.height > vp.height + 1) {
				fail(`${vp.name}: the "${label}" sheet runs off the bottom`);
			}
			if (share > SHEET_MAX_SHARE) {
				fail(
					`${vp.name}: the "${label}" sheet takes ${Math.round(share * 100)} % of the screen, over the ${Math.round(SHEET_MAX_SHARE * 100)} % a drawer may have`
				);
			}
			if (open > 1) fail(`${vp.name}: "${label}" left ${open} panels open at once`);
			// Every control inside it, against the floor.
			//
			// `button.link` is measured against a lower one and the exception is stated rather
			// than hidden: it is a word inside a sentence — "Meant something else? alarm
			// recruitment contact" — and a paragraph whose words are 44 px tall is not a
			// paragraph. It buys its reach from padding on an inline box instead, which is
			// hit-tested without moving the line, and lands around 30 px. Anything else short
			// is a fault.
			const small = await page.evaluate(
				({ min, inlineMin }) => {
					const panel = [...document.querySelectorAll('.panel')].find(
						(p) => p.getBoundingClientRect().height > 0
					);
					if (!panel) return null;
					const bad = [];
					for (const el of panel.querySelectorAll('button, select, input, a, summary')) {
						const r = el.getBoundingClientRect();
						if (!r.width || !r.height) continue;
						// A checkbox is a small box inside a large label; the label is the target.
						const target = el.closest('label') ?? el;
						const tr = target.getBoundingClientRect();
						const h = Math.max(r.height, tr.height);
						const floor = el.classList.contains('link') ? inlineMin : min;
						if (h < floor - 1)
							bad.push(
								`${el.tagName.toLowerCase()}${el.className ? '.' + String(el.className).split(' ')[0] : ''}:${Math.round(h)}px "${(el.innerText || el.value || el.type || '').replace(/\s+/g, ' ').slice(0, 18)}"`
							);
					}
					return bad;
				},
				{ min: TOUCH_MIN, inlineMin: INLINE_MIN }
			);
			if (small?.length) {
				fail(
					`${vp.name}: ${small.length} control(s) in the "${label}" drawer are under the touch floor — ${small.slice(0, 5).join(', ')}`
				);
			} else {
				say(`  ${label.padEnd(12)} touch targets`, `all at or over ${TOUCH_MIN} px`);
			}
			// Tapping the open one again puts the stage back.
			await item.click();
			await page.waitForTimeout(400);
			const stillOpen = await page.locator('.panel:visible').count();
			if (stillOpen) fail(`${vp.name}: tapping "${label}" again did not close it`);
		}
	}

	// --- 4. nothing overflows with everything shut -------------------------------------------
	const overflow = await page.evaluate(() => {
		const out = [];
		const w = window.innerWidth;
		const h = window.innerHeight;
		const named = ['.hud', '.readings', '.dock', '.history', '.viewctl', '.stage-wrap', '.bench'];
		for (const sel of named) {
			for (const el of document.querySelectorAll(sel)) {
				const r = el.getBoundingClientRect();
				if (!r.width || !r.height) continue;
				const over = {
					left: Math.round(-r.x),
					right: Math.round(r.right - w),
					bottom: Math.round(r.bottom - h)
				};
				if (over.left > 1 || over.right > 1 || over.bottom > 1)
					out.push(`${sel} l${over.left} r${over.right} b${over.bottom}`);
				if (r.width <= 0) out.push(`${sel} has zero width`);
			}
		}
		return {
			out,
			docScrollW: document.documentElement.scrollWidth,
			winW: w,
			bodyH: document.body.getBoundingClientRect().height
		};
	});
	say('document scroll width vs window', `${overflow.docScrollW} / ${overflow.winW}`);
	if (overflow.docScrollW > overflow.winW + 1)
		fail(`${vp.name}: the document scrolls sideways by ${overflow.docScrollW - overflow.winW} px`);
	if (overflow.out.length) for (const o of overflow.out) fail(`${vp.name}: ${o}`);
	else say('overflowing elements', 'none');

	// --- 5. the readings row -----------------------------------------------------------------
	const readings = await page.evaluate(() => {
		const el = document.querySelector('.readings');
		if (!el) return null;
		const cs = getComputedStyle(el);
		return {
			display: cs.display,
			overflowX: cs.overflowX,
			cells: el.children.length,
			scrollW: el.scrollWidth,
			clientW: el.clientWidth
		};
	});
	say(
		'readings row',
		readings
			? `${readings.display}, ${readings.cells} cells, ${readings.scrollW}/${readings.clientW} px (${readings.overflowX})`
			: 'absent'
	);
	if (readings && readings.display !== 'none' && readings.scrollW > readings.clientW + 1 && readings.overflowX === 'visible')
		fail(`${vp.name}: the readings row overflows and cannot be scrolled`);

	// --- 6. the stage keeps its share with everything shut ------------------------------------
	const stage = await page.locator('.stage-wrap').first().boundingBox().catch(() => null);
	if (stage) {
		say('stage', `${Math.round(stage.width)}x${Math.round(stage.height)} (${Math.round((stage.height / vp.height) * 100)} % of screen)`);
		if (stage.height / vp.height < 0.5)
			fail(`${vp.name}: the stage gets under half the screen with every panel shut`);
	}

	// --- 7. the pages -------------------------------------------------------------------------
	for (const which of ['info', 'learn']) {
		const opener = page.locator('.reading-open', { hasText: new RegExp(which, 'i') }).first();
		if (!(await opener.count())) {
			say(`${which} page opener`, 'absent');
			continue;
		}
		await opener.click();
		await page.waitForTimeout(1200);
		const box = await page.evaluate(() => {
			const p = document.querySelector('.stagepage');
			if (!p) return null;
			const r = p.getBoundingClientRect();
			return {
				w: Math.round(r.width),
				scrollW: p.scrollWidth,
				clientW: p.clientWidth,
				closeH: Math.round(document.querySelector('.pageclose')?.getBoundingClientRect().height ?? 0)
			};
		});
		say(`${which} page`, box ? `${box.w} px wide, content ${box.scrollW}/${box.clientW}` : 'did not open');
		if (box && box.scrollW > box.clientW + 1)
			fail(`${vp.name}: the ${which} page scrolls sideways by ${box.scrollW - box.clientW} px`);
		await page.screenshot({ path: `${SHOT}/mobile-${vp.name}-${which}.png` });
		await page.locator('.pageclose').first().click().catch(() => {});
		await page.waitForTimeout(600);
	}

	await page.screenshot({ path: `${SHOT}/mobile-${vp.name}.png` });
	say('console errors', errors.length);
	for (const e of errors.slice(0, 4)) console.log('    ', e.slice(0, 160));
	await page.close();
}

await browser.close();
console.log(`\n${fails.length ? `*** ${fails.length} failure(s)` : 'all clear'}`);
process.exit(fails.length ? 1 : 0);

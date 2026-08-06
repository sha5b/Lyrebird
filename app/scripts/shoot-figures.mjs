/**
 * The README's figures, taken by a script rather than by hand.
 *
 * Screenshots of a live instrument go stale in a way prose does not: the Sing tab lost its
 * Stop button, the display panel grew four folds and the mobile layout did not exist, and
 * `static/figures/fig-stage.png` went on showing all three as they were in July. A figure that
 * disagrees with the interface is worse than no figure, because a reader believes it.
 *
 * So every image the README embeds is produced here, from a running dev server, and can be
 * retaken with one command whenever the interface moves:
 *
 *     npm run figures            # dev server on 5173
 *     PROBE_URL=http://localhost:5199/ npm run figures
 *
 * The waits are long on purpose. The corpus is ~113 MB of asset parsed in the browser, the
 * chorus schedules its first song seconds after that, and a tag only exists for a knot that is
 * sounding — so a figure taken too early is a picture of a loading screen, which is exactly the
 * kind of quiet wrong answer the rest of this repository's probes exist to prevent.
 */
import { chromium } from 'playwright';
import { mkdir } from 'node:fs/promises';
import { execFileSync } from 'node:child_process';

const URL = process.env.PROBE_URL ?? 'http://localhost:5173/';
const OUT = process.env.FIGURES_DIR ?? '../docs/figures';

await mkdir(OUT, { recursive: true });

const browser = await chromium.launch({
	args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader']
});

/** Open a page, wait out the load, and get past the audio gate. */
async function open(width, height, mobile = false) {
	const page = await browser.newPage({
		viewport: { width, height },
		deviceScaleFactor: 2,
		isMobile: mobile,
		hasTouch: mobile
	});
	await page.goto(URL, { waitUntil: 'load', timeout: 180000 });
	await page
		.waitForFunction(() => document.querySelector('.bench') !== null, null, { timeout: 300000 })
		.catch(() => {});
	await page.waitForTimeout(3000);
	const gate = page.locator('.overlay button', { hasText: /start listening/i }).first();
	if (await gate.count()) {
		await gate.click();
		// The chorus starts itself here; give it long enough to schedule a song, because a
		// stage with nothing sounding has no tags and no threads on it — a picture of the
		// instrument switched off.
		await page.waitForTimeout(14000);
	}
	return page;
}

/**
 * Take the shot, then halve it.
 *
 * The pages are rendered at `deviceScaleFactor: 2` because the interface is hairlines and
 * 9 px monospace, and a 1x screenshot of that is mush. Two-times of a 1600 px bench is a
 * 3200 px file, though, and nine of those are 5.7 MB in a repository that a reader clones —
 * for images a README displays at about 900 px. Resampling to 1600 keeps the hairlines (it is
 * still above the display size) and gives back more than half the bytes.
 *
 * ImageMagick rather than a node dependency: it is already on the machine, and a figure script
 * is not worth a new package in `package.json`.
 */
const shot = async (page, name) => {
	const path = `${OUT}/${name}.png`;
	await page.screenshot({ path });
	try {
		execFileSync('magick', [path, '-resize', '1600x>', '-strip', path]);
	} catch {
		console.log(`${name.padEnd(24)} written (full size — ImageMagick is not on this machine)`);
		return;
	}
	console.log(`${name.padEnd(24)} written`);
};

// --- the bench ------------------------------------------------------------------------------
{
	const page = await open(1600, 900);
	await shot(page, 'stage');

	// The Display panel open over the stage: what a reader can change about the picture.
	//
	// **No bird-selection figure, and the reason is worth keeping.** One was taken and thrown
	// away: choosing a species flies the camera to the region its knots occupy, and for a bird
	// with fourteen fitted types that region is a thread of dots on an otherwise empty sheet.
	// It is the correct behaviour and a bad picture, and a README figure that makes a working
	// feature look like an empty screen is worse than one fewer figure.
	await page.locator('.viewbtn').first().click({ force: true });
	await page.waitForTimeout(1200);
	await shot(page, 'display');

	// The provenance tint, from the panel that is already open: where every sound came from,
	// which is the one colour language that reads at this density.
	const prov = page.locator('label.check', { hasText: /provenance colour/i }).locator('input');
	if (await prov.count()) {
		await prov.check();
		await page.waitForTimeout(2500);
		await page.locator('.viewbtn').first().click({ force: true });
		await page.waitForTimeout(1500);
		await shot(page, 'colour');
		await page.locator('.viewbtn').first().click({ force: true });
		await page.waitForTimeout(600);
		await prov.uncheck();
		await page.waitForTimeout(1500);
	}
	await page.locator('.viewbtn').first().click({ force: true });

	// The two pages.
	await page.locator('.reading-open', { hasText: /info/i }).first().click();
	await page.waitForTimeout(2000);
	await shot(page, 'info');
	await page.locator('.pageclose').first().click().catch(() => {});
	await page.waitForTimeout(800);
	await page.locator('.reading-open', { hasText: /learn/i }).first().click();
	await page.waitForTimeout(2500);
	await shot(page, 'learn');
	await page.close();
}

// --- the phone ------------------------------------------------------------------------------
{
	const page = await open(390, 844, true);
	await shot(page, 'phone-stage');
	await page.locator('.dock button', { hasText: /sing/i }).first().click();
	await page.waitForTimeout(1500);
	await shot(page, 'phone-sing');
	await page.locator('.dock button', { hasText: /reading/i }).first().click();
	await page.waitForTimeout(1500);
	await shot(page, 'phone-reading');
	await page.close();
}

// --- the phone on its side --------------------------------------------------------------------
{
	const page = await open(844, 390, true);
	await page.locator('.dock button', { hasText: /sing/i }).first().click();
	await page.waitForTimeout(1500);
	await shot(page, 'phone-landscape');
	await page.close();
}

await browser.close();
console.log(`\nfigures in ${OUT}`);

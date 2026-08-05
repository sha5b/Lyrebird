/**
 * The browser half of the neighbour-agreement channel: does the switch change the picture,
 * and does it change *only* the channel it is allowed to spend.
 *
 * `verify:trust` checks the asset and the source chain, and `probe:stage` checks that the
 * program links. Neither can catch the failure this file exists for: a uniform that is
 * wired, compiled, eased and multiplied by something that happens to be zero. That draws
 * an identical frame and every other check passes. The channel that prompted all of this
 * — `points.knnAgreement`, shipped per point and read by nothing — was invisible for
 * exactly that reason, so "the toggle moves pixels" is asserted here with numbers.
 *
 * Measured on the composited frame, decoded in the page rather than in Node so no image
 * library is needed:
 *
 *   - **mean chroma over the ink** must FALL when the channel comes up. That is the whole
 *     claim: colour drains where a mark's ten drawn neighbours do not share its type.
 *   - **the ink area must hold**, within the drift of a live cloud. Size and weight belong
 *     to activation and to the figure/ground swap; if this channel moves them too then a
 *     low-agreement position is being drawn as a quiet sound, which is a different claim
 *     and the wrong one.
 *
 * Needs a dev server, like `probe:stage`. `PROBE_URL` overrides the port.
 */
import { chromium } from 'playwright';

const URL = process.env.PROBE_URL ?? 'http://localhost:5173/';
const SHOT = process.env.PROBE_SHOTS ?? 'out/probe';

let failures = 0;
const ok = (name, cond, detail = '') => {
	if (cond) console.log(`  ${name.padEnd(50)} ok${detail ? ` (${detail})` : ''}`);
	else {
		failures++;
		console.error(`  ${name.padEnd(50)} FAIL ${detail}`);
	}
};

const browser = await chromium.launch({
	args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader']
});
const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });
const shaderErrors = [];
page.on('console', (m) => {
	if (/shader|WebGLProgram|GLSL/i.test(m.text())) shaderErrors.push(m.text());
});

await page.goto(URL, { waitUntil: 'load', timeout: 120000 });
await page
	.waitForFunction(() => /POINTS/i.test(document.body.innerText), null, { timeout: 180000 })
	.catch(() => {});
await page.waitForTimeout(14000);

// The audio gate intercepts every pointer event until it is entered — see probe-stage.mjs.
const gate = page.locator('.overlay button', { hasText: /start listening/i }).first();
if (await gate.count()) {
	await gate.click();
	await page.waitForTimeout(3000);
}
const viewBtn = page.locator('.viewbtn').first();
if (await viewBtn.count()) {
	await viewBtn.click();
	await page.waitForTimeout(800);
}

// Provenance colours on, or there is no chroma to drain and the test would pass on a black
// and white picture for the wrong reason.
const prov = page.locator('label.check:has-text("Provenance colours") input').first();
if ((await prov.count()) && !(await prov.isChecked())) {
	await prov.check({ force: true });
	await page.waitForTimeout(3000);
}

/**
 * Mean saturation over the marks, and how many marks there are. Decoded inside the page:
 * the canvas is WebGL and may not preserve its drawing buffer, so the frame is read back
 * through a screenshot data URL and an OffscreenCanvas rather than from the GL context.
 */
const frame = async () => {
	const shot = (await page.locator('canvas').first().screenshot()).toString('base64');
	return page.evaluate(async (b64) => {
		const blob = await (await fetch(`data:image/png;base64,${b64}`)).blob();
		const bmp = await createImageBitmap(blob);
		const c = new OffscreenCanvas(bmp.width, bmp.height);
		const ctx = c.getContext('2d');
		ctx.drawImage(bmp, 0, 0);
		const { data } = ctx.getImageData(0, 0, bmp.width, bmp.height);
		let sat = 0;
		let ink = 0;
		for (let i = 0; i < data.length; i += 4) {
			const max = Math.max(data[i], data[i + 1], data[i + 2]);
			const min = Math.min(data[i], data[i + 1], data[i + 2]);
			// Paper is the near-white background; everything darker is a mark or the chrome.
			if (max < 250) {
				sat += max === 0 ? 0 : (max - min) / max;
				ink++;
			}
		}
		return { chroma: ink ? sat / ink : 0, ink };
	}, shot);
};

console.log(`the channel, on ${URL}`);

const box = page.locator('label.check:has-text("Neighbours disagree") input').first();
ok('the control exists', (await box.count()) === 1);
ok('and is enabled on a build that ships the array', await box.isEnabled());

const off = await frame();
await page.screenshot({ path: `${SHOT}/trust-off.png` });
await box.check({ force: true });
await page.waitForTimeout(6000); // uTrust eases in; a cut here would measure the transition
const on = await frame();
await page.screenshot({ path: `${SHOT}/trust-on.png` });

const drop = off.chroma ? (100 * (off.chroma - on.chroma)) / off.chroma : 0;
const inkDrift = off.ink ? Math.abs(100 * (on.ink - off.ink)) / off.ink : 0;

ok('no shader errors', shaderErrors.length === 0, `${shaderErrors.length}`);
ok(
	'the channel drains chroma',
	drop > 5,
	`${off.chroma.toFixed(4)} -> ${on.chroma.toFixed(4)}, ${drop.toFixed(1)} % down`
);
ok(
	'and spends nothing else: the ink area holds',
	inkDrift < 5,
	`${off.ink.toLocaleString()} -> ${on.ink.toLocaleString()} px, ${inkDrift.toFixed(1)} % drift`
);

console.log(`\n  screenshots: ${SHOT}/trust-off.png, ${SHOT}/trust-on.png`);
console.log(failures ? `\n${failures} trust probes FAILED` : '\nall trust probes passed');
await browser.close();
process.exit(failures ? 1 : 0);

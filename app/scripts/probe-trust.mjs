/**
 * The browser half of the shared doubt channel: do both switches change the picture, do they
 * change it *differently*, and do they change *only* the channel they are allowed to spend.
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
 *   - **mean chroma over the ink** must FALL when either source comes up. That is the whole
 *     claim: colour drains where a mark has a recorded reason to be doubted.
 *   - **the two sources must draw different pictures.** Agreement and SNR share one
 *     attribute, rewritten in place when the switch moves, so if the two frames matched it
 *     would mean the rewrite never happened and the second control is decorative — a
 *     failure that looks exactly like success from every other angle.
 *   - **the ink area must hold**, within the drift of a live cloud. Size and weight belong
 *     to activation and to the figure/ground swap; if this channel moves them too then a
 *     doubtful position is being drawn as a quiet sound, which is a different claim and the
 *     wrong one.
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
// **Rotation off, or nothing below is a comparison.** The galaxy drifts continuously, so two
// frames taken a few seconds apart differ everywhere for a reason that has nothing to do with
// the channel — which is also why the first version of the cross-check below read 3.0 % on one
// run and 0.5 % on the next and meant neither.
const spin = page.locator('label.check:has-text("Rotate") input').first();
if ((await spin.count()) && (await spin.isChecked())) {
	await spin.uncheck({ force: true });
	await page.waitForTimeout(2500);
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
		const satMap = new Array(data.length / 4).fill(0);
		for (let i = 0; i < data.length; i += 4) {
			const max = Math.max(data[i], data[i + 1], data[i + 2]);
			const min = Math.min(data[i], data[i + 1], data[i + 2]);
			// Paper is the near-white background; everything darker is a mark or the chrome.
			if (max < 250) {
				const v = max === 0 ? 0 : (max - min) / max;
				sat += v;
				satMap[i / 4] = v;
				ink++;
			}
		}
		return { chroma: ink ? sat / ink : 0, ink, sat: satMap };
	}, shot);
};

/**
 * Mean absolute difference in per-pixel saturation between two frames, over the pixels
 * either of them inked.
 *
 * **The mean is not a discriminator and that is why this exists.** Agreement and SNR drain
 * *different marks*, but on this corpus they happen to drain a similar *amount* — mean
 * agreement 0.457 against a median SNR sitting at 0.41 of its own ramp — so comparing the
 * two frames' mean chroma compared two numbers that were never going to differ, and the
 * first version of this check passed on frame-to-frame drift instead. Per pixel, two
 * different sets of drained marks cannot look alike.
 */
const perPixel = (a, b) => {
	let sum = 0;
	let n = 0;
	for (let i = 0; i < a.sat.length; i++) {
		if (a.sat[i] === 0 && b.sat[i] === 0) continue;
		sum += Math.abs(a.sat[i] - b.sat[i]);
		n++;
	}
	return n ? sum / n : 0;
};

console.log(`the channel, on ${URL}`);

const agree = page.locator('label.check:has-text("Neighbours disagree") input').first();
const noisy = page.locator('label.check:has-text("Recording is noisy") input').first();
ok('the agreement control exists', (await agree.count()) === 1);
ok('the SNR control exists on the same channel', (await noisy.count()) === 1);
ok('both are enabled on a build that ships both arrays', (await agree.isEnabled()) && (await noisy.isEnabled()));

const off = await frame();
await page.screenshot({ path: `${SHOT}/trust-off.png` });

/** Turn one source on, let the uniform ease, measure. A cut would measure the transition. */
const measure = async (box, name) => {
	await box.check({ force: true });
	await page.waitForTimeout(6000);
	const f = await frame();
	await page.screenshot({ path: `${SHOT}/trust-${name}.png` });
	return f;
};

const onAgree = await measure(agree, 'agreement');
// **The switch, which is the point of sharing the channel.** Ticking SNR must clear
// agreement — one channel cannot carry both doubts at once — and the frame must change
// again, or the second source is wired to a buffer that never got rewritten.
const onSnr = await measure(noisy, 'snr');
ok('choosing SNR cleared agreement', !(await agree.isChecked()));

const pct = (a, b) => (a ? (100 * (a - b)) / a : 0);
const dropAgree = pct(off.chroma, onAgree.chroma);
const dropSnr = pct(off.chroma, onSnr.chroma);
const inkDrift = off.ink ? Math.abs(100 * (onSnr.ink - off.ink)) / off.ink : 0;
const between = Math.abs(pct(onAgree.chroma, onSnr.chroma));

ok('no shader errors', shaderErrors.length === 0, `${shaderErrors.length}`);
ok(
	'agreement drains chroma',
	dropAgree > 5,
	`${off.chroma.toFixed(4)} -> ${onAgree.chroma.toFixed(4)}, ${dropAgree.toFixed(1)} % down`
);
ok(
	'SNR drains chroma too, from its own buffer',
	dropSnr > 5,
	`${off.chroma.toFixed(4)} -> ${onSnr.chroma.toFixed(4)}, ${dropSnr.toFixed(1)} % down`
);
// If the two sources drew identically the attribute was never rewritten and the second
// switch is decorative. Measured per pixel against the same frame with the channel off, so
// the comparison is "how far did each move this picture", not "what was each one's average".
const moveAgree = perPixel(off, onAgree);
const moveSnr = perPixel(off, onSnr);
const apart = perPixel(onAgree, onSnr);
ok(
	'and the two sources draw different pictures',
	apart > 0.2 * Math.max(moveAgree, moveSnr),
	`per-pixel: agreement moved ${moveAgree.toFixed(4)}, snr ${moveSnr.toFixed(4)}, ` +
		`and they sit ${apart.toFixed(4)} apart (mean chroma alone: ${between.toFixed(1)} %)`
);
ok(
	'neither spends anything else: the ink area holds',
	inkDrift < 5,
	`${off.ink.toLocaleString()} -> ${onSnr.ink.toLocaleString()} px, ${inkDrift.toFixed(1)} % drift`
);

console.log(`\n  screenshots: ${SHOT}/trust-off.png, trust-agreement.png, trust-snr.png`);
console.log(failures ? `\n${failures} trust probes FAILED` : '\nall trust probes passed');
await browser.close();
process.exit(failures ? 1 : 0);

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
 *   - **mean chroma over the ink** must RISE when either source comes up, and by a lot.
 *     This assertion was inverted until 2026-08-06, when the channel stopped draining
 *     saturation and became the third colour mode: doubtful marks now take the ink instead
 *     of losing it. The old direction is what the owner saw as "nearly not visible", and it
 *     is worth stating plainly why the old check passed anyway — it asserted a 5 % move on
 *     a cloud that is grey at rest, which a barely perceptible drain clears easily. The
 *     threshold here is set from the measured rise, not from what is easy to pass.
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

// **The baseline is the default ink cloud, and provenance is forced OFF to get it.**
//
// It used to be forced ON, because a drain needs chroma to take away. The ramp needs the
// opposite: doubt is now one of three mutually exclusive colour modes, so ticking it clears
// provenance by design — and measuring off-with-provenance against on-with-doubt would
// compare two changes at once and call the sum of them the channel's effect.
const prov = page.locator('label.check:has-text("Provenance colours") input').first();
if ((await prov.count()) && (await prov.isChecked())) {
	await prov.uncheck({ force: true });
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
		let lum = 0;
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
				// Rec.709, so "darker" means darker to the eye rather than in one channel.
				lum += (0.2126 * data[i] + 0.7152 * data[i + 1] + 0.0722 * data[i + 2]) / 255;
				ink++;
			}
		}
		return { chroma: ink ? sat / ink : 0, lum: ink ? lum / ink : 1, ink, sat: satMap };
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
await agree.uncheck({ force: true });
await page.waitForTimeout(4000);
const onSnr = await measure(noisy, 'snr');
// **The overlay, which is the point of the vec2.** The two doubts shared one float and had to
// take turns; ticking one must no longer clear the other, and the both-on frame must differ from
// each single-channel frame or the second ramp is being drawn over the first rather than with it.
await agree.check({ force: true });
await page.waitForTimeout(4000);
const onBoth = await frame();
await page.screenshot({ path: `${SHOT}/trust-both.png` });
ok('both channels stay on together', (await agree.isChecked()) && (await noisy.isChecked()));

// Rise as a share of the baseline. The baseline is a near-neutral cloud, so this is a
// large number by construction — which is the point: the mode has to be unmistakable.
const pct = (a, b) => (a ? (100 * (b - a)) / a : 0);
const riseAgree = pct(off.chroma, onAgree.chroma);
const riseSnr = pct(off.chroma, onSnr.chroma);
const inkDrift = off.ink ? Math.abs(100 * (onSnr.ink - off.ink)) / off.ink : 0;
const between = Math.abs(pct(onAgree.chroma, onSnr.chroma));

ok('no shader errors', shaderErrors.length === 0, `${shaderErrors.length}`);
// **The direction is half the assertion and the size is the other half**, and the floor is
// set from three measurements rather than from a round number:
//
//   7.5 %       the first version of the ramp, ends #9d1240/#8fa2b8 with the resting wash
//               left at 0.5 — indistinguishable by eye from the drain it replaced
//   21.7-35.2 % the shipped version, over two runs of this probe, both sources
//
// So 15 %, not 20: the shipped range is wide because the cloud is live — the chorus is
// playing, the level-of-detail frontier is still settling, and the same build measured 35.2 %
// and then 21.7 % on consecutive runs. A floor inside that spread would fail on the run
// rather than on the code. 15 % still fails the 7.5 % version by a factor of two, which is
// the regression this number exists to catch. The drain-era check used 5 %, which the 7.5 %
// version cleared — which is why the measurements are written down beside the threshold
// instead of the threshold being written down alone.
ok(
	'agreement colours the cloud, and visibly',
	riseAgree > 15,
	`${off.chroma.toFixed(4)} -> ${onAgree.chroma.toFixed(4)}, ${riseAgree.toFixed(1)} % up`
);
ok(
	'SNR colours it too, from its own buffer',
	riseSnr > 15,
	`${off.chroma.toFixed(4)} -> ${onSnr.chroma.toFixed(4)}, ${riseSnr.toFixed(1)} % up`
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
// The overlay has to be a third picture, not a copy of either half. Measured per pixel against
// both singles: if `both` matched one of them, the other channel is contributing nothing.
const bothVsAgree = perPixel(onBoth, onAgree);
const bothVsSnr = perPixel(onBoth, onSnr);
ok(
	'the overlay is its own picture, not one of the two halves',
	bothVsAgree > 0.2 * moveAgree && bothVsSnr > 0.2 * moveSnr,
	`per-pixel: both sits ${bothVsAgree.toFixed(4)} from agreement-only and ` +
		`${bothVsSnr.toFixed(4)} from snr-only`
);
// **Measured as darkness, not as chroma, and the first version of this check had it wrong.**
//
// It asserted that both-on is at least as *chromatic* as either half, which sounds right and is
// not: the composition subtracts toward two different hues, so a mark bad on both counts lands
// between rose and amber — nearer neutral, and therefore LESS saturated than either pure ramp
// while being further from the quiet end. Measured: chroma both 0.0505 against agreement 0.0607.
// The code was correct and the expectation was not.
//
// What the subtraction does guarantee is monotone darkening: each channel moves the colour away
// from the shared pale quiet end, so two channels move it further than one. That is the property
// worth protecting, because losing it would mean the two ramps are cancelling rather than
// accumulating — which is exactly what a sign error or a nested mix would produce.
ok(
	'and it is at least as dark as either half',
	onBoth.lum <= Math.min(onAgree.lum, onSnr.lum) + 0.004,
	`mean ink luminance: both ${onBoth.lum.toFixed(4)}, agreement ${onAgree.lum.toFixed(4)}, ` +
		`snr ${onSnr.lum.toFixed(4)}, off ${off.lum.toFixed(4)}`
);
// And both halves must darken the frame relative to no channel at all, or "accumulating" is
// being asserted about two channels that individually do nothing.
ok(
	'each half darkens the frame on its own',
	onAgree.lum < off.lum && onSnr.lum < off.lum,
	`off ${off.lum.toFixed(4)} -> agreement ${onAgree.lum.toFixed(4)}, snr ${onSnr.lum.toFixed(4)}`
);

console.log(`\n  screenshots: ${SHOT}/trust-off.png, trust-agreement.png, trust-snr.png`);
console.log(failures ? `\n${failures} trust probes FAILED` : '\nall trust probes passed');
await browser.close();
process.exit(failures ? 1 : 0);

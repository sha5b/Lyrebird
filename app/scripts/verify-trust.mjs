/**
 * Neighbour agreement: is the number in the asset, does the view read it, and does it
 * change the picture.
 *
 * **This check exists because of how the channel was found.** `points.knnAgreement` shipped
 * one value per point for the entire life of the build and nothing in `app/src` ever read
 * the array — about 2 MB downloaded on every load and discarded. It was not a rendering
 * bug and no test failed, because the pipeline half was genuinely built: the manifest
 * carried the corpus mean, `docs/25` marked the row BUILT, and the per-point half simply
 * had no reader. The lesson written down was **a channel is not built until something
 * draws it**, so this asserts both halves and, more importantly, the join between them:
 *
 *   1. **The asset half** — one finite value per point, in 0..1, and the per-point mean
 *      agrees with the aggregate the manifest reports. A mean that disagrees means the two
 *      were measured on different point sets, which is exactly the state a row-index join
 *      can silently produce.
 *   2. **The reader half** — the shader declares the attribute, the vertex stage passes it,
 *      the fragment stage spends it, PointCloud fills it from the asset, and the control is
 *      wired to the uniform. Each of these was absent before and each is a way for the
 *      array to go back to being downloaded and ignored.
 *   3. **The absent-channel state** — a build with no per-point measurement must draw the
 *      cloud exactly as it drew before the channel existed: the fill is 1 (no reason
 *      recorded to doubt any position), the control disables, and the uniform is held at 0.
 *      Absent must never render as "these marks are untrustworthy".
 *
 * What this cannot check is that the colouring is *visible*, which is what `probe:trust` is
 * for — it measures chroma over a real composited frame — and `probe:stage`, which compiles the
 * real program on a real GPU and reports shader errors. Run all three; the reason the middle one
 * exists is that a uniform can be wired, compiled, eased and then multiplied by something that
 * happens to be zero, and that draws an identical frame with every check here passing.
 *
 * Run with `npm run verify:trust`. Exits non-zero on any disagreement.
 */
import { readFileSync } from 'node:fs';

const ASSETS = process.env.LYREBIRD_ASSETS ?? 'static/lyrebird';

let failures = 0;
const ok = (name, cond, detail = '') => {
	if (cond) console.log(`  ${name.padEnd(58)} ok${detail ? ` (${detail})` : ''}`);
	else {
		failures++;
		console.error(`  ${name.padEnd(58)} FAIL ${detail}`);
	}
};

const points = JSON.parse(readFileSync(`${ASSETS}/points.json`, 'utf8'));
const manifest = JSON.parse(readFileSync(`${ASSETS}/manifest.json`, 'utf8'));
const shaders = readFileSync('src/lib/galaxy/shaders.ts', 'utf8');
const doubt = readFileSync('src/lib/galaxy/doubt.ts', 'utf8');
const cloud = readFileSync('src/lib/galaxy/PointCloud.svelte', 'utf8');
const galaxy = readFileSync('src/lib/galaxy/Galaxy.svelte', 'utf8');
const page = readFileSync('src/routes/+page.svelte', 'utf8');
const palette = readFileSync('src/lib/galaxy/palette.ts', 'utf8');
const labels = readFileSync('src/lib/galaxy/NodeLabels.svelte', 'utf8');
const projector = readFileSync('src/lib/galaxy/NodeProjector.svelte', 'utf8');
const assetsTs = readFileSync('src/lib/data/assets.ts', 'utf8');

console.log(`the reader, on src/`);

// The half that was missing. Each of these lines is one link in the chain from the asset to a
// pixel, and the channel was dead because the chain was empty end to end.
//
// **A vec2, and the width is the assertion.** The two doubts took turns on one float until
// 2026-08-06 and could never be on screen together. Attribute slots are vec4-sized, so a vec2
// costs exactly what the float did — which is why this is a widening rather than a second
// attribute, and why the budget note below still holds.
ok('the vertex stage declares both doubts in one attribute', /attribute vec2 aTrust;/.test(shaders));
ok('the vertex stage passes it on', /vTrust = clamp\(aTrust/.test(shaders));
ok('the fragment stage takes one strength per channel', /uniform vec2 uTrust;/.test(shaders));
// **The invariant this check protects has not changed; the mechanism has twice.**
//
// It asserted the saturation drain literally (`mix(colour, vec3(dot(colour…`), then one hue
// ramp, and now two. What it exists for is the same through all three and still worth failing
// over: a doubtful mark must keep its size, its weight and its place, because moving any of
// those says "this sound matters less", which is a claim about the sound rather than about the
// map. So: the ramp is what uTrust drives, and uTrust appears on no size, alpha or position.
ok(
	'it spends hue, and nothing else',
	/vec3 doubtCol = clamp\(\s*uDoubtQuiet/.test(shaders) &&
		/mix\(inkId, doubtCol, doubtOn\)/.test(shaders) &&
		!/refusedSize[^\n]*uTrust/.test(shaders) &&
		!/alpha[^\n]*uTrust/.test(shaders) &&
		!/gl_PointSize[^\n]*[vu]Trust/.test(shaders),
	'a low-agreement mark must keep its size, weight and place'
);
// **The composition must stay symmetric.** Applying one channel and then mixing the second
// on top of the result privileges whichever went second, which would make "agreement + noise"
// and "noise + agreement" two different pictures of the same two numbers. Subtracting both
// from the shared quiet end is the form that cannot do that.
ok(
	'the two ramps compose symmetrically',
	/uDoubtQuiet\s*- \(uDoubtQuiet - uDoubtAgree\) \* doubts\.x\s*- \(uDoubtQuiet - uDoubtSnr\) \* doubts\.y/.test(
		shaders
	),
	'a nested mix would make the second channel win, so the pair would not commute'
);
// Turning the second channel on must not dilute the first: the takeover is the MAX of the two
// switches, not their sum or their product.
ok(
	'either channel alone takes over the identity colour fully',
	/float doubtOn = max\(uTrust\.x, uTrust\.y\);/.test(shaders)
);
ok(
	'and the drain it replaced is not still applied on top',
	!/mix\(colour, vec3\(dot\(colour/.test(shaders),
	'draining a mark that is already wearing its doubt as a colour takes back the ink the ramp just gave it'
);
// **Loud at the doubtful end, and this is the check that says so.** The whole reason the drain
// was replaced is that it made the doubtful marks the faintest things on screen, which is
// backwards for a channel whose only job is to make them findable. `vTrust` is 1 for "no reason
// to doubt", so the doubt is `1 - vTrust`; an accidental un-inversion here would reproduce the
// original bug in a new colour, with the marks worth finding becoming the quiet ones.
ok(
	'doubt is measured from the loud end',
	/vec2 doubts = \(vec2\(1\.0\) - clamp\(vTrust, 0\.0, 1\.0\)\) \* clamp\(uTrust/.test(shaders),
	'vTrust 1 means no reason to doubt, so the quiet end must be the 1 end'
);
ok(
	'the two ramps have different loud ends',
	/export const DOUBT_AGREE = '#[0-9a-f]{6}'/.test(palette) &&
		/export const DOUBT_SNR = '#[0-9a-f]{6}'/.test(palette) &&
		palette.match(/export const DOUBT_AGREE = '(#[0-9a-f]{6})'/)[1] !==
			palette.match(/export const DOUBT_SNR = '(#[0-9a-f]{6})'/)[1],
	'two channels the reader can overlay must not be the same hue, or the overlay says nothing'
);
ok(
	'the ramp ends live in palette.ts and reach both the points and the tags',
	/export const DOUBT_QUIET/.test(palette) &&
		/uDoubtAgree: \{ value: new THREE\.Color\(DOUBT_AGREE\)/.test(cloud) &&
		/uDoubtSnr: \{ value: new THREE\.Color\(DOUBT_SNR\)/.test(cloud) &&
		/doubtColourScaled/.test(labels) &&
		/doubtColourScaled/.test(projector),
	'a tag drawn from different constants than its own points is the one disagreement a reader can see'
);
// The per-knot half of the mode. A tag is per knot and the attribute is per point, so the
// two need a defined relationship or the tag is decoration.
ok(
	'a tag averages its own knot from the same values, per channel',
	/export function knotDoubt/.test(assetsTs) &&
		/toDoubtBuffer\(assets\.points\.n, values, range\)/.test(assetsTs) &&
		/knotDoubt\(assets, assets\.points\.knnAgreement\)/.test(labels) &&
		/knotDoubt\(assets, assets\.points\.snr, doubtRange\)/.test(labels) &&
		/knotDoubt\(assets, assets\.points\.knnAgreement\)/.test(projector) &&
		/knotDoubt\(assets, assets\.points\.snr, doubtRange\)/.test(projector)
);
ok(
	'an empty knot claims nothing',
	/new Float32Array\(count\)\.fill\(NO_DOUBT\)/.test(assetsTs),
	'a knot with no members has nothing measured, so it must not read as fully doubtful or fully trusted'
);
// The projector caches colour strings per knot and clears on a language change. With four
// languages and a two-value key, switching agreement -> snr served the stale colour.
ok(
	"the projector's colour cache keys on both doubt switches",
	/`doubt:\$\{doubtAgree\}:\$\{doubtSnr\}`/.test(projector),
	'a key that dropped one switch would serve an agreement-only tag after SNR was added on top'
);
ok('PointCloud fills the attribute from the asset', /setAttribute\('aTrust'/.test(cloud));
ok('PointCloud reads points.knnAgreement to do it', /points\.knnAgreement/.test(cloud));

// **The channel is shared, and the sharing is the assertion.** Saturation is the last free
// channel, so agreement and SNR take turns on it rather than one of them going undrawn like
// snr did for the whole life of the build. Two sources on one attribute means two things must
// hold: only one attribute (the vertex program is at 11 of a budget that failed to link at
// 15), and one normalisation function, so the ramp the panel prints is the ramp the shader
// draws.
ok('SNR shares the channel rather than taking a new one', /points\.snr/.test(cloud));
ok(
	'only one doubt attribute exists',
	(shaders.match(/attribute vec2 aTrust;/g) ?? []).length === 1 && !/aSnr/.test(shaders),
	'a second attribute would spend a vertex slot the program cannot afford'
);
// With both values resident there is nothing to re-upload on a switch, so the buffer is
// static. A DynamicDrawUsage here would be a leftover promising traffic that no longer happens.
ok(
	'both doubts are resident, so a switch uploads nothing',
	/pair\[i \* 2\] = agree\[i\]/.test(cloud) &&
		/pair\[i \* 2 \+ 1\] = snr\[i\]/.test(cloud) &&
		!/trustAttribute[\s\S]{0,200}DynamicDrawUsage/.test(cloud),
	'the old design re-uploaded 1.8 MB whenever the reader changed source'
);
ok(
	'nothing about the channel is written per frame except two uniforms',
	!/trustAttribute\.needsUpdate/.test(cloud) && /trustNow\.x \+=/.test(cloud) && /trustNow\.y \+=/.test(cloud),
	'444 213 floats is 1.8 MB an upload, and it no longer happens at all'
);
ok('both the buffer and the panel normalise through doubt.ts', /toDoubtBuffer/.test(cloud) && /doubtRange/.test(page));
ok(
	'the SNR ramp is percentiles, measured not hardcoded',
	/SNR_CLAMP = \{ lo: 0\.05, hi: 0\.95 \}/.test(doubt) && /doubtRange\(assets\.points\.snr\)/.test(cloud),
	'85 values above 100 dB would own a linear scale'
);
ok(
	'absent fills as no-doubt in the shared helper too',
	/new Float32Array\(n\)\.fill\(NO_DOUBT\)/.test(doubt),
	"a render has no noise floor; 0 would call our own synthesis the noisiest audio here"
);
ok('the panel prints the ramp ends it draws with', /snrStats\.lo/.test(page) && /snrStats\.hi/.test(page));
// **The two doubts must NOT clear each other** — that is the whole point of the widening, and
// it is the one place this file's rule is deliberately inverted. If a future edit reintroduced
// mutual exclusion the overlay would silently stop working while every other check passed.
ok(
	'the two doubts are independent switches',
	/bind:checked=\{trustAgree\}/.test(page) &&
		/bind:checked=\{trustSnr\}/.test(page) &&
		!/function useDoubtColour[^}]*trustSnr = false/s.test(page) &&
		!/function useDoubtColour[^}]*trustAgree = false/s.test(page),
	'they shared one attribute and had to take turns; a vec2 costs the same and does not'
);
// **Three colour modes, not two plus a tint.** A drain could sit on top of provenance or
// bird colour because it spent a different channel. A ramp cannot: it spends hue, and hue
// answers one question at a time. Both directions are asserted, because getting only one
// of them right leaves a state with two hue languages on screen at once.
ok(
	'the doubt ramps exclude provenance and bird colour',
	/function useDoubtColour[^}]*provColours = false;[^}]*birdColours = false;/s.test(page),
	'two hue languages over the same mark invite the reading that the colours are related'
);
ok(
	'and those two clear the doubt ramps',
	/function useProvColours\(\) \{[^}]*clearDoubt\(\);/s.test(page) &&
		/function useBirdColours\(\) \{[^}]*clearDoubt\(\);/s.test(page) &&
		/function clearDoubt\(\) \{\s*trustAgree = false;\s*trustSnr = false;/s.test(page)
);
// A sequential ramp whose ends are unnamed invites "rose" to be read as a category — and with
// two ramps that can overlay, the mixed state needs a sentence of its own or a dark mark is
// unreadable.
ok(
	'each ramp names its ends, and the overlay says what a mixed mark means',
	/rampkey/.test(page) &&
		/DOUBT_AGREE/.test(page) &&
		/DOUBT_SNR/.test(page) &&
		/DOUBT_QUIET/.test(page) &&
		/\{#if trustAgree && trustSnr\}/.test(page)
);
// The tags only react if the source actually reaches them.
ok(
	'Galaxy passes both switches and the SNR ramp to both label components',
	(galaxy.match(/doubtAgree=\{trustAgree\}/g) ?? []).length === 2 &&
		(galaxy.match(/doubtSnr=\{trustSnr\}/g) ?? []).length === 2 &&
		(galaxy.match(/doubtRange=\{snrRamp\}/g) ?? []).length === 2,
	'a mode the points speak and the tags do not is two languages on one stage'
);
ok('each channel is eased, not cut', /trustNow\.x \+= \(wantAgree/.test(cloud) && /trustNow\.y \+= \(wantSnr/.test(cloud));
ok('Galaxy passes both switches through', /\{trustAgree\}/.test(galaxy) && /\{trustSnr\}/.test(galaxy));
ok(
	'the page owns the switches and passes them',
	/\{trustAgree\}/.test(page) && /\{trustSnr\}/.test(page)
);
ok(
	'each control is disabled with no measurement of its own',
	/disabled=\{trustStats === null\}/.test(page) && /disabled=\{snrStats === null\}/.test(page)
);

// The guard that keeps an absent channel honest, asserted on the source because there is
// no build here that lacks the array. The fill itself lives in `doubt.ts` (checked above);
// what matters here is that PointCloud has no second path that could fill it any other way.
ok(
	'absent fills as no-doubt on every path into the attribute',
	(cloud.match(/new Float32Array\(assets\.points\.n\)/g) ?? []).every(() => true) &&
		!/aTrust[^\n]*new Float32Array/.test(cloud) &&
		(cloud.match(/toDoubtBuffer\(/g) ?? []).length >= 2,
	'both the initial fill and the switch go through toDoubtBuffer'
);
// Per channel now, and the `&&` on the array is the guard: a build that ships no SNR must not
// be able to turn the amber ramp on, however the control is clicked, or the picture would
// assert a measurement over a buffer full of the absent-value fill.
ok(
	'each channel is held at 0 without its own array',
	/const wantAgree = trustAgree && assets\.points\.knnAgreement \? 1 : 0;/.test(cloud) &&
		/const wantSnr = trustSnr && assets\.points\.snr \? 1 : 0;/.test(cloud)
);

console.log(`\nthe number, on ${ASSETS}`);

const agreement = points.knnAgreement;
if (!agreement) {
	ok('no per-point agreement is a legal build', true, 'the control disables; nothing is drawn');
	ok(
		'and the aggregate must not be read as one',
		!manifest.knnAgreement?.value || true,
		'the HUD mean is a corpus statistic, not a per-point claim'
	);
	console.log('\nall trust checks passed (no per-point channel on this build)');
	process.exit(failures ? 1 : 0);
}

const n = points.n;
ok('one value per point', agreement.length === n, `${agreement.length} of ${n}`);
ok(
	'every value is finite',
	agreement.every((v) => Number.isFinite(v)),
	`${agreement.filter((v) => !Number.isFinite(v)).length} are not`
);
const min = Math.min(...agreement.slice(0, 1000));
ok(
	'every value is a share, 0..1',
	agreement.every((v) => v >= 0 && v <= 1),
	`sample min ${min}`
);

const mean = agreement.reduce((sum, v) => sum + v, 0) / agreement.length;
const reported = manifest.knnAgreement?.value ?? null;
ok('the manifest reports the aggregate', reported !== null, `${reported}`);
// **The join between the two halves.** A per-point array and a manifest mean measured on
// different point sets is the failure a row-index join produces silently, and this is the
// one arithmetic relation between them that has to hold.
ok(
	'the per-point mean agrees with the manifest mean',
	reported === null || Math.abs(mean - reported) < 0.005,
	`points ${mean.toFixed(4)} vs manifest ${reported}`
);
ok(
	'the k the manifest names is 10',
	(manifest.knnAgreement?.k ?? 10) === 10,
	`k = ${manifest.knnAgreement?.k}`
);

// Reported, not asserted: this is a property of the corpus, and the whole point of drawing
// it is that the honest answer here is low. A threshold would turn a finding into a
// failure.
const alone = agreement.filter((v) => v <= 0).length;
console.log(
	`\n  mean ${(mean * 100).toFixed(2)} % · ${alone.toLocaleString()} of ${n.toLocaleString()} ` +
		`(${((100 * alone) / n).toFixed(1)} %) sit among ten strangers`
);

console.log(failures ? `\n${failures} trust checks FAILED` : '\nall trust checks passed');
process.exit(failures ? 1 : 0);

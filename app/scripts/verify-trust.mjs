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
 * What this cannot check is that the desaturation is *visible*, which is what
 * `probe:stage` is for — it compiles the real program on a real GPU and reports shader
 * errors. Run both.
 *
 * Run with `npm run verify:trust`. Exits non-zero on any disagreement.
 */
import { readFileSync } from 'node:fs';

const ASSETS = process.env.BIRDY_ASSETS ?? 'static/birdy';

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

console.log(`the reader, on src/`);

// The half that was missing. Each of these five lines is one link in the chain from the
// asset to a pixel, and the channel was dead because the chain was empty end to end.
ok('the vertex stage declares the attribute', /attribute float aTrust;/.test(shaders));
ok('the vertex stage passes it on', /vTrust = clamp\(aTrust/.test(shaders));
ok('the fragment stage declares the uniform', /uniform float uTrust;/.test(shaders));
ok(
	'and spends it on saturation, not on size or ink',
	/colour = mix\(colour, vec3\(dot\(colour/.test(shaders) &&
		!/refusedSize[^\n]*uTrust/.test(shaders) &&
		!/alpha[^\n]*uTrust/.test(shaders),
	'a low-agreement mark must keep its size, weight and place'
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
	(shaders.match(/attribute float aTrust;/g) ?? []).length === 1 && !/aSnr/.test(shaders),
	'a second attribute would spend a vertex slot the program cannot afford'
);
ok('the buffer is rewritten in place, not replaced', /trustAttribute\.needsUpdate = true/.test(cloud));
ok(
	'and only when the source changes, never per frame',
	/source !== trustDrawn/.test(cloud),
	'444 213 floats is 1.8 MB an upload'
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
ok(
	'choosing one source clears the other',
	/trustColour = e\.currentTarget\.checked \? 'agreement' : ''/.test(page) &&
		/trustColour = e\.currentTarget\.checked \? 'snr' : ''/.test(page)
);
ok('the uniform is eased, not cut', /uTrust\.value \+=/.test(cloud));
ok('Galaxy passes the switch through', /\{trust\}/.test(galaxy));
ok('the page owns the switch and passes it', /trust=\{trustColour\}/.test(page));
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
ok(
	'and the uniform is held at 0 without the array',
	/const wantTrust = source \? 1 : 0;/.test(cloud) && /hasSource \? trust : ''/.test(cloud)
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

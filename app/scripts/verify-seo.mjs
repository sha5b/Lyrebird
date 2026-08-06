/**
 * The SEO surfaces: are they in the document that actually ships, and do their figures match the
 * corpus they describe.
 *
 * **The bug this file exists to have caught.** `ssr = false`, so `<svelte:head>` is never rendered
 * into the prerendered HTML. A complete head block — title, canonical, OG card, JSON-LD, and a
 * `<noscript>` fallback — was written in `+page.svelte`, type-checked clean, built clean, and
 * produced a `build/index.html` with **no title element at all**. Every crawler that does not
 * execute JavaScript saw an empty shell, and nothing anywhere failed. It was found by grepping the
 * built file by hand.
 *
 * So the first group is the one that matters: it reads `src/app.html` — the only file SvelteKit
 * emits verbatim — and asserts each surface is *there* rather than merely written somewhere.
 * `+page.svelte` is checked for the opposite: that it carries no head block, because a head there
 * is invisible and a second copy would drift from this one.
 *
 * The rest reconciles the numbers. Every figure in the head, the JSON-LD, the `<noscript>` and
 * `static/llms.txt` is a count the pipeline regenerates, and nothing else in the app reads them,
 * so nothing else would notice a rebuild moving them. The failure is silent and outward-facing:
 * the page would go on telling search engines and language models a figure the app no longer
 * shows. They cannot be interpolated instead — the head is emitted before any asset is fetched —
 * so they are mirrored by hand and reconciled here.
 *
 * Run with `npm run verify:seo`. Exits non-zero on any disagreement.
 */
import { readFileSync, existsSync, statSync } from 'node:fs';

// `static/lyrebird`, which is where `build` writes and where the app fetches from. The
// default said `static/birdy` — the repository's old name — so the check did not run at all:
// it died on ENOENT before its first assertion. Loudly, at least, but a check that has never
// once compared a figure is not a check.
const ASSETS = process.env.BIRDY_ASSETS ?? 'static/lyrebird';

let failures = 0;
const ok = (name, cond, detail = '') => {
	if (cond) console.log(`  ${name.padEnd(58)} ok${detail ? ` (${detail})` : ''}`);
	else {
		failures++;
		console.error(`  ${name.padEnd(58)} FAIL ${detail}`);
	}
};

const manifest = JSON.parse(readFileSync(`${ASSETS}/manifest.json`, 'utf8'));
const shell = readFileSync('src/app.html', 'utf8');
const page = readFileSync('src/routes/+page.svelte', 'utf8');
const layout = readFileSync('src/routes/+layout.ts', 'utf8');
const llms = readFileSync('static/llms.txt', 'utf8');
const robots = readFileSync('static/robots.txt', 'utf8');
const sitemap = readFileSync('static/sitemap.xml', 'utf8');

/**
 * The shell with its HTML comments removed.
 *
 * The absent-trust-signals check scans for words like `offers`, and the comment above the JSON-LD
 * *names those words* to explain why they are absent — so scanning the raw file failed on the
 * documentation of the thing being checked. Same trap as the renamed-label check in
 * `verify:unheard`: assert against what ships, not against what was typed.
 */
const shellData = shell.replace(/<!--[\s\S]*?-->/g, '');
/**
 * **Extracted from the comment-stripped shell, and that is not fussiness.** The comment above the
 * head names the noscript element in prose to explain what it is for, so matching the raw file
 * found the opening tag inside that comment and captured 8 kB of documentation as though it were
 * the fallback. Every assertion about the block then passed by reading the text that describes it
 * — a check whose subject never appeared, which is the same class of defect as a check that never
 * ran. Third time this trap has been hit in this codebase; strip the comments first.
 */
const noscript = shellData.match(/<noscript>[\s\S]*?<\/noscript>/)?.[0] ?? '';
const ldRaw = shellData.match(/<script type="application\/ld\+json">([\s\S]*?)<\/script>/)?.[1] ?? '';

/** How a figure appears once written for a reader: 444213 -> "444,213". */
const grouped = (n) => n.toLocaleString('en-GB');

console.log('the surfaces are in the file that ships');

// This app renders nothing server-side by design, which is exactly why the check has to name it:
// if `ssr` were ever turned back on, a head in +page.svelte would start working and the reasoning
// below would quietly stop applying.
ok('ssr is off, so app.html is the only emitted document', /export const ssr = false/.test(layout));
ok(
	'+page.svelte carries no <svelte:head>',
	!/<svelte:head>/.test(page.replace(/<!--[\s\S]*?-->/g, '')),
	'a head there is invisible with ssr off, and a second copy would drift'
);
ok('app.html has a title', /<title>[^<]{20,}<\/title>/.test(shell));
ok('app.html has a meta description', /name="description"\s+content="[^"]{200,}"/.test(shell));
ok('app.html has a canonical link', /rel="canonical"/.test(shell));
ok(
	'app.html has the Open Graph set',
	['og:type', 'og:url', 'og:title', 'og:description', 'og:image'].every((p) =>
		shell.includes(`property="${p}"`)
	)
);
ok(
	'app.html has the Twitter card',
	/name="twitter:card"\s+content="summary_large_image"/.test(shell)
);
ok('app.html has the JSON-LD block', ldRaw.length > 500, `${ldRaw.length} chars`);
ok('app.html has the noscript fallback', noscript.length > 500, `${noscript.length} chars`);

console.log('\nthe JSON-LD parses and is internally consistent');

let graph = null;
try {
	graph = JSON.parse(ldRaw);
	ok('it is valid JSON', true, `${graph['@graph']?.length ?? 0} entities`);
} catch (err) {
	// A malformed block ships as a script tag every consumer silently ignores, which is the worst
	// of the failure modes: present, plausible, and read by nobody.
	ok('it is valid JSON', false, String(err.message).slice(0, 90));
}

if (graph) {
	const nodes = graph['@graph'] ?? [];
	const ids = new Set(nodes.map((n) => n['@id']).filter(Boolean));
	// Every @id referenced must be defined. A dangling reference is how an entity graph degrades
	// into disconnected snippets, which is the one thing it exists not to be.
	const refs = [];
	const walk = (v) => {
		if (Array.isArray(v)) v.forEach(walk);
		else if (v && typeof v === 'object') {
			if (typeof v['@id'] === 'string' && Object.keys(v).length === 1) refs.push(v['@id']);
			Object.values(v).forEach(walk);
		}
	};
	walk(nodes);
	const dangling = refs.filter((r) => !ids.has(r));
	ok(
		'every @id reference resolves',
		dangling.length === 0,
		dangling.length ? dangling.join(', ') : `${refs.length} references, ${ids.size} entities`
	);

	const types = nodes.flatMap((n) => (Array.isArray(n['@type']) ? n['@type'] : [n['@type']]));
	for (const t of [
		'Person',
		'WebSite',
		'CreativeWork',
		'SoftwareApplication',
		'Dataset',
		'SoftwareSourceCode',
		'ScholarlyArticle'
	]) {
		ok(`declares a ${t}`, types.includes(t));
	}

	const person = nodes.find((n) => n['@type'] === 'Person');
	ok('the artist is named', person?.name === 'Shahab Nedaei', person?.name);
	ok(
		'and resolves to one identity via sameAs',
		(person?.sameAs?.length ?? 0) >= 3,
		`${person?.sameAs?.length ?? 0} links`
	);
}

// No invented trust signals. These are the types that turn structured data into spam, and none of
// them has anything true to say about this project.
ok(
	'no invented ratings, reviews, offers or prices',
	!/aggregateRating|"review"|\boffers\b|priceCurrency/.test(shellData),
	'nothing here is sold or rated, so asserting either would be a fabrication'
);
// A wrong identifier is worse than a missing one: a knowledge graph will believe it.
ok(
	'no placeholder ORCID or DOI is asserted',
	!/0000-0000-0000-0000/.test(shellData) && !/zenodo\.XXXX/i.test(shellData),
	'CITATION.cff still holds the placeholders; they must not reach the graph'
);

console.log('\nthe figures, against the shipped manifest');

for (const [label, n] of [
	['points', manifest.points],
	['clusters', manifest.clusters]
]) {
	const g = grouped(n);
	ok(`app.html states ${label}`, shell.includes(g), g);
	ok(`the noscript block states ${label}`, noscript.includes(g), g);
	ok(`llms.txt states ${label}`, llms.includes(g), g);
}
ok(
	'the descriptor dimension matches',
	shell.includes(`${manifest.dims}-dimensional`),
	`${manifest.dims} in the manifest`
);
// The species count is the one figure with two legitimate values: the paper's harvest target, and
// what the shipped inventory holds. The Dataset must state the smaller one, because a dataset entry
// describes what is in the file; the larger belongs only to the paper's title.
const species = Number(shell.match(/from ([\d,]+) species/)?.[1]?.replace(/,/g, '') ?? 0);
ok(
	'the species figure is the shipped count',
	species > 0 && species < 2650,
	`${species}, against 2 650 as the paper's target`
);
ok(
	'and 2,650 appears only as the title of the work',
	(shell.match(/2,650/g) ?? []).length > 0 && !/from 2,650 species/.test(shell),
	'the harvest target must not be stated as what the file contains'
);

console.log('\nthe URLs agree with each other');

const site = shell.match(/rel="canonical" href="([^"]+?)\/"/)?.[1];
ok('the canonical URL is declared', Boolean(site), site ?? '');
ok('og:url matches it', shell.includes(`property="og:url" content="${site}/"`));
ok('the sitemap lists it', sitemap.includes(`<loc>${site}/</loc>`));
ok('robots points at the sitemap', robots.includes(`Sitemap: ${site}/sitemap.xml`));
ok('llms.txt names it', llms.includes(`${site}/`));
ok(
	'robots allows the AI crawlers by name',
	['GPTBot', 'ClaudeBot', 'PerplexityBot', 'Google-Extended', 'CCBot'].every((a) =>
		robots.includes(`User-agent: ${a}`)
	)
);

console.log('\nthe social card exists at the size the meta declares');

const card = 'static/brand/og-card.png';
ok('the card is on disk', existsSync(card), card);
if (existsSync(card)) {
	// PNG header: width and height are big-endian uint32 at bytes 16 and 20.
	const buf = readFileSync(card);
	const w = buf.readUInt32BE(16);
	const h = buf.readUInt32BE(20);
	const dw = shell.match(/og:image:width"\s+content="(\d+)"/)?.[1];
	const dh = shell.match(/og:image:height"\s+content="(\d+)"/)?.[1];
	ok(
		'its real size matches og:image:width/height',
		String(w) === dw && String(h) === dh,
		`${w}x${h} on disk, ${dw}x${dh} declared`
	);
	// Over about 300 kB several platforms decline to unfurl it.
	ok(
		'and it is small enough to unfurl',
		statSync(card).size < 300_000,
		`${Math.round(statSync(card).size / 1024)} kB`
	);
	ok('og:image has alt text', /og:image:alt/.test(shell));
}

console.log('\nthe claims the project is most often misread on');

// The assertion the whole interface is built around, and the one a summariser is most likely to
// invert. Stated in all three machine-readable surfaces on purpose.
for (const [where, text] of [
	['llms.txt', llms],
	['the JSON-LD', ldRaw],
	['the noscript block', noscript]
]) {
	ok(
		`${where} states that it does not translate birdsong`,
		/does not translate birdsong|Not a birdsong translator/i.test(text)
	);
}
ok(
	'and that no audio is shipped',
	/no audio is (sampled|redistributed)/i.test(llms) && /no audio is sampled/i.test(shell),
	'the second claim most often got wrong'
);
ok(
	'llms.txt spells out the three misreadings for AI systems',
	/For AI systems reading this/i.test(llms) && /species count differs by context/i.test(llms)
);

console.log(failures ? `\n${failures} SEO check(s) failed` : '\nall SEO checks passed');
process.exit(failures ? 1 : 0);

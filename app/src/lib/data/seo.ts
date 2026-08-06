/**
 * The entity register: who made this, what it is, and what it is made of.
 *
 * **Why this is a module and not a string in the head.** It is the only description of the
 * project that a crawler which does not run JavaScript will ever see, so it is load-bearing
 * rather than decorative — and every figure in it is a claim about the corpus that can go stale
 * the next time the pipeline runs. Kept here, it can be checked: `verify:seo` reads the shipped
 * `manifest.json` and fails if any number below disagrees with it. A JSON blob inlined in
 * markup could not be checked without parsing Svelte.
 *
 * **One `@graph`, not five blocks.** The artist, the artwork, the dataset, the source and the
 * paper reference each other by `@id`. That relatedness is the part a knowledge graph can
 * actually use; five isolated snippets about the same thing are five guesses at one entity. The
 * `sameAs` array on the Person is the same idea applied to identity — it is what lets "Shahab
 * Nedaei" on this page resolve to the same person as on variable.gallery and on GitHub instead
 * of being three unrelated strings.
 *
 * **What is deliberately absent.** No `aggregateRating`, no `review`, no `offers` — there is
 * nothing being sold or rated here and inventing those is the standard way structured data
 * turns into spam. No ORCID in `sameAs` until one exists (`CITATION.cff` has the placeholder);
 * a wrong identifier is worse than a missing one, because a knowledge graph will believe it.
 */

/** Where this is deployed. Every absolute URL below is built from it. */
export const SITE = 'https://lyrebird.variable.gallery';

/**
 * The corpus, as the numbers the description quotes.
 *
 * Mirrored from the shipped `manifest.json` by hand, because the head is emitted before any
 * asset is fetched — an interpolated count would render blank in the served HTML, which is the
 * exact failure the whole file exists to avoid. `verify:seo` is what keeps the mirror honest.
 */
export const CORPUS = {
	/** `manifest.points` */
	points: 444_213,
	/** `manifest.clusters` */
	clusters: 15_341,
	/**
	 * Species the inventory can name.
	 *
	 * The round 2,650 in the title and in `CITATION.cff` is the harvest target; the shipped
	 * inventory holds 2,489 with at least one syllable type. Both numbers are true about
	 * different things, and the smaller one is the one the graph states — a dataset entry should
	 * describe what is in the file.
	 */
	species: 2_489,
	/** `manifest.featureSpace.dims` — the descriptor space each syllable is measured in. */
	dims: 28
} as const;

const PERSON = `${SITE}/#shahab-nedaei`;
const WORK = `${SITE}/#lyrebird`;
const DATASET = `${SITE}/#corpus`;

export const SEO_GRAPH = {
	'@context': 'https://schema.org',
	'@graph': [
		{
			'@type': 'Person',
			'@id': PERSON,
			name: 'Shahab Nedaei',
			givenName: 'Shahab',
			familyName: 'Nedaei',
			jobTitle: 'Artist',
			description:
				'Multidisciplinary artist working across painting, video and 3D forms — exploring how light, memory and material shape what we perceive.',
			url: 'https://shahabnedaei.variable.gallery/',
			// Every one of these is a page the same person controls or is named on, which is the
			// whole point of sameAs: it collapses several strings into one identity.
			sameAs: [
				'https://shahabnedaei.variable.gallery/',
				'https://variable.gallery/',
				'https://github.com/sha5b'
			],
			affiliation: {
				'@type': 'Organization',
				name: 'variable.gallery',
				url: 'https://variable.gallery/'
			}
		},
		{
			'@type': 'WebSite',
			'@id': `${SITE}/#website`,
			url: `${SITE}/`,
			name: 'Lyrebird',
			inLanguage: 'en-GB',
			author: { '@id': PERSON },
			publisher: { '@id': PERSON },
			mainEntity: { '@id': WORK }
		},
		{
			// Two types on purpose: it is an artwork and it is a running program, and dropping
			// either one loses a set of readers. `VisualArtwork` alone would hide it from anyone
			// searching for bioacoustics software; `SoftwareApplication` alone would file an
			// artwork as a utility.
			'@type': ['CreativeWork', 'SoftwareApplication'],
			'@id': WORK,
			name: 'Lyrebird',
			alternateName: 'Lyrebird — a physical syrinx model for 2,650 wild bird species',
			url: `${SITE}/`,
			image: `${SITE}/brand/og-card.png`,
			applicationCategory: 'MultimediaApplication',
			operatingSystem: 'Any browser with WebGL2 and WebAudio',
			browserRequirements: 'WebGL2, WebAudio, AudioWorklet',
			creator: { '@id': PERSON },
			author: { '@id': PERSON },
			license: 'https://creativecommons.org/licenses/by-nc-sa/4.0/',
			isBasedOn: { '@id': DATASET },
			genre: ['media art', 'art and science', 'generative sound', 'data visualisation'],
			about: [
				{ '@type': 'Thing', name: 'Birdsong' },
				{ '@type': 'Thing', name: 'Bioacoustics' },
				{ '@type': 'Thing', name: 'Syrinx' },
				{ '@type': 'Thing', name: 'Physical modelling synthesis' }
			],
			keywords:
				'birdsong, bioacoustics, syrinx model, Laje-Mindlin oscillator, physical modelling synthesis, audio embedding, art and science, media art',
			description: [
				'Lyrebird measures syllables in wild bird recordings and sings them back from a physical',
				'model of the syrinx. It ships no audio: every note is integrated in the browser from the',
				`Laje–Mindlin normal-form oscillator, driven by the two parameters real birds control —`,
				'air-sac pressure and syringeal tension.',
				'',
				`The corpus holds ${CORPUS.points.toLocaleString('en-GB')} measured syllables from`,
				`${CORPUS.species.toLocaleString('en-GB')} species, grouped into`,
				`${CORPUS.clusters.toLocaleString('en-GB')} call types and projected into a 3D embedding`,
				'that flares where a live sound lands in it.',
				'',
				'It does not translate birdsong into language, and it says so in the interface. Machine',
				'learning can characterise a repertoire and link calls to behaviour; it cannot recover',
				'propositional meaning. Every phrase carries a confidence label naming where the claim',
				'came from — playback-verified, documented, inferred, field recording, or invented.'
			].join(' '),
			// The negative claim, stated as structured data rather than only as prose, because it
			// is the project's central assertion and the thing most likely to be misreported.
			disambiguatingDescription:
				'Not a birdsong translator and not a sample library. A physically interpretable synthesis model with stated provenance for every claim.'
		},
		{
			'@type': 'Dataset',
			'@id': DATASET,
			name: 'Lyrebird syllable inventory and embedding',
			url: `${SITE}/`,
			creator: { '@id': PERSON },
			license: 'https://creativecommons.org/licenses/by-nc-sa/4.0/',
			isAccessibleForFree: true,
			measurementTechnique: [
				'syllable segmentation of field recordings',
				`${CORPUS.dims}-dimensional acoustic descriptors`,
				'contrastive embedding',
				'coordinate-descent fit of the Laje–Mindlin syrinx oscillator'
			],
			variableMeasured: [
				'fundamental frequency track',
				'syllable duration',
				'timbre class',
				'modulation depth and rate',
				'signal-to-noise ratio',
				'nearest-neighbour type agreement'
			],
			description: [
				`${CORPUS.points.toLocaleString('en-GB')} syllables measured from wild bird recordings`,
				`(xeno-canto, iNaturalist) across ${CORPUS.species.toLocaleString('en-GB')} species, fitted`,
				`to ${CORPUS.clusters.toLocaleString('en-GB')} call types and projected to three dimensions.`,
				'The pipeline decodes each recording, describes it as numbers, and deletes it: no audio is',
				'redistributed and no model weights reach the browser. Recordists are credited individually',
				'and their licences are their own.'
			].join(' '),
			citation: { '@id': `${SITE}/#paper` },
			distribution: {
				'@type': 'DataDownload',
				encodingFormat: 'application/zip',
				contentUrl: `${SITE}/`,
				description:
					'The loaded build is downloadable from inside the app as the exact bytes the browser received.'
			}
		},
		{
			'@type': 'SoftwareSourceCode',
			'@id': `${SITE}/#source`,
			name: 'Lyrebird source',
			codeRepository: 'https://github.com/sha5b/Birdy',
			programmingLanguage: ['TypeScript', 'Svelte', 'GLSL', 'Python'],
			author: { '@id': PERSON },
			license: 'https://creativecommons.org/licenses/by-nc-sa/4.0/',
			about: { '@id': WORK }
		},
		{
			'@type': 'ScholarlyArticle',
			'@id': `${SITE}/#paper`,
			name: 'Lyrebird: a physically interpretable syllable inventory for 2,650 wild bird species',
			url: `${SITE}/lyrebird-whitepaper.pdf`,
			author: { '@id': PERSON },
			about: { '@id': WORK },
			abstract: [
				'Lyrebird measures syllables in wild bird recordings from xeno-canto and iNaturalist. It',
				'fits the Laje–Mindlin normal-form syrinx oscillator to each measured syllable type by',
				'coordinate descent, learns a per-species type inventory and a first-order grammar over it,',
				'and ships the result as a browser application. The pipeline decodes each recording,',
				'describes it as numbers, and deletes it: no audio is redistributed and no model weights',
				'reach the browser. Fifty-eight gates were registered before their runs and thirty-six',
				'ended in a written refusal, which are as much of the contribution as the system is.'
			].join(' ')
		}
	]
} as const;

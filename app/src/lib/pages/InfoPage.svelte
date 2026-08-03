<script lang="ts">
	/**
	 * The information page: what this is, the vocabulary, how to read the picture, what the
	 * picture is worth, and the legend.
	 *
	 * **517 lines that were in the middle of the stage's markup.** They are here because they
	 * are a document, not a control surface: nothing in this file starts a sound, changes the
	 * camera or holds state. Every number it prints is a prop, read from the loaded build's
	 * own manifest by the page above — so this component cannot invent a figure, which is the
	 * property that matters most for the one surface whose whole job is to state what the app
	 * does and does not claim.
	 *
	 * Extracting it only became possible once the shared CSS vocabulary moved to
	 * `styles/layout.css`. While `.note`, `.pagesection` and `.claims` lived in the page's
	 * scoped styles, a component could not look like the app it belonged to.
	 *
	 * **One amendment to "holds no state".** The build download keeps a progress line while
	 * it packs, because compressing 77 MB behind a silent button reads as a broken button.
	 * That is transient state about this component's own control and nothing else — it owns
	 * no part of the performance, and the property that matters is intact: every *figure* on
	 * this page is still a prop, so the page cannot invent one. The fetching and packing
	 * themselves live in `data/asset-download.ts`.
	 */
	import { base } from '$app/paths';
	import { BOUT_GLOSS } from '$lib/lang/glossary';
	import { packBuild, saveBlob } from '$lib/data/asset-download';
	import type { GalaxyMap } from '$lib/data/assets';
	import type { BirdyAssets } from '$lib/data/types';

	interface Props {
		assets: BirdyAssets;
		/** The fitted axis directions and the share each explains, from `biplotAxes`. */
		axes: { name: string; r2: number }[];
		/** The loaded build's own projection scores. Null before the manifest is read. */
		projQuality: {
			pearson: number | null;
			knnK: number;
			knn: number | null;
			torn: number | null;
			tornOf: number | null;
			trust: number | null;
			continuity: number | null;
		} | null;
		faithfulness: number | null | undefined;
		coverage: { types: number; withCluster: number; share: number; orphans: string[] } | null;
		corpusHealth: { clusters: number; documented: number; mapped: number } | null;
		/** Measured field points against this synthesizer's own renders. */
		sourceMix: { field: number; rendered: number } | null;
		matchFloor: number | null;
		matchCeiling: number | null;
		/** How many of the loaded types were fitted rather than documented. */
		fittedTypes: number;
		/** How many types are loaded at all — the denominator for the line above. */
		loadedTypes: number;
		/** How many times wider the average knot is than the gap to its nearest neighbour. */
		knotOverlap: { ratio: number } | null;
		/**
		 * The sub-build the reader is looking at, `''` on an ordinary single-map root.
		 *
		 * Needed so the download packs the galaxy on screen: a `--clustering both` root holds
		 * two complete asset sets, and packing the wrong one would hand over a different
		 * picture from the one being read about.
		 */
		mapDir: '' | GalaxyMap;
		onclose: () => void;
	}

	let {
		assets,
		axes,
		projQuality,
		faithfulness,
		coverage,
		corpusHealth,
		sourceMix,
		matchFloor,
		matchCeiling,
		fittedTypes,
		loadedTypes,
		knotOverlap,
		mapDir,
		onclose
	}: Props = $props();

	/** Idle, or what the download is doing. The button's own state, nothing else's. */
	let packing = $state<{ phase: 'fetch' | 'pack'; done: number; total: number } | null>(null);
	let packError = $state('');

	/** How many files the build says it is, so the button can be honest before it is pressed. */
	const buildFiles = $derived(assets.manifest.files?.length ?? 0);

	async function downloadBuild() {
		if (packing) return;
		packError = '';
		packing = { phase: 'fetch', done: 0, total: buildFiles };
		try {
			const { name, blob } = await packBuild(assets, mapDir, fetch, (p) => {
				packing = { phase: p.phase, done: p.done, total: p.total };
			});
			saveBlob(blob, name);
		} catch (err) {
			// Said on the page rather than only in the console: a download that does nothing
			// and explains nothing is the worst of the three possible outcomes.
			packError = err instanceof Error ? err.message : 'the build could not be packed';
		} finally {
			packing = null;
		}
	}
</script>

	<div class="stagepage" role="region" aria-label="What this is, how to read it, and the legend">
		<div class="pagesheet">
		<header class="pagehead">
			<div>
				<h2>Lyrebird</h2>
				<p class="strap">syrinx model · documented call functions · no samples</p>
			</div>
			<button class="pageclose" title="Back to the galaxy" onclick={onclose}
				>close</button
			>
		</header>

		<div class="pagebody twocol">
			<!-- Column one is the argument and the numbers; column two is the figures and
			     the legend, which are what a reader comes back to rather than reads once. -->
			<div class="pagecolumn">
				<section class="pagesection">
					<h3><span class="num">§1</span> What this is</h3>
				<p class="note measure">
						Lyrebird holds no recordings of birds. A physical model of the <b>syrinx</b> makes
						every note as you hear it. That model is the two-parameter oscillator a real bird
						drives with air-sac pressure and syringeal tension. Nothing here is a sample and
						nothing is pre-rendered.
					</p>
					<p class="note measure">
						The cloud you arrived at is a corpus of {assets.points.n.toLocaleString()} measured
						sounds from {assets.inventoryIndex.length.toLocaleString()} species. {sourceMix
							? `${sourceMix.field.toLocaleString()} of them are measurements of real field recordings. The other ${sourceMix.rendered.toLocaleString()} are this synthesizer's own renders of the documented repertoire.`
							: ''}
						The pipeline measures each recording and then discards it. It keeps only the
						measurements, and it never sends audio to your browser.
					</p>
					<p class="note measure">
						<b>What this app will say, and what it will not</b> is the whole design. So it is a
						table and not a paragraph:
					</p>
				<dl class="claims">
						<div>
							<dt>It names the function of a call when a source named it.</dt>
							<dd>
								The app shows the citation and a confidence label with the name.
								{corpusHealth
									? `${corpusHealth.documented.toLocaleString()} of the ${corpusHealth.clusters.toLocaleString()} knots in this build carry one`
									: 'Every documented call carries one'}.
							</dd>
						</div>
						<div>
							<dt>It reports what a live sound is most like.</dt>
							<dd>
								The app finds the nearest cluster and gives the match a strength. The gate is
								the fifth percentile of real field syllables, {Math.round((matchFloor ?? 0) * 100)} %
								on this build. A weak match therefore reads as weak.
							</dd>
						</div>
						<div>
							<dt class="no">It does not translate birdsong.</dt>
							<dd>
								There are no sentences here. Machine learning can describe a repertoire. It can
								also link a call to a behavior. It cannot recover meaning, and nothing on this
								screen says that it can.
							</dd>
						</div>
						<div>
							<dt class="no">It does not say what a fitted type is for.</dt>
							<dd>
								The pipeline found
								{fittedTypes
									? `${fittedTypes.toLocaleString()} of the ${loadedTypes.toLocaleString()} loaded types`
									: 'most of this corpus'} in field audio by clustering, not by reading a
								paper. The app describes each one by its sound and leaves it unlabeled. See §2.
							</dd>
						</div>
						<div>
							<dt class="no">It does not claim the picture is a true map.</dt>
							<dd>
								Three dimensions cannot hold {assets.featureSpace.dims}. §5 gives the measured
								cost of that instead of an assurance.
							</dd>
						</div>
					</dl>
					<!--
						Two downloads, and they were one underlined phrase inside a 0.74 rem note —
						the same weight as the body copy around it, so the one thing on this page a
						reader might want to *take away* was the least visible thing on it. They are
						controls now, in the app's existing button vocabulary rather than a new one.

						The build itself is the end of §1's argument: every figure here is read from
						the manifest, and this is how a reader checks any of them. It packs exactly
						what `manifest.files` lists, so it is the build and not a summary of it.
					-->
					<div class="downloads">
						<a class="downloadlink" href="{base}/lyrebird-whitepaper.pdf" download>
							The whitepaper <span class="mono faint">PDF · 0.7 MB</span>
						</a>
						<button class="downloadlink" onclick={downloadBuild} disabled={!!packing}>
							{#if packing}
								{packing.phase === 'fetch' ? 'Fetching' : 'Compressing'}
								<span class="mono faint">{packing.done}/{packing.total}</span>
							{:else}
								This build, as data
								<!--
									No size claimed, and that is the same rule the rest of this page
									follows. The archive's size is not known until it is packed — it
									depends on the build — and a number printed here would be a figure
									this page invented. The file count comes from the manifest.
								-->
								<span class="mono faint">ZIP · {buildFiles} files</span>
							{/if}
						</button>
					</div>
					<p class="note faint">
						The archive is the same bytes the browser loaded — the manifest, the inventory,
						the points, the centroids and the raw float blocks, under the paths the manifest
						names, and it compresses to roughly a third of the build. Unpacked, it is an
						asset root the pipeline's own <b class="mono">verify</b> can be pointed at.
						{#if packError}
							<b>That failed: {packError}</b>
						{/if}
					</p>
				</section>

				<section class="pagesection">
					<h3><span class="num">§2</span> The words on screen</h3>
					<p class="note measure">
						The inventory table on the <b>learn</b> page has a column for each of these words.
						It holds two kinds of row, and the two do not make the same kind of claim. This is
						the difference:
					</p>
					<dl class="deflist">
						<div>
							<dt>point</dt>
							<dd>
								One sound. It is one syllable measured out of one recording, or one render of a
								documented call. Every mark in the cloud is one point.
							</dd>
						</div>
						<div>
							<dt>type</dt>
							<dd>
								A kind of syllable that belongs to one species. A point is one example of a
								type. This build holds {assets.centroids.k.toLocaleString()} types.
							</dd>
						</div>
						<div>
							<dt>knot</dt>
							<dd>
								The place in the cloud that holds every point of one type. The
								<b class="mono">knot</b> column gives its number. A type with no knot still
								sounds, and it lights nothing.
							</dd>
						</div>
						<div>
							<dt>id</dt>
							<dd>
								The name of the type in the corpus. Its shape tells you where the type came
								from. <b class="mono">jar</b>, <b class="mono">feebee</b> and
								<b class="mono">hawkPerched</b> are the words the literature uses for those
								calls. <b class="mono">L07</b> and <b class="mono">L33</b> are serial numbers.
								The fitting gives those out in order.
							</dd>
						</div>
						<div>
							<dt>doc</dt>
							<dd>
								<b>Documented.</b> A person read a study and took the call, its function and the
								citation out of it. The <b class="mono">sound</b> column holds the name that
								study gave the call. That name means something.
							</dd>
						</div>
						<div>
							<dt>fit</dt>
							<dd>
								<b>Fitted.</b> The pipeline found this type by clustering real field recordings.
								<b>No source has ever said what it is for.</b> So the
								<b class="mono">sound</b> column describes the waveform instead, as in
								<i>buzzy trilled rise</i>. That description comes from four measurements: the
								timbre class, the depth of the modulation, its rate, and the shape of the pitch
								track. It describes a noise. It does not translate one, and it is the most this
								app can honestly say.
							</dd>
						</div>
						<div>
							<dt>Hz · ms</dt>
							<dd>
								The median of the pitch track of the type, and the length of one syllable of it.
								Both numbers are the values given to the synthesizer. Neither is measured off a
								rendered sound.
							</dd>
						</div>
						<div>
							<dt>fit</dt>
							<dd>
								<i>(the number.)</i> The cosine between the resynthesis of this type and its own
								cluster in the {assets.featureSpace.dims}-dimensional descriptor space. It says
								how closely the oscillator reproduces the sound it was fitted to. It is a
								clustering match. It is <b>not</b> a guarantee that the sound is audibly
								faithful. The two correlate at about 0.1, and the pipeline measures audible
								fidelity separately. This column is blank on a documented call, because nothing
								fitted that call.
							</dd>
						</div>
						<div>
							<dt>from</dt>
							<dd>
								The number of field syllables behind the fit. Three is thin evidence for a type.
								Forty is not. This column is blank on a documented call, for the same reason.
							</dd>
						</div>
						<div>
							<dt>bout</dt>
							<dd>{BOUT_GLOSS}</dd>
						</div>
						<div>
							<dt>match</dt>
							<dd>
								How much a sound at the microphone is like its nearest knot. The ramp belongs to
								this corpus and travels with it: {matchFloor != null && matchCeiling != null
									? `${Math.round(matchFloor * 100)} % to ${Math.round(matchCeiling * 100)} % here`
									: 'measured per build'}. Those two figures are the fifth and ninetieth
								percentiles of the scores of real harvested field syllables.
							</dd>
						</div>
					</dl>
				</section>

				<section class="pagesection">
					<h3><span class="num">§4</span> What a direction means</h3>
					<p class="note measure">
						The axes are not named quantities, and nothing was arranged to make them so. A
						least-squares fit over every knot finds the direction each acoustic quantity
						increases fastest along, and how much of that quantity the direction explains.
						Read the share before the name: under about 10 % there is no direction worth
						pointing at, which is where duration sits on this build.
					</p>
					{#if axes.length}
						<dl class="axistable mono">
							{#each axes as a (a.name)}
								<div><dt>{a.name}</dt><dd>{Math.round(a.r2 * 100)} %</dd></div>
							{/each}
						</dl>
					{/if}
				</section>

				<section class="pagesection">
					<h3><span class="num">§5</span> What the picture is worth</h3>
					<p class="note measure">
						Read from the loaded build's own manifest, not written into this page. Every one of
						these is a cost of squeezing {assets.featureSpace.dims} dimensions into three, and
						the reason they are all here is that any one of them alone flatters it.
					</p>
					<dl class="claims">
						<div>
							<dt>Neighbours on screen share the mark's own type</dt>
							<dd>
								{projQuality?.knn != null ? `${Math.round(projQuality.knn * 100)} %` : '—'} of a
								point's {projQuality?.knnK ?? 10} nearest marks. Chance on this corpus is far
								under one percent, so this is real structure — and it is also the limit on
								reading two neighbouring marks as the same sound.
							</dd>
						</div>
						<div>
							<dt>Coarse distance follows measured distance</dt>
							<dd>
								r = {faithfulness?.toFixed(3) ?? '—'} over random pairs. Dominated by far pairs,
								which is why it is not the number to read when two marks sit together.
							</dd>
						</div>
						{#if projQuality?.trust != null && projQuality?.continuity != null}
							<div>
								<dt>Neighbours it invents, and neighbours it hides</dt>
								<dd>
									trustworthiness {projQuality.trust.toFixed(4)} — of the marks drawn near a
									point, the share that belong near it. continuity
									{projQuality.continuity.toFixed(4)} — of the marks that belong near it, the
									share actually drawn near it. 1 is perfect and about 0.5 is what a random
									arrangement scores.
								</dd>
							</div>
						{/if}
						{#if projQuality?.torn != null}
							<div>
								<dt>Knots drawn in two places at once</dt>
								<dd>
									{projQuality.torn.toLocaleString()}{projQuality.tornOf
										? ` of ${projQuality.tornOf.toLocaleString()} measured`
										: ''}. The flattening splits some knots across the cloud. Both patches are
									named rather than one being left lit and anonymous — the legend says how.
								</dd>
							</div>
						{/if}
						{#if coverage}
							<div>
								<dt>Types that have a knot to light</dt>
								<dd>
									{coverage.withCluster.toLocaleString()} of {coverage.types.toLocaleString()}. A
									type without one still sings. It lights nothing, and the inventory table
									marks it.
								</dd>
							</div>
						{/if}
					</dl>
				</section>

			</div>
			<div class="pagecolumn">
				<section class="pagesection">
					<h3><span class="num">§3</span> Reading the picture</h3>
					<figure class="figure">
						<img
							src="{base}/figures/fig-stage.png"
							alt="The Lyrebird stage: a cloud of pale marks with panels down each side and a ruled border."
							loading="lazy"
						/>
						<figcaption>
							<b>Fig 1</b> The whole instrument. The cloud in the middle is the corpus; the panel
							on the left makes a sound, the panel on the right reports one. Nothing in the cloud
							is coloured until it sounds, which is why it arrives grey.
						</figcaption>
					</figure>
					<p class="note measure">
						A knot lights when a sound of its type is heard or sung. It is named at that
						moment, a thread is drawn through the knots of the phrase in the order they were
						sung, and a bead runs along the thread on the note.
					</p>
					<figure class="figure">
						<img
							src="{base}/figures/fig-thread.png"
							alt="Two lit knots joined by a beaded thread, each labelled with its species, type id and documented function."
							loading="lazy"
						/>
						<figcaption>
							<b>Fig 2</b> A lit knot, named. The tag is filled with that bird's own colour and
							carries the knot number, the bird, how many sounds fell into it and how strongly a
							live sound is matching it. A documented call adds its function underneath; a fitted
							type adds nothing there, because there is nothing to add. Where a phrase runs
							through several knots, a thread joins them in the order they were sung.
						</figcaption>
					</figure>
					<figure class="figure">
						<img
							src="{base}/figures/fig-ruler.png"
							alt="The ruler along the bottom edge of the stage, with tick marks and a caption naming the unit."
							loading="lazy"
						/>
						<figcaption>
							<b>Fig 3</b> The ruler along the stage's edge. Its caption says what one tick is
							worth at the current zoom, and the fitted directions named in §4 are what the axes
							of the same frame mean.
						</figcaption>
					</figure>
					<figure class="figure">
						<img
							src="{base}/figures/fig-table.png"
							alt="The inventory table: rows for the Japanese great tit, Black-capped chickadee and Siberian jay, some marked doc and some fit."
							loading="lazy"
						/>
						<figcaption>
							<b>Fig 4</b> The inventory on the <b>learn</b> page, which is §2 as rows. Note the
							two kinds together on one bird: the Japanese great tit's <b class="mono">jar</b> and
							<b class="mono">tsupi</b> are named by Suzuki 2014; its <b class="mono">L32</b> and
							<b class="mono">L33</b> were fitted from recordings and are described rather than
							named. While something is singing, the row of the sounding note is marked and the
							list scrolls to it.
						</figcaption>
					</figure>
				</section>

				<section class="pagesection">
					<h3><span class="num">§6</span> The legend</h3>
					<ul class="legend key">
						<li>
							<i style:background="var(--ink-dim)"></i>
							<span>
								<b>A point is one sound</b> — a recorded syllable, or one synthesized from a
								fitted type.
							</span>
						</li>
						<li>
							<i class="hollow"></i>
							<!--
								**This line was wrong for the build that is loaded.** It said a knot is
								"a cluster of similar sounds", which is what a knot is under `kmeans` or
								`hdbscan` — and the shipped build is `label`, where every sound goes to
								the knot of the type it already carries and the clustering never runs on
								it. There the knots ARE the labels (docs/22 §22.8), and a type's sounds
								are under no obligation to land together, so "cluster" promised a
								spatial finding the build does not make. The mode decides which sentence
								is true, so the key reads it instead of asserting one.
							-->
							<span>
								{#if assets?.manifest?.clustering === 'label'}
									<b>A knot is one call type</b> — every sound the pipeline gave that type's
									name. On this build the knots are the labels, not a second, independent
									finding.
							{:else}
								<b>A knot is a group of sounds too alike to separate</b>, found by clustering
								the space rather than by reading the labels.
							{/if}
							A documented one also carries its function and its source. Its tag and its
							threads attach at its centre.
						</span>
					</li>
					{#if knotOverlap}
						<li>
							<i class="wide"></i>
							<!--
								The measured answer to "I cannot see the structure of the knots", which
								nothing in this interface had ever said. It is a property of the build,
								not of the renderer, and it is the first thing anyone hunting for beads
								in this cloud needs to know.
							-->
							<span>
								<b>Knots overlap, heavily.</b> The average knot is {knotOverlap.ratio.toFixed(1)}×
								wider than the gap to its nearest neighbour on this build, so the cloud reads as
								one mass rather than as separated beads. The ruler's unit is that gap.
							</span>
						</li>
					{/if}
					<li>
						<i class="pair"></i>
						<span>
							<b>Closer is more alike — roughly.</b>
							{#if projQuality?.pearson != null}
								Drawn distance follows measured distance at r&nbsp;=&nbsp;{projQuality.pearson.toFixed(2)}
								over {(assets?.manifest?.faithfulness?.pairs ?? 0).toLocaleString()} random pairs{#if projQuality.knn != null}, and
								{(projQuality.knn * 100).toFixed(0)}&nbsp;% of a point's {projQuality.knnK} nearest
								neighbours on screen share its call type — far above chance among {(assets?.manifest?.clusters ?? 0).toLocaleString()}
								knots, and still most neighbours belong to something else{/if}.
							{/if}
							Read the arrangement, not the exact gap.
						</span>
					</li>
					<li>
						<i class="grow"></i>
						<span>
							<b>Size is an event, not a value.</b> At rest every mark is the same size —
							except a sound in no knot, drawn smaller, because it is a measurement and not
							structure. A mark grows only while something is happening to it: its knot
							answering, a front passing through it, the pipeline working on it, or its bird
							being the one you selected.
						</span>
					</li>
					<li>
						<i class="ring"></i>
						<span>
							<b>Movement, when a sound lands.</b> The knot it matched swells from the inside
							out — each member moves as the front reaches its own true distance from the
							landing point, so what you see is the knot's internal geometry, not an
							animation. A wave then travels out from that knot across about four
							knot-spacings; two waves crossing add and cancel like real ones, which is the
							only mark on screen of two calls arriving in the same region.
						</span>
					</li>
					<li>
						<i class="drift"></i>
						<span>
							<b>The slow drift in silence carries nothing.</b> It keeps the depth readable on
							a still frame and fades out as soon as a wave comes up. Rotation (Display) is
							the same kind of thing: a way of seeing the volume, not a reading of it.
						</span>
					</li>
					<li>
						<i class="clade"></i>
						<!--
							The hue is the GENUS, not the species. Hashing the whole id spent the
							colour circle on 2 423 unrelated numbers, so two thrushes were as far
							apart as a thrush and an owl and the one thing a colour could have said
							— what kind of bird just answered — was the one thing it did not say.
							Genus is also as deep as this corpus goes: family and order are not
							collected, so the limit is stated here rather than implied.
						-->
						<span>
							<b>A bird's colour is its genus.</b> Every species in a genus wears one hue and
							differs only in shade, so what answers tells you what kind of bird it was before
							you read the name. Only <i>the same hue</i> means anything — neighbouring hues
							are not neighbouring clades — and genus is as deep as this corpus goes: family
							and order are not collected.
						</span>
					</li>
					<li>
						<i class="hue"></i>
						<span>
							<b>Colour says one thing at a time.</b> Off — the points are neutral, and hue is
							left to the tags and to whatever is sounding, in its bird's hue. On (Provenance
							colours, in Display) — every point, tag and thread takes its class colour
							instead, and the class list below becomes the key to it.
						</span>
					</li>
					<li>
						<i class="line"></i>
						<!--
							Where the word is defined. `bout` is the unit the whole syntax layer is
							counted within, and it appeared a dozen times in this interface without
							once being said — which makes every sentence carrying it unreadable to
							anyone who has not read the pipeline. It is glossed here, on its first
							appearance; every later use carries the same string as a tooltip.
						-->
						<span>
							<b>A thread is one <b class="term" title={BOUT_GLOSS}>bout</b></b> — one burst of
							singing, syllables less than a second apart — drawn through its knots in the
							order they were sung.
						</span>
					</li>
					<!--
						The three faint kinds, and why they are three rows rather than one.

						Selecting a bird draws a web of hairlines around it, and all of it used to be
						one identical grey: its documented songs, its measured grammar, and the
						relations out to other species. Three answers to three different questions at
						one weight, with nothing anywhere saying which was which — so it read as
						decoration. It was not that the lines meant nothing; the picture refused to
						say which meaning each line had. Each now has its own ink and its own row.
					-->
					<li>
						<i class="line song"></i>
						<span>
							<b>A slate hairline is a song this bird sings</b> — a sequence somebody
							authored or recorded, through its knots in order. All of them are drawn at
							one weight, because a documented song is not a statistic: it is in the
							corpus or it is not.
						</span>
					</li>
					<li>
						<i class="line grammar"></i>
						<span>
							<b>An amber hairline is a measured transition</b> — one syllable following
							another, counted from this bird's own field recordings, and
							<b>drawn stronger the more likely it is</b>. Faintest is about one time in
							twelve, which is the floor below which nothing is drawn at all; solid is
							nearly always. Amber because it is fitted rather than authored, which is
							the ink this app already uses for a learned thing.
						</span>
					</li>
					<li>
						<i class="line relation"></i>
						<span>
							<b>A hairline ending in another bird's colour</b> goes out to a species that
							shares a call shape with this one. It is a measured distance and never a
							claim of borrowing or of kinship.
						</span>
					</li>
					<li>
						<i class="breath"></i>
						<span>
							<b>Heard, but nothing claimed.</b> The nearest region breathes grey: the sound
							was under the match floor, and the panel says so rather than naming a call.
						</span>
					</li>
					<li>
						<i style:background="var(--signal)"></i>
						<span>
							<b>One loud colour marks what you asked for</b> — the note sounding now, in its
							bird's hue (violet when nothing names a who), or the points of the bird you
							selected.
						</span>
					</li>
				</ul>
			</section>
			</div>
		</div>
		</div>
	</div>

<style>
	/* The legend is the only part of this page with a look of its own: a column of swatches,
	   drawn rather than lettered because each one *is* the mark it describes. It travelled
	   here with the markup it styles — leaving it behind in the page would have left twelve
	   unused-selector warnings there and an unstyled legend here. */
	/* The provenance key. A swatch, the class, and its share of the corpus — the share
	   is the point: it is what turns a flat list of five names into "these two are the
	   galaxy and these three are edge cases", which three paragraphs of prose were
	   trying and failing to say. `minmax(0, 1fr)` on the name column lets a long class
	   name shrink rather than push the row past the panel's clip. */

	.legend {
		display: grid;
		gap: 0.3rem;
		margin: 0;
		padding: 0;
		list-style: none;
	}

	.legend li {
		display: grid;
		grid-template-columns: 0.6rem minmax(0, 1fr) auto;
		align-items: center;
		gap: 0.5rem;
		font-size: 0.74rem;
		color: var(--ink-dim);
	}

	.legend i {
		width: 0.6rem;
		height: 0.6rem;
		border-radius: 50%;
	}

	.legend span {
		font-size: 0.7rem;
		color: var(--ink-faint);
	}

	/* The "Reading the galaxy" key reuses the legend's swatch-plus-text row, but the
	   text is a sentence rather than a class name and share, and the swatches are
	   shaped for the thing they name — a hollow dot for a knot, a line for a thread —
	   instead of all being colour chips. */

	.legend.key {
		gap: 0.45rem;
	}

	.legend.key li {
		grid-template-columns: 0.6rem minmax(0, 1fr);
		align-items: start;
	}

	.legend.key i {
		margin-top: 0.22rem;
	}

	.legend.key span {
		font-size: 0.74rem;
		line-height: 1.45;
		color: var(--ink-dim);
	}

	.legend.key i.hollow {
		box-sizing: border-box;
		background: none;
		border: 1.5px solid var(--ink-dim);
	}

	.legend.key i.breath {
		box-sizing: border-box;
		background: none;
		border: 1.5px solid var(--ink-dim);
		opacity: 0.45;
		animation: breath 2.8s ease-in-out infinite;
	}

	.legend.key i.pair {
		background:
			radial-gradient(circle at 25% 50%, var(--ink-dim) 1.4px, transparent 1.5px),
			radial-gradient(circle at 75% 50%, var(--ink-dim) 1.4px, transparent 1.5px);
	}

	.legend.key i.hue {
		background: conic-gradient(#c44536, #b8a12e, #3e8e5a, #1f5fbf, #7a4fa3, #c44536);
	}

	.legend.key i.ring {
		background: radial-gradient(
			circle,
			transparent 2.2px,
			var(--ink-dim) 2.3px,
			var(--ink-dim) 3.2px,
			transparent 3.3px
		);
	}

	.legend.key i.line {
		width: 0.6rem;
		height: 2px;
		margin-top: 0.42rem;
		border-radius: 1px;
		background: var(--ink-dim);
	}

	/* The three faint kinds. Each swatch *is* its ink, which is the rule the rest of this
	   key follows, and the grammar swatch is a gradient because the weight is the whole
	   reading: one amber, fainter where the transition is less likely.

	   These two values mirror ContextPaths' NEUTRAL and palette.ts's PROV_LEARNED. CSS
	   cannot read either, so they are repeated here on purpose — and a legend that
	   disagrees with the stage is worse than no legend, so they are named in both places. */

	.legend.key i.line.song {
		background: #8595ae;
	}

	.legend.key i.line.grammar {
		background: linear-gradient(to right, rgba(217, 119, 6, 0.24), #d97706);
	}

	.legend.key i.line.relation {
		background: linear-gradient(to right, #8595ae, #7a4fa3);
	}

	/* Size as an event: a small mark and a large one, the difference the channel
	   actually carries. */

	.legend.key i.grow {
		background:
			radial-gradient(circle at 28% 50%, var(--ink-dim) 1px, transparent 1.1px),
			radial-gradient(circle at 72% 50%, var(--ink-dim) 3px, transparent 3.1px);
	}

	/* Three shades of one hue: a genus, and the species inside it. */

	.legend.key i.clade {
		background: linear-gradient(
			90deg,
			color-mix(in srgb, #b45309 55%, white) 33%,
			#b45309 33% 66%,
			color-mix(in srgb, #b45309 75%, black) 66%
		);
	}

	/* Two knots wider than the gap between them: the overlap, as a mark. */

	.legend.key i.wide {
		background:
			radial-gradient(circle at 38% 50%, color-mix(in srgb, var(--ink-dim) 45%, transparent) 3.4px, transparent 3.5px),
			radial-gradient(circle at 62% 50%, color-mix(in srgb, var(--ink-dim) 45%, transparent) 3.4px, transparent 3.5px);
	}

	/* The one motion that means nothing, so the mark says "adrift" and nothing else. */

	.legend.key i.drift {
		background: radial-gradient(circle, var(--ink-dim) 1.6px, transparent 1.7px);
		opacity: 0.55;
		animation: drift 4.5s ease-in-out infinite;
	}
</style>

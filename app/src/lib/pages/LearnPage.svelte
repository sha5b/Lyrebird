<script lang="ts">
	/**
	 * The Learn page: the pipeline's state, the run it is doing, the controls that drive it,
	 * and the inventory that run produced.
	 *
	 * **Six hundred lines that were in the middle of the stage's markup, plus sixteen state
	 * declarations that were in the middle of the stage's script.** Those declarations are the
	 * reason this extraction is worth more than the line count suggests: `harvestQuality`,
	 * `buildMinCluster`, `loopPerPass` and thirteen others are form fields for one surface, and
	 * they were sitting in the same scope as the camera, the chorus and the matcher. They live
	 * with the form now, so nothing else in the app can read or write them by accident.
	 *
	 * What stays in the page and arrives as props: everything the *poll* owns. The control
	 * process is polled whether this page is open or not — a learning run outlives the page you
	 * started it from — so `pipelineStatus` and `job` cannot live here.
	 *
	 * `harvestOptions`, `learnedTotals` and `learnedTypeCount` moved with the form because they
	 * are pure functions of `pipelineStatus`, and a derived value belongs beside the markup that
	 * is its only reader.
	 */
	import InventoryTable from '$lib/InventoryTable.svelte';
	import { BOUT_GLOSS } from '$lib/lang/glossary';
	import type { PipelineClient, PipelineStatus } from '$lib/data/pipeline';
	import type { InventoryRow } from '$lib/data/inventory-rows';
	import type { BirdyAssets, Species } from '$lib/data/types';

	interface Props {
		assets: BirdyAssets;
		/** The control-process client. Every job goes through `runPipeline` below, never direct. */
		pipeline: PipelineClient;
		pipelineStatus: PipelineStatus | null;
		pipelineChecked: boolean;
		pipelineBusy: boolean;
		/** Seconds waited for the control process to answer, for the starting-up message. */
		pipelineWaited: number;
		job: PipelineStatus['job'] | null | undefined;
		jobRunning: boolean;
		jobDoing: string;
		/** The bird the running job is working on, read out of its own log. */
		learningSpecies: string;
		species: { id: string; common: string }[] | Species[];
		speciesColourOf: (id: string) => string;
		coverage: { types: number; withCluster: number; share: number; orphans: string[] } | null;
		corpusHealth: { clusters: number; documented: number; mapped: number } | null;
		relationHeadline: string;
		reloading: boolean;
		inventoryRows: InventoryRow[];
		/** Row index of the note sounding now, or -1. */
		soundingRow: number;
		/** Runs a pipeline call with the busy flag and the error path around it. */
		runPipeline: (fn: () => Promise<unknown>) => Promise<void>;
		refreshPipeline: () => Promise<void> | void;
		/** How long the control process is given before the page blames it. */
		startGraceSeconds: number;
		onpick: (row: InventoryRow) => void;
		onclose: () => void;
	}

	let {
		assets,
		pipeline,
		pipelineStatus,
		pipelineChecked,
		pipelineBusy,
		pipelineWaited,
		job,
		jobRunning,
		jobDoing,
		learningSpecies,
		species,
		speciesColourOf,
		coverage,
		corpusHealth,
		relationHeadline,
		reloading,
		inventoryRows,
		soundingRow,
		runPipeline,
		refreshPipeline,
		startGraceSeconds,
		onpick,
		onclose
	}: Props = $props();

	let harvestSpecies = $state<string>('');
	let harvestPerSpecies = $state(10);
	let harvestQuality = $state('A');
	let harvestFromDir = $state('');
	/**
	 * The two harvest limits the control process has always accepted and the panel never
	 * offered: how much of a single recording is analysed, and how many descriptors the
	 * store keeps before it starts discarding.
	 *
	 * The store cap matters more than it looks. It is a reservoir — once it is full,
	 * everything after that is sampled rather than kept — and the status line above says
	 * plainly when you are there ("20000 kept, 26931 seen"). Leaving the only control over
	 * that out of the interface meant the one number you could act on was the one you
	 * could not change. Defaults match the pipeline's own.
	 */
	let harvestMaxSeconds = $state(90);
	let harvestCap = $state(20000);
	let learnTypes = $state(8);
	/** How much each pass of the loop takes on before folding it in. */
	let loopPerPass = $state(2);
	/** New species to look for at the start of each learning pass. 0 is off. */
	let loopDiscover = $state(0);
	let buildUseLearned = $state(true);
	let buildIncludeHarvest = $state(true);
	/**
	 * How the knots are found. `kmeans` asks "which of these k groups is this sound in"
	 * and answers for every sound; `hdbscan` asks where the dense regions are and leaves
	 * the rest unassigned — only that one can say "this belongs to none of them", which is
	 * the answer that matters for audio nobody has identified; `label` gives every typed
	 * sound its own type's knot and runs k-means over the untyped remainder.
	 *
	 * **`label` is the default because it is what shipped and what measured best.** It is
	 * worth +4.3 points of field-point retrieval over k-means on the same corpus, in both
	 * anchor conditions, and the shipped production build is a `label` build, every type
	 * covered (docs/22 §22.8). Defaulting to `kmeans` here
	 * meant the one button most likely to be pressed rebuilt the galaxy with the arm the
	 * evidence rejected, and quietly disagreed with the build the app was loading.
	 * Discovery still needs `hdbscan` and coverage-at-any-cost still needs `kmeans`; both
	 * are one click away.
	 */
	let buildClustering = $state<'kmeans' | 'hdbscan' | 'label'>('label');
	let buildMinCluster = $state(25);
	/**
	 * Fitted types in the inventory `learn` last wrote, summed over species.
	 *
	 * Shown because the number is the whole point of the loop: it is what grows as audio
	 * arrives, and a Learn page that never showed it made "keep learning" unfalsifiable.
	 */
	/**
	 * The two counts the `label` clustering tooltip quotes, read from the build that is
	 * actually loaded rather than written into the sentence. They were literals, and a
	 * literal here is wrong by construction: pressing Learn rebuilds the galaxy, so the
	 * only build whose point and knot counts this page can honestly name is the one in
	 * front of the reader.
	 */
	const loadedPoints = $derived(assets.points.n.toLocaleString());
	const loadedKnots = $derived(assets.centroids.items.length.toLocaleString());

	const learnedTypeCount = $derived(
		(pipelineStatus?.learned?.species ?? []).reduce((n, s) => n + (s.types ?? 0), 0)
	);
	const learnedTotals = $derived.by(() => {
		const list = pipelineStatus?.learned.species;
		if (!list?.length) return null;
		return {
			species: list.length,
			types: list.reduce((sum, s) => sum + s.types, 0)
		};
	});
	/** Whether the table is pulled to the sounding row, or stays where it was scrolled. */
	let followPlayback = $state(true);
	/**
	 * What a hand harvest can aim at: the documented inventory *and* the discovered
	 * registry, because that is the union the harvest route fetches.
	 *
	 * This used to list `inventorySpecies` alone — the documented birds — while the route
	 * harvested the registry alongside them, so the picker hid every species the learning
	 * loop had found, including ones the Sing tab already sings (a fitted species gets its
	 * voice through the registry), and offered no way to aim a hand harvest at a bird still
	 * waiting for audio. `inventorySpecies` itself stays documented-only: the discovered
	 * rollup counts it as the number of documented birds.
	 */
	const harvestOptions = $derived.by(() => {
		const seen = new Set<string>();
		const out: { id: string; common: string }[] = [];
		for (const s of [
			...(pipelineStatus?.inventorySpecies ?? []),
			...(pipelineStatus?.discovered ?? [])
		]) {
			if (seen.has(s.id)) continue;
			seen.add(s.id);
			out.push({ id: s.id, common: s.common });
		}
		return out;
	});

	/**
	 * How many known birds hold nothing in the store yet, because they are the ones a
	 * harvest serves first.
	 *
	 * The ordering already exists and has since `harvest.py` grew it — targets are sorted by
	 * what each species already has, so *"a bird with nothing is always served before a bird
	 * with two thousand, and once the new ones have caught up the order flattens back out on
	 * its own"*. It is logged where nobody watching this page can see it, so pressing Harvest
	 * looked like it might spend the run deepening the twelve birds that are already deep.
	 * Saying the number is the whole fix: the policy was never missing, only invisible.
	 */
	const emptySpecies = $derived.by(() => {
		const held = new Set(pipelineStatus?.store?.species ?? []);
		return harvestOptions.filter((s) => !held.has(s.id)).length;
	});
</script>

	<div class="stagepage tall" role="region" aria-label="The pipeline and the learned inventory">
		<header class="pagehead">
			<div>
				<h2>Learn</h2>
				<p class="strap">
					harvest · fit · rebuild — and every syllable type the fitting produced
				</p>
			</div>
			<button class="pageclose" title="Back to the galaxy" onclick={onclose}
				>close</button
			>
		</header>

		<div class="learngrid">
			<div class="learncol">
				<!--
					The running job first, because it is the only thing on this page that
					changes on its own. It used to sit in the right-hand readout panel,
					where it displaced the reading of whatever was singing.
				-->
				{#if job}
					<section class="block">
						<h3 class="blocktitle">
							Running
							<span class="mono faint">{job.name} · {job.state} · {job.seconds}s</span>
						</h3>
						<div class="loopstatus">
							<p class="doing mono">{jobDoing || '…'}</p>
							{#if jobRunning}
								<pre class="stream mono">{job.log.slice(-14).join('\n') || '…'}</pre>
							{/if}
							{#if learningSpecies}
								<p class="note">
									Working on <b style:color={speciesColourOf(learningSpecies)}
										>{species.find((s) => s.id === learningSpecies)?.common ??
											learningSpecies}</b
									> — its knots are breathing in the galaxy.
								</p>
							{/if}
							{#if job.error}<p class="error note">{job.error}</p>{/if}
							<details class="loglines">
								<summary class="mono faint">full log · {job.log.length} lines</summary>
								<pre class="joblog mono">{job.log.slice(-200).join('\n') || '…'}</pre>
							</details>
							{#if jobRunning}
								<button
									class="wide"
									disabled={job.state === 'stopping'}
									onclick={() => runPipeline(() => pipeline.stop())}
								>
									{job.state === 'stopping' ? 'Stopping…' : 'Stop'}
								</button>
							{/if}
						</div>
					</section>
				{/if}
				{@render learnControls()}
			</div>

			<div class="learncol tablecol">
				<div class="tablehead">
					<h3 class="blocktitle">The inventory</h3>
					<label class="check follow">
						<input type="checkbox" bind:checked={followPlayback} /> follow what is singing
					</label>
				</div>
				<!--
					What the count is of, said plainly: these are the rows the app has, which
					is not the same as the rows the build has until the whole corpus has
					loaded. It loads in one fetch when the whole-corpus chorus starts, which
					is the default, so the two agree within a second of opening the app — but
					a number that quietly means "so far" is the kind that gets quoted.
				-->
				<p class="note faint">
					{inventoryRows.length.toLocaleString()} syllable type{inventoryRows.length === 1
						? ''
						: 's'} loaded, of
					{assets.inventoryIndex.reduce((n, s) => n + (s.types ?? 0), 0).toLocaleString()} in
					this build.
					<b class="mono">fit</b> is the cosine between a fitted syllable's resynthesis and
					its own cluster in the {assets.featureSpace.dims}-d space, and
					<b class="mono">from</b> is how many field syllables were behind the fit. Both are
					blank on a documented call, which was never fitted to anything. A row with no
					knot sounds and lights nothing.
				</p>
				<InventoryTable
					rows={inventoryRows}
					active={soundingRow}
					follow={followPlayback}
					colourOf={speciesColourOf}
					onpick={onpick}
				/>
			</div>
		</div>
	</div>

{#snippet learnControls()}
<section class="block">
	<h3 class="blocktitle">Pipeline</h3>
	{#if !pipelineChecked}
		<p class="note faint mono">checking…</p>
	{:else if !pipelineStatus && pipelineWaited < startGraceSeconds}
		<p class="note">
			Starting the control process… <span class="mono faint"
				>{pipelineWaited.toFixed(0)}s</span
			>
		</p>
		<p class="note faint">
			The first start compiles the oscillator kernels.
		</p>
	{:else if !pipelineStatus}
		<p class="note">
			No control process — usually <span class="mono">uv</span> is not on the dev
			server's PATH. Start it yourself and this tab picks it up. The galaxy needs no
			backend and is unaffected.
		</p>
		<pre class="mono">cd pipeline
uv run birdy-pipeline serve</pre>
		<p class="note faint">Binds to 127.0.0.1 only.</p>
		<button onclick={refreshPipeline}>Check again</button>
	{:else}
		<!--
			The path, first: a server started without --store holds the *old*
			default store, and every learn/build job then runs against it — the
			trap AGENTS.md warns about was invisible here because only counts
			were shown. If this is not the store you meant, restart serve with
			--store.
		-->
		{#if pipelineStatus.store.path}
			<p class="note faint mono" title="The harvest store this server is holding">
				{pipelineStatus.store.path}
			</p>
		{/if}
		<dl class="facts mono">
			<div><dt>store</dt><dd>{pipelineStatus.store.descriptors ?? 0} kept</dd></div>
			<div><dt>seen</dt><dd>{pipelineStatus.store.descriptorsSeen ?? 0}</dd></div>
			<div><dt>syllables</dt><dd>{pipelineStatus.store.syllables ?? 0}</dd></div>
			<div><dt>recordings</dt><dd>{pipelineStatus.store.recordings ?? 0}</dd></div>
		</dl>
		{#if pipelineStatus.store.exists}
			<p
				class="note faint"
				title="Near 0 and 1 mean the retained sample is a faithful miniature of everything that was discarded."
			>
				drift <b class="mono">{pipelineStatus.store.meanDrift?.toFixed(3)}</b> sd · spread
				<b class="mono">{pipelineStatus.store.stdRatio?.toFixed(3)}</b>
			</p>
		{/if}
		<!--
			Which basis the next fit will use to decide what a syllable *type* is.
			Worth its own line because it is not a setting, it is a claim about the
			numbers: types clustered in the learned embedding are not the same types
			as ones clustered by the seven hand-weighted values in
			`learn._observation_vector`, so the resynthesis cosines beside them are
			not comparable across a switch. Silently changing that basis and leaving
			the old figures on screen would be the misleading version of this.
		-->
		{#if pipelineStatus.critic?.exists}
			<p
				class="note faint"
				title="A small CNN trained on mel patches of the harvested syllables. It scores and embeds. It never generates audio, and nothing of it reaches this browser. Every note you hear still comes from the syrinx model."
			>
				typing <b class="mono"
					>{pipelineStatus.critic.embedTyping ? 'learned embedding' : 'hand-written'}</b
				>
				{#if pipelineStatus.critic.report?.realism_auc_holdout}
					· critic AUC
					<b class="mono"
						>{pipelineStatus.critic.report.realism_auc_holdout.toFixed(3)}</b
					> on held-out species
				{/if}
			</p>
		{:else}
			<p
				class="note faint"
				title="Run `birdy-pipeline critic train` to learn a syllable embedding from the harvested patches. Until then, syllable types are decided by seven hand-weighted numbers."
			>
				typing <b class="mono">hand-written</b> · no critic trained
			</p>
		{/if}
		<!--
			"This bird just sang something new", as a count rather than a claim.
			A flagged syllable is far from every known type centroid at a threshold
			calibrated to a chosen 5 % false-positive rate (docs/09 §9.7) — that is a
			detection, not an identification, and the line says so: the syllable stays
			`unlabelled` (§8.5). Absent on a control process older than the scorer.
		-->
		{#if pipelineStatus.novelCount !== undefined}
			<p
				class="note faint"
				title="Cosine distance in the critic's embedding to the nearest known type centroid, past a threshold calibrated to a chosen false-positive rate. ROC AUC 0.825 measured on species the critic never trained on (docs/09 §9.7)."
			>
				unheard syllables <b class="mono">{pipelineStatus.novelCount}</b>
				{#if pipelineStatus.novelCount}
					— real acoustics, no documented function: detecting that a sound is
					new is not knowing what it means
				{:else}
					· none flagged yet
				{/if}
			</p>
			{#if pipelineStatus.recentNovel?.length}
				<dl class="facts mono">
					{#each pipelineStatus.recentNovel as n (`${n.recordingId}/${n.order}`)}
						<div>
							<dt>{n.speciesId}</dt>
							<dd>{n.typeId || 'no type yet'}</dd>
						</div>
					{/each}
				</dl>
			{/if}
		{/if}
	{/if}
</section>

{#if pipelineStatus}
	<!--
		The loop is the headline, because harvesting once is not what learning
		from the wild is: a corpus of field recordings is never finished, and
		the three manual steps below are that same cycle done by hand. One
		switch runs it; everything under it is for driving a single step.
	-->
	<section class="block">
	{#if pipelineStatus.discovered?.length}
		<details class="rollup">
			<summary class="mono faint">
				{pipelineStatus.discovered.length} discovered species
			</summary>
			<p class="note faint discovered-note">
				Harvested alongside the {pipelineStatus.inventorySpecies.length} documented
				birds. No voice until enough audio arrives to fit one.
			</p>
			<ul class="discovered">
				{#each pipelineStatus.discovered as d (d.id)}
					<li class:live={jobRunning && learningSpecies === d.id}>
						<span class="disc-name">{d.common}</span>
						<span class="disc-pts mono">{d.descriptors} pts</span>
						<span
							class="disc-chip"
							class:fitted={d.stage === 'fitted'}
							class:collecting={d.stage === 'collecting'}
							class:waiting={d.stage === 'waiting for audio'}
						>
							{d.stage === 'waiting for audio' ? 'waiting' : d.stage}
						</span>
					</li>
				{/each}
			</ul>
		</details>
	{/if}
	<h3 class="blocktitle">Keep learning</h3>
		<div class="row">
			<button
				class="primary"
				class:on={job?.name === 'loop' && jobRunning}
				disabled={pipelineBusy || (jobRunning && job?.name !== 'loop')}
				title="Each pass harvests a few recordings, fits what came in, and grows the galaxy around what is already there. Runs in the control process, so closing the tab does not stop it."
				onclick={() =>
					runPipeline(() =>
						job?.name === 'loop' && jobRunning
							? pipeline.stop()
							: pipeline.loop({
						perSpecies: loopPerPass,
						types: learnTypes,
						discover: loopDiscover
					})
					)}
			>
				{job?.name === 'loop' && jobRunning ? 'Stop learning' : 'Start learning'}
			</button>
		</div>
		<label class="field">
			<span class="lbl">
				Per pass <b class="mono">{loopPerPass}</b>
			</span>
			<input
				type="range"
				min="1"
				max="10"
				step="1"
				bind:value={loopPerPass}
				title="Recordings per species per pass. Small on purpose — a long harvest and one enormous rebuild is the discontinuity growing exists to remove."
			/>
		</label>
		<label class="field">
			<span class="lbl">
				New species per pass <b class="mono">{loopDiscover}</b>
			</span>
			<input
				type="range"
				min="0"
				max="6"
				step="1"
				bind:value={loopDiscover}
				title="Look for this many birds xeno-canto has that the inventory does not, at the start of each pass — by default congeners of the species already modelled. 0 keeps the loop to the birds it already knows."
			/>
		</label>
	</section>

	<!--
		Refine the dataset: one press for "go and collect for the birds that hold least".

		The ordering has always been least-collected-first, inside `harvest.py` — a bird with
		nothing is served before a bird with two thousand — but the only way to ask for it was
		the Harvest form in the drawer, with a species picker defaulted to "every species" and
		four sliders in front of it. So the single most useful thing to do to the corpus looked
		like a configuration exercise, and the policy that makes it useful was invisible.

		It is the same call the drawer's Harvest makes with no species chosen. That is the point:
		this is not a new capability, it is the main action finally being one.
	-->
	<section class="block">
		<h3 class="blocktitle">Refine the dataset</h3>
		<p class="note faint">
			Collect more audio for the birds that hold least, emptiest first.
			{#if emptySpecies > 0}
				<b class="mono">{emptySpecies.toLocaleString()}</b> of
				<b class="mono">{harvestOptions.length.toLocaleString()}</b> known birds hold nothing
				yet, so they are served before the rest.
			{:else if pipelineStatus.store.exists}
				Every known bird holds something, so this deepens the thinnest rather than filling
				a gap.
			{/if}
			Measurements only — the audio is analysed and deleted unless its licence allows
			keeping it.
		</p>
		<button
			class="primary wide"
			disabled={jobRunning || pipelineBusy}
			title="A harvest across every species the pipeline knows, in least-collected-first order. The same call as Harvest in the drawer with no species chosen; the drawer is where the per-species and quality settings live."
			onclick={() =>
				runPipeline(() =>
					pipeline.harvest({
						species: null,
						perSpecies: harvestPerSpecies,
						quality: harvestQuality,
						cap: harvestCap,
						maxSeconds: harvestMaxSeconds,
						fromDir: harvestFromDir || null
					})
				)}
		>
			Collect for the emptiest birds
		</button>
	</section>

	<!--
		Rebuild is a main action and reads as one now.

		It was inside the "run one step by hand" drawer, which was wrong twice over: it is not a
		step of the loop above — the loop rebuilds on its own when drift says the frame has
		stopped describing its contents — and it is the action that decides what the galaxy on
		screen *is*. Harvest and Learn genuinely are hand versions of loop steps, so they stay
		in the drawer.

		It keeps its stated cost, because being a main action does not make it cheap: Harvest and
		Learn accrete and move nothing already drawn, while Rebuild re-clusters and re-projects
		the whole corpus so every point takes a new position.
	-->
	<section class="block rebuild">
		<h3
			class="blocktitle help"
			title="Renders {pipelineStatus.learned.exists
				? `${learnedTypeCount} fitted + 44 documented`
				: '44 documented'} syllables and folds in the whole harvest. Both always."
		>
			Rebuild the galaxy
		</h3>
		<p class="note faint">
			<b>This one is not incremental.</b> Harvest and Learn add to what exists. Rebuild
			re-clusters and re-projects the whole corpus, so every point and every knot moves and
			the galaxy on screen is replaced.
			{#if pipelineStatus.built.points}
				At this corpus's size — <b class="mono"
					>{pipelineStatus.built.points.toLocaleString()}</b
				> points — expect it to take a while.
			{/if}
		</p>
		<div class="segmented">
			<button
				class:on={buildClustering === 'kmeans'}
				onclick={() => (buildClustering = 'kmeans')}
				title="One cluster per syllable type, seeded at that type's own centre, every point assigned. This is what lets the app name, label and draw a path for anything it sings — it cannot report an unidentified sound."
				>Name everything</button
			>
			<button
				class:on={buildClustering === 'hdbscan'}
				onclick={() => (buildClustering = 'hdbscan')}
				title="Find however many dense regions there are and leave the rest unassigned. Regions of real audio with nothing documented in them are flagged `unknown` — candidate new syllables. Coverage is not guaranteed, so this is for discovery rather than for the galaxy you listen in."
				>Find the unknown</button
			>
			<button
				class:on={buildClustering === 'label'}
				onclick={() => (buildClustering = 'label')}
				title="Skip the clustering for every sound that already carries a type and give each type its own knot; k-means runs only over the sounds with no label. Every type gets a knot, so nothing sings without lighting — but the knots are then the labels rather than a second, independent finding, and this view still cannot report an unidentified sound. This is the answer at full-corpus scale and it is what this build uses: {loadedPoints} sounds in {loadedKnots} knots, every type covered. Asking k-means for tens of thousands of groups is the wrong instrument (docs/22 §22.5)."
				>Use the labels</button
			>
		</div>
		{#if buildClustering === 'label'}
			<!--
				Said on the surface that offers it, because it is the one honesty
				difference between this and "Name everything": coverage becomes
				certain and purity stops being a measurement (docs/22 §22.8).
			-->
			<p class="note faint">
				Every type gets its own knot, so type coverage will read 100 % — by
				construction, not as a finding. Cluster purity stops measuring the map for
				the same reason; what still measures it is whether a live sound's nearest
				knot is its own type.
			</p>
		{/if}
		{#if buildClustering === 'hdbscan'}
			<label class="field">
				<span class="lbl">
					Smallest type <b class="mono">{buildMinCluster}</b>
				</span>
				<input
					type="range"
					min="5"
					max="200"
					step="5"
					bind:value={buildMinCluster}
					title="Fewest points that may be called a syllable type. Lower finds more, smaller groups and calls less of the corpus noise."
				/>
			</label>
		{/if}
		<details class="diag">
			<summary
				class="note faint"
				title="For reading a measurement, not for a galaxy to use: leaving a half out of the corpus is how you verify a figure, at the price of a galaxy that is missing it."
			>
				Leave one out (diagnostic)
			</summary>
			<div class="checks">
				<label
					class="check"
					title="Off: build the documented repertoire alone, without the syllables fitted to real recordings."
				>
					<input
						type="checkbox"
						bind:checked={buildUseLearned}
						disabled={!pipelineStatus.learned.exists}
					/> Fitted syllables
				</label>
				<label
					class="check"
					title="Off: build the renders alone. Useful for reading verify:features; the galaxy loses the real repertoire's shape."
				>
					<input type="checkbox" bind:checked={buildIncludeHarvest} /> Harvested audio
				</label>
			</div>
		</details>
		<button
			class="wide"
			disabled={jobRunning || pipelineBusy}
			title="Each learning pass rebuilds when the repertoire has moved on; this only forces it now. Clustering and the projection are computed over the whole corpus at once, so a syllable learned a minute ago has no position until the next build."
			onclick={() =>
				runPipeline(() =>
					pipeline.build({
						useLearned: buildUseLearned,
						includeHarvest: buildIncludeHarvest,
						clustering: buildClustering,
						minClusterSize: buildMinCluster
					})
				)}>Rebuild</button
		>
		{#if pipelineStatus.built.exists}
			<dl class="facts mono">
				<div><dt>points</dt><dd>{pipelineStatus.built.points ?? '—'}</dd></div>
				<div><dt>clusters</dt><dd>{pipelineStatus.built.clusters ?? '—'}</dd></div>
				{#if coverage}
					<div>
						<dt>named</dt>
						<dd class:warn={coverage.share < 0.98}>
							{coverage.withCluster}/{coverage.types}
						</dd>
					</div>
				{/if}
			</dl>
			{#if coverage && coverage.orphans.length}
				<p class="note faint">
					{coverage.orphans.length} type{coverage.orphans.length === 1 ? '' : 's'} with
					no cluster, so nothing lights when they are sung:
					<span class="mono">{coverage.orphans.slice(0, 4).join(', ')}</span
					>{coverage.orphans.length > 4 ? ` +${coverage.orphans.length - 4}` : ''}
				</p>
			{/if}
			{#if relationHeadline}
				<p class="note faint">Geometry: {relationHeadline}</p>
			{/if}
		{/if}
		{#if corpusHealth}
			<dl
				class="facts mono"
				title="Knots that carry a documented function, and knots a syllable can be sung into. A corpus with none of the second draws no threads at all, because nothing resolves to a place."
			>
				<div><dt>documented</dt><dd>{corpusHealth.documented}/{corpusHealth.clusters}</dd></div>
				<div><dt>singable</dt><dd>{corpusHealth.mapped}</dd></div>
			</dl>
			{#if corpusHealth.mapped === 0}
				<p class="note faint">
					<b>No knot in this galaxy is tied to a syllable</b>, so nothing draws a
					thread and nothing lights when a bird sings. A harvest-only build has that
					shape: it is real audio with no documented calls in it. Rebuild with
					<b>synthetic renders</b> — with <b>Harvested</b> still ticked — to get a
					corpus that carries both.
				</p>
			{/if}
		{/if}
		{#if reloading}
			<p class="note faint">Loading the new galaxy…</p>
		{/if}
	</section>

	<hr class="groupsplit" />

	<details class="rollup block">
		<summary class="mono faint">run one step by hand</summary>

	<section class="block">
		<h3 class="blocktitle">Harvest</h3>
		<!--
			The queue policy, said out loud, because it was only ever logged on the server. The
			count lives with "Refine the dataset" above rather than being repeated here: this is
			the form for choosing *which* bird and how deeply, and the ordering only applies when
			no species is chosen.
		-->
		<p class="note faint">
			<b>Emptiest first</b> when no species is chosen: a bird with nothing is served before
			a bird with two thousand, and the order flattens out again once the new ones have
			caught up. Choose a species and it collects for that one only.
		</p>
		{#if !pipelineStatus.hasKey && !harvestFromDir}
			<p class="note faint">
				No <span class="mono">XC_API_KEY</span> in the server's environment. Set one to
				download from xeno-canto, or point at a folder you already have.
			</p>
		{/if}
		<label class="field">
			<span class="lbl">Species</span>
			<select bind:value={harvestSpecies}>
				<option value="">every species the pipeline knows</option>
				{#each harvestOptions as s (s.id)}
					<option value={s.id}>{s.common}</option>
				{/each}
			</select>
		</label>
		<div class="sliders two">
			<label class="field">
				<span class="lbl">Per species <b class="mono">{harvestPerSpecies}</b></span>
				<input type="range" min="1" max="60" step="1" bind:value={harvestPerSpecies} />
			</label>
			<label class="field">
				<span class="lbl">Quality</span>
				<select bind:value={harvestQuality}>
					<option value="A">A only</option>
					<option value="&gt;B">B and better</option>
					<option value="&gt;C">C and better</option>
				</select>
			</label>
		</div>
		<div class="sliders two">
			<label class="field">
				<span class="lbl"
					>Analysed per recording <b class="mono">{harvestMaxSeconds}s</b></span
				>
				<input
					type="range"
					min="15"
					max="300"
					step="15"
					bind:value={harvestMaxSeconds}
				/>
			</label>
			<label class="field">
				<span class="lbl"
					>Store cap <b class="mono">{harvestCap.toLocaleString()}</b> kept</span
				>
				<input
					type="range"
					min="5000"
					max="100000"
					step="5000"
					bind:value={harvestCap}
				/>
			</label>
		</div>
		<label class="field">
			<span class="lbl">Or a local folder</span>
			<input type="text" placeholder="/path/to/recordings" bind:value={harvestFromDir} />
		</label>
		<div class="row">
			<button
				disabled={jobRunning || pipelineBusy}
				onclick={() =>
					runPipeline(() =>
						pipeline.harvest({
							species: harvestSpecies || null,
							perSpecies: harvestPerSpecies,
							quality: harvestQuality,
							cap: harvestCap,
							maxSeconds: harvestMaxSeconds,
							fromDir: harvestFromDir || null,
							dryRun: true
						})
					)}>Dry run</button
			>
			<button
				class="primary"
				disabled={jobRunning || pipelineBusy}
				title="Fetched and analysed one at a time, then deleted unless its licence allows keeping it. Only the measurements go into the store, and no audio is ever shipped."
				onclick={() =>
					runPipeline(() =>
						pipeline.harvest({
							species: harvestSpecies || null,
							perSpecies: harvestPerSpecies,
							quality: harvestQuality,
							cap: harvestCap,
							maxSeconds: harvestMaxSeconds,
							fromDir: harvestFromDir || null
						})
					)}>Harvest</button
			>
		</div>
	</section>

	<section class="block">
		<h3 class="blocktitle">Learn</h3>
		<label class="field">
			<span class="lbl">Fewest types per species <b class="mono">{learnTypes}</b></span>
			<input
				type="range"
				min="2"
				max="24"
				step="1"
				bind:value={learnTypes}
				title="A floor, not the answer. The repertoire size is chosen per species by silhouette over a sweep, so a well-recorded bird gets more types than a thinly recorded one; this is only where that sweep starts."
			/>
		</label>
		<button
			class="wide"
			disabled={jobRunning || pipelineBusy || !pipelineStatus.store.syllables}
			title="Fitted syllables are written next to the documented calls, never instead of them: ids start with L and carry no function."
			onclick={() => runPipeline(() => pipeline.learn({ types: learnTypes }))}
			>Fit syllables and syntax</button
		>
		{#if pipelineStatus.learned.exists}
			<dl
				class="facts mono"
				title="Cosine between each fitted syllable's resynthesis and its type's cluster in the 28-d descriptor space — a clustering match, not an audible-fidelity guarantee: docs/19 measured its correlation with audible distortion at ≈ 0.1. Audible fidelity is measured separately (MCD, on the bench), and is not shown here."
			>
				<div><dt>median cosine</dt><dd>{pipelineStatus.learned.medianCosine ?? '—'}</dd></div>
				<div><dt>worst</dt><dd>{pipelineStatus.learned.worstCosine ?? '—'}</dd></div>
			</dl>
			{#if learnedTotals}
				<details class="rollup">
					<summary class="mono faint"
						>{learnedTotals.species} species · {learnedTotals.types} types fitted</summary
					>
					<div class="fitted">
						{#each pipelineStatus.learned.species ?? [] as sp (sp.id)}
							<div
								class="fit"
								title={sp.bout.length
									? `one sampled bout — a burst of singing, syllables under a second apart: ${sp.bout.join(' ')}`
									: 'no bout sampled'}
							>
								<span class="fit-name">{sp.common}</span>
								<span class="mono faint">{sp.types}t · {sp.states}s</span>
							</div>
						{/each}
					</div>
				</details>
			{/if}
		{:else}
			<p class="note faint">Nothing fitted yet. Harvest some recordings first.</p>
		{/if}
	</section>

	</details>
{/if}
{/snippet}

<style>
	/* The boundary between the page's main actions and the hand versions of the loop's steps.

	   Above it: start learning, refine the dataset, rebuild the galaxy — the three things
	   somebody comes to this page to do. Below it, in a drawer: Harvest and Learn on their own,
	   which are what the loop does per pass and are for driving one step deliberately.

	   A rule and a little air rather than a box or a colour: the two groups are still the
	   same kind of control, and the only claim being made is that one of them is different
	   in kind. A warning tint would say "dangerous", which is wrong — a rebuild is the
	   normal end of a learning run, just not an incremental one. */

	.groupsplit {
		border: 0;
		border-top: 1px solid var(--rule);
		margin: 1.6rem 0 0.2rem;
	}

	/* This page's own arrangement: a fixed-height two-pane layout, which is why it does not
	   share the scrolling-document rules in `styles/layout.css`. The table keeps its own
	   scrollbar because it is a windowed list, and a windowed list inside a scrolling page
	   has two offsets when its row arithmetic is computed from one. */
	.learngrid {
		display: grid;
		gap: 1.2rem 2.6rem;
		grid-template-columns: 1fr;
		min-height: 0;
		flex: 1;
		/* Its own padding rather than `.pagebody`'s, because this one is a fixed-height
		   two-pane layout and that one is a scrolling document; sharing a class would mean
		   one of them fighting the other's grid template. */
		padding: 1.6rem 2.6rem 1.8rem;
	}

	/* The controls beside the table rather than above it, once there is room. The controls
	   keep a column's width because that is what a strip of range sliders is legible at;
	   everything else goes to the table, which is the thing with nine columns. */

	@media (min-width: 66rem) {
		.learngrid {
			grid-template-columns: minmax(0, 22rem) minmax(0, 1fr);
		}
	}

	.learncol {
		display: flex;
		flex-direction: column;
		min-height: 0;
		/* `min-width: 0` is the fix, not a tidy-up: a grid item's default minimum is its
		   content's, so the store path — one unbreakable 52-character string — was widening
		   this column past its own track and having the overflow clipped. Both halves are
		   needed, because the path has no break opportunity for the column to use. */
		min-width: 0;
		overflow-y: auto;
	}

	.learncol :global(.mono),
	.learncol :global(.facts dd),
	.learncol :global(p) {
		overflow-wrap: anywhere;
	}

	.learncol > :global(section.block),
	.learncol > :global(details.block) {
		margin-bottom: 1.2rem;
	}

	/* The table's own column does not scroll — the table does. */

	.tablecol {
		overflow: hidden;
	}

	.tablehead {
		display: flex;
		align-items: baseline;
		justify-content: space-between;
		gap: 1rem;
	}

	.tablehead .blocktitle {
		margin-bottom: 0;
	}

	.follow {
		flex: initial;
		font-size: 0.72rem;
	}

	/* The running job, at the top of the Learn page. It used to report in the right-hand
	   readout panel, where it displaced the reading of whatever was singing. No padding of
	   its own any more: on the page it sits inside a `.block`, which has its own. */

	.loopstatus {
		display: grid;
		gap: 0.6rem;
		align-content: start;
	}

	/* Discovered birds, one row each: the name, what has arrived, and how far it has got
	   as a coloured chip rather than a sentence. The row breathes while the loop is
	   working on that bird, so a live harvest reads as live. */

	.discovered-note {
		margin-top: 0.45rem;
	}

	.discovered {
		margin: 0.3rem 0 0;
		padding: 0;
		list-style: none;
		display: grid;
		gap: 0.15rem;
	}

	.discovered li {
		display: flex;
		align-items: baseline;
		gap: 0.5rem;
		padding: 0.2rem 0.3rem;
		border-radius: 2px;
		border-bottom: 1px dotted var(--rule);
	}

	.disc-chip.fitted {
		color: var(--documented);
		background: color-mix(in srgb, var(--documented) 9%, transparent);
	}

	.discovered li.live {
		animation: disc-breathe 1.6s ease-in-out infinite;
	}

	.fitted {
		display: grid;
		gap: 0.1rem;
		margin-top: 0.3rem;
		padding-left: 0.65rem;
		border-left: 1px solid var(--rule);
	}

	.fit {
		display: flex;
		justify-content: space-between;
		gap: 0.5rem;
		font-size: 0.62rem;
		color: var(--ink-dim);
		cursor: help;
	}

	.fit-name {
		overflow: hidden;
		white-space: nowrap;
		text-overflow: ellipsis;
	}
</style>

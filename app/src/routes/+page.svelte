<script lang="ts">
	import { onMount } from 'svelte';
	import Galaxy from '$lib/galaxy/Galaxy.svelte';
	import {
		buildClusterLookup,
		buildSpeciesIndex,
		clusterIndexFor,
		loadAssets,
		songSyllables,
		speciesById,
		type ClusterLookup
	} from '$lib/data/assets';
	import { BirdyEngine, type ScheduledSyllable } from '$lib/audio/engine';
	import { Listener } from '$lib/audio/listener';
	import { createIndividual } from '$lib/audio/individual';
	import { compilePhrase, improvise, type Phrase } from '$lib/lang/grammar';
	import { citationsFor, confidenceLabel, type Reading } from '$lib/lang/translate';
	import {
		CLAIM_LEGEND,
		COLOUR_MEANING,
		COLOUR_RESPONSE,
		createSignal,
		type VisualSignal
	} from '$lib/galaxy/shaders';
	import { speciesPalette } from '$lib/galaxy/palette';
	import { PipelineClient, type PipelineStatus } from '$lib/data/pipeline';
	import type { BirdyAssets } from '$lib/data/types';

	// $state.raw, not $state: a deep reactive proxy of the corpus cannot be structured-cloned
	// into the AudioWorklet, and there is nothing here that benefits from deep reactivity.
	let assets = $state.raw<BirdyAssets | null>(null);
	let loadError = $state<string | null>(null);
	let engine = $state<BirdyEngine | null>(null);
	let listener = $state<Listener | null>(null);
	// The renderer reads `signal` every frame and mutates it in place, so it must not be a
	// reactive proxy; the meters the UI shows come from the listener's callback instead.
	let signal = $state.raw<VisualSignal>(createSignal(1));
	let reading = $state<Reading | null>(null);
	let audioError = $state<string | null>(null);
	let level = $state(0);
	let pitch = $state(0);
	let strength = $state(0);
	let rateNote = $state<string | null>(null);
	let contextSpecies = $state<string | null>(null);
	let singer = $state<string | null>(null);
	let perPointMeasured = $state(false);

	let tab = $state<'sing' | 'words' | 'listen' | 'learn'>('sing');
	let speciesId = $state('parus_minor');
	let songId = $state('abc_d');
	let text = $state('danger — come here');
	let distance = $state(0.15);
	let volume = $state(0.8);
	let chorus = $state<'off' | 'solo' | 'global'>('off');
	let micOn = $state(false);
	let inputSource = $state<'microphone' | 'system'>('microphone');
	let inputDeviceId = $state('');
	let inputDevices = $state<MediaDeviceInfo[]>([]);
	let recording = $state(false);
	let recordings = $state<{ url: string; name: string }[]>([]);
	let viewOpen = $state(false);
	let pointSize = $state(6);
	let spin = $state(true);
	let showLabels = $state(true);
	let colourMode = $state(COLOUR_RESPONSE);
	let tempo = $state(1);
	let lastPhrase = $state<Phrase | null>(null);
	let nowSinging = $state<ScheduledSyllable[]>([]);
	let voices = $state(0);
	let pinnedCluster = $state(-1);
	let chorusVoices = $state<{ label: string; speciesId: string; at: number }[]>([]);

	const clusters = $derived<ClusterLookup | null>(assets ? buildClusterLookup(assets.centroids) : null);
	const speciesIndex = $derived(assets ? buildSpeciesIndex(assets) : null);
	const species = $derived(assets?.inventory.species ?? []);
	const currentSpecies = $derived(species.find((s) => s.id === speciesId) ?? species[0]);
	// Deterministic, so the bird you audition keeps its voice for the whole session.
	const soloVoice = $derived(
		currentSpecies ? createIndividual(currentSpecies.id, 0, currentSpecies.common) : null
	);
	const songs = $derived(currentSpecies?.songs ?? []);
	const currentSong = $derived(songs.find((s) => s.id === songId) ?? songs[0]);
	/** -1 during a global chorus: every species is equally the subject. */
	const focus = $derived(
		chorus === 'global' ? -1 : (speciesIndex?.get(currentSpecies?.id ?? '') ?? -1)
	);
	/**
	 * Listening distance as a viewing scale. Close is large and near, far is small and
	 * distant, so the slider moves the picture the same way it moves the filters.
	 */
	const spread = $derived(1.35 - 0.8 * distance);

	onMount(() => {
		loadAssets()
			.then((loaded) => {
				assets = loaded;
				signal = createSignal(loaded.centroids.items.length, loaded.points.n);
			})
			.catch((err: unknown) => {
				loadError = err instanceof Error ? err.message : String(err);
			});
		return () => {
			listener?.stop();
			engine?.dispose();
		};
	});

	/** Audio can only start from a user gesture, so the whole audio side begins here. */
	async function enter() {
		if (!assets || engine) return;
		try {
			const created = await BirdyEngine.create(assets);
			await created.resume();
			created.setDistance(distance);
			created.setVolume(volume);
			created.onState = (s) => {
				voices = s.voices;
			};
			// The chorus schedules its own songs, so the picture follows the engine rather
			// than the menus: whatever sings next draws its own trajectory.
			created.onScheduled = ({ speciesId: singing, scheduled, voice }) => {
				singer = voice?.label ?? null;
				noteSinger(singing, voice?.label ?? singing);
				addLive(singing, scheduled, voice?.label ?? '');
				if (chorus !== 'global' && singing !== contextSpecies) {
					contextSpecies = singing;
					showContext(singing);
				}
			};
			const live = new Listener(created, assets);
			live.onReading = (r) => {
				reading = r;
			};
			live.onMeters = (m) => {
				level = m.level;
				pitch = m.f0;
				strength = m.strength;
			};
			live.start();
			signal = live.signal;
			engine = created;
			listener = live;
			perPointMeasured = live.perPointMeasured;
			// The aviary starts full. A silent galaxy gives no reason to believe any of
			// this is live, and the whole-corpus chorus is what the view is built to show.
			setChorus('global');
			if (created.sampleRateMismatch) {
				rateNote = `This browser is running audio at ${Math.round(created.ctx.sampleRate)} Hz, but the corpus was analysed at ${assets.featureSpace.sampleRate} Hz. Matching still works, slightly less precisely.`;
			}
		} catch (err) {
			audioError = err instanceof Error ? err.message : String(err);
		}
	}

	function noteSinger(id: string, label: string) {
		const now = performance.now() / 1000;
		chorusVoices = [...chorusVoices.filter((v) => now - v.at < 6), { label, speciesId: id, at: now }].slice(
			-8
		);
	}

	/** Adds the trajectory a phrase takes through the galaxy, in time with the audio. */
	function addLive(speciesId: string, scheduled: ScheduledSyllable[], label = '') {
		if (!clusters || !listener || !scheduled.length) return;
		listener.addLive(
			scheduled.map((s) => clusterIndexFor(clusters, speciesId, s.syllableId)),
			scheduled.map((s) => ({ start: s.at, end: s.at + s.dur })),
			speciesId,
			label
		);
	}

	/** Every song this species sings, as the faint backdrop behind the selected one. */
	function showContext(speciesId: string) {
		if (!assets || !clusters || !listener) return;
		const species = speciesById(assets.inventory, speciesId);
		if (!species) return;
		listener.setContext(
			species.songs.map((song) => {
				const resolved = songSyllables(species, song.id);
				return resolved
					? resolved.syllables.map((syl) => clusterIndexFor(clusters, speciesId, syl.id))
					: [];
			})
		);
	}

	function sing() {
		if (!engine || !currentSpecies || !currentSong) return;
		nowSinging = engine.playSong(currentSpecies.id, currentSong.id, {
			voice: soloVoice ?? undefined,
			distance
		});
		lastPhrase = {
			speciesId: currentSpecies.id,
			label: currentSong.label,
			gloss: currentSong.gloss,
			function: currentSong.function,
			confidence: currentSong.confidence,
			refs: currentSong.refs,
			syllables: [],
			gaps: [],
			source: 'documented',
			matched: [],
			note: 'Rendered from this species’ documented syllable inventory.'
		};
	}

	function singPhrase(phrase: Phrase | null) {
		if (!engine || !phrase) return;
		lastPhrase = phrase;
		nowSinging = engine.playSequence(phrase.syllables, phrase.gaps, {
			voice: soloVoice ?? undefined,
			distance
		});
		singer = soloVoice?.label ?? null;
		addLive(phrase.speciesId, nowSinging, singer ?? '');
	}

	function singWords() {
		if (!assets) return;
		singPhrase(compilePhrase(assets.inventory, text, { speciesId }));
	}

	function singImprovisation() {
		if (!assets) return;
		singPhrase(improvise(assets.inventory, speciesId));
	}

	async function toggleMic() {
		if (!engine) return;
		audioError = null;
		try {
			if (engine.micActive) {
				engine.stopInput();
				micOn = false;
			} else {
				await engine.startInput(inputSource, inputDeviceId || undefined);
				micOn = true;
				// Device labels are withheld until permission has been granted once, so the
				// list is worth re-reading the moment it has been.
				inputDevices = await BirdyEngine.inputDevices();
			}
		} catch (err) {
			audioError = err instanceof Error ? err.message : String(err);
			micOn = false;
		}
	}

	/** Hands a browser recording to the pipeline, which segments it for learning. */
	async function sendRecording(clip: { url: string; name: string }) {
		await runPipeline(async () => {
			const blob = await (await fetch(clip.url)).blob();
			await pipeline.ingest(blob, speciesId, clip.name);
		});
	}

	async function toggleRecording() {
		if (!engine) return;
		if (engine.recording) {
			const blob = await engine.stopRecording();
			recording = false;
			if (blob) {
				const url = URL.createObjectURL(blob);
				recordings = [...recordings, { url, name: `birdy-${recordings.length + 1}.webm` }];
			}
		} else if (engine.startRecording()) {
			recording = true;
		}
	}

	/**
	 * `solo` keeps the selection: this bird, its backdrop, its highlighted points.
	 * `global` drops all of it — no focus, no context, no preview thread — so the only
	 * thing on screen is every trajectory being drawn as it is actually sung.
	 */
	function setChorus(mode: 'off' | 'solo' | 'global') {
		if (!engine) return;
		chorus = chorus === mode ? 'off' : mode;
		engine.stopAmbient();
		listener?.clearPaths();
		chorusVoices = [];
		if (chorus === 'off') {
			contextSpecies = null;
			refreshSelection();
			return;
		}
		if (chorus === 'global') {
			listener?.setContext([]);
			contextSpecies = null;
			engine.startAmbient(species.map((s) => s.id), 22 * tempo, 2);
		} else if (currentSpecies) {
			contextSpecies = currentSpecies.id;
			showContext(currentSpecies.id);
			engine.startAmbient([currentSpecies.id], 12 * tempo, 3);
		}
	}

	/**
	 * Silence means silence. Killing the voices without dropping the trajectories leaves
	 * their travelling highlights animating through notes that will never sound.
	 */
	function silence() {
		engine?.panic();
		chorus = 'off';
		listener?.clearPaths();
		chorusVoices = [];
		contextSpecies = null;
		refreshSelection();
	}

	/** Redraws the selected call's thread and its species backdrop. */
	function refreshSelection() {
		if (!assets || !currentSpecies || !currentSong || !listener || chorus === 'global') return;
		const resolved = songSyllables(currentSpecies, currentSong.id);
		if (resolved) {
			listener.setPreview(
				resolved.syllables.map((s) => clusterIndexFor(clusters!, currentSpecies.id, s.id)),
				currentSpecies.id,
				currentSong.label
			);
		}
		if (contextSpecies !== currentSpecies.id) {
			contextSpecies = currentSpecies.id;
			showContext(currentSpecies.id);
		}
	}

	/** Clicking a node's tag jumps the selection to whatever that cluster is. */
	function pickCluster(index: number) {
		if (!assets) return;
		pinnedCluster = pinnedCluster === index ? -1 : index;
		const centroid = assets.centroids.items[index];
		if (!centroid) return;
		if (species.some((s) => s.id === centroid.speciesId)) {
			speciesId = centroid.speciesId;
			if (tab === 'listen') tab = 'sing';
		}
	}

	// --- the optional local pipeline control surface ---

	const pipeline = new PipelineClient();
	let pipelineStatus = $state<PipelineStatus | null>(null);
	let pipelineChecked = $state(false);
	let pipelineBusy = $state(false);
	let harvestSpecies = $state<string>('');
	let harvestPerSpecies = $state(10);
	let harvestQuality = $state('A');
	let harvestFromDir = $state('');
	let learnTypes = $state(8);
	let buildUseLearned = $state(true);

	async function refreshPipeline() {
		pipelineStatus = await pipeline.status();
		pipelineChecked = true;
	}

	$effect(() => {
		if (tab !== 'learn') return;
		refreshPipeline();
		// Poll while the tab is open: a harvest run takes minutes and its log is the only
		// honest progress indicator. Cleared as soon as the tab closes.
		const id = setInterval(refreshPipeline, 1500);
		return () => clearInterval(id);
	});

	async function runPipeline(fn: () => Promise<unknown>) {
		pipelineBusy = true;
		audioError = null;
		try {
			await fn();
			await refreshPipeline();
		} catch (err) {
			audioError = err instanceof Error ? err.message : String(err);
		} finally {
			pipelineBusy = false;
		}
	}

	const job = $derived(pipelineStatus?.job ?? null);
	const jobRunning = $derived(job?.state === 'running');

	$effect(() => {
		engine?.setDistance(distance);
	});
	$effect(() => {
		engine?.setVolume(volume);
	});
	$effect(() => {
		// keep the song selection valid when the species changes
		if (currentSpecies && !currentSpecies.songs.some((s) => s.id === songId)) {
			songId = currentSpecies.songs[0]?.id ?? '';
		}
	});
	$effect(() => {
		// a solo chorus follows the selection and the tempo
		const id = currentSpecies?.id;
		const rate = tempo;
		if (chorus === 'solo' && engine && id) engine.startAmbient([id], 12 * rate, 3);
		if (chorus === 'global' && engine) {
			engine.startAmbient(species.map((s) => s.id), 22 * rate, 2);
		}
	});
	$effect(() => {
		listener?.setFocus(focus);
	});
	$effect(() => {
		// selecting a different call redraws its path, so the shape of a phrase is visible
		// before you play it
		void currentSong;
		refreshSelection();
	});

	const preview = $derived(
		assets && text.trim() ? compilePhrase(assets.inventory, text, { speciesId }) : null
	);
	const faithfulness = $derived(
		(assets?.manifest as { faithfulness?: { pearson?: number } } | undefined)?.faithfulness?.pearson
	);
	const pinned = $derived(
		pinnedCluster >= 0 ? (assets?.centroids.items[pinnedCluster] ?? null) : null
	);
	const palette = speciesPalette();
	// The hue of the *selected* bird, which is not the same as the focused one: during a
	// global chorus nothing is focused, but the selection still has a colour in the cloud.
	const speciesColour = $derived.by(() => {
		const slot = speciesIndex?.get(currentSpecies?.id ?? '');
		return slot === undefined ? 'var(--ink-faint)' : palette.hot[slot % palette.hot.length];
	});
</script>

<svelte:head>
	<title>Birdy — what birds have been saying all along</title>
	<meta
		name="description"
		content="Record real birds, match their calls to documented functions, and sing back scientifically grounded synthetic birdsong inside an audio-reactive embedding galaxy."
	/>
</svelte:head>

{#if loadError}
	<div class="centred">
		<div class="card">
			<h1>Birdy needs its galaxy built</h1>
			<p>{loadError}</p>
			<p>
				The 3D map, the cluster centroids and the syrinx calibration table are generated offline by
				the Python pipeline. From the repository root:
			</p>
			<pre class="mono">cd pipeline
uv sync
uv run birdy-pipeline build</pre>
			<p class="faint">That writes <code>app/static/birdy/</code>. Reload afterwards.</p>
		</div>
	</div>
{:else if !assets}
	<div class="centred"><p class="faint mono">loading corpus…</p></div>
{:else}
	<div class="bench">
		<header class="hud">
			<div class="brand">
				<h1>Birdy</h1>
				<p class="strap">syrinx model · documented call functions · no samples</p>
			</div>
			<dl class="readings mono">
				<div><dt>points</dt><dd>{assets.points.n.toLocaleString()}</dd></div>
				<div><dt>clusters</dt><dd>{assets.centroids.k}</dd></div>
				<div><dt>distance r</dt><dd>{faithfulness?.toFixed(3) ?? '—'}</dd></div>
				<div><dt>voices</dt><dd>{voices}</dd></div>
				<div><dt>f0</dt><dd>{pitch > 20 ? Math.round(pitch) : '—'}<span class="unit">Hz</span></dd></div>
				<div class="meter">
					<dt>level</dt>
					<dd><span class="level"><span style:width={`${Math.min(100, level * 100)}%`}></span></span></dd>
				</div>
				<div class="meter">
					<dt>match</dt>
					<dd>
						<span class="level"><span class="hot" style:width={`${strength * 100}%`}></span></span>
					</dd>
				</div>
			</dl>
		</header>

		<div class="stage-wrap">
			<Galaxy
				{assets}
				{signal}
				{pointSize}
				{spin}
				{focus}
				{colourMode}
				{spread}
				speed={tempo}
				labels={showLabels}
				pinned={pinnedCluster}
				onpick={pickCluster}
			/>

			<!-- Display settings belong on the thing they change, not in the tab strip. -->
			<div class="viewctl" class:open={viewOpen}>
				<button
					class="viewbtn"
					aria-label="Display settings"
					aria-expanded={viewOpen}
					onclick={() => (viewOpen = !viewOpen)}
				>
					<svg viewBox="0 0 16 16" width="15" height="15" aria-hidden="true">
						<circle cx="8" cy="8" r="2.4" fill="none" stroke="currentColor" stroke-width="1.3" />
						<path
							d="M8 1.2v2M8 12.8v2M1.2 8h2M12.8 8h2M3.2 3.2l1.4 1.4M11.4 11.4l1.4 1.4M12.8 3.2l-1.4 1.4M4.6 11.4l-1.4 1.4"
							stroke="currentColor"
							stroke-width="1.3"
							stroke-linecap="round"
						/>
					</svg>
				</button>
				{#if viewOpen}
					<div class="viewpanel">
						<h3 class="blocktitle">Colour</h3>
						<div class="segmented">
							<button
								class:on={colourMode === COLOUR_RESPONSE}
								onclick={() => (colourMode = COLOUR_RESPONSE)}>Bird</button
							>
							<button
								class:on={colourMode === COLOUR_MEANING}
								onclick={() => (colourMode = COLOUR_MEANING)}>Meaning</button
							>
						</div>
						<p class="note faint">
							{colourMode === COLOUR_MEANING
								? 'One colour per claim class. Three, because that is how many stay separable.'
								: 'One colour per bird, pale at rest and saturated where the sound lands.'}
						</p>
						<label class="field">
							<span class="lbl">Point size <b class="mono">{pointSize.toFixed(1)}</b></span>
							<input type="range" min="1" max="10" step="0.1" bind:value={pointSize} />
						</label>
						<label class="field">
							<span class="lbl">Tempo <b class="mono">{tempo.toFixed(2)}×</b></span>
							<input type="range" min="0.1" max="2" step="0.05" bind:value={tempo} />
						</label>
						<div class="checks">
							<label class="check"><input type="checkbox" bind:checked={spin} /> Rotate</label>
							<label class="check"><input type="checkbox" bind:checked={showLabels} /> Labels</label>
						</div>
					</div>
				{/if}
			</div>

			{#if colourMode === COLOUR_MEANING}
				<div class="legend">
					<span class="legend-title">how much meaning is claimed</span>
					{#each CLAIM_LEGEND as entry (entry.id)}
						<span class="legend-item">
							<span class="swatch" style:background={entry.hex}></span>
							<b>{entry.label}</b> — {entry.hint}
						</span>
					{/each}
				</div>
			{/if}

			<aside class="readout">
				<h2>Reading</h2>
				{#if reading?.best}
					{@const best = reading.best}
					<div class="best">
						<span class="badge {best.centroid.confidence}">
							{confidenceLabel(best.centroid.confidence).text}
						</span>
						<h3 class="strong">{best.centroid.label}</h3>
						<!--
							Deliberately not showing the singer here: this panel reports what the audio
							was matched to, and the singer is who we scheduled. During a chorus those
							are different claims, and concatenating them reads as "this cluster was
							sung by that bird", which we do not know.
						-->
						<p class="accent">{best.speciesCommon}</p>
						<p class="note">{best.centroid.function}</p>
						<div class="gauge">
							<span class="lbl">urgency</span>
							<span class="level"><span style:width={`${reading.urgency * 100}%`}></span></span>
						</div>
						{#if best.centroid.refs.length}
							<ul class="refs">
								{#each citationsFor(assets.inventory, best.centroid.refs) as ref (ref)}
									<li class="note faint">{ref}</li>
								{/each}
							</ul>
						{/if}
					</div>
					<div class="candidates">
						{#each reading.candidates as candidate (candidate.centroid.id)}
							<div class="candidate">
								<span class="bar"><span style:width={`${candidate.probability * 100}%`}></span></span>
								<span class="note">{candidate.centroid.label}</span>
								<span class="note mono">{(candidate.probability * 100).toFixed(0)}%</span>
							</div>
						{/each}
					</div>
				{:else if lastPhrase}
					<div class="best">
						<span class="badge {lastPhrase.confidence}">
							{confidenceLabel(lastPhrase.confidence).text}
						</span>
						<h3 class="strong">{lastPhrase.label}</h3>
						{#if singer}<p class="accent">sung by {singer}</p>{/if}
						<p class="accent">“{lastPhrase.gloss}”</p>
						<p class="note">{lastPhrase.function}</p>
						<p class="note faint">{lastPhrase.note}</p>
						{#if nowSinging.length}
							<div class="chips">
								{#each nowSinging as item (item.at)}
									<span class="chip">{item.label}</span>
								{/each}
							</div>
						{/if}
						{#if lastPhrase.refs.length}
							<ul class="refs">
								{#each citationsFor(assets.inventory, lastPhrase.refs) as ref (ref)}
									<li class="note faint">{ref}</li>
								{/each}
							</ul>
						{/if}
					</div>
				{:else}
					<p class="note faint">
						Sing something, or turn on the microphone. Clusters flare where the sound lands in
						the corpus — and stay dark when it lands nowhere.
					</p>
				{/if}
				<p class="caveat note">
					{reading?.caveat ??
						'Birdy reports documented call functions with a confidence label. Machine learning can characterise repertoires and link calls to behaviour; it cannot translate them into sentences.'}
				</p>
			</aside>

			<aside class="panel controls">
			<nav class="tabs">
				<button class:active={tab === 'sing'} onclick={() => (tab = 'sing')}>Sing</button>
				<button class:active={tab === 'words'} onclick={() => (tab = 'words')}>Words</button>
				<button class:active={tab === 'listen'} onclick={() => (tab = 'listen')}>Listen</button>
				<button class:active={tab === 'learn'} onclick={() => (tab = 'learn')}>Learn</button>
			</nav>

			<div class="tabbody">
				{#if tab === 'sing'}
					<section class="block">
						<label class="field">
							<span class="lbl">
								Species
								<!-- the hue this bird carries in the galaxy, so the two are connected -->
								<span class="swatch" style:background={speciesColour}></span>
							</span>
							<select bind:value={speciesId}>
								{#each species as s (s.id)}
									<option value={s.id}>{s.common}</option>
								{/each}
							</select>
						</label>
						{#if currentSpecies}
							<p class="note">{currentSpecies.summary}</p>
						{/if}
						<label class="field">
							<span class="lbl">Call or song</span>
							<select bind:value={songId}>
								{#each songs as s (s.id)}
									<option value={s.id}>{s.label} — {s.gloss}</option>
								{/each}
							</select>
						</label>
						<div class="row">
							<button class="primary" disabled={!engine} onclick={sing}>Sing it</button>
							<button disabled={!engine} onclick={singImprovisation}>Improvise</button>
						</div>
					</section>

					<section class="block">
						<h3 class="blocktitle">Chorus</h3>
						<div class="row">
							<button class:on={chorus === 'solo'} disabled={!engine} onclick={() => setChorus('solo')}>
								This bird
							</button>
							<button class:on={chorus === 'global'} disabled={!engine} onclick={() => setChorus('global')}>
								All species
							</button>
							<button disabled={!engine} onclick={silence}>Stop</button>
						</div>
						<p class="note">
							{#if chorus === 'global'}
								Every species at once. The selection is set aside — each bird draws its own
								trajectory as it sings.
							{:else if chorus === 'solo'}
								{currentSpecies?.common} only, three individuals answering each other.
							{:else}
								Held individual voices on a Poisson schedule: each bird keeps its pitch, timing
								and position for as long as it runs.
							{/if}
						</p>
						{#if chorusVoices.length}
							<div class="chips">
								{#each chorusVoices.slice(-6) as v (v.at)}
									<span class="chip">{v.label}</span>
								{/each}
							</div>
						{/if}
					</section>

					<section class="block">
						<div class="sliders">
							<label class="field">
								<span class="lbl">Distance <b class="mono">{distance.toFixed(2)}</b></span>
								<input type="range" min="0" max="1" step="0.01" bind:value={distance} />
							</label>
							<label class="field">
								<span class="lbl">Volume <b class="mono">{volume.toFixed(2)}</b></span>
								<input type="range" min="0" max="1" step="0.01" bind:value={volume} />
							</label>
						</div>
						<p class="note">Distance drives air absorption, reverb and the viewing scale together.</p>
					</section>
				{:else if tab === 'words'}
					<section class="block">
						<label class="field">
							<span class="lbl">Words to sing</span>
							<textarea bind:value={text} placeholder="danger — come here"></textarea>
						</label>
						<label class="field">
							<span class="lbl">Voice</span>
							<select bind:value={speciesId}>
								{#each species as s (s.id)}
									<option value={s.id}>{s.common}</option>
								{/each}
							</select>
						</label>
						{#if preview}
							<div class="callout">
								<span class="badge {preview.confidence}">{confidenceLabel(preview.confidence).text}</span>
								<p class="note">{preview.note}</p>
								{#if preview.source === 'documented'}
									<p class="note">
										Matched <span class="mono">{preview.matched.join(', ')}</span> → {preview.label}
									</p>
								{:else}
									<p class="note faint">{preview.syllables.length} syllables</p>
								{/if}
								{#if preview.documentedElsewhere?.length}
									<p class="note faint">
										A documented call for this exists, but not for this bird:
										{#each preview.documentedElsewhere as other (other)}
											<button class="link" onclick={() => (speciesId = other)}>
												{speciesById(assets.inventory, other)?.common ?? other}
											</button>
										{/each}
									</p>
								{/if}
							</div>
						{/if}
						<button class="primary wide" disabled={!engine || !preview} onclick={singWords}>
							Sing the words
						</button>
						<p class="note faint">
							Only a handful of calls have experimentally established meanings. Anything else is
							rendered through the species' own song syntax and labelled as our invention.
						</p>
					</section>
				{:else if tab === 'listen'}
					<section class="block">
						<h3 class="blocktitle">Input</h3>
						<div class="segmented">
							<button class:on={inputSource === 'microphone'} onclick={() => (inputSource = 'microphone')}>
								Microphone
							</button>
							<button class:on={inputSource === 'system'} onclick={() => (inputSource = 'system')}>
								Computer audio
							</button>
						</div>
						{#if inputSource === 'microphone'}
							<label class="field">
								<span class="lbl">Device</span>
								<select bind:value={inputDeviceId}>
									<option value="">system default</option>
									{#each inputDevices as d (d.deviceId)}
										<option value={d.deviceId}>{d.label || `input ${d.deviceId.slice(0, 6)}`}</option>
									{/each}
								</select>
							</label>
							{#if inputDevices.length && !inputDevices[0].label}
								<p class="note faint">
									Device names appear once you have granted microphone permission once.
								</p>
							{/if}
						{:else}
							<p class="note faint">
								The browser will ask which screen or tab to capture. Tick <b>share audio</b> in
								that dialog, or no sound arrives.
							</p>
						{/if}
						<div class="row">
							<button class:on={micOn} disabled={!engine} onclick={toggleMic}>
								{micOn ? 'Stop input' : 'Start input'}
							</button>
							<button class:on={recording} disabled={!engine || !micOn} onclick={toggleRecording}>
								{recording ? 'Stop recording' : 'Record'}
							</button>
						</div>
						<p class="note">
							Whatever you choose feeds the same analysis path as the synthetic bird: a
							28-dimensional MFCC descriptor every frame, matched to the nearest documented
							cluster. Nothing leaves your device unless you send a recording to the store below.
						</p>
						<p class="note faint">
							The match meter in the header says how well what it hears resembles the corpus.
							Below about 25 % nothing is reported — which is what silence, room tone and hum all
							measure.
						</p>
					</section>

					{#if recordings.length}
						<section class="block">
							<h3 class="blocktitle">Recordings</h3>
							{#each recordings as clip (clip.url)}
								<div class="clip">
									<audio controls src={clip.url}></audio>
									<div class="row">
										<a class="chip" href={clip.url} download={clip.name}>save</a>
										<button
											disabled={!pipelineStatus || jobRunning || pipelineBusy}
											onclick={() => sendRecording(clip)}
										>
											Learn from this
										</button>
									</div>
								</div>
							{/each}
							<p class="note faint">
								{#if pipelineStatus}
									"Learn from this" sends the audio to the local pipeline, which segments it into
									syllables with the same code it uses on downloaded recordings and folds them
									into the learning store. Then fit them in the Learn tab.
								{:else}
									Start <span class="mono">birdy-pipeline serve</span> to send a recording into
									the learning store.
								{/if}
							</p>
						</section>
					{/if}
					{#if pinned}
						<section class="block">
							<h3 class="blocktitle">Pinned cluster</h3>
							<p class="strong">{pinned.label}</p>
							<dl class="facts mono">
								<div><dt>points</dt><dd>{pinned.count}</dd></div>
								{#if pinned.cohesion !== undefined}<div><dt>cohesion</dt><dd>{pinned.cohesion.toFixed(3)}</dd></div>{/if}
								{#if pinned.meanDuration}<div><dt>duration</dt><dd>{Math.round(pinned.meanDuration * 1000)} ms</dd></div>{/if}
								{#if pinned.functionClass}<div><dt>class</dt><dd>{pinned.functionClass}</dd></div>{/if}
							</dl>
							<p class="note">{pinned.function || 'No documented function.'}</p>
							<button onclick={() => (pinnedCluster = -1)}>Unpin</button>
						</section>
					{/if}
				{:else}
					<section class="block">
						<h3 class="blocktitle">Pipeline</h3>
						{#if !pipelineChecked}
							<p class="note faint mono">checking…</p>
						{:else if !pipelineStatus}
							<p class="note">
								Learning runs the offline Python pipeline, so it needs its control process. The
								galaxy itself needs no backend and is unaffected.
							</p>
							<pre class="mono">cd pipeline
uv run birdy-pipeline serve</pre>
							<p class="note faint">
								Binds to 127.0.0.1 only. This tab picks it up within a second or two.
							</p>
							<button onclick={refreshPipeline}>Check again</button>
						{:else}
							<dl class="facts mono">
								<div><dt>store</dt><dd>{pipelineStatus.store.descriptors ?? 0} kept</dd></div>
								<div><dt>seen</dt><dd>{pipelineStatus.store.descriptorsSeen ?? 0}</dd></div>
								<div><dt>syllables</dt><dd>{pipelineStatus.store.syllables ?? 0}</dd></div>
								<div><dt>recordings</dt><dd>{pipelineStatus.store.recordings ?? 0}</dd></div>
							</dl>
							{#if pipelineStatus.store.exists}
								<p class="note faint">
									Sample drift from the full stream: mean
									<b class="mono">{pipelineStatus.store.meanDrift?.toFixed(3)}</b> sd, spread ratio
									<b class="mono">{pipelineStatus.store.stdRatio?.toFixed(3)}</b>. Near 0 and 1 mean
									the retained sample is a faithful miniature of everything discarded.
								</p>
							{/if}
						{/if}
					</section>

					{#if pipelineStatus}
						<section class="block">
							<h3 class="blocktitle">Harvest</h3>
							{#if !pipelineStatus.hasKey && !harvestFromDir}
								<p class="note faint">
									No <span class="mono">XC_API_KEY</span> in the server's environment. Set one to
									download from xeno-canto, or point at a folder you already have.
								</p>
							{/if}
							<label class="field">
								<span class="lbl">Species</span>
								<select bind:value={harvestSpecies}>
									<option value="">every species in the inventory</option>
									{#each pipelineStatus.inventorySpecies as s (s.id)}
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
												fromDir: harvestFromDir || null,
												dryRun: true
											})
										)}>Dry run</button
								>
								<button
									class="primary"
									disabled={jobRunning || pipelineBusy}
									onclick={() =>
										runPipeline(() =>
											pipeline.harvest({
												species: harvestSpecies || null,
												perSpecies: harvestPerSpecies,
												quality: harvestQuality,
												fromDir: harvestFromDir || null
											})
										)}>Harvest</button
								>
							</div>
							<p class="note faint">
								Each recording is fetched, analysed and deleted before the next one starts. Only
								descriptors and syllable measurements are kept.
							</p>
						</section>

						<section class="block">
							<h3 class="blocktitle">Learn</h3>
							<label class="field">
								<span class="lbl">Types per species <b class="mono">{learnTypes}</b></span>
								<input type="range" min="2" max="24" step="1" bind:value={learnTypes} />
							</label>
							<button
								class="wide"
								disabled={jobRunning || pipelineBusy || !pipelineStatus.store.syllables}
								onclick={() => runPipeline(() => pipeline.learn({ types: learnTypes }))}
								>Fit syllables and syntax</button
							>
							{#if pipelineStatus.learned.exists}
								<dl class="facts mono">
									<div><dt>median cosine</dt><dd>{pipelineStatus.learned.medianCosine ?? '—'}</dd></div>
									<div><dt>worst</dt><dd>{pipelineStatus.learned.worstCosine ?? '—'}</dd></div>
								</dl>
								{#each pipelineStatus.learned.species ?? [] as sp (sp.id)}
									<p class="note">
										<b>{sp.common}</b> — {sp.types} types, {sp.states} states
										{#if sp.bout.length}<br /><span class="mono">{sp.bout.join(' ')}</span>{/if}
									</p>
								{/each}
								<p class="note faint">
									Cosine between each fitted syllable's resynthesis and the audio it came from.
									1.0 would mean the syrinx model reproduces the recording exactly.
								</p>
							{:else}
								<p class="note faint">Nothing fitted yet. Harvest some recordings first.</p>
							{/if}
						</section>

						<section class="block">
							<h3 class="blocktitle">Rebuild the galaxy</h3>
							<label class="check">
								<input type="checkbox" bind:checked={buildUseLearned} disabled={!pipelineStatus.learned.exists} />
								Use the learned inventory
							</label>
							<button
								class="wide"
								disabled={jobRunning || pipelineBusy}
								onclick={() =>
									runPipeline(() =>
										pipeline.build({ useLearned: buildUseLearned, includeHarvest: true })
									)}>Rebuild</button
							>
							<p class="note faint">
								The galaxy is computed offline and loaded once, so it does not change while the app
								runs. Rebuilding rewrites the assets; reload the page to see the new clusters.
							</p>
						</section>

						{#if job}
							<section class="block">
								<h3 class="blocktitle">
									{job.name}
									<span class="mono faint">{job.state} · {job.seconds}s</span>
								</h3>
								<pre class="joblog mono">{job.log.slice(-14).join('\n') || '…'}</pre>
								{#if job.error}<p class="error note">{job.error}</p>{/if}
							</section>
						{/if}
					{/if}
				{/if}
			</div>

			{#if rateNote}<p class="note faint pad">{rateNote}</p>{/if}
			{#if audioError}<p class="error note pad">{audioError}</p>{/if}
			</aside>
		</div>
	</div>

	{#if !engine}
		<div class="centred overlay">
			<div class="card">
				<h1>Enter the aviary</h1>
				<p>
					Every note here is synthesised from a physical model of the syrinx — the two-parameter
					oscillator real birds drive with air-sac pressure and syringeal tension. Nothing is
					sampled, nothing is pre-rendered.
				</p>
				<p class="faint">
					Audio needs a click to start. Headphones are a good idea if you plan to use the
					microphone.
				</p>
				<button class="primary" onclick={enter}>Start listening</button>
				{#if audioError}<p class="error">{audioError}</p>{/if}
			</div>
		</div>
	{/if}
{/if}

<style>
	/* A bench, not a page: a rule across the top, an instrument panel down each side and
	   the specimen between them. Fixed rows and columns mean the sidebars get the whole
	   height of the window, which is what stops the controls needing to scroll. */
	/* A rule across the top and the specimen filling everything under it. Both panels
	   float over the stage rather than docking, so the picture is never boxed in. */
	.bench {
		position: absolute;
		inset: 0;
		display: grid;
		grid-template-rows: auto 1fr;
	}

	.hud {
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: 1rem;
		padding: 0.55rem 1rem;
		background: var(--paper-raised);
		border-bottom: 1px solid var(--rule);
		z-index: 4;
	}

	.hud h1 {
		font-size: 0.95rem;
		letter-spacing: 0.02em;
	}

	.strap {
		margin: 0;
		color: var(--ink-faint);
		font-size: 0.66rem;
		letter-spacing: 0.02em;
	}

	/* Every live figure in one strip, labelled, monospaced, tabular — an instrument
	   readout rather than a status bar. */
	.readings {
		display: flex;
		margin: 0;
		font-size: 0.68rem;
	}

	.readings > div {
		display: grid;
		gap: 0.1rem;
		padding: 0 0.75rem;
		border-left: 1px solid var(--rule);
	}

	.readings dt {
		color: var(--ink-faint);
		text-transform: uppercase;
		letter-spacing: 0.08em;
		font-size: 0.56rem;
	}

	.readings dd {
		margin: 0;
		color: var(--ink);
		font-size: 0.8rem;
	}

	.readings .unit {
		color: var(--ink-faint);
		margin-left: 0.15rem;
		font-size: 0.68em;
	}

	.readings .meter dd {
		display: flex;
		align-items: center;
		height: 1.1rem;
	}

	.stage-wrap {
		position: relative;
		overflow: hidden;
	}

	/* --- display settings, on the view itself --- */

	.viewctl {
		position: absolute;
		top: 1rem;
		right: 1rem;
		z-index: 4;
		display: grid;
		justify-items: end;
		gap: 0.4rem;
	}

	.viewbtn {
		display: grid;
		place-items: center;
		width: 2rem;
		height: 2rem;
		padding: 0;
		color: var(--ink-dim);
		box-shadow: 0 1px 6px rgba(15, 23, 42, 0.06);
	}

	.viewctl.open .viewbtn {
		border-color: var(--signal);
		color: var(--signal);
	}

	.viewpanel {
		display: grid;
		gap: 0.6rem;
		width: 15rem;
		padding: 0.8rem 0.85rem;
		background: var(--paper-raised);
		border: 1px solid var(--rule);
		border-radius: var(--radius);
		box-shadow: 0 2px 16px rgba(15, 23, 42, 0.09);
	}

	.level {
		display: block;
		width: 5rem;
		height: 3px;
		background: var(--rule);
		overflow: hidden;
	}

	.level span {
		display: block;
		height: 100%;
		background: var(--ink-dim);
		transition: width 80ms linear;
	}

	.level span.hot {
		background: var(--signal);
	}

	/* --- panels --- */

	/* Sized to its content, capped at the window. `fit-content` is the point: a docked
	   full-height column leaves a slab of empty paper under short tabs, and a fixed
	   height makes long ones overflow. */
	.panel {
		position: absolute;
		z-index: 3;
		display: grid;
		grid-template-rows: auto minmax(0, 1fr);
		height: fit-content;
		max-height: calc(100% - 2rem);
		background: var(--paper-raised);
		border: 1px solid var(--rule);
		border-radius: var(--radius);
		box-shadow: 0 1px 16px rgba(15, 23, 42, 0.07);
		overflow: hidden;
	}

	.controls {
		top: 1rem;
		left: 1rem;
		width: 20rem;
	}

	/* The reading stays a card floating over the specimen rather than a third column:
	   it reports on one moment, and it belongs next to the thing it is reporting on. */
	.readout {
		position: absolute;
		bottom: 1rem;
		right: 1rem;
		z-index: 3;
		width: min(21rem, calc(100% - 2rem));
		max-height: calc(100% - 2rem);
		overflow-y: auto;
		display: grid;
		gap: 0.6rem;
		align-content: start;
		padding: 0.9rem 1rem 0.8rem;
		background: color-mix(in srgb, var(--paper-raised) 94%, transparent);
		border: 1px solid var(--rule);
		border-radius: var(--radius);
		box-shadow: 0 1px 16px rgba(15, 23, 42, 0.06);
	}

	.readout h2 {
		padding: 0 0 0.5rem;
	}

	.readout .best,
	.readout .candidates {
		display: grid;
		gap: 0.4rem;
	}

	.readout .caveat {
		margin: 0;
		padding: 0.6rem 0 0;
	}

	.tabbody {
		min-height: 0;
		overflow-y: auto;
		display: grid;
		align-content: start;
	}

	.tabs {
		display: flex;
		border-bottom: 1px solid var(--rule);
	}

	.tabs button {
		flex: 1;
		padding: 0.6rem 0.3rem;
		font-size: 0.76rem;
		background: none;
		border: none;
		border-bottom: 2px solid transparent;
		border-radius: 0;
		margin-bottom: -1px;
	}

	.tabs button.active {
		color: var(--ink);
		border-bottom-color: var(--signal);
		font-weight: 500;
	}

	/* One rhythm for the whole panel: sections separated by a rule, a single padding
	   value, and a single gap between everything inside them. */
	.block {
		display: grid;
		gap: 0.6rem;
		padding: 0.9rem 1rem;
		border-bottom: 1px solid var(--rule);
		align-content: start;
	}

	.block:last-child {
		border-bottom: none;
	}

	.clip {
		display: grid;
		gap: 0.4rem;
	}

	.clip audio {
		width: 100%;
		height: 2rem;
	}

	a.chip {
		text-decoration: none;
		display: grid;
		place-items: center;
		padding: 0.4rem 0.7rem;
	}

	.blocktitle {
		display: flex;
		justify-content: space-between;
		align-items: baseline;
		gap: 0.5rem;
		font-size: 0.58rem;
		text-transform: uppercase;
		letter-spacing: 0.11em;
		color: var(--ink-faint);
		font-weight: 600;
	}

	h2 {
		font-size: 0.58rem;
		text-transform: uppercase;
		letter-spacing: 0.11em;
		color: var(--ink-faint);
		padding: 0.85rem 1rem 0.6rem;
		border-bottom: 1px solid var(--rule);
	}

	.field {
		display: grid;
		gap: 0.3rem;
	}

	.lbl {
		display: flex;
		justify-content: space-between;
		align-items: baseline;
		gap: 0.5rem;
		font-size: 0.6rem;
		color: var(--ink-faint);
		text-transform: uppercase;
		letter-spacing: 0.08em;
	}

	.lbl b {
		color: var(--ink-dim);
		font-weight: 500;
		text-transform: none;
		letter-spacing: 0;
	}

	.sliders {
		display: grid;
		gap: 0.6rem;
	}

	.sliders.two {
		grid-template-columns: 1fr 1fr;
		gap: 0.6rem 0.75rem;
	}

	.row {
		display: flex;
		gap: 0.4rem;
	}

	.row > button {
		flex: 1;
		white-space: nowrap;
	}

	button.wide {
		width: 100%;
	}

	.segmented {
		display: flex;
	}

	.segmented button {
		flex: 1;
		border-radius: 0;
	}

	.segmented button:first-child {
		border-radius: var(--radius) 0 0 var(--radius);
	}

	.segmented button:last-child {
		border-radius: 0 var(--radius) var(--radius) 0;
		margin-left: -1px;
	}

	.checks {
		display: flex;
		gap: 1rem;
	}

	.check {
		display: flex;
		align-items: center;
		gap: 0.4rem;
		font-size: 0.76rem;
		color: var(--ink-dim);
	}

	.check input {
		width: auto;
	}

	.note {
		margin: 0;
		font-size: 0.74rem;
		line-height: 1.5;
		color: var(--ink-dim);
	}

	.note.pad {
		padding: 0 1rem 0.9rem;
	}

	.faint {
		color: var(--ink-faint);
	}

	.strong {
		margin: 0;
		font-size: 0.95rem;
		color: var(--ink);
	}

	.accent {
		margin: 0;
		font-size: 0.78rem;
		color: var(--signal);
	}

	.callout {
		display: grid;
		gap: 0.35rem;
		padding: 0.6rem 0.7rem;
		border: 1px solid var(--rule);
		border-radius: var(--radius);
		background: var(--paper);
	}

	/* label/value pairs on one baseline, so figures line up down the column */
	.facts {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 0.3rem 0.75rem;
		margin: 0;
		font-size: 0.7rem;
	}

	.facts > div {
		display: flex;
		justify-content: space-between;
		gap: 0.4rem;
		border-bottom: 1px dotted var(--rule);
		padding-bottom: 0.15rem;
	}

	.facts dt {
		color: var(--ink-faint);
	}

	.facts dd {
		margin: 0;
		color: var(--ink);
	}

	pre {
		margin: 0;
		padding: 0.55rem 0.65rem;
		background: var(--paper);
		border: 1px solid var(--rule);
		border-radius: var(--radius);
		overflow-x: auto;
		font-size: 0.7rem;
	}

	.joblog {
		max-height: 12rem;
		overflow: auto;
		white-space: pre-wrap;
		word-break: break-word;
		font-size: 0.64rem;
		line-height: 1.45;
		color: var(--ink-dim);
	}

	.badge {
		justify-self: start;
		font-size: 0.56rem;
		text-transform: uppercase;
		letter-spacing: 0.1em;
		padding: 0.1rem 0.35rem;
		border-radius: 2px;
		border: 1px solid currentColor;
	}

	.badge.experimental { color: var(--experimental); }
	.badge.documented { color: var(--documented); }
	.badge.inferred { color: var(--inferred); }
	.badge.invented { color: var(--invented); }
	.badge.unlabelled { color: var(--unlabelled); }

	.candidate {
		display: grid;
		grid-template-columns: 3rem 1fr auto;
		gap: 0.5rem;
		align-items: center;
	}

	.bar {
		display: block;
		height: 3px;
		background: var(--rule);
		overflow: hidden;
	}

	.bar span {
		display: block;
		height: 100%;
		background: var(--ink-dim);
		transition: width 120ms linear;
	}

	.gauge {
		display: grid;
		gap: 0.2rem;
	}

	.gauge .level {
		width: 100%;
	}

	.chips {
		display: flex;
		flex-wrap: wrap;
		gap: 0.25rem;
	}

	.chip {
		font-size: 0.66rem;
		padding: 0.08rem 0.35rem;
		border-radius: 2px;
		background: var(--paper);
		border: 1px solid var(--rule);
		color: var(--ink-dim);
	}

	.refs {
		margin: 0;
		padding-left: 0.9rem;
		display: grid;
		gap: 0.15rem;
	}

	.caveat {
		padding: 0.7rem 1rem;
		border-top: 1px solid var(--rule);
		color: var(--ink-faint);
		font-size: 0.68rem;
	}

	.error {
		color: #b91c1c;
	}

	button.link {
		display: inline;
		padding: 0;
		margin: 0 0.1rem;
		border: none;
		background: none;
		color: var(--signal);
		text-decoration: underline;
		font-size: inherit;
	}

	/* --- legend --- */

	.legend {
		position: absolute;
		left: 1rem;
		bottom: 1rem;
		display: grid;
		gap: 0.3rem;
		padding: 0.6rem 0.75rem;
		background: color-mix(in srgb, var(--paper-raised) 92%, transparent);
		border: 1px solid var(--rule);
		border-radius: var(--radius);
		max-width: 26rem;
		font-size: 0.7rem;
		color: var(--ink-dim);
	}

	.legend-title {
		font-size: 0.56rem;
		text-transform: uppercase;
		letter-spacing: 0.11em;
		color: var(--ink-faint);
	}

	.legend-item {
		display: flex;
		align-items: baseline;
		gap: 0.4rem;
	}

	.legend-item b {
		color: var(--ink);
		font-weight: 600;
	}

	.swatch {
		flex: none;
		width: 9px;
		height: 9px;
		border-radius: 2px;
		transform: translateY(1px);
	}

	/* --- overlay --- */

	.centred {
		position: absolute;
		inset: 0;
		display: grid;
		place-items: center;
		padding: 1.5rem;
	}

	.overlay {
		background: rgba(250, 251, 252, 0.72);
		backdrop-filter: blur(2px);
		z-index: 6;
	}

	.card {
		max-width: 34rem;
		background: var(--paper-raised);
		border: 1px solid var(--rule);
		border-radius: var(--radius);
		padding: 1.6rem;
		display: grid;
		gap: 0.8rem;
		box-shadow: 0 1px 24px rgba(15, 23, 42, 0.08);
	}

	.card h1 {
		font-size: 1.25rem;
	}

	@media (max-width: 1180px) {
		.readout {
			display: none;
		}
	}

	@media (max-width: 760px) {
		.controls {
			left: 0.6rem;
			right: 0.6rem;
			width: auto;
			max-height: calc(100% - 1.2rem);
		}

		.readings {
			display: none;
		}
	}
</style>

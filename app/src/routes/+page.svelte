<script lang="ts">
	import { onMount } from 'svelte';
	import Galaxy from '$lib/galaxy/Galaxy.svelte';
	import {
		buildClusterLookup,
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
	import { createSignal, type VisualSignal } from '$lib/galaxy/shaders';
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
	let rateNote = $state<string | null>(null);
	let contextSpecies = $state<string | null>(null);
	let singer = $state<string | null>(null);

	let tab = $state<'sing' | 'words' | 'listen'>('sing');
	let speciesId = $state('parus_minor');
	let songId = $state('abc_d');
	let text = $state('danger — come here');
	let distance = $state(0.15);
	let volume = $state(0.8);
	let ambient = $state(false);
	let micOn = $state(false);
	let recording = $state(false);
	let recordings = $state<{ url: string; name: string }[]>([]);
	let pointSize = $state(7);
	let spin = $state(true);
	let lastPhrase = $state<Phrase | null>(null);
	let nowSinging = $state<ScheduledSyllable[]>([]);
	let voices = $state(0);

	const clusters = $derived<ClusterLookup | null>(assets ? buildClusterLookup(assets.centroids) : null);
	const species = $derived(assets?.inventory.species ?? []);
	const currentSpecies = $derived(species.find((s) => s.id === speciesId) ?? species[0]);
	// Deterministic, so the bird you audition keeps its voice for the whole session.
	const soloVoice = $derived(
		currentSpecies ? createIndividual(currentSpecies.id, 0, currentSpecies.common) : null
	);
	const songs = $derived(currentSpecies?.songs ?? []);
	const currentSong = $derived(songs.find((s) => s.id === songId) ?? songs[0]);

	onMount(() => {
		loadAssets()
			.then((loaded) => {
				assets = loaded;
				signal = createSignal(loaded.centroids.items.length);
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
			// The chorus schedules its own songs, so the trajectory follows the engine rather
			// than the menus: whatever sings next redraws the path and its species backdrop.
			created.onScheduled = ({ speciesId: singing, scheduled, voice }) => {
				singer = voice?.label ?? null;
				showPath(singing, scheduled);
				if (singing !== contextSpecies) {
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
			};
			live.start();
			signal = live.signal;
			engine = created;
			listener = live;
			if (created.sampleRateMismatch) {
				rateNote = `This browser is running audio at ${Math.round(created.ctx.sampleRate)} Hz, but the corpus was analysed at ${assets.featureSpace.sampleRate} Hz. Matching still works, slightly less precisely.`;
			}
		} catch (err) {
			audioError = err instanceof Error ? err.message : String(err);
		}
	}

	/** Lights the trajectory the phrase takes through the galaxy, in time with the audio. */
	function showPath(speciesId: string, scheduled: ScheduledSyllable[]) {
		if (!clusters || !listener) return;
		listener.setPath(
			scheduled.map((s) => clusterIndexFor(clusters, speciesId, s.syllableId)),
			scheduled.map((s) => ({ start: s.at, end: s.at + s.dur }))
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

	/** The same trajectory without timing: what a selected-but-unplayed call looks like. */
	function previewPath(speciesId: string, syllableIds: string[]) {
		if (!clusters || !listener) return;
		listener.setPath(syllableIds.map((id) => clusterIndexFor(clusters, speciesId, id)));
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
		showPath(phrase.speciesId, nowSinging);
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
				engine.stopMic();
				micOn = false;
			} else {
				await engine.startMic();
				micOn = true;
			}
		} catch (err) {
			audioError = err instanceof Error ? err.message : String(err);
		}
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

	function toggleAmbient() {
		if (!engine) return;
		ambient = !ambient;
		if (ambient) {
			engine.startAmbient(
				species.map((s) => s.id),
				14
			);
		} else {
			engine.stopAmbient();
		}
	}

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
		// selecting a different call redraws its path, so the shape of a phrase is visible
		// before you play it
		if (!assets || !currentSpecies || !currentSong || !listener) return;
		const resolved = songSyllables(currentSpecies, currentSong.id);
		if (resolved) previewPath(currentSpecies.id, resolved.syllables.map((s) => s.id));
		if (contextSpecies !== currentSpecies.id) {
			contextSpecies = currentSpecies.id;
			showContext(currentSpecies.id);
		}
	});

	const preview = $derived(
		assets && text.trim() ? compilePhrase(assets.inventory, text, { speciesId }) : null
	);
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
	<div class="centred"><p class="faint">Loading the galaxy…</p></div>
{:else}
	<Galaxy {assets} {signal} {pointSize} {spin} />

	<header class="hud">
		<div>
			<h1>Birdy</h1>
			<p class="tagline">
				{assets.points.n.toLocaleString()} calls · {assets.centroids.k} clusters · syrinx voice, no
				samples
			</p>
		</div>
		<div class="meters">
			<span class="mono">{voices} voice{voices === 1 ? '' : 's'}</span>
			<span class="mono">{pitch ? `${Math.round(pitch)} Hz` : '—'}</span>
			<div class="level"><span style:width={`${Math.min(100, level * 100)}%`}></span></div>
		</div>
	</header>

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

	<aside class="panel controls">
		<nav class="tabs">
			<button class:active={tab === 'sing'} onclick={() => (tab = 'sing')}>Sing</button>
			<button class:active={tab === 'words'} onclick={() => (tab = 'words')}>Words</button>
			<button class:active={tab === 'listen'} onclick={() => (tab = 'listen')}>Listen</button>
		</nav>

		{#if tab === 'sing'}
			<label>
				Species
				<select bind:value={speciesId}>
					{#each species as s (s.id)}
						<option value={s.id}>{s.common}</option>
					{/each}
				</select>
			</label>
			{#if currentSpecies}
				<p class="faint small">{currentSpecies.summary}</p>
			{/if}
			<label>
				Call or song
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
			<div class="row">
				<button disabled={!engine} onclick={toggleAmbient}>
					{ambient ? 'Stop chorus' : 'Dawn chorus'}
				</button>
				<button disabled={!engine} onclick={() => engine?.panic()}>Silence</button>
			</div>
			<label>
				Distance <span class="mono">{distance.toFixed(2)}</span>
				<input type="range" min="0" max="1" step="0.01" bind:value={distance} />
			</label>
			<label>
				Volume <span class="mono">{volume.toFixed(2)}</span>
				<input type="range" min="0" max="1" step="0.01" bind:value={volume} />
			</label>
		{:else if tab === 'words'}
			<label>
				Words to sing
				<textarea bind:value={text} placeholder="danger — come here"></textarea>
			</label>
			<label>
				Voice
				<select bind:value={speciesId}>
					{#each species as s (s.id)}
						<option value={s.id}>{s.common}</option>
					{/each}
				</select>
			</label>
			{#if preview}
				<div class="preview">
					<span class="badge {preview.confidence}">{confidenceLabel(preview.confidence).text}</span>
					<p class="small">{preview.note}</p>
					{#if preview.source === 'documented'}
						<p class="small">
							Matched <span class="mono">{preview.matched.join(', ')}</span> → {preview.label}
						</p>
					{:else}
						<p class="small faint">{preview.syllables.length} syllables</p>
					{/if}
				</div>
			{/if}
			<button class="primary" disabled={!engine || !preview} onclick={singWords}>
				Sing the words
			</button>
			<p class="small faint">
				Only a handful of calls have experimentally established meanings. Anything else is rendered
				through the species' own song syntax and labelled as our invention.
			</p>
		{:else}
			<div class="row">
				<button disabled={!engine} onclick={toggleMic}>
					{micOn ? 'Stop mic' : 'Use microphone'}
				</button>
				<button disabled={!engine || !micOn} onclick={toggleRecording}>
					{recording ? 'Stop recording' : 'Record'}
				</button>
			</div>
			<p class="small faint">
				The microphone feeds the same analysis path as the synthetic bird: a 28-dimensional MFCC
				descriptor every frame, matched to the nearest documented cluster. Nothing leaves your
				device.
			</p>
			{#each recordings as clip (clip.url)}
				<div class="row">
					<audio controls src={clip.url}></audio>
					<a href={clip.url} download={clip.name}>save</a>
				</div>
			{/each}
			<label>
				Point size <span class="mono">{pointSize.toFixed(1)}</span>
				<input type="range" min="1" max="8" step="0.1" bind:value={pointSize} />
			</label>
			<label class="checkbox">
				<input type="checkbox" bind:checked={spin} /> Slow rotation
			</label>
		{/if}
		{#if rateNote}<p class="small faint">{rateNote}</p>{/if}
		{#if audioError}<p class="error small">{audioError}</p>{/if}
	</aside>

	<aside class="panel readout">
		<h2>Reading</h2>
		{#if reading?.best}
			{@const best = reading.best}
			<div class="best">
				<span class="badge {best.centroid.confidence}">
					{confidenceLabel(best.centroid.confidence).text}
				</span>
				<h3>{best.centroid.label}</h3>
				<!--
					Deliberately not showing the singer here: this panel reports what the audio was
					matched to, and the singer is who we scheduled. During a chorus those are
					different claims, and concatenating them reads as "this cluster was sung by
					that bird", which we do not know.
				-->
				<p class="species">{best.speciesCommon}</p>
				<p>{best.centroid.function}</p>
				<div class="urgency">
					<span class="small faint">urgency</span>
					<div class="level"><span style:width={`${reading.urgency * 100}%`}></span></div>
				</div>
				{#if best.centroid.refs.length}
					<ul class="refs">
						{#each citationsFor(assets.inventory, best.centroid.refs) as ref (ref)}
							<li class="small faint">{ref}</li>
						{/each}
					</ul>
				{/if}
			</div>
			<div class="candidates">
				{#each reading.candidates as candidate (candidate.centroid.id)}
					<div class="candidate">
						<div class="bar"><span style:width={`${candidate.probability * 100}%`}></span></div>
						<span class="small">{candidate.centroid.label}</span>
						<span class="small mono">{(candidate.probability * 100).toFixed(0)}%</span>
					</div>
				{/each}
			</div>
		{:else if lastPhrase}
			<div class="best">
				<span class="badge {lastPhrase.confidence}">
					{confidenceLabel(lastPhrase.confidence).text}
				</span>
				<h3>{lastPhrase.label}</h3>
				{#if singer}<p class="species">sung by {singer}</p>{/if}
				<p class="gloss">“{lastPhrase.gloss}”</p>
				<p>{lastPhrase.function}</p>
				<p class="small faint">{lastPhrase.note}</p>
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
							<li class="small faint">{ref}</li>
						{/each}
					</ul>
				{/if}
			</div>
		{:else}
			<p class="faint small">
				Sing something, or turn on the microphone. Clusters in the galaxy flare where the sound lands
				in the corpus.
			</p>
		{/if}
		<p class="caveat small">
			{reading?.caveat ??
				'Birdy reports documented call functions with a confidence label. Machine learning can characterise repertoires and link calls to behaviour; it cannot translate them into sentences.'}
		</p>
	</aside>
{/if}

<style>
	.centred {
		position: absolute;
		inset: 0;
		display: grid;
		place-items: center;
		padding: 1.5rem;
	}

	.overlay {
		background: rgba(3, 6, 12, 0.6);
		backdrop-filter: blur(3px);
		z-index: 5;
	}

	.card {
		max-width: 34rem;
		background: var(--panel);
		border: 1px solid var(--panel-border);
		border-radius: 16px;
		padding: 1.75rem;
		backdrop-filter: blur(12px);
		display: grid;
		gap: 0.85rem;
	}

	.card h1 {
		font-size: 1.4rem;
	}

	.card pre {
		margin: 0;
		padding: 0.75rem 0.9rem;
		background: rgba(0, 0, 0, 0.45);
		border-radius: var(--radius);
		overflow-x: auto;
	}

	.hud {
		position: absolute;
		top: 0;
		left: 0;
		right: 0;
		z-index: 3;
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
		gap: 1rem;
		padding: 1.1rem 1.35rem;
		pointer-events: none;
	}

	.hud h1 {
		font-size: 1.35rem;
		letter-spacing: 0.05em;
	}

	.tagline {
		margin: 0.15rem 0 0;
		color: var(--ink-dim);
		font-size: 0.8rem;
	}

	.meters {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		color: var(--ink-dim);
		font-size: 0.78rem;
	}

	.level {
		width: 6rem;
		height: 4px;
		border-radius: 2px;
		background: rgba(255, 255, 255, 0.12);
		overflow: hidden;
	}

	.level span {
		display: block;
		height: 100%;
		background: var(--accent);
		transition: width 80ms linear;
	}

	.panel {
		position: absolute;
		bottom: 1.1rem;
		z-index: 2;
		width: min(23rem, calc(100vw - 2.2rem));
		max-height: min(38rem, calc(100vh - 7rem));
		overflow-y: auto;
		background: var(--panel);
		border: 1px solid var(--panel-border);
		border-radius: 14px;
		padding: 1rem;
		backdrop-filter: blur(14px);
		display: grid;
		gap: 0.7rem;
		align-content: start;
	}

	.controls {
		left: 1.1rem;
	}

	.readout {
		right: 1.1rem;
	}

	.tabs {
		display: flex;
		gap: 0.35rem;
	}

	.tabs button {
		flex: 1;
		padding: 0.35rem 0.5rem;
		font-size: 0.85rem;
	}

	.tabs button.active {
		background: rgba(255, 212, 121, 0.16);
		border-color: rgba(255, 212, 121, 0.4);
		color: var(--accent);
	}

	label {
		display: grid;
		gap: 0.3rem;
		font-size: 0.72rem;
		color: var(--ink-dim);
		text-transform: uppercase;
		letter-spacing: 0.07em;
	}

	label.checkbox {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		text-transform: none;
		letter-spacing: 0;
		font-size: 0.85rem;
	}

	label.checkbox input {
		width: auto;
	}

	.row {
		display: flex;
		gap: 0.5rem;
		align-items: center;
	}

	.row > button {
		flex: 1;
	}

	.row audio {
		flex: 1;
		height: 2rem;
	}

	h2 {
		font-size: 0.72rem;
		text-transform: uppercase;
		letter-spacing: 0.1em;
		color: var(--ink-dim);
	}

	h3 {
		font-size: 1.05rem;
	}

	.best {
		display: grid;
		gap: 0.4rem;
	}

	.best p {
		margin: 0;
	}

	.species,
	.gloss {
		color: var(--accent);
		font-size: 0.85rem;
	}

	.badge {
		justify-self: start;
		font-size: 0.66rem;
		text-transform: uppercase;
		letter-spacing: 0.09em;
		padding: 0.15rem 0.45rem;
		border-radius: 999px;
		border: 1px solid currentColor;
	}

	.badge.experimental {
		color: var(--experimental);
	}

	.badge.documented {
		color: var(--documented);
	}

	.badge.inferred {
		color: var(--inferred);
	}

	.badge.invented {
		color: var(--invented);
	}

	.candidates {
		display: grid;
		gap: 0.3rem;
	}

	.candidate {
		display: grid;
		grid-template-columns: 3.5rem 1fr auto;
		gap: 0.5rem;
		align-items: center;
	}

	.bar {
		height: 4px;
		border-radius: 2px;
		background: rgba(255, 255, 255, 0.1);
		overflow: hidden;
	}

	.bar span {
		display: block;
		height: 100%;
		background: var(--documented);
		transition: width 120ms linear;
	}

	.urgency {
		display: grid;
		gap: 0.2rem;
	}

	.urgency .level {
		width: 100%;
	}

	.chips {
		display: flex;
		flex-wrap: wrap;
		gap: 0.3rem;
	}

	.chip {
		font-size: 0.72rem;
		padding: 0.1rem 0.45rem;
		border-radius: 999px;
		background: rgba(255, 255, 255, 0.08);
		border: 1px solid var(--panel-border);
	}

	.refs {
		margin: 0.2rem 0 0;
		padding-left: 1rem;
		display: grid;
		gap: 0.2rem;
	}

	.caveat {
		border-top: 1px solid var(--panel-border);
		padding-top: 0.6rem;
		color: var(--ink-faint);
		margin: 0;
	}

	.small {
		font-size: 0.78rem;
	}

	.faint {
		color: var(--ink-faint);
	}

	.error {
		color: #ff9c7a;
	}

	.preview {
		display: grid;
		gap: 0.3rem;
		padding: 0.6rem;
		border: 1px solid var(--panel-border);
		border-radius: var(--radius);
		background: rgba(0, 0, 0, 0.25);
	}

	.preview p {
		margin: 0;
	}

	@media (max-width: 900px) {
		.panel {
			position: relative;
			bottom: auto;
			left: auto;
			right: auto;
			width: auto;
			margin: 0 1rem 1rem;
			max-height: none;
		}

		.controls {
			margin-top: 60vh;
		}
	}
</style>

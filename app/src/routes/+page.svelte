<script lang="ts">
	import { onMount, untrack } from 'svelte';
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
		COLOUR_MONO,
		COLOUR_RESPONSE,
		createSignal,
		type VisualSignal
	} from '$lib/galaxy/shaders';
	import { MONO_HOT, speciesPalette } from '$lib/galaxy/palette';
	import type { LayoutId } from '$lib/galaxy/layouts';
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
	// Empty on purpose: the app opens on the whole corpus rather than on one bird, and
	// the camera frames all of it. Choosing a bird is what narrows the view.
	let speciesId = $state('');
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
	// Off by default: with 176 clusters the hues cannot separate them anyway, and the
	// arrangement plus the labels carry identity. Colour is something you turn on to ask
	// a specific question, not the resting state of the picture.
	let coloured = $state(false);
	let tempo = $state(1);
	let lastPhrase = $state<Phrase | null>(null);
	let nowSinging = $state<ScheduledSyllable[]>([]);
	let voices = $state(0);
	let pinnedCluster = $state(-1);
	let layout = $state<LayoutId>('acoustic');

	/**
	 * What has been sung, newest first. The strip along the bottom is the only record of
	 * a chorus: songs come and go faster than anyone can read the reading panel, and
	 * without it there is no way to go back to the one you just heard.
	 */
	interface Sung {
		id: number;
		speciesId: string;
		common: string;
		label: string;
		voice: string;
		nodes: number[];
	}
	let history = $state<Sung[]>([]);
	let selectedSung = $state<number | null>(null);
	let sungCounter = 0;
	/** Enough to overflow any window; the strip clips the rest at the far end. */
	const HISTORY_CAP = 24;

	const clusters = $derived<ClusterLookup | null>(assets ? buildClusterLookup(assets.centroids) : null);
	const speciesIndex = $derived(assets ? buildSpeciesIndex(assets) : null);
	const species = $derived(assets?.inventory.species ?? []);
	const currentSpecies = $derived(species.find((s) => s.id === speciesId) ?? null);
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
	 *
	 * The whole range has moved up twice now, both times for the same reason: below a
	 * certain scale the islands sit on top of each other and the arrangement, though still
	 * correct, is unreadable. A scale that destroys the structure is not a viewing
	 * distance. The bottom of the slider is now roughly where the *top* of it used to be
	 * and the top is double that, so the run is 5.6 to 12.0 where it was originally
	 * 0.9 to 6.0. Anchored at 0.1 rather than 0: the slider's very bottom is a limit
	 * nobody sits at, and pinning the useful end of the scale to it wasted a third of the
	 * travel.
	 */
	const SPREAD_AT_LOW = 6.0;
	const SPREAD_AT_FULL = 12.0;
	const SPREAD_RATE = Math.log(SPREAD_AT_FULL / SPREAD_AT_LOW) / 0.9;
	const spread = $derived(SPREAD_AT_LOW * Math.exp(SPREAD_RATE * (distance - 0.1)));

	/**
	 * One switch, not a list of schemes. The arrangement already says what the grouping
	 * is, so colour only has to say whether to carry it: `Arrange` by meaning and the
	 * hues are the three claim colours, anything else and they are the species hues.
	 * `Monochrome` drops the category entirely and leaves response to value and size,
	 * which twelve indistinguishable species hues were never really adding to.
	 */
	const colourMode = $derived(
		!coloured ? COLOUR_MONO : layout === 'meaning' ? COLOUR_MEANING : COLOUR_RESPONSE
	);

	/**
	 * Choosing a bird ends the whole-aviary chorus, which is the other half of the rule
	 * that starting one clears the bird.
	 *
	 * Without it the two states contradict each other and the contradiction is invisible.
	 * The aviary opens singing, `focus` is deliberately -1 for the duration — during a
	 * global chorus no species is more the subject than any other — so picking a bird
	 * from the list changed the labels and the camera while leaving every point in the
	 * corpus at exactly the same weight. The selection looked ignored, and there was
	 * nothing on screen to say why.
	 */
	let lastSpeciesChoice = $state('');
	$effect(() => {
		const chosen = speciesId;
		if (chosen === lastSpeciesChoice) return;
		lastSpeciesChoice = chosen;
		if (chosen && untrack(() => chorus) === 'global') untrack(() => setChorus('off'));
	});

	/** Cluster ids per species, for framing a whole repertoire at once. */
	const clustersOfSpecies = $derived.by(() => {
		const map = new Map<string, number[]>();
		assets?.centroids.items.forEach((c, i) => {
			const list = map.get(c.speciesId);
			if (list) list.push(i);
			else map.set(c.speciesId, [i]);
		});
		return map;
	});
	const allClusters = $derived(assets ? assets.centroids.items.map((_, i) => i) : []);

	/**
	 * What the camera holds in frame, most specific first: a phrase picked out of the
	 * history, a pinned node, the selected bird's whole repertoire, or — with nothing
	 * selected, which is how the app opens — the entire galaxy.
	 */
	const frameNodes = $derived.by(() => {
		if (selectedSung !== null) {
			const nodes = history.find((h) => h.id === selectedSung)?.nodes;
			if (nodes?.length) return nodes;
		}
		if (pinnedCluster >= 0) return [pinnedCluster];
		if (currentSpecies) return clustersOfSpecies.get(currentSpecies.id) ?? allClusters;
		return allClusters;
	});

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

	/**
	 * Picks up a rebuild without a page reload: new nodes, new birds, new syntax appear
	 * in the running app.
	 *
	 * It is a *reload*, not a live stream, and the difference is the pipeline's, not the
	 * interface's: clustering, the projection and the per-point feature space are all
	 * computed over the whole corpus at once, so a syllable learned at 14:02 does not have
	 * a position until the build that places every other point again. What this does is
	 * remove the manual step between that build finishing and seeing it — the Learn tab
	 * notices the manifest's stamp change and swaps the galaxy under you.
	 *
	 * The engine is rebuilt with it, because the inventory it synthesises from is part of
	 * the same asset set; carrying the old one over would leave the app singing syllables
	 * that no longer have nodes.
	 */
	let galaxyVersion = $state(0);
	let reloading = $state(false);
	async function reloadGalaxy(stamp: string) {
		if (reloading) return;
		reloading = true;
		const wasSinging = chorus;
		const hadMic = micOn;
		try {
			const loaded = await loadAssets(fetch, stamp);
			listener?.stop();
			engine?.dispose();
			listener = null;
			engine = null;
			micOn = false;
			reading = null;
			history = [];
			selectedSung = null;
			pinnedCluster = -1;
			assets = loaded;
			signal = createSignal(loaded.centroids.items.length, loaded.points.n);
			galaxyVersion += 1;
			// Only if audio was already running: `enter` needs a user gesture the first time,
			// and by here there has been one. It restores the whole-corpus chorus itself.
			chorus = 'off';
			if (wasSinging !== 'off' || hadMic) {
				await enter();
				if (wasSinging === 'solo') setChorus('solo');
			}
		} catch (err) {
			loadError = err instanceof Error ? err.message : String(err);
		} finally {
			reloading = false;
		}
	}

	$effect(() => {
		// The pipeline reports the build it has on disk; the assets carry the one in the
		// browser. When they differ, this session is looking at a galaxy that no longer
		// exists.
		const built = pipelineStatus?.built?.builtAt;
		const loaded = assets?.manifest?.builtAt;
		if (built && loaded && built !== loaded && !jobRunning) untrack(() => reloadGalaxy(built));
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
			created.onScheduled = ({ speciesId: singing, songId, scheduled, voice }) => {
				singer = voice?.label ?? null;
				addLive(singing, scheduled, voice?.label ?? '');
				recordSung(singing, songId, scheduled, voice?.label ?? '');
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

	/** Adds a sung phrase to the strip along the bottom. */
	function recordSung(
		id: string,
		songId: string,
		scheduled: ScheduledSyllable[],
		voice: string
	) {
		if (!assets || !clusters || !scheduled.length) return;
		const sp = speciesById(assets.inventory, id);
		history = [
			{
				id: ++sungCounter,
				speciesId: id,
				common: sp?.common ?? id,
				label: sp?.songs.find((s) => s.id === songId)?.label ?? songId,
				voice,
				nodes: scheduled
					.map((s) => clusterIndexFor(clusters!, id, s.syllableId))
					.filter((n) => n >= 0)
			},
			...history
		].slice(0, HISTORY_CAP);
	}

	/**
	 * Selecting a past phrase draws its path as a static thread and focuses its bird, so
	 * you can go back to something you heard go past. Selecting it again, or clicking
	 * empty space in the view, clears it.
	 */
	function selectSung(entry: Sung) {
		if (selectedSung === entry.id) {
			clearSelection();
			return;
		}
		selectedSung = entry.id;
		speciesId = entry.speciesId;
		listener?.setPreview(entry.nodes, entry.speciesId, entry.label);
	}

	function clearSelection() {
		if (selectedSung === null && pinnedCluster < 0) return;
		selectedSung = null;
		pinnedCluster = -1;
		refreshSelection();
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
	/** Every song one bird sings, as paths through the cloud. */
	function songPathsOf(id: string): number[][] {
		if (!assets || !clusters) return [];
		const bird = speciesById(assets.inventory, id);
		if (!bird) return [];
		return bird.songs.map((song) => {
			const resolved = songSyllables(bird, song.id);
			return resolved
				? resolved.syllables.map((syl) => clusterIndexFor(clusters, id, syl.id))
				: [];
		});
	}

	/**
	 * The faint backdrop of songs behind the live ones.
	 *
	 * Passing no bird draws every bird's, rather than nothing. "All birds" is a selection
	 * like any other and should behave like one — the backdrop is how you see which
	 * transitions a repertoire reuses, and at the whole-corpus scale it is how you see
	 * that the aviary has a shape at all. Leaving it empty made the entry that shows the
	 * most look like the entry that shows the least.
	 */
	function showContext(id: string) {
		if (!listener) return;
		if (id) {
			listener.setContext(songPathsOf(id));
			return;
		}
		listener.setContext(species.flatMap((s) => songPathsOf(s.id)));
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
		if (chorus === 'off') {
			contextSpecies = null;
			refreshSelection();
			return;
		}
		if (chorus === 'global') {
			showContext('');
			contextSpecies = null;
			// The whole aviary is the subject, so nothing should still be claiming to be
			// it: clearing the bird also releases the camera back to the entire galaxy,
			// which is the only framing in which a chorus of twelve makes any sense.
			speciesId = '';
			pinnedCluster = -1;
			selectedSung = null;
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
		contextSpecies = null;
		refreshSelection();
	}

	/** Redraws the selected call's thread and its species backdrop. */
	function refreshSelection() {
		// A phrase picked out of the history owns the preview thread until it is cleared.
		if (selectedSung !== null) return;
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

	/** Seconds spent waiting for a control process that is not answering yet. */
	let pipelineWaited = $state(0);
	/** How long the dev server's autostart is given before the tab blames it. */
	const PIPELINE_START_GRACE_S = 12;

	async function refreshPipeline() {
		pipelineStatus = await pipeline.status();
		pipelineChecked = true;
		pipelineWaited = pipelineStatus ? 0 : pipelineWaited + 1.5;
	}

	$effect(() => {
		if (tab !== 'learn') return;
		pipelineWaited = 0;
		refreshPipeline();
		// Poll while the tab is open: a harvest run takes minutes and its log is the only
		// honest progress indicator. It is also what picks up the control process the dev
		// server starts in the background, which takes a few seconds to compile its
		// kernels. Cleared as soon as the tab closes.
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
	const jobRunning = $derived(job?.state === 'running' || job?.state === 'stopping');

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
		// Tempo is one control over the whole aviary: the drift, the pulse, how long each
		// syllable lasts and how often a bird starts. Restarting the scheduler is what
		// applies the new arrival rate.
		const id = currentSpecies?.id;
		const rate = tempo;
		if (engine) engine.tempo = rate;
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
	/** Follows the display switch: a swatch cannot say "this bird is blue" in monochrome. */
	function speciesColourOf(id: string): string {
		const slot = speciesIndex?.get(id);
		if (!coloured) return MONO_HOT;
		return slot === undefined ? 'var(--ink-faint)' : palette.hot[slot % palette.hot.length];
	}
	// The hue of the *selected* bird, which is not the same as the focused one: during a
	// global chorus nothing is focused, but the selection still has a colour in the cloud.
	const speciesColour = $derived(speciesColourOf(currentSpecies?.id ?? ''));
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
			{#key galaxyVersion}
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
				{layout}
				frame={frameNodes}
				onpick={pickCluster}
			/>
			{/key}

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
					<div class="panel viewpanel">
						<h2>Display</h2>
						<div class="cardbody">
							<section class="block">
								<h3 class="blocktitle">Arrange</h3>
								<div class="segmented">
									<button class:on={layout === 'acoustic'} onclick={() => (layout = 'acoustic')}>
										Sound
									</button>
									<button class:on={layout === 'species'} onclick={() => (layout = 'species')}>
										Bird
									</button>
									<button class:on={layout === 'meaning'} onclick={() => (layout = 'meaning')}>
										Meaning
									</button>
								</div>
								<p class="note faint">
									{#if layout === 'acoustic'}
										Points sit where they sound. Distance is acoustic distance.
									{:else if layout === 'species'}
										Regrouped by bird, each keeping its own shape. Watch which species tore
										apart on the way here — those were the ones overlapping acoustically.
									{:else}
										Regrouped by how much meaning is claimed — and the grey island is the
										one to look at: those clusters are real audio of a known bird with no
										documented function of any kind. Position no longer means acoustic
										similarity.
									{/if}
								</p>
							</section>

							<section class="block">
								<h3 class="blocktitle">Colour</h3>
								<div class="segmented">
									<button class:on={!coloured} onclick={() => (coloured = false)}>Monochrome</button>
									<button class:on={coloured} onclick={() => (coloured = true)}>Coloured</button>
								</div>
								<p class="note faint">
									{#if !coloured}
										One ink. Response reads as value and size, and the arrangement carries the
										grouping on its own.
									{:else if layout === 'meaning'}
										A hue per claim of meaning, matching the arrangement.
									{:else}
										A hue per bird. Twelve cannot be told apart by colour alone — the labels
										and the selection are what name them.
									{/if}
								</p>
							</section>

							<section class="block">
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
									<label class="check"
										><input type="checkbox" bind:checked={showLabels} /> Labels</label
									>
								</div>
							</section>
						</div>
					</div>
				{/if}
			</div>

			{#if coloured && colourMode === COLOUR_MEANING}
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

			{#if history.length}
				<!--
					Newest sits against the reading panel and the run extends left, clipping at
					the far end: what just happened is where your eye already is.
				-->
				<div class="history">
					{#each history as entry (entry.id)}
						<button
							class="sung"
							class:on={selectedSung === entry.id}
							style:--accent={speciesColourOf(entry.speciesId)}
							onclick={() => selectSung(entry)}
							title="{entry.common} — {entry.label}{entry.voice ? ` · ${entry.voice}` : ''}"
						>
							<span class="swatch"></span>
							<span class="sung-name">{entry.common}</span>
							<span class="sung-label mono">{entry.label}</span>
						</button>
					{/each}
				</div>
			{/if}

			<aside class="panel readout">
				<h2>
					Reading
					{#if selectedSung !== null || pinnedCluster >= 0}
						<button class="link" onclick={clearSelection}>clear selection</button>
					{/if}
				</h2>
				<div class="cardbody">
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
				</div>
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
								<option value="">all birds</option>
								{#each species as s (s.id)}
									<option value={s.id}>{s.common}</option>
								{/each}
							</select>
						</label>
						<!--
							"All birds" is a place in the list, not an absence of one, so it gets the same
							shape as every other entry: a description, a thing to play, and the transport.
							The old version left the call menu sitting there empty — a control with no
							options, for a selection that has no single call — and put the aviary chorus in
							a separate block that only ever applied to this one case. Folding the chorus in
							as the action of "all birds" makes the panel say the same thing whichever entry
							is chosen, and removes the button that could contradict the selection.
						-->
						{#if currentSpecies}
							<p class="note">{currentSpecies.summary}</p>
							<label class="field">
								<span class="lbl">Call or song</span>
								<select bind:value={songId}>
									{#each songs as s (s.id)}
										<option value={s.id}>{s.label} — {s.gloss}</option>
									{/each}
								</select>
							</label>
							<!--
								Two rows, not four buttons across. Four never fitted the panel and the
								last of them was pushed past its right edge, which is why the chorus
								looked like it did nothing: it was still there, just not clickable.
							-->
							<div class="row">
								<button class="primary" disabled={!engine || !currentSong} onclick={sing}>
									Sing it
								</button>
								<button disabled={!engine} onclick={singImprovisation}>Improvise</button>
							</div>
							<div class="row">
								<button class:on={chorus === 'solo'} disabled={!engine} onclick={() => setChorus('solo')}>
									Chorus
								</button>
								<button disabled={!engine} onclick={silence}>Stop</button>
							</div>
							<p class="note">
								{#if chorus === 'solo'}
									{currentSpecies.common} only, three individuals answering each other. Held on a
									Poisson schedule: each voice keeps its pitch, timing and position for as long
									as it runs.
								{:else}
									<b>Sing it</b> plays the chosen call once. <b>Improvise</b> walks this bird's
									measured grammar. <b>Chorus</b> holds three of them answering each other.
								{/if}
							</p>
						{:else}
							<p class="note">
								The whole corpus, nothing dimmed and the camera holding all of it. Choosing a
								bird narrows the labels to its repertoire and flies to the region its clusters
								occupy.
							</p>
							<div class="row">
								<button
									class="primary"
									class:on={chorus === 'global'}
									disabled={!engine}
									onclick={() => setChorus('global')}
								>
									Chorus
								</button>
								<button disabled={!engine} onclick={silence}>Stop</button>
							</div>
							<p class="note">
								Every species at once, each drawing its own trajectory as it sings. Held on a
								Poisson schedule: each voice keeps its pitch, timing and position for as long as
								it runs.
							</p>
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
						{:else if !pipelineStatus && pipelineWaited < PIPELINE_START_GRACE_S}
							<p class="note">
								Starting the control process… <span class="mono faint"
									>{pipelineWaited.toFixed(0)}s</span
								>
							</p>
							<p class="note faint">
								The dev server launches it in the background; the first start compiles the
								oscillator kernels, which takes a few seconds.
							</p>
						{:else if !pipelineStatus}
							<p class="note">
								Learning runs the offline Python pipeline, so it needs its control process, and
								the dev server could not start one — usually because <span class="mono">uv</span>
								is not on its PATH. Start it yourself and this tab picks it up within a second or
								two. The galaxy itself needs no backend and is unaffected.
							</p>
							<pre class="mono">cd pipeline
uv run birdy-pipeline serve</pre>
							<p class="note faint">Binds to 127.0.0.1 only.</p>
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
							<p class="note faint">
								Fitted types are written next to the documented calls, not instead of them:
								their ids start with <span class="mono">L</span>, they carry no function, and
								every documented call keeps its citation.
							</p>
						</section>

						<section class="block">
							<h3 class="blocktitle">Rebuild the galaxy</h3>
							<label class="check">
								<input type="checkbox" bind:checked={buildUseLearned} disabled={!pipelineStatus.learned.exists} />
								Include the syllables fitted to real recordings
							</label>
							<button
								class="wide"
								disabled={jobRunning || pipelineBusy}
								onclick={() =>
									runPipeline(() =>
										pipeline.build({ useLearned: buildUseLearned, includeHarvest: true })
									)}>Rebuild</button
							>
							{#if pipelineStatus.built.exists}
								<dl class="facts mono">
									<div><dt>points</dt><dd>{pipelineStatus.built.points ?? '—'}</dd></div>
									<div><dt>clusters</dt><dd>{pipelineStatus.built.clusters ?? '—'}</dd></div>
								</dl>
							{/if}
							<p class="note faint">
								{#if reloading}
									Loading the new galaxy…
								{:else}
									A build re-places every point at once — a syllable learned a minute ago has no
									position until then — but you do not have to reload the page for it: when the
									build finishes, this tab notices the new stamp and swaps the galaxy, the
									inventory and the voices under you.
								{/if}
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
								{#if jobRunning}
									<button
										class="wide"
										disabled={job.state === 'stopping'}
										onclick={() => runPipeline(() => pipeline.stop())}
									>
										{job.state === 'stopping' ? 'Stopping…' : 'Stop'}
									</button>
									<p class="note faint">
										{#if job.name === 'build'}
											A build stops between species while it renders, and every sixty-fourth
											clip while it measures. It writes nothing on the way out: half an asset
											set is not a galaxy, so the previous build stays where it is.
										{:else}
											Stops after the recording being analysed, or the species being fitted —
											everything already done is kept, so a stopped harvest is a shorter
											harvest rather than a wasted one.
										{/if}
									</p>
								{/if}
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

	/* Sits in the flow of the button it hangs from, so `.panel`'s absolute positioning and
	   its percentage max-height are undone here — everything else about the shell is
	   shared with the left column. Two classes deep on purpose: `.panel` is declared
	   after this block and would otherwise win. */
	.viewctl .viewpanel {
		position: static;
		width: 16rem;
		max-height: calc(100vh - 8rem);
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
	   it reports on one moment, and it belongs next to the thing it is reporting on.
	   Same shell as the left column, so the two read as one instrument. */
	.readout {
		bottom: 1rem;
		right: 1rem;
		width: min(21rem, calc(100% - 2rem));
		/* Short enough that the display panel, which drops from the button above it, has
		   somewhere to be. The body scrolls, so this costs nothing but the illusion that
		   a long reading has to be read all at once. */
		max-height: min(26rem, calc(100% - 2rem));
	}

	/* The scrolling half of a card, under its header. */
	.cardbody {
		min-height: 0;
		overflow-y: auto;
		display: grid;
		align-content: start;
	}

	.readout .best,
	.readout .candidates {
		display: grid;
		gap: 0.5rem;
		padding: 0.9rem 1rem;
	}

	.readout .best + .candidates {
		border-top: 1px solid var(--rule);
	}

	.readout > .cardbody > .note {
		padding: 0.9rem 1rem;
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
		display: flex;
		justify-content: space-between;
		align-items: baseline;
		gap: 0.5rem;
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
		/* Wrap rather than overflow. `flex: 1` on a nowrap button only distributes space
		   that exists; past three buttons the labels are wider than the panel and the last
		   one leaves the panel entirely, where it is invisible and unclickable. */
		flex-wrap: wrap;
	}

	.row > button {
		flex: 1 1 6.5rem;
		min-width: 0;
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

	/* --- what has been sung --- */

	.history {
		position: absolute;
		bottom: 1rem;
		/* the lane between the two columns: it clips at the left rather than sliding
		   under the controls, and stops before the reading card rather than behind it */
		left: calc(20rem + 2rem);
		right: calc(21rem + 2rem);
		z-index: 2;
		display: flex;
		flex-direction: row-reverse;
		justify-content: flex-start;
		gap: 0.3rem;
		overflow: hidden;
		mask-image: linear-gradient(to right, transparent, #000 3rem);
		pointer-events: none;
	}

	.sung {
		flex: none;
		display: flex;
		align-items: center;
		gap: 0.35rem;
		padding: 0.25rem 0.5rem;
		max-width: 12rem;
		pointer-events: auto;
		background: color-mix(in srgb, var(--paper-raised) 92%, transparent);
		border-color: var(--rule);
	}

	.sung.on {
		border-color: var(--accent);
		background: var(--paper-raised);
	}

	.sung .swatch {
		flex: none;
		width: 7px;
		height: 7px;
		border-radius: 2px;
		background: var(--accent);
	}

	.sung-name {
		font-size: 0.68rem;
		color: var(--ink);
		white-space: nowrap;
	}

	.sung-label {
		font-size: 0.62rem;
		color: var(--ink-faint);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
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

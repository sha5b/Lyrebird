<script lang="ts">
	import { onMount, untrack } from 'svelte';
	import Galaxy from '$lib/galaxy/Galaxy.svelte';
	import FitMonitor from '$lib/galaxy/FitMonitor.svelte';
	import {
		buildClusterLookup,
		buildSpeciesIndex,
		clusterIndexFor,
		loadAssets,
		songSyllables,
		speciesById,
		syllableCoverage,
		type ClusterLookup
	} from '$lib/data/assets';
	import { BirdyEngine, type ScheduledSyllable } from '$lib/audio/engine';
	import { Listener } from '$lib/audio/listener';
	import { createIndividual } from '$lib/audio/individual';
	import { compilePhrase, improvise, type Phrase } from '$lib/lang/grammar';
	import { citationsFor, confidenceLabel, type Reading } from '$lib/lang/translate';
	import { createSignal, type VisualSignal } from '$lib/galaxy/shaders';
	import { ACCENT, MONO_HOT } from '$lib/galaxy/palette';
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
	/**
	 * The last reading that named something, kept on screen for a few seconds after the
	 * sound that produced it has stopped.
	 *
	 * The panel only reports while `strength` is above the floor, which for a syllable is
	 * a tenth of a second — so it filled in and emptied again faster than it could be
	 * read, and during a chorus it was a flicker of text nobody could catch. Holding the
	 * last one is the only way the panel is legible at all.
	 *
	 * It is held, not faked: the moment it stops being live the panel says so, because
	 * "this is what I am hearing" and "this is what I last heard" are different claims
	 * and the whole card is built on not confusing them.
	 */
	let heldReading = $state<Reading | null>(null);
	let holdTimer: ReturnType<typeof setTimeout> | null = null;
	/** Long enough to read a name, a function and a citation without hurrying. */
	const READING_HOLD_MS = 6000;
	function holdReading(r: Reading) {
		heldReading = r;
		if (holdTimer) clearTimeout(holdTimer);
		holdTimer = setTimeout(() => {
			heldReading = null;
			holdTimer = null;
		}, READING_HOLD_MS);
	}
	/** What the panel draws: the live reading if there is one, else the last one. */
	const panelReading = $derived(reading?.best ? reading : heldReading);
	const readingIsLive = $derived(Boolean(reading?.best));
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
	// Particles are marks, not blobs. At 6 the cloud reads as poster paint once the
	// camera holds the whole corpus; 3 keeps thirty thousand of them countable.
	let pointSize = $state(3);
	let spin = $state(true);
	let showLabels = $state(true);
	let tempo = $state(1);
	let lastPhrase = $state<Phrase | null>(null);
	let nowSinging = $state<ScheduledSyllable[]>([]);
	let voices = $state(0);
	let pinnedCluster = $state(-1);
	/**
	 * The aviary opens arranged **by bird**, and choosing one switches to **sound**.
	 *
	 * The two arrangements answer the two questions in the order they get asked. Opening on
	 * the acoustic layout shows a single undifferentiated cloud of thirty thousand marks —
	 * true, and unreadable as a first impression, because nothing in it says the corpus is
	 * twelve birds. Twelve islands says that immediately. Then, once you have picked one,
	 * the question stops being "who is here" and becomes "what does this one sound like,
	 * and what else sounds like it" — which is the acoustic layout and nothing else, since
	 * it is the only arrangement where distance is a measurement rather than a grouping.
	 */
	let layout = $state<LayoutId>('species');
	/**
	 * Set the moment the viewer touches `Arrange`, and never cleared until the page is
	 * reloaded. An automatic rearrangement is a convenience for someone who has not
	 * expressed a preference; the instant they have, it becomes the interface overruling
	 * them, which is worse than never having helped.
	 */
	let layoutPinned = $state(false);
	function chooseLayout(id: LayoutId) {
		// The islands are a property of the arrangement, so a region framed in one of them
		// does not survive into another — the heading you asked for is not on screen any more.
		framedIsland = null;
		layout = id;
		layoutPinned = true;
	}

	/**
	 * The island heading whose region the camera is holding, if any.
	 *
	 * An island heading names the only thing on screen at the scale a viewer navigates by —
	 * a whole bird, or every call that claims the same kind of meaning — and until now it
	 * was the one mark that did nothing when clicked. Reaching that region meant finding the
	 * bird in a dropdown and trusting the island under the cursor was the same one.
	 *
	 * Framing only. It deliberately does **not** select the bird, because selecting one
	 * switches the arrangement to *Sound* (see the effect below) and the islands you just
	 * clicked would dissolve under the camera on its way there. "Take me to this region" and
	 * "make this bird the subject" are different requests and the second one has its own
	 * control.
	 */
	let framedIsland = $state<{ key: string; label: string; members: number[] } | null>(null);

	function pickIsland(group: { key: string; label: string; members: number[] }) {
		// Clicking the heading again releases it, which is the only way back to the whole
		// galaxy without touching a different control.
		if (framedIsland?.key === group.key) {
			framedIsland = null;
			return;
		}
		// A region is a coarser request than a node or a phrase, and those outrank it in
		// `frameNodes` — leaving one set would frame the node and light the heading.
		pinnedCluster = -1;
		selectedSung = null;
		framedIsland = group.members.length ? group : null;
	}

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

	/**
	 * How much of the selected call the galaxy can actually place.
	 *
	 * A syllable only wins a cluster if enough of its renders land together, and on this
	 * corpus many do not — so a call can be perfectly playable and still have no thread, or
	 * a thread that skips half its notes. The cluster lookup returns -1 for those and the
	 * trajectory drops them, which is the honest answer and an invisible one. This is what
	 * makes it visible: a call whose notes are all unplaced should say so, not look like a
	 * renderer that failed.
	 */
	const songCoverage = $derived.by(() => {
		if (!assets || !clusters || !currentSpecies || !currentSong) return null;
		const resolved = songSyllables(currentSpecies, currentSong.id);
		if (!resolved?.syllables.length) return null;
		return syllableCoverage(
			clusters,
			currentSpecies.id,
			resolved.syllables.map((s) => s.id)
		);
	});
	/** The same question for the whole repertoire, which is what a selection lights up. */
	const repertoireCoverage = $derived.by(() => {
		if (!clusters || !currentSpecies) return null;
		return syllableCoverage(
			clusters,
			currentSpecies.id,
			currentSpecies.syllables.map((s) => s.id)
		);
	});
	/**
	 * And for the fitted grammar, which is what `Improvise` walks.
	 *
	 * Worth its own tally rather than being folded into the repertoire's, because it is
	 * the one that got materially worse when unplaced syllables stopped being given a
	 * borrowed position: only 64 of the corpus's 132 fitted types won a cluster, so an
	 * improvisation now typically loses about half its nodes and draws a sparser thread
	 * than the same walk did last week. That is the honest picture rather than a
	 * regression, and it should be legible as one.
	 */
	const grammarCoverage = $derived.by(() => {
		if (!clusters || !currentSpecies) return null;
		const states = Object.keys(currentSpecies.grammar?.transitions ?? {});
		if (!states.length) return null;
		return syllableCoverage(clusters, currentSpecies.id, states);
	});
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
	 * Choosing a bird hands it the chorus, and releasing it hands the chorus back.
	 *
	 * The whole-aviary chorus and a chosen bird contradict each other, and the
	 * contradiction used to be invisible: `focus` is deliberately -1 during a global
	 * chorus — no species is more the subject than any other — so picking a bird changed
	 * the labels and the camera while leaving every point at the same weight, and the
	 * selection looked ignored. The old rule silenced the aviary and left you with a
	 * chosen bird and nothing to hear. Starting *its* chorus instead is the answer to the
	 * same contradiction: the subject changes, the aviary does not go quiet.
	 *
	 * Guarded on the current mode because `setChorus` toggles — calling it with the mode
	 * that is already running is how you stop it, which would make selecting a bird that
	 * is already singing switch it off.
	 */
	let lastSpeciesChoice = $state('');
	$effect(() => {
		const chosen = speciesId;
		if (chosen === lastSpeciesChoice) return;
		lastSpeciesChoice = chosen;
		untrack(() => {
			if (!engine) return;
			if (chosen) {
				if (chorus !== 'solo') setChorus('solo');
				else refreshSelection();
			} else if (chorus === 'solo') {
				setChorus('off');
			}
		});
	});

	// Selecting a bird arranges by sound, releasing it goes back to the twelve islands —
	// unless the arrangement has been chosen by hand, which wins for the rest of the
	// session. Tracks the selection only; the pin is read outside the dependency.
	$effect(() => {
		const chosen = speciesId;
		if (untrack(() => layoutPinned)) return;
		layout = chosen ? 'acoustic' : 'species';
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
	 * history, a pinned node, an island whose heading was clicked, the selected bird's whole
	 * repertoire, or — with nothing selected, which is how the app opens — the entire galaxy.
	 *
	 * The island sits below the node and the phrase because it is the coarsest of the three
	 * and a viewer who has since asked for one knot means that knot.
	 */
	const frameNodes = $derived.by(() => {
		if (selectedSung !== null) {
			const nodes = history.find((h) => h.id === selectedSung)?.nodes;
			if (nodes?.length) return nodes;
		}
		if (pinnedCluster >= 0) return [pinnedCluster];
		if (framedIsland?.members.length) return framedIsland.members;
		if (currentSpecies) return clustersOfSpecies.get(currentSpecies.id) ?? allClusters;
		return allClusters;
	});

	/**
	 * Which bird the running job is working on, read out of its own log.
	 *
	 * Learning is not a progress bar with an unknown interior. The pipeline says what it is
	 * doing line by line — which species it is harvesting, rendering or fitting — and every
	 * one of those lines names a bird the galaxy already draws. Matching the newest mention
	 * against the inventory turns the log into a position, and the corpus can then show the
	 * work happening in the place it is happening.
	 *
	 * Deliberately last-mention-wins over a short window: a line like the per-species
	 * retention summary names several, and the useful answer is the most recent one.
	 */
	const learningSpecies = $derived.by(() => {
		const log = job?.log;
		if (!job || job.state !== 'running' || !log?.length) return '';
		for (let i = log.length - 1; i >= Math.max(0, log.length - 6); i--) {
			const line = log[i];
			const hit = species.find((s) => line.includes(s.id));
			if (hit) return hit.id;
		}
		return '';
	});
	/** Those clusters, for the cloud to pulse while the work is going on. */
	const learningClusters = $derived(
		learningSpecies ? (clustersOfSpecies.get(learningSpecies) ?? []) : []
	);

	/**
	 * One line saying what is happening, in place of fourteen lines of log.
	 *
	 * The last line the pipeline printed is almost always the answer, and the log itself
	 * stays available underneath for when it is not.
	 */
	/**
	 * Whether the fit monitor is welcome. Dismissing it is per-session and deliberate:
	 * a loop can run for an hour and an overlay nobody can close is a worse overlay.
	 * It reappears on the next job, because the next job is a new thing to watch.
	 */
	let fitMonitorOpen = $state(true);
	$effect(() => {
		if (job?.state === 'running') fitMonitorOpen = true;
	});
	/** The `FIT` lines in the current log, so the panel can outlive the job that wrote them. */
	const fitLines = $derived.by(() =>
		(job?.log ?? []).filter((l) => l.trimStart().startsWith('FIT '))
	);

	const jobDoing = $derived.by(() => {
		const log = job?.log;
		if (!log?.length) return '';
		for (let i = log.length - 1; i >= 0; i--) {
			const line = log[i].trim();
			// The per-type `FIT` lines are for the monitor, which draws them. Here they would
			// replace "fitting syllables and syntax" with a row of numbers a hundred times a
			// second, which is less information rather than more.
			if (line && !line.startsWith('FIT ')) return line;
		}
		return '';
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
			// The hold is a timer, and a timer that outlives the component writes state
			// into a page that has gone.
			if (holdTimer) clearTimeout(holdTimer);
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
			// The held reading outlives the live one by design, and a reload is the one moment
			// that is wrong: it names a cluster from a galaxy that no longer exists.
			heldReading = null;
			if (holdTimer) {
				clearTimeout(holdTimer);
				holdTimer = null;
			}
			history = [];
			selectedSung = null;
			pinnedCluster = -1;
			// A rebuild re-places every point, so the cluster ids the framed island held are
			// not the same clusters any more.
			framedIsland = null;
			assets = loaded;
			// A new inventory can drop a species — `--learned-only` does exactly that — and a
			// selection pointing at one that is gone leaves `currentSpecies` null, which reads
			// as "all birds" while the dropdown still shows the missing name.
			if (speciesId && !loaded.inventory.species.some((s) => s.id === speciesId)) {
				speciesId = '';
			}
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
		// **No longer gated on the job being finished, which used to exclude the one case
		// that matters.** `loop` holds a job open for as long as it runs — that is its whole
		// nature — so waiting for the job to end meant every galaxy it grew was invisible
		// until you stopped it, and "learning while the app runs" quietly meant "learning,
		// then reloading the page". The gate was there to avoid reading a half-written asset
		// set, and it is not needed for that: `manifest.json` is written *last* by both
		// `build` and `grow`, so a changed stamp is itself the proof that everything else
		// already landed, and every fetch is pinned to that stamp.
		if (built && loaded && built !== loaded) untrack(() => reloadGalaxy(built));
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
				if (r.best) holdReading(r);
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
		if (selectedSung === null && pinnedCluster < 0 && !framedIsland) return;
		selectedSung = null;
		pinnedCluster = -1;
		framedIsland = null;
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
	 * Transitions below this probability are not drawn.
	 *
	 * A measured first-order grammar is a dense matrix — every type has some chance of
	 * following every other, and drawing all of it is a complete graph, which shows
	 * nothing. The floor keeps the transitions a bird actually uses. It is a display
	 * threshold and it hides real structure, so it is a named constant rather than a
	 * number buried in a loop.
	 */
	const GRAMMAR_FLOOR = 0.08;

	/**
	 * The measured grammar as threads: which fitted type follows which.
	 *
	 * Without this a selected bird had almost nothing joining its knots, and the reason was
	 * not a rendering fault. The authored songs are sequences of *documented* syllables —
	 * `A`, `B`, `C` — while everything `learn` fits is `L00`…`L11`, and the syntax measured
	 * over those lives in `grammar`, which nothing was drawing. So the twelve types this
	 * project actually learned from field audio appeared as unconnected dots while the six
	 * hand-authored calls got all the lines.
	 *
	 * These are two-node threads rather than paths: a first-order grammar is a set of
	 * pairs, and stringing them into a route would assert an order that was never measured.
	 */
	function grammarPathsOf(id: string): number[][] {
		if (!assets || !clusters) return [];
		const bird = speciesById(assets.inventory, id);
		const transitions = bird?.grammar?.transitions;
		if (!transitions) return [];
		const out: number[][] = [];
		for (const [from, nexts] of Object.entries(transitions)) {
			const a = clusterIndexFor(clusters, id, from);
			if (a < 0) continue;
			for (const [to, p] of Object.entries(nexts)) {
				if (to === 'end' || p < GRAMMAR_FLOOR) continue;
				const b = clusterIndexFor(clusters, id, to);
				if (b >= 0 && b !== a) out.push([a, b]);
			}
		}
		return out;
	}

	/**
	 * Everything that touches one node: the songs that pass through it and the measured
	 * transitions into and out of it.
	 *
	 * Clicking a knot asks a narrower question than choosing a bird does — not "where does
	 * this bird live" but "what does *this* sound connect to" — and drawing the bird's
	 * whole backdrop answers the wider one on top of it, which buries the answer in forty
	 * other threads. Restricting the backdrop to the segments that actually touch the
	 * picked node leaves the connection visible on its own.
	 */
	function nodePathsOf(id: string, cluster: number): number[][] {
		const touching = (path: number[]) => path.includes(cluster);
		const songs = songPathsOf(id)
			.map((p) => p.filter((n) => n >= 0))
			.filter((p) => p.length > 1 && touching(p));
		const grammar = grammarPathsOf(id).filter(touching);
		return [...songs, ...grammar];
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
		// A pinned node narrows the backdrop to itself, and it has to be decided *here*
		// rather than at the click, because half a dozen things refresh the context — the
		// chorus starting, the song changing, the selection settling — and any of them
		// would otherwise paint the bird's whole repertoire back over the one node you
		// asked about.
		const pinnedOf = assets?.centroids.items[pinnedCluster];
		if (pinnedCluster >= 0 && pinnedOf && (!id || pinnedOf.speciesId === id)) {
			listener.setContext(nodePathsOf(pinnedOf.speciesId, pinnedCluster));
			return;
		}
		if (id) {
			listener.setContext([...songPathsOf(id), ...grammarPathsOf(id)]);
			return;
		}
		listener.setContext(species.flatMap((s) => [...songPathsOf(s.id), ...grammarPathsOf(s.id)]));
	}

	function sing() {
		if (!engine || !currentSpecies || !currentSong) return;
		nowSinging = engine.playSong(currentSpecies.id, currentSong.id, {
			voice: soloVoice ?? undefined,
			distance
		});
		// Register the phrase as a live path, which is what draws the thread through its
		// knots and runs the bead along it. Without this "Sing it" made a sound and left
		// the galaxy completely static — `singImprovisation` did it and this did not, so
		// improvising drew a trajectory and playing a documented call drew nothing.
		singer = soloVoice?.label ?? null;
		addLive(currentSpecies.id, nowSinging, singer ?? '');
		recordSung(currentSpecies.id, currentSong.id, nowSinging, singer ?? '');
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

	/**
	 * Clicking a node's tag makes that cluster the subject: its bird is selected, its
	 * bird's voice starts, and the backdrop narrows to the threads that touch this one
	 * knot.
	 *
	 * Selecting the species is what hands it the accent and the chorus — that happens in
	 * the effect watching `speciesId`, one tick later — so the context is refreshed here
	 * *and* recomputed there through `showContext`, which now reads the pin. Clicking the
	 * same node again unpins it and the bird's whole repertoire comes back.
	 */
	function pickCluster(index: number) {
		if (!assets) return;
		pinnedCluster = pinnedCluster === index ? -1 : index;
		const centroid = assets.centroids.items[index];
		if (!centroid) return;
		if (species.some((s) => s.id === centroid.speciesId)) {
			speciesId = centroid.speciesId;
			if (tab === 'listen') tab = 'sing';
		}
		showContext(centroid.speciesId);
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
	let buildUseLearned = $state(true);
	let buildIncludeHarvest = $state(true);
	/** Which audio the build renders from; the server has taken this since it existed. */
	let buildSource = $state<'synthetic' | 'local' | 'harvest'>('synthetic');
	/**
	 * How the knots are found. `kmeans` asks "which of these k groups is this sound in"
	 * and answers for every sound; `hdbscan` asks where the dense regions are and leaves
	 * the rest unassigned. Only the second can say "this belongs to none of them", which
	 * is the answer that matters for audio nobody has identified.
	 */
	let buildClustering = $state<'kmeans' | 'hdbscan'>('kmeans');
	let buildMinCluster = $state(25);

	/** Seconds spent waiting for a control process that is not answering yet. */
	let pipelineWaited = $state(0);
	/** How long the dev server's autostart is given before the tab blames it. */
	const PIPELINE_START_GRACE_S = 12;

	async function refreshPipeline() {
		pipelineStatus = await pipeline.status();
		pipelineChecked = true;
		pipelineWaited = pipelineStatus ? 0 : pipelineWaited + 1.5;
	}

	/**
	 * Poll the control process on every tab, quickly on Learn and slowly elsewhere.
	 *
	 * **It used to stop the moment you left the Learn tab, which is the moment you would
	 * leave it.** You start a loop, go back to Sing to listen while it works, and from then
	 * on `pipelineStatus` is frozen at whatever it held when you switched: the effect below
	 * that swaps in a finished build never re-evaluates, so the app cannot notice its own
	 * galaxy has been replaced. The whole point of learning while the app runs is that you
	 * are somewhere else in the app while it happens.
	 *
	 * Slower off the Learn tab because the reason to poll is different. On Learn it is the
	 * job log, which is a progress indicator and wants to move; everywhere else it is one
	 * question — has the build stamp changed — and asking that every six seconds is enough.
	 */
	const POLL_MS = { learn: 1500, elsewhere: 6000 };
	$effect(() => {
		const fast = tab === 'learn';
		if (fast) pipelineWaited = 0;
		refreshPipeline();
		const id = setInterval(refreshPipeline, fast ? POLL_MS.learn : POLL_MS.elsewhere);
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

	/**
	 * One line standing in for eleven paragraphs.
	 *
	 * The fitted repertoire was printed a species at a time, two lines each, and on a
	 * twelve-bird corpus that was more than half of the whole Learn tab — a wall you
	 * scrolled past on the way to every control under it. The totals are what you check
	 * after a fit; the per-species breakdown is what you open when a total looks wrong.
	 */
	/**
	 * Whether the galaxy currently loaded can draw anything at all.
	 *
	 * A build from the harvest alone produces a corpus of real audio in which no cluster
	 * carries a syllable id, so nothing resolves to a knot, so there are no threads and
	 * no travelling beads — and the picture gives no hint why. It looks like the renderer
	 * has failed. Three numbers next to the Rebuild button say plainly which kind of
	 * corpus you asked for and what it can support.
	 */
	const corpusHealth = $derived.by(() => {
		if (!assets || !clusters) return null;
		const items = assets.centroids.items;
		return {
			clusters: items.length,
			documented: items.filter((c) => c.function).length,
			mapped: clusters.bySyllable.size
		};
	});

	const learnedTotals = $derived.by(() => {
		const list = pipelineStatus?.learned.species;
		if (!list?.length) return null;
		return {
			species: list.length,
			types: list.reduce((sum, s) => sum + s.types, 0)
		};
	});

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
	/**
	 * How many clusters carry a syllable name — which is how many the app can respond in.
	 *
	 * Counted from the centroids rather than read from `manifest.typeCoverage`, so it is also
	 * right for an asset set built before that field existed.
	 */
	const namedTypes = $derived(
		assets ? assets.centroids.items.filter((c) => c.syllableId).length : 0
	);
	const pinned = $derived(
		pinnedCluster >= 0 ? (assets?.centroids.items[pinnedCluster] ?? null) : null
	);
	/**
	 * The colour a bird's mark carries, matching exactly what the galaxy would draw for it.
	 *
	 * There are two cases, because the cloud has two: the selected bird wears the accent
	 * and everything else is ink. Deriving both from the same rule is the only way a chip
	 * in the history strip and a knot in the cloud are recognisably the same thing.
	 */
	function speciesColourOf(id: string): string {
		return id && id === currentSpecies?.id ? ACCENT : MONO_HOT;
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
				{spread}
				speed={tempo}
				labels={showLabels}
				pinned={pinnedCluster}
				{layout}
				frame={frameNodes}
				learning={learningClusters}
				onpick={pickCluster}
				onpickisland={pickIsland}
				activeIsland={framedIsland?.key ?? ''}
			/>
			{/key}

			<!--
				The fit, while it happens, over the galaxy it is going to change. On every tab,
				because a loop runs for as long as you let it and you will not be sitting on
				Learn while it does.
			-->
			<FitMonitor
				show={fitMonitorOpen && (jobRunning || fitLines.length > 0)}
				log={job?.log ?? []}
				jobName={job?.name ?? ''}
				doing={jobDoing}
				commonOf={(id) => species.find((s) => s.id === id)?.common ?? id}
				onclose={() => (fitMonitorOpen = false)}
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
					<div class="panel viewpanel">
						<h2>Display</h2>
						<div class="cardbody">
							<section class="block">
								<h3 class="blocktitle">Arrange</h3>
								<div class="segmented">
									<button class:on={layout === 'acoustic'} onclick={() => chooseLayout('acoustic')}>
										Sound
									</button>
									<button class:on={layout === 'species'} onclick={() => chooseLayout('species')}>
										Bird
									</button>
									<button class:on={layout === 'meaning'} onclick={() => chooseLayout('meaning')}>
										Meaning
									</button>
								</div>
								<!--
									One line, because the arrangement is on screen the moment you pick it and
									the panel does not need to describe what you are already looking at. What
									is not visible is whether distance means anything, so that is the line.
								-->
								<p class="note faint">
									{#if layout === 'acoustic'}
										Distance is acoustic distance.
									{:else if layout === 'species'}
										One island per bird. Distance is arrangement, not measurement.
									{:else}
										Grouped by how much meaning is documented; the big island has none.
										Distance is arrangement, not measurement.
									{/if}
									{#if !layoutPinned}
										<br />Following the selection until you pick one here.
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
				{#if panelReading?.best}
					{@const best = panelReading.best}
					<div class="best" class:past={!readingIsLive}>
						<span class="badge {best.centroid.confidence}">
							{confidenceLabel(best.centroid.confidence).text}
						</span>
						{#if !readingIsLive}
							<span class="badge past-badge">last heard</span>
						{/if}
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
							<span class="level"
								><span style:width={`${panelReading.urgency * 100}%`}></span></span
							>
						</div>
						{#if best.centroid.refs.length}
							<ul class="refs">
								{#each citationsFor(assets.inventory, best.centroid.refs) as ref (ref)}
									<li class="note faint">{ref}</li>
								{/each}
							</ul>
						{/if}
					</div>
					<div class="candidates" class:past={!readingIsLive}>
						{#each panelReading.candidates as candidate (candidate.centroid.id)}
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
				{:else if namedTypes === 0}
					<!--
						A galaxy built from field audio alone has no cluster carrying a syllable name,
						and every response in this interface goes through one: the trajectory, the node
						tag, the reported match. So the app sings, the cloud drifts, and nothing else
						happens — which looks exactly like a bug and was reported as one. It is a
						property of the build, and the build now records it, so the panel can say which
						of the two it is instead of leaving a silent picture to be interpreted.
					-->
					<p class="note">
						<strong>This galaxy cannot respond.</strong> It was built from field audio only,
						so not one of its {assets.centroids.k} clusters carries a syllable name — there is
						nothing for a sung phrase to light, label or draw a path through. Rebuild with the
						rendered inventory included (<span class="mono">Learn → build</span>, or
						<span class="mono">--source synthetic --harvest-store …</span>).
					</p>
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
								<!--
									Coverage as a tally rather than a paragraph. It answers "why is so much of
									this bird lit when so little of it sings", which is worth having on screen
									permanently — but as three characters with the explanation on hover, not as
									four lines of prose in a panel that already has too many.
								-->
								{#if repertoireCoverage && repertoireCoverage.placed < repertoireCoverage.total}
									<span
										class="tally mono"
										title="{repertoireCoverage.placed} of this bird's {repertoireCoverage.total} syllables won a cluster. Selecting it lights all of its points, including harvested field audio and fitted types that no note can reach."
									>{repertoireCoverage.placed}/{repertoireCoverage.total}</span>
								{/if}
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
								<span class="lbl">
										Call or song
										{#if songCoverage && songCoverage.placed < songCoverage.total}
											<span
												class="tally mono"
												class:none={songCoverage.placed < 2}
												title="{songCoverage.placed} of this call's {songCoverage.total} syllables have a place in the galaxy. The thread joins those and skips the rest rather than guessing at them; below two there is no thread to draw. It plays either way — the synthesis does not need the galaxy."
											>{songCoverage.placed}/{songCoverage.total}</span>
										{/if}
									</span>
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
							<!--
								What each button does is written on the button, and again on hover. It was
								set out a third time in a paragraph underneath; that paragraph is gone.
							-->
							<div class="row">
								<button
									class="primary"
									disabled={!engine || !currentSong}
									onclick={sing}
									title="Play the chosen call once."
									>Sing it</button
								>
								<button
									disabled={!engine}
									onclick={singImprovisation}
									title={grammarCoverage
										? `Walk this bird's measured grammar — the transitions fitted to its own field recordings. ${grammarCoverage.placed} of its ${grammarCoverage.total} fitted types won a cluster, so the thread shows those and skips the rest.`
										: "Walk this bird's measured grammar — the transitions fitted to its own field recordings."}
								>
									Improvise
									{#if grammarCoverage && grammarCoverage.placed < grammarCoverage.total}
										<span class="tally inline mono" class:none={grammarCoverage.placed < 2}
											>{grammarCoverage.placed}/{grammarCoverage.total}</span
										>
									{/if}
								</button>
							</div>
							<div class="row">
								<button
									class:on={chorus === 'solo'}
									disabled={!engine}
									onclick={() => setChorus('solo')}
									title="Three individuals of this bird answering each other on a Poisson schedule. Each voice holds its pitch, timing and position for as long as it runs."
									>Chorus</button
								>
								<button disabled={!engine} onclick={silence}>Stop</button>
							</div>
						{:else}
							<p class="note">
								The whole corpus, nothing dimmed. Choosing a bird narrows the labels to its
								repertoire and arranges by sound.
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
							<p class="note faint">
								Every species at once, each drawing its own trajectory as it sings.
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
						<p class="note faint">
							Same analysis path as the synthetic bird — a 28-d MFCC descriptor every frame,
							matched to the nearest cluster. Nothing leaves your device. Below about 25 % on
							the match meter nothing is reported, which is what silence and room tone measure.
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
									Segmented into syllables and folded into the learning store; fit them in the
									Learn tab.
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
							<h3 class="blocktitle">Keep learning</h3>
							<div class="row">
								<button
									class="primary"
									class:on={job?.name === 'loop' && jobRunning}
									disabled={pipelineBusy || (jobRunning && job?.name !== 'loop')}
									onclick={() =>
										runPipeline(() =>
											job?.name === 'loop' && jobRunning
												? pipeline.stop()
												: pipeline.loop({ perSpecies: loopPerPass, types: learnTypes })
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
							<p class="note faint">
								Each pass harvests a few recordings, fits what came in, and grows the galaxy
								around what is already there. Runs in the control process, so closing the tab
								does not stop it.
							</p>
						</section>

						<details class="rollup block">
							<summary class="mono faint">run one step by hand</summary>

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
							<p class="note faint">
								Fetched, analysed and deleted one at a time; only measurements are kept.
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
								<dl
									class="facts mono"
									title="Cosine between each fitted syllable's resynthesis and the audio it came from; 1.0 would mean the syrinx model reproduces the recording exactly."
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
														? `sampled bout: ${sp.bout.join(' ')}`
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
							<p class="note faint">
								Written next to the documented calls, never instead of them: ids start with
								<span class="mono">L</span> and carry no function.
							</p>
						</section>

						<section class="block">
							<h3 class="blocktitle">Rebuild the galaxy</h3>
							<div class="segmented">
								<button
									class:on={buildClustering === 'kmeans'}
									onclick={() => (buildClustering = 'kmeans')}
									title="Fit exactly k groups and put every point in one of them.">Fixed k</button
								>
								<button
									class:on={buildClustering === 'hdbscan'}
									onclick={() => (buildClustering = 'hdbscan')}
									title="Find however many dense regions there are, and leave sounds that belong to none of them unassigned. Clusters holding both documented renders and field audio hand the field audio a candidate identity."
									>Density</button
								>
							</div>
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
							<label class="field">
								<span class="lbl">Render from</span>
								<select bind:value={buildSource}>
									<option value="synthetic">synthetic renders</option>
									<option value="local">local audio</option>
									<option value="harvest">harvested audio</option>
								</select>
							</label>
							<div class="checks">
								<label class="check" title="Include the syllables fitted to real recordings.">
									<input
										type="checkbox"
										bind:checked={buildUseLearned}
										disabled={!pipelineStatus.learned.exists}
									/> Fitted
								</label>
								<label class="check" title="Fold the harvested descriptor store into the corpus.">
									<input type="checkbox" bind:checked={buildIncludeHarvest} /> Harvested
								</label>
							</div>
							<button
								class="wide"
								disabled={jobRunning || pipelineBusy}
								onclick={() =>
									runPipeline(() =>
										pipeline.build({
											useLearned: buildUseLearned,
											includeHarvest: buildIncludeHarvest,
											source: buildSource,
											clustering: buildClustering,
											minClusterSize: buildMinCluster
										})
									)}>Rebuild</button
							>
							<!--
								Growing is the cheap half of the same job: new audio is placed in the
								frame the current galaxy already has, so nothing on screen moves and the
								cloud gains marks around what you were looking at. It cannot discover a
								cluster, which is what the drift figures in the job log are for.
							-->
							<button
								class="wide"
								disabled={jobRunning || pipelineBusy || !pipelineStatus.store.syllables}
								onclick={() => runPipeline(() => pipeline.grow({}))}
								title="Add the store's newest audio to the galaxy without rebuilding it. Existing points keep their positions."
								>Grow it instead</button
							>
							{#if pipelineStatus.built.exists}
								<dl class="facts mono">
									<div><dt>points</dt><dd>{pipelineStatus.built.points ?? '—'}</dd></div>
									<div><dt>clusters</dt><dd>{pipelineStatus.built.clusters ?? '—'}</dd></div>
								</dl>
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
							<p
								class="note faint"
								title="Clustering and the projection are computed over the whole corpus at once, so a syllable learned a minute ago has no position until the next build."
							>
								{#if reloading}
									Loading the new galaxy…
								{:else}
									Re-places every point at once, and swaps itself in when it finishes — no
									reload needed.
								{/if}
							</p>
						</section>

						</details>

						{#if job}
							<section class="block">
								<h3 class="blocktitle">
									{job.name}
									<span class="mono faint">{job.state} · {job.seconds}s</span>
								</h3>
								<!--
									One line of what is happening, not fourteen. A running job printed a
									scrolling wall that pushed every control out of the panel, and nearly
									all of it was the same message with a counter on the end. The newest
									line is the answer; the rest is one click away when it is not.
								-->
								<p class="doing mono">{jobDoing || '…'}</p>
								<!--
									A running loop is the one job you watch rather than wait for: it
									harvests, fits and grows for as long as you leave it, and the only
									record of what it learned is what it printed. The tail is live while
									anything is running and folds away when nothing is.
								-->
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
								<details class="loglines">
									<summary class="mono faint">full log · {job.log.length} lines</summary>
									<pre class="joblog mono">{job.log.slice(-200).join('\n') || '…'}</pre>
								</details>
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
											Stops cleanly and writes nothing; the previous build stays where it is.
										{:else}
											Stops after the current item. Everything already done is kept.
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

	/**
	 * One line, clipped, never wrapping. A job's newest message is the status; letting it
	 * wrap to three lines makes the panel jump every time the message changes length,
	 * which is most seconds.
	 */
	.doing {
		margin: 0;
		padding: 0.4rem 0.5rem;
		border-left: 2px solid var(--signal);
		background: var(--paper);
		font-size: 0.66rem;
		line-height: 1.4;
		color: var(--ink);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.loglines summary {
		cursor: pointer;
		font-size: 0.6rem;
		padding: 0.2rem 0;
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

	/* A held reading is drawn back, so "what I am hearing now" and "what I last heard"
	   never look like the same claim. It is still fully readable — that is the point of
	   holding it — just visibly no longer live. */
	.best.past,
	.candidates.past {
		opacity: 0.62;
		transition: opacity 240ms linear;
	}

	.past-badge {
		background: transparent;
		border: 1px solid var(--rule);
		color: var(--ink-faint);
	}

	.swatch {
		flex: none;
		width: 9px;
		height: 9px;
		border-radius: 2px;
		transform: translateY(1px);
	}

	/* How much of something the galaxy can place, as a tally beside its label. Three
	   characters where there used to be a paragraph; the sentence lives in the tooltip. */
	.tally {
		margin-left: auto;
		padding: 0.05rem 0.3rem;
		border: 1px solid var(--rule);
		border-radius: 999px;
		font-size: 0.56rem;
		color: var(--ink-faint);
		cursor: help;
	}

	/* Nothing to draw at all is a different fact from drawing part of it, and the one
	   case a viewer is likely to read as a fault. */
	.tally.none {
		border-color: color-mix(in srgb, var(--signal) 45%, var(--rule));
		color: var(--signal);
	}

	/* Sitting inside a button rather than at the end of a label row, where the auto
	   margin would shove it against the far edge. */
	.tally.inline {
		margin-left: 0.3rem;
		cursor: inherit;
	}

	/* A summary line with the detail folded behind it. The totals are what you check
	   after a fit; the per-species breakdown is what you open when a total looks wrong,
	   and printing it always was more than half the Learn tab. */
	.rollup > summary {
		font-size: 0.6rem;
		cursor: pointer;
		list-style: none;
	}

	/* The manual steps folded behind one line: they are the same cycle the switch above
	   runs, done by hand, and they should not be the first thing the tab shows. */
	.rollup.block > summary {
		text-transform: uppercase;
		letter-spacing: 0.09em;
	}

	/* The live tail of a running job. Fixed height so a chatty pass cannot push the
	   controls out of the panel, which is what the full log used to do. */
	.stream {
		margin: 0.35rem 0 0;
		padding: 0.4rem 0.5rem;
		max-height: 11rem;
		overflow-y: auto;
		background: var(--paper);
		border: 1px solid var(--rule);
		border-radius: var(--radius);
		font-size: 0.58rem;
		line-height: 1.45;
		color: var(--ink-dim);
		white-space: pre-wrap;
		word-break: break-word;
	}

	.rollup > summary::before {
		content: '▸ ';
	}

	.rollup[open] > summary::before {
		content: '▾ ';
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

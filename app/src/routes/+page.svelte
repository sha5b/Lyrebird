<script lang="ts">
	import { onMount, untrack } from 'svelte';
	import Galaxy from '$lib/galaxy/Galaxy.svelte';
	import SpeciesPicker from '$lib/SpeciesPicker.svelte';
	import {
		buildClusterLookup,
		buildSpeciesIndex,
		buildSyllablePointIndex,
		CLASS_COUNT,
		PROVENANCE,
		clusterIndexFor,
		detectGalaxyMaps,
		loadAssets,
		pointProvenance,
		songSyllables,
		speciesById,
		syllableCoverage,
		type ClusterLookup,
		type GalaxyMap
	} from '$lib/data/assets';
	import { BirdyEngine, type ScheduledSyllable } from '$lib/audio/engine';
	import { Listener } from '$lib/audio/listener';
	import { createIndividual } from '$lib/audio/individual';
	import { compilePhrase, improvise, type Phrase } from '$lib/lang/grammar';
	import {
		applyTextRhythm,
		chunkCompletions,
		expandSongType,
		nextOptions,
		tokensToPhrase,
		type Provenance,
		type Token
	} from '$lib/lang/compose';
	import { citationsFor, confidenceLabel, type Reading } from '$lib/lang/translate';
	import { createSignal, type VisualSignal } from '$lib/galaxy/shaders';
	import {
		MONO_HOT,
		PROV_NAMES,
		provenanceColour,
		speciesColour as speciesHue
	} from '$lib/galaxy/palette';
	import { PipelineClient, type PipelineStatus } from '$lib/data/pipeline';
	import type { BirdyAssets, SongType, Species, SpeciesRelation } from '$lib/data/types';

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
	/** The docs/20 session gate's live state, null when the assets ship no gate. */
	let sessionGate = $state<{ flagged: boolean; score: number; threshold: number } | null>(
		null
	);
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
	// The composer (Compose tab): one chip strip, three ways to fill it. `tokens` is the
	// sequence being edited; `provenance` is why it holds what it holds, which is what
	// decides the honesty label `tokensToPhrase` writes — so every edit path updates it.
	let composeMode = $state<'free' | 'guided' | 'types'>('guided');
	let composeTokens = $state<Token[]>([]);
	let composeProvenance = $state<Provenance>({ kind: 'guided' });
	let distance = $state(0.15);
	// Well above the old 0.8 ceiling: see the limiter note on the slider. Nothing in the
	// synthesis path ever reaches full scale on its own, so unity was quiet rather than loud.
	let volume = $state(1.5);
	let chorus = $state<'off' | 'solo' | 'global'>('off');
	let micOn = $state(false);
	let inputSource = $state<'microphone' | 'system'>('microphone');
	let inputDeviceId = $state('');
	let inputDevices = $state<MediaDeviceInfo[]>([]);
	let recording = $state(false);
	let recordings = $state<{ url: string; name: string }[]>([]);
	let viewOpen = $state(false);
	let helpOpen = $state(false);
	/**
	 * The known/unknown map switcher. `mapsAvailable` is probed once at startup: a
	 * `--clustering both` build ships `known/` and `unknown/` next to the root asset set,
	 * and only then does the corner stack gain the toggle. `mapDir` records which map the
	 * running galaxy was loaded from ('' = the root build); `mapKind` below is what the
	 * loaded manifest itself says it is, so the toggle can never disagree with the picture.
	 */
	let mapsAvailable = $state(false);
	let mapDir = $state<'' | GalaxyMap>('');
	// Particles are marks, not blobs. At 6 the cloud reads as poster paint once the
	// camera holds the whole corpus; 3 keeps thirty thousand of them countable.
	let pointSize = $state(3);
	let spin = $state(true);
	let showLabels = $state(true);
	// Off means every point is neutral grey; on tints each point by where its sound
	// comes from (the provenance classes the note below names). Default off: the
	// corpus is one cloud first, and the class tint is a layer you ask for.
	/**
	 * The points' colour language: neutral ink, the species hue the labels already
	 * speak ("who"), or the provenance classes ("what kind of thing"). The tags and
	 * threads only move between bird-hue and provenance (a third language would sit
	 * on screen at the same time as the points' own, and two hue readings of one
	 * stage invite confusion) — so 'bird' is a points-only switch into the labels'
	 * existing language.
	 */
	let pointColour = $state<'ink' | 'bird' | 'prov'>('ink');
	const provColours = $derived(pointColour === 'prov');
	/**
	 * Per-class point visibility in PROVENANCE order (documented, learned, field,
	 * unlabelled, candidate). The arrivals live view is the two-class isolate —
	 * "only the unidentified": everything a bird never made, gone from the picture.
	 * Hiding removes points from the picture, never from the corpus.
	 */
	let provShown = $state<boolean[]>([true, true, true, true, true]);
	/**
	 * Which songs the chorus may draw from, in the same provenance vocabulary the
	 * points speak: documented (a person named it — literature or playback-verified),
	 * synthesized (our own mapping, inferred or composed), recorded (real audio with
	 * nothing documented attached). All on is the behaviour before the filter
	 * existed; turning a class off re-pools the chorus on the next effect run, and
	 * songs already playing finish.
	 */
	let chorusClasses = $state<Record<string, boolean>>({
		documented: true,
		synthesized: true,
		recorded: true
	});
	/**
	 * The song-confidence values each provenance word covers. Songs carry
	 * confidence, points carry provenance — two axes that answer "why should I
	 * believe this sound" with one vocabulary, mapped here once rather than at
	 * every use.
	 */
	const CHORUS_CLASS_CONFIDENCE: Record<string, string[]> = {
		documented: ['documented', 'experimental'],
		synthesized: ['inferred', 'invented'],
		recorded: ['unlabelled']
	};
	let tempo = $state(1);
	// How often the chorus starts a song, as a multiplier on its Poisson rate. Read by
	// the scheduler per gap, so the slider retunes the next pause live (engine.songRate).
	let songRate = $state(1);
	let lastPhrase = $state<Phrase | null>(null);
	let nowSinging = $state<ScheduledSyllable[]>([]);
	let voices = $state(0);
	let pinnedCluster = $state(-1);

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
	// The pickers' species list: id + common + counts from the inventory index, complete
	// from startup. Full entries (syllables, songs, grammar) live behind loadSpecies.
	const species = $derived(assets?.inventoryIndex ?? []);
	/**
	 * The selected bird's full entry, fetched as a shard on demand rather than parsed
	 * out of a whole-corpus inventory up front. State rather than a derivation of
	 * `speciesId`: the fetch is async, and a stale resolution (two quick switches) is
	 * dropped rather than shown.
	 */
	let currentSpecies = $state<Species | null>(null);
	$effect(() => {
		const id = speciesId;
		const loaded = assets;
		if (!loaded || !id) {
			currentSpecies = null;
			return;
		}
		let stale = false;
		loaded.loadSpecies(id).then((sp) => {
			if (!stale) currentSpecies = sp ?? null;
		});
		return () => {
			stale = true;
		};
	});
	// Deterministic, so the bird you audition keeps its voice for the whole session.
	const soloVoice = $derived(
		currentSpecies ? createIndividual(currentSpecies.id, 0, currentSpecies.common) : null
	);
	const songs = $derived(currentSpecies?.songs ?? []);
	const currentSong = $derived(songs.find((s) => s.id === songId) ?? songs[0]);

	/**
	 * The song tally's tooltip, honest about which repertoire is which. A documented
	 * song (authored syllable ids) can read "0 of 4 placed" while the bird visibly
	 * owns knots: those knots are its *learned* types, fitted from field audio, and
	 * saying so is the difference between "the galaxy failed" and "this call is from
	 * the other inventory". The clarification only appears in exactly that situation —
	 * every syllable unplaced, the species owning clusters, and the song built from
	 * documented (not learned) ids.
	 */
	const songCoverageHint = $derived.by(() => {
		if (!songCoverage || !currentSpecies || !currentSong) return '';
		const base =
			`${songCoverage.placed} of this call's ${songCoverage.total} syllables have a place in the galaxy. ` +
			'The thread joins those and skips the rest rather than guessing at them; below two there is no thread to draw. ' +
			'It plays either way — the synthesis does not need the galaxy.';
		if (songCoverage.placed > 0) return base;
		const knots = (clustersOfSpecies.get(currentSpecies.id) ?? []).length;
		if (!knots) return base;
		const resolved = songSyllables(currentSpecies, currentSong.id);
		const documented = Boolean(
			resolved?.syllables.length &&
				resolved.syllables.every((s) => !s.id.startsWith('L') && !s.id.startsWith('U'))
		);
		if (!documented) return base;
		return (
			base +
			` This call is from the documented inventory, which won no knot of its own; the bird's ${knots} ` +
			`knot${knots === 1 ? '' : 's'} in the galaxy are its learned types, fitted from field audio.`
		);
	});

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
	 *
	 * Two leaks this guard used to leave open:
	 *
	 * - Switching bird *while* solo ran only refreshed the display: the ambient pool
	 *   still held the previous species, so the old bird — not the new one — kept
	 *   singing, sometimes for as long as its shard took to load.
	 * - `stopAmbient` stops the scheduler but not the notes already posted to the
	 *   worklet, so the aviary's in-flight songs played on into the solo. Only the
	 *   selected bird (and its same-species duet partners) may be heard in solo, so
	 *   the voices are cut when a selection change takes the chorus over.
	 *
	 * And one state machine for the way back: returning to all birds restores the
	 * whole-aviary chorus if it was running when the selection began, and stays
	 * silent if the user had stopped it — both are "how it was", which is the only
	 * honest answer to "what should all birds sound like".
	 */
	let lastSpeciesChoice = $state('');
	/**
	 * Whether the whole-aviary chorus had the air when the current selection took it.
	 * Written here, read on the way back; `silence` and any toggle to 'off' clear it,
	 * because an explicit stop must survive the round trip.
	 */
	let resumeGlobal = false;
	$effect(() => {
		const chosen = speciesId;
		if (chosen === lastSpeciesChoice) return;
		lastSpeciesChoice = chosen;
		untrack(() => {
			if (!engine) return;
			if (chosen) {
				if (chorus !== 'solo') {
					resumeGlobal = chorus === 'global';
					// Cut in-flight notes only when a chorus was actually running — with
					// the chorus off, what is playing is something the user asked for
					// by hand, and selecting a bird must not silence it.
					if (chorus !== 'off') engine.panic();
					void setChorus('solo');
				} else {
					// A different bird while solo runs: rebuild the pool for it. The
					// shard may still be in flight, so wait for it like setChorus does.
					engine.panic();
					const eng = engine;
					void assets?.loadSpecies(chosen).then((bird) => {
						if (bird && speciesId === chosen && chorus === 'solo') {
							eng.startAmbient([bird.id], 12 * tempo, 3);
						}
					});
					refreshSelection();
				}
			} else if (chorus === 'solo') {
				if (resumeGlobal) void setChorus('global');
				else void setChorus('off');
				resumeGlobal = false;
			}
		});
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
	const jobDoing = $derived.by(() => {
		const log = job?.log;
		if (!log?.length) return '';
		for (let i = log.length - 1; i >= 0; i--) {
			const line = log[i].trim();
			// The per-type `FIT` lines are progress rows, printed a hundred times a second —
			// here they would replace "fitting syllables and syntax" with a row of numbers,
			// which is less information rather than more.
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
		// One probe pair, answered once: whether this asset root carries both clustering
		// maps. A single-map build answers 404 and the toggle simply never appears.
		detectGalaxyMaps(fetch).then((ok) => (mapsAvailable = ok));
		// The device list is readable before any permission — only the labels are
		// withheld — so the picker can show what is plugged in straight away, and track
		// it when hardware comes and goes.
		const refreshDevices = () => {
			BirdyEngine.inputDevices().then((d) => (inputDevices = d));
		};
		refreshDevices();
		navigator.mediaDevices?.addEventListener('devicechange', refreshDevices);
		// Capture phase, so it runs before the stage's own pointer handlers: the
		// background click-away needs to know what the gesture started on (a node
		// tag's click is a selection, not empty space).
		const trackDown = (e: PointerEvent) => {
			downTarget = e.target;
		};
		window.addEventListener('pointerdown', trackDown, true);
		return () => {
			navigator.mediaDevices?.removeEventListener('devicechange', refreshDevices);
			window.removeEventListener('pointerdown', trackDown, true);
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
			const loaded = await loadAssets(fetch, stamp, mapDir);
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
			assets = loaded;
			// A new inventory can drop a species — `--learned-only` does exactly that — and a
			// selection pointing at one that is gone leaves `currentSpecies` null, which reads
			// as "all birds" while the dropdown still shows the missing name.
			if (speciesId && !loaded.inventoryIndex.some((s) => s.id === speciesId)) {
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

	/** Which map the loaded galaxy is, read from its own manifest rather than remembered. */
	const mapKind = $derived<GalaxyMap>(
		assets?.manifest.clustering === 'hdbscan' ? 'unknown' : 'known'
	);

	/**
	 * The map switcher is a full reload, not an in-place mutation: the two maps are two
	 * complete asset sets — different knots, different positions, different inventories —
	 * so switching takes exactly the path a rebuild-triggered reload takes, down to the
	 * engine being rebuilt against the new inventory.
	 */
	async function switchMap(kind: GalaxyMap) {
		if (reloading || !mapsAvailable || kind === mapKind) return;
		mapDir = kind;
		// No stamp: the sub-build's own manifest supplies it, the same way the initial
		// load's does.
		await reloadGalaxy('');
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
		if (built && loaded && built !== loaded && !mapDir) untrack(() => reloadGalaxy(built));
		// `!mapDir` because the pipeline reports the *root* build's stamp: while a clustering
		// map is showing, the loaded manifest carries the sub-build's own stamp, which never
		// equals it — comparing them would reload forever. Switching back reloads fresh.
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
				sessionGate = m.session ?? null;
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
				common: sp?.common ?? assets.speciesCommon(id),
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
	 * The chorus the aviary was running when the current selection began, so clearing the
	 * selection can hand the air back to it. Picking a phrase or a knot starts that bird's
	 * solo chorus (see the effect on `speciesId`); going back should restore what it
	 * replaced rather than leaving silence, and "what it replaced" is only ever the
	 * whole-corpus chorus or nothing.
	 */
	let chorusToResume = $state(false);
	function noteChorusBeforeSelecting() {
		if (selectedSung === null && pinnedCluster < 0) chorusToResume = chorus === 'global';
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
		noteChorusBeforeSelecting();
		selectedSung = entry.id;
		speciesId = entry.speciesId;
		listener?.setPreview(entry.nodes, entry.speciesId, entry.label);
	}

	/**
	 * Clicking empty space in the view clears whatever the view is about: a phrase
	 * picked from the history, a pinned knot — or simply the bird chosen in the
	 * dropdown, which is a selection like the others. Releasing it returns to all
	 * birds, and the `speciesId` effect then hands the chorus back the way it came.
	 */
	function clearSelection() {
		if (selectedSung === null && pinnedCluster < 0 && !speciesId) return;
		selectedSung = null;
		pinnedCluster = -1;
		// Back to the whole corpus: the selection had narrowed it to one bird.
		speciesId = '';
		refreshSelection();
		// `setChorus` toggles, so guard the mode as well: starting the aviary chorus by
		// hand already clears the selection, and this must never switch it back off.
		if (chorusToResume && engine && chorus !== 'global') void setChorus('global');
		chorusToResume = false;
	}

	/**
	 * What the pointer went down on, tracked in the capture phase so the background
	 * handler can tell a click on empty space from one that merely *ended* over the
	 * stage. The node tags live inside it, so their clicks bubble up here — and a tag
	 * click is a selection (pickCluster), not a request to clear one.
	 */
	let downTarget: EventTarget | null = null;
	function backgroundClicked() {
		if (downTarget instanceof Element && downTarget.closest('.tag')) return;
		clearSelection();
	}

	/**
	 * Every point each syllable type owns, for the orphan flash. A type that won no
	 * cluster resolves to -1 everywhere the galaxy is asked to place it — but its
	 * renders and field members still have positions, and this is the map to them.
	 */
	const syllablePoints = $derived(assets ? buildSyllablePointIndex(assets) : null);

	/** Adds the trajectory a phrase takes through the galaxy, in time with the audio. */
	function addLive(speciesId: string, scheduled: ScheduledSyllable[], label = '') {
		const live = listener;
		if (!clusters || !live || !scheduled.length) return;
		live.addLive(
			scheduled.map((s) => clusterIndexFor(clusters, speciesId, s.syllableId)),
			scheduled.map((s) => ({ start: s.at, end: s.at + s.dur })),
			speciesId,
			label
		);
		// The syllables that resolved to no cluster draw nothing above — the thread
		// drops them by design. Their own points still exist, so they flash while the
		// note sounds: visible, and visibly not a knot.
		if (!syllablePoints) return;
		scheduled.forEach((s) => {
			if (clusterIndexFor(clusters, speciesId, s.syllableId) >= 0) return;
			const points = syllablePoints.get(`${speciesId}/${s.syllableId}`);
			if (points?.length) live.addOrphanPulse(points, { start: s.at, end: s.at + s.dur });
		});
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
	 * The faint backdrop of songs behind the live ones — for a chosen bird, never for
	 * the whole aviary at once.
	 *
	 * The whole-corpus backdrop (every bird's every song and grammar pair, drawn at
	 * 0.28 with overlap-darkening) was written when the galaxy held a dozen species
	 * and read as "the aviary has a shape". At 116 species it is thousands of static
	 * segments that never fade, and it buried the point cloud under a grey tangle —
	 * measured by looking at it: the cloud, which is the subject, was invisible
	 * behind threads, which are context. A thread is a current event: the backdrop
	 * now answers a question about *one* bird (selected or pinned), and a global
	 * chorus shows only the live trajectories, which have a lifecycle (capped, and
	 * faded out ~1.4 s after their phrase ends — see `advancePaths` in listener.ts).
	 */
	/**
	 * The species the embedding says share call shapes with `id`, strongest first
	 * (relations.json — measured candidates, never documented relationships, §8.5).
	 */
	function relationsOf(id: string, limit = 3): SpeciesRelation[] {
		if (!assets?.relations) return [];
		return assets.relations.speciesPairs
			.filter((p) => p.a === id || p.b === id)
			.sort((x, y) => x.distance - y.distance)
			.slice(0, limit);
	}

	/** The partner's display name in a relation pair involving `id`. */
	function relationPartner(p: SpeciesRelation, id: string): string {
		return p.a === id ? p.bCommon : p.aCommon;
	}

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
		listener.setContext([]);
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
		if (!assets || !currentSpecies) return;
		singPhrase(compilePhrase(assets.inventory, text, { speciesId }));
	}

	function singImprovisation() {
		if (!assets || !currentSpecies) return;
		singPhrase(improvise(assets.inventory, speciesId));
	}

	// --- Compose tab ---------------------------------------------------------------

	/**
	 * Audition one fitted type: the same render the strip would schedule, voice and
	 * distance included, so the keyboard is a keyboard and not a list of names.
	 */
	function auditionSyllable(typeId: string) {
		if (!engine || !currentSpecies) return;
		const syllable = currentSpecies.syllables.find((s) => s.id === typeId);
		if (syllable) engine.playSyllable(syllable, { voice: soloVoice ?? undefined, distance });
	}

	/**
	 * A manual edit invalidates a loaded song type or rhythm: the strip is no longer the
	 * observed ordering once a chip is added, moved or removed, and the phrase must not
	 * keep saying it is. The mode the user is looking at becomes the provenance.
	 */
	function editCompose(tokens: Token[]) {
		composeTokens = tokens;
		composeProvenance = {
			kind: composeMode === 'types' ? 'free' : composeMode,
			text: composeProvenance.text
		};
	}

	function appendToken(typeId: string, source: Token['source']) {
		auditionSyllable(typeId);
		editCompose([...composeTokens, { typeId, source }]);
	}

	function appendChunk(insert: string[]) {
		editCompose([...composeTokens, ...insert.map((typeId) => ({ typeId, source: 'chunk' as const }))]);
	}

	function removeToken(index: number, shiftKey: boolean) {
		if (shiftKey && index > 0) {
			const moved = [...composeTokens];
			[moved[index - 1], moved[index]] = [moved[index], moved[index - 1]];
			editCompose(moved);
			return;
		}
		editCompose(composeTokens.filter((_, i) => i !== index));
	}

	function clearCompose() {
		composeTokens = [];
		composeProvenance = { kind: composeMode === 'types' ? 'free' : composeMode };
	}

	function applyRhythm() {
		if (!currentSpecies) return;
		const tokens = applyTextRhythm(currentSpecies, text);
		if (!tokens) return;
		composeTokens = tokens;
		composeProvenance = { kind: composeMode === 'types' ? 'guided' : composeMode, text: text.trim() };
	}

	/**
	 * Playing a type re-expands the run-collapsed medoid — a trill is one act in the
	 * stored sequence — and the expansion is sampled from the measured repeat rates, so
	 * two plays of one type honestly differ in trill length. The strip shows what played.
	 */
	function playSongType(songType: SongType) {
		if (!currentSpecies) return;
		composeTokens = expandSongType(currentSpecies, songType);
		composeProvenance = { kind: 'songType', songType };
		singCompose();
	}

	function singCompose() {
		if (!currentSpecies) return;
		singPhrase(tokensToPhrase(currentSpecies, composeTokens, composeProvenance));
	}

	function syllableLabelOf(typeId: string): string {
		return currentSpecies?.syllables.find((s) => s.id === typeId)?.label ?? typeId;
	}

	/** Fit quality behind the keyboard's quality dot; absent on hand-authored syllables. */
	function resynthesisOf(typeId: string): number | undefined {
		return currentSpecies?.syllables.find((s) => s.id === typeId)?.learned?.resynthesisCosine;
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
			audioError = describeInputError(err, inputSource);
			micOn = false;
		}
	}

	/**
	 * Capture failures arrive as bare DOMException names; translate the three that actually
	 * happen. `NotAllowedError` means different things per source: for the microphone it is
	 * a denied permission, for display capture it is usually the picker being cancelled.
	 */
	function describeInputError(err: unknown, source: 'microphone' | 'system'): string {
		if (err instanceof DOMException) {
			if (err.name === 'NotAllowedError')
				return source === 'microphone'
					? 'Microphone access was denied. Allow it in the browser\u2019s site settings, then try again.'
					: 'The capture was cancelled. Tick "share audio" in the picker, or no sound arrives.';
			if (err.name === 'NotFoundError' || err.name === 'OverconstrainedError')
				return 'No microphone matches that selection — it may have been unplugged. Pick another device.';
			if (err.name === 'NotReadableError')
				return 'The microphone is already in use by another application.';
		}
		return err instanceof Error ? err.message : String(err);
	}

	/**
	 * Switching the source or the device while the input is open means opening it again — a
	 * MediaStream is bound to whatever it was captured from. A recording in progress is
	 * filed first: it belongs to the input it was captured on.
	 */
	let switchingInput = false;
	async function restartInput() {
		if (!engine || !micOn || switchingInput) return;
		switchingInput = true;
		audioError = null;
		try {
			if (engine.recording) await toggleRecording();
			await engine.startInput(inputSource, inputDeviceId || undefined);
			inputDevices = await BirdyEngine.inputDevices();
		} catch (err) {
			audioError = describeInputError(err, inputSource);
			micOn = false;
		} finally {
			switchingInput = false;
		}
	}

	function setInputSource(source: 'microphone' | 'system') {
		if (inputSource === source) return;
		inputSource = source;
		void restartInput();
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
	async function setChorus(mode: 'off' | 'solo' | 'global') {
		if (!engine || !assets) return;
		chorus = chorus === mode ? 'off' : mode;
		engine.stopAmbient();
		listener?.clearPaths();
		if (chorus === 'off') {
			// An explicit stop survives a later deselect: the aviary must not resume
			// behind a chorus the user deliberately ended.
			resumeGlobal = false;
			contextSpecies = null;
			refreshSelection();
			return;
		}
		if (chorus === 'global') {
			contextSpecies = null;
			// The whole aviary is the subject, so nothing should still be claiming to be
			// it: clearing the bird also releases the camera back to the entire galaxy,
			// which is the only framing in which a chorus of twelve makes any sense.
			speciesId = '';
			pinnedCluster = -1;
			selectedSung = null;
			// Every bird's songs is the one thing a whole-corpus chorus cannot get
			// lazily — and exactly what the whole file is for: one fetch, after which
			// every shard lookup is a cache hit.
			await assets.ensureSpecies();
			if (chorus !== 'global') return; // toggled off while the corpus loaded
			showContext('');
			engine.startAmbient(
				species.map((s) => s.id),
				22 * tempo,
				2
			);
			return;
		}
		// Solo: the bird's shard may still be in flight (this runs one tick after the
		// picker changed), so wait for it rather than trusting currentSpecies to be
		// the new bird already.
		const bird = await assets.loadSpecies(speciesId);
		if (chorus !== 'solo' || !bird) return;
		contextSpecies = bird.id;
		showContext(bird.id);
		engine.startAmbient([bird.id], 12 * tempo, 3);
	}

	/**
	 * Silence means silence. Killing the voices without dropping the trajectories leaves
	 * their travelling highlights animating through notes that will never sound.
	 */
	function silence() {
		engine?.panic();
		chorus = 'off';
		resumeGlobal = false;
		listener?.clearPaths();
		contextSpecies = null;
		refreshSelection();
	}

	/** Redraws the selected call's thread and its species backdrop. */
	function refreshSelection() {
		// A phrase picked out of the history owns the preview thread until it is cleared.
		if (selectedSung !== null) return;
		// Pinned to a local: the shard effect reassigns currentSpecies, so the guard's
		// narrowing does not reach inside the closures below.
		const bird = currentSpecies;
		if (!assets || !bird || !currentSong || !listener || chorus === 'global') return;
		const resolved = songSyllables(bird, currentSong.id);
		if (resolved) {
			listener.setPreview(
				resolved.syllables.map((s) => clusterIndexFor(clusters!, bird.id, s.id)),
				bird.id,
				currentSong.label
			);
		}
		if (contextSpecies !== bird.id) {
			contextSpecies = bird.id;
			showContext(bird.id);
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
		noteChorusBeforeSelecting();
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
	/**
	 * Fitted types in the inventory `learn` last wrote, summed over species.
	 *
	 * Shown because the number is the whole point of the loop: it is what grows as audio
	 * arrives, and a Learn tab that never showed it made "keep learning" unfalsifiable.
	 */
	const learnedTypeCount = $derived(
		(pipelineStatus?.learned?.species ?? []).reduce((n, s) => n + (s.types ?? 0), 0)
	);
	/** From the loaded manifest, so both describe the galaxy currently on screen. */
	const coverage = $derived(assets?.manifest?.typeCoverage ?? null);
	const relationHeadline = $derived(assets?.manifest?.relations?.headline ?? '');
	/** New species to look for at the start of each learning pass. 0 is off. */
	let loopDiscover = $state(0);
	let buildUseLearned = $state(true);
	let buildIncludeHarvest = $state(true);
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
	 * Birds the learning loop found and fitted, marked wherever species are listed.
	 * They sing like any other once they are in the inventory — the mark only says how
	 * they got there.
	 */
	const discoveredIds = $derived(new Set((pipelineStatus?.discovered ?? []).map((d) => d.id)));
	const speciesOptions = $derived(
		species.map((s) => ({ id: s.id, common: s.common, discovered: discoveredIds.has(s.id) }))
	);

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
		// The scheduler reads this per gap it draws, so no restart: the next pause
		// between songs comes out at the new rate.
		if (engine) engine.songRate = songRate;
	});
	/**
	 * The mean pause between songs at the current settings, for the slider's label.
	 * Poisson arrivals have no typical gap, only a mean one — the tooltip says so —
	 * and the base rate differs between the two choruses (22/min whole aviary,
	 * 12/min one bird), both already scaled by tempo where they are set.
	 */
	const songGapSeconds = $derived(
		60 / ((chorus === 'solo' ? 12 : 22) * Math.max(0.05, tempo) * Math.max(0.05, songRate))
	);
	/**
	 * Which provenance classes the loaded galaxy actually holds, and how much of it each
	 * one is. The legend quotes the share and marks the empty classes, so a colour you
	 * cannot find on screen reads as an empty pool rather than a broken renderer — and
	 * so the two classes that carry the galaxy are named as such instead of sitting in a
	 * flat list beside three that are absent.
	 *
	 * Counted from the same function the shader attribute is built from, so the legend
	 * can never drift from what is drawn.
	 */
	const provShare = $derived.by(() => {
		const share = new Float64Array(CLASS_COUNT);
		if (!assets) return share;
		const classes = pointProvenance(assets);
		for (let i = 0; i < classes.length; i++) share[classes[i]]++;
		if (classes.length) for (let c = 0; c < CLASS_COUNT; c++) share[c] /= classes.length;
		return share;
	});

	/** The legend's rows, strongest-carrying class first so the eye starts where the mass is. */
	const provLegend = $derived.by(() =>
		[
			PROVENANCE.learned,
			PROVENANCE.field,
			PROVENANCE.documented,
			PROVENANCE.unlabelled,
			PROVENANCE.candidate
		].map((cls) => ({
			cls,
			name: PROV_NAMES[cls],
			colour: provenanceColour(cls),
			share: provShare[cls] ?? 0
		}))
	);
	$effect(() => {
		// Tempo is one control over the whole aviary: the drift, the pulse, how long each
		// syllable lasts and how often a bird starts. Restarting the scheduler is what
		// applies the new arrival rate.
		const id = currentSpecies?.id;
		const rate = tempo;
		// Read per restart, so a checkbox change re-pools the chorus like a tempo one.
		const allowed = Object.entries(chorusClasses)
			.filter(([, v]) => v)
			.flatMap(([k]) => CHORUS_CLASS_CONFIDENCE[k] ?? []);
		if (engine) engine.tempo = rate;
		if (chorus === 'solo' && engine && id) engine.startAmbient([id], 12 * rate, 3, allowed);
		if (chorus === 'global' && engine && assets) {
			const loaded = assets;
			void loaded.ensureSpecies().then(() => {
				if (chorus === 'global')
					engine?.startAmbient(
						loaded.inventoryIndex.map((s) => s.id),
						22 * rate,
						2,
						allowed
					);
			});
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

	// compilePhrase only ever reads the selected bird out of the inventory, so it waits
	// for that bird's shard rather than for a whole-corpus parse.
	const preview = $derived(
		assets && currentSpecies && text.trim()
			? compilePhrase(assets.inventory, text, { speciesId })
			: null
	);

	// --- Compose tab derived state ---------------------------------------------------
	// Suggestions and chunk offers re-derive from the strip itself, so the context row
	// always answers "what comes next from *here*", which is the grammar's only claim.
	const composeGrammar = $derived(currentSpecies?.grammar);
	const composeNext = $derived(
		currentSpecies && composeMode === 'guided' ? nextOptions(currentSpecies, composeTokens) : null
	);
	const composeChunks = $derived(
		currentSpecies && composeMode === 'guided'
			? chunkCompletions(currentSpecies, composeTokens).slice(0, 4)
			: []
	);
	const composeTypes = $derived(
		(composeGrammar?.songTypes ?? []).slice().sort((a, b) => b.count - a.count)
	);
	const composeTyping = $derived(composeGrammar?.songTyping);
	const composePreview = $derived(
		currentSpecies && composeTokens.length
			? tokensToPhrase(currentSpecies, composeTokens, composeProvenance)
			: null
	);
	const composeCoverage = $derived.by(() => {
		if (!clusters || !currentSpecies || !composeTokens.length) return null;
		return syllableCoverage(
			clusters,
			currentSpecies.id,
			composeTokens.map((t) => t.typeId)
		);
	});
	// The strip holds fitted type ids of one bird; switching species empties it rather
	// than letting it quote a repertoire the chips no longer belong to.
	let composeSpeciesHeld = untrack(() => speciesId);
	$effect(() => {
		if (speciesId === untrack(() => composeSpeciesHeld)) return;
		composeSpeciesHeld = speciesId;
		composeTokens = [];
		composeProvenance = { kind: composeMode === 'types' ? 'free' : composeMode };
	});
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
	 * The colour a bird's mark carries, matching exactly what the galaxy draws for it.
	 *
	 * The bird's own hue now, not the generic accent: the accent in the cloud eases to
	 * the same `speciesColour` when this bird is the subject, so a chip in the history
	 * strip, the swatch next to the picker, and a lit knot are recognisably one thing.
	 * Hue is presentation here — the chip and the tag both still carry the bird's name.
	 */
	function speciesColourOf(id: string): string {
		return id ? speciesHue(id) : MONO_HOT;
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
				plain={!provColours}
			bird={pointColour === 'bird'}
				{provShown}
				pinned={pinnedCluster}
				frame={frameNodes}
				learning={learningClusters}
				onpick={pickCluster}
				onbackground={backgroundClicked}
			/>
			{/key}

			<!-- Display settings belong on the thing they change, not in the tab strip. -->
			<div class="viewctl">
				{#if mapsAvailable}
					<!--
						Two maps of the same corpus, one render: the same choice the Learn
						tab's build buttons offer, applied to the galaxy already loaded.
						Absent on a single-map build — probed once at startup, so there is
						no toggle and no subdir fetch on today's production assets.
					-->
					<div class="segmented mapctl" role="group" aria-label="Galaxy map">
						<button
							class:on={mapKind === 'known'}
							disabled={reloading}
							title="One cluster per syllable type, seeded at that type's own centre, every point assigned. This is what lets the app name, label and draw a path for anything it sings — it cannot report an unidentified sound."
							onclick={() => switchMap('known')}>Name everything</button
						>
						<button
							class:on={mapKind === 'unknown'}
							disabled={reloading}
							title="Find however many dense regions there are and leave the rest unassigned. Regions of real audio with nothing documented in them are flagged `unknown` — candidate new syllables. Coverage is not guaranteed, so this is for discovery rather than for the galaxy you listen in."
							onclick={() => switchMap('unknown')}>Find the unknown</button
						>
					</div>
				{/if}
				<button
					class="viewbtn"
					class:open={viewOpen}
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
								<label class="field">
									<span class="lbl">Point size <b class="mono">{pointSize.toFixed(1)}</b></span>
									<input type="range" min="1" max="10" step="0.1" bind:value={pointSize} />
								</label>
								<div class="checks">
									<label class="check" title="Slow drift of the whole galaxy, so depth stays readable while you listen.">
										<input type="checkbox" bind:checked={spin} /> Rotate
									</label>
									<label class="check" title="Name tags on the knots a syllable can be sung into.">
										<input type="checkbox" bind:checked={showLabels} /> Labels
									</label>
								</div>
								<!--
									One colour language at a time on the points, chosen as a mode:
									neutral ink (hue lives on the tags, saying which bird), the
									species hue itself ("who", points-only — the tags already speak
									it), or the provenance classes ("what kind of thing", which moves
									the tags and threads too, so the stage never speaks two hue
									languages at once).
								-->
								<div class="checks" role="radiogroup" aria-label="Point colour">
									<label class="check" title="Neutral ink points; hue on the tags and threads says which bird.">
										<input type="radio" bind:group={pointColour} value="ink" /> Ink
									</label>
									<label class="check" title="Each point in its bird's hue — the same colour its tags and threads already use.">
										<input type="radio" bind:group={pointColour} value="bird" /> Bird
									</label>
									<label class="check" title="Colour everything by where each sound comes from, not by which bird it is.">
										<input type="radio" bind:group={pointColour} value="prov" /> Provenance
									</label>
								</div>
								{#if provColours}
									<ul class="legend">
										{#each provLegend as row (row.cls)}
											<li class:absent={row.share === 0}>
												<i style:background={row.colour}></i>
												<b>{row.name}</b>
												<span class="mono"
													>{row.share === 0 ? 'none' : `${Math.round(row.share * 100)}%`}</span
												>
											</li>
										{/each}
									</ul>
									<p class="note faint">
										Hue says what kind of thing a sound is; the tag beside it names the
										bird. The big split is whether a bird made the sound or we did.
									</p>
								{:else if pointColour === 'bird'}
									<p class="note faint">
										Points and tags share one hue: the bird. The big split is who, not
										what kind of thing — the Provenance mode has that key instead.
									</p>
								{:else}
									<p class="note faint">
										Points are neutral ink. Hue on the tags and threads says which bird.
									</p>
								{/if}
							</section>
							<section class="block">
								<!--
									Per-class visibility. The two-class isolate is the arrivals live
									view: only the sounds nobody has named — unlabelled field audio
									and the candidates the novelty pass grouped — stay on screen, so
									"what don't we know" is a picture, not a count. Hiding a class
									removes its points from the picture, never from the corpus.
								-->
								<div class="checks">
									{#each [PROVENANCE.documented, PROVENANCE.learned, PROVENANCE.field, PROVENANCE.unlabelled, PROVENANCE.candidate] as cls (cls)}
										<label class="check">
											<input type="checkbox" bind:checked={provShown[cls]} />
											<i class="swatch" style:background={provenanceColour(cls)}></i>
											{PROV_NAMES[cls]}
										</label>
									{/each}
								</div>
								<button
									class="link"
									onclick={() => {
										provShown = [false, false, false, true, true];
									}}>only the unidentified</button
								>
								{#if provShown.some((v) => !v)}
									<button
										class="link"
										onclick={() => {
											provShown = [true, true, true, true, true];
										}}>show everything</button
									>
								{/if}
							</section>
						</div>
					</div>
				{/if}
				<button
					class="viewbtn"
					class:open={helpOpen}
					aria-label="Reading the galaxy"
					aria-expanded={helpOpen}
					title="What am I looking at?"
					onclick={() => (helpOpen = !helpOpen)}
				>
					<svg viewBox="0 0 16 16" width="15" height="15" aria-hidden="true">
						<path
							d="M6.2 5.6c.2-1.1 1-1.9 2.1-1.9 1.2 0 2.1.9 2.1 2 0 1.6-1.6 1.9-1.9 3v.5"
							fill="none"
							stroke="currentColor"
							stroke-width="1.3"
							stroke-linecap="round"
						/>
						<circle cx="8.4" cy="12.2" r="0.9" fill="currentColor" />
					</svg>
				</button>
				{#if helpOpen}
					<div class="panel viewpanel">
						<h2>Reading the galaxy</h2>
						<div class="cardbody">
							<section class="block">
								<ul class="legend key">
									<li>
										<i style:background="var(--ink-dim)"></i>
										<span>A point is one sound: a recorded syllable, or one synthesized from a fitted type.</span>
									</li>
									<li>
										<i class="hollow"></i>
										<span>A knot is a cluster of similar sounds. A named knot is a call type; a documented one carries its function and source.</span>
									</li>
									<li>
										<i class="pair"></i>
										<span>Distance is acoustic similarity: closer is more alike.</span>
									</li>
									<li>
										<i class="hue"></i>
										<span>Hue says which bird — on the tags and threads always, on the points too in Bird mode. In provenance mode it says what kind of thing instead — the Display panel has both keys.</span>
									</li>
									<li>
										<i class="ring"></i>
										<span>When a sound plays or is heard, the best-matching knot answers first and the response ripples outward.</span>
									</li>
									<li>
										<i class="line"></i>
										<span>A thread links the knots of one bout in the order its syllables were sung.</span>
									</li>
									<li>
										<i class="breath"></i>
										<span>Heard, but nothing claimed: the nearest region breathes grey — below the match floor, and the panel says so instead of naming a call.</span>
									</li>
									<li>
										<i style:background="var(--signal)"></i>
										<span>Violet marks what you asked for: the note singing now, or the selected bird's points.</span>
									</li>
								</ul>
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
			{#if tab === 'learn'}
				<!--
					The right-hand panel answers to the tab: everywhere else it is the reading,
					on Learn it is the learning run itself. A loop runs for as long as you let it,
					and its status used to be buried at the bottom of the control column, under
					every knob that drives it.
				-->
				<h2>
					Learning
					{#if job}<span class="mono faint">{job.name} · {job.state} · {job.seconds}s</span>{/if}
				</h2>
				<div class="cardbody">
					{#if job}
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
					{:else}
						<p class="note faint standfirst">
							No learning run yet. Start one under <b>Keep learning</b> and its progress
							reports here, pass by pass.
						</p>
					{/if}
				</div>
			{:else}
				<h2>
					Reading
					{#if selectedSung !== null || pinnedCluster >= 0}
						<button class="link" onclick={clearSelection}>clear selection</button>
					{/if}
				</h2>
				<div class="cardbody">
				{#if sessionGate?.flagged && reading?.active}
					<!--
						The docs/20 session gate, first in the chain: when the live session
						sits off everything the map was fitted on, the panel says so instead
						of naming a call — a confident-looking match through an out-of-
						manifold map is exactly the wrong-knots-with-total-confidence case
						the gate exists to catch. Scheduled songs are unaffected: they are
						known, not matched, and their audio is in-corpus, which pulls the
						score back under the line on its own.
					-->
					<div class="best">
						<span class="badge unlabelled">off the map</span>
						<h3 class="strong">This session is off everything the galaxy knows</h3>
						<p class="accent">positions are guesses — nothing here is a documented call</p>
						<p class="note">
							This sound sits past the calibrated line
							({sessionGate.score.toFixed(2)} &gt; {sessionGate.threshold.toFixed(2)}).
							Usual causes: an unusual recorder, heavy background, or a sound kind
							the corpus does not cover. Where it lights means little.
						</p>
						{#if assets.featureSpace.embedding?.sessionGate?.calibration}
							<p class="note faint">
								{assets.featureSpace.embedding.sessionGate.calibration}
							</p>
						{/if}
					</div>
				{:else if panelReading?.best}
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
					{#if assets.relations}
						{@const rels = relationsOf(best.centroid.speciesId)}
						{#if rels.length}
							<!--
								relations.json's cross-species pairs, shown where the matched bird
								is reported. The copy carries the honesty line with it — a shared
								call shape in the embedding is a candidate (ancestry, convergence,
								or artifact), never a documented relationship (§8.5).
							-->
							<p class="note faint">
								Shares call shapes with {rels
									.map((p) => relationPartner(p, best.centroid.speciesId))
									.join(', ')} — measured in the embedding; candidates, not documented
								relationships.
							</p>
						{/if}
					{/if}
				{:else if reading?.active}
					<!--
						Live input, no confident match. This used to fall through to the idle
						hint, so a bird the corpus could not place produced exactly the same
						panel as silence — position-only, and reported as "colour and label
						not firing". The honest reading is a state of its own: heard, real
						acoustics, and no cluster close enough to name (§8.5). The nearest
						cluster is shown with its similarity so "below the floor" is a
						number, not a shrug.
					-->
					{@const nearest = reading.candidates[0]}
					<div class="best">
						<span class="badge unlabelled">field recording</span>
						<h3 class="strong">Heard, but not in this corpus</h3>
						<p class="accent">unlabelled: real acoustics, no documented function</p>
						<p class="note">
							{#if nearest}
								Nearest knot: {nearest.centroid.label} at
								{(nearest.similarity * 100).toFixed(0)} % similarity — below the
								match floor, so this is not a claim it was that call.
							{:else}
								Nothing in the galaxy is close enough to name.
							{/if}
							{#if reading.strength > 0.01}
								It may be a sound form the corpus has too little of — the
								current build places {assets.manifest.typeCoverage
									? `${assets.manifest.typeCoverage.withCluster} of ${assets.manifest.typeCoverage.types}`
									: 'just over half of its'} learned types.
							{/if}
						</p>
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
						so no cluster carries a syllable name. A sung phrase has nothing to light,
						label or draw a path through. Rebuild with the rendered inventory included
						(<span class="mono">Learn → build</span>).
					</p>
				{:else}
					<p class="note faint">
						Sing something, or turn on the microphone. Clusters flare where the sound lands in
						the corpus — and stay dark when it lands nowhere.
					</p>
				{/if}
				{#if mapKind}
					<!--
						Which map is showing, stated where the reading lives. In the
						density map the unassigned share is the headline honesty number: those are
						real sounds the build refused to place, and the panel says so in the
						interface's own unidentified language (§8.5) rather than letting the gaps
						read as empty space. Gated on the loaded map's own kind, not on both maps
						existing — a single-map build needs the line just as much (a hdbscan-only
						build is exactly the build whose honesty number this is).
					-->
					<p class="caveat note">
						{#if mapKind === 'known'}
							Map: one knot per type, every sound assigned — this view cannot report an
							unidentified sound.
						{:else}
							Map: dense regions only. {assets.manifest.unassigned?.toLocaleString() ?? 'Some'}
							of {assets.points.n.toLocaleString()} sounds sit in no region — unidentified:
							real acoustics, no documented function.
						{/if}
					</p>
					{#if assets.featureSpace.embedding?.mapQuality?.centroidAgreement !== undefined}
						<!--
							The map's own measured honesty, where the build recorded it (docs/20):
							how often a live sound would light the same knot through the browser's
							28-d -> 32-d bridge as through the critic — raw, tie-adjusted (near-ties
							excluded), and at species level, which is the claim the panel makes.
						-->
						{@const mq = assets.featureSpace.embedding.mapQuality}
						<p class="caveat note faint">
							Live matching: knot
							<b class="mono">{((mq.centroidAgreement as number) * 100).toFixed(0)}%</b>
							{#if mq.centroidAgreementTieAdjusted !== undefined}
								· near-ties free
								<b class="mono">{((mq.centroidAgreementTieAdjusted as number) * 100).toFixed(0)}%</b>
							{/if}
							{#if mq.speciesAgreement !== undefined}
								· species
								<b class="mono">{((mq.speciesAgreement as number) * 100).toFixed(0)}%</b>
							{/if}
							— knot-level answers are "nearest of several close knots".
						</p>
					{/if}
				{/if}
				<p class="caveat note">
					{reading?.caveat ??
						'Birdy reports documented call functions with a confidence label. Machine learning can characterise repertoires and link calls to behaviour. It cannot translate them into sentences.'}
				</p>
				</div>
			{/if}
			</aside>

			<aside class="panel controls">
			<nav class="tabs">
				<button class:active={tab === 'sing'} onclick={() => (tab = 'sing')}>Sing</button>
				<button class:active={tab === 'words'} onclick={() => (tab = 'words')}>Compose</button>
				<button class:active={tab === 'listen'} onclick={() => (tab = 'listen')}>Listen</button>
				<button class:active={tab === 'learn'} onclick={() => (tab = 'learn')}>Learn</button>
			</nav>

			<div class="tabbody">
				{#if tab === 'sing'}
					<section class="block">
						<div class="field">
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
							<SpeciesPicker options={speciesOptions} bind:value={speciesId} />
						</div>
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
												title={songCoverageHint}
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
									title="Three individuals of this bird answer each other at random intervals. Each voice keeps its own pitch, timing and position."
									>Chorus</button
								>
								<button disabled={!engine} onclick={silence}>Stop</button>
							</div>
						{:else}
							<div class="row">
								<!--
									Not `primary`: Chorus is a toggle, and the filled style is
									reserved for one-shot actions — on a toggle it made the *off*
									state render black, which reads as pressed. The `.on` class
									carries the active look, as it does for the solo Chorus above.
								-->
								<button
									class:on={chorus === 'global'}
									disabled={!engine}
									onclick={() => setChorus('global')}
									title="The whole aviary at once. Every species draws its own trajectory as it sings. Choose a bird to narrow the labels to its repertoire."
								>
									Chorus
								</button>
								<button disabled={!engine} onclick={silence}>Stop</button>
							</div>
						{/if}
						{#if chorus !== 'off'}
							<div class="checks">
								{#each ['documented', 'synthesized', 'recorded'] as cls, i (cls)}
									{@const hint =
										cls === 'documented'
											? 'A person named this song — described in the literature or established by playback experiments.'
											: cls === 'synthesized'
												? 'Our own mapping: fitted from recordings or composed from them. Not a claim about real birds.'
												: 'Real audio of this species with no documented function attached.'}
									<label class="check" title={hint}>
										<input type="checkbox" bind:checked={chorusClasses[cls]} />
										<i
											class="swatch"
											style:background={provenanceColour(
												[PROVENANCE.documented, PROVENANCE.learned, PROVENANCE.field][i]
											)}
										></i>
										{cls}
									</label>
								{/each}
							</div>
							<p class="note faint">
								Which songs the chorus may draw from. Off re-pools the next song;
								nothing already playing is cut.
							</p>
						{/if}
					</section>


					<section class="block">
						<div class="sliders">
							<label class="field">
								<span class="lbl">Distance <b class="mono">{distance.toFixed(2)}</b></span>
								<input
									type="range"
									min="0"
									max="1"
									step="0.01"
									bind:value={distance}
									title="How far away the birds sound and look: air absorption, reverb and the viewing scale move together."
								/>
							</label>
							<label class="field">
								<span class="lbl">Volume <b class="mono">{volume.toFixed(2)}</b></span>
								<!--
									**Ceiling raised past unity, which is only safe because of the limiter.**
									A master gain of 1.0 was the loudest the app could go, and it was not loud:
									every note is normalised by `ampPP` so no syllable ever approaches full
									scale, and the reverb split takes another chunk. Above 1.0 the sum of a
									twelve-voice chorus would hard-clip at the output, so `BirdyEngine` now
									ends in a limiter and the extra headroom is usable rather than distorted.
								-->
								<input type="range" min="0" max="3" step="0.02" bind:value={volume} />
							</label>
							<!--
								**Tempo belongs to the birds, so it lives with them.** It sat in the display
								panel and multiplied the cloud's rotation as well as the song rate, which made
								it read as a view setting: slowing the birds down to hear a call also froze the
								picture, and the one control did two unrelated jobs. Here it does one — how
								fast the aviary sings — and `Rotate` under display does the other.
							-->
							<label class="field">
								<span class="lbl">Tempo <b class="mono">{tempo.toFixed(2)}×</b></span>
								<input
									type="range"
									min="0.1"
									max="2"
									step="0.05"
									bind:value={tempo}
									title="How fast the birds sing: syllable length, start rate, trill and vibrato rate. Pitch does not change — a slowed bird sings longer, not lower."
								/>
							</label>
							<label class="field">
								<span class="lbl">Song gap <b class="mono">~{songGapSeconds.toFixed(1)} s</b></span>
								<input
									type="range"
									min="0.25"
									max="3"
									step="0.05"
									bind:value={songRate}
									title="Mean pause between songs. Gaps scatter around the mean — arrivals are Poisson. Applies to the next gap; songs already playing are untouched."
								/>
							</label>
						</div>
					</section>
				{:else if tab === 'words'}
					<section class="block">
						<label class="field">
							<span class="lbl">Species</span>
							<select bind:value={speciesId}>
								{#each species as s (s.id)}
									<option value={s.id}>{s.common}</option>
								{/each}
							</select>
						</label>
						<!--
							Three ways to fill one strip. The mode changes only what the context
							row offers; every mode ends in the same singPhrase, so badge, note, galaxy
							thread and coverage tally are the existing machinery throughout.
						-->
						<div class="segmented">
							<button
								class:on={composeMode === 'free'}
								onclick={() => (composeMode = 'free')}
								title="Build a sequence from this bird's fitted syllable types, in your order. Labelled invented: our sequence."
							>Free</button>
							<button
								class:on={composeMode === 'guided'}
								onclick={() => (composeMode = 'guided')}
								title="The same chips, ranked by the transition probabilities counted from this bird's field recordings, with repeated motifs offered whole. Labelled: measured statistics, our bout."
							>Guided</button>
							<button
								class:on={composeMode === 'types'}
								onclick={() => (composeMode = 'types')}
								title="Orderings this bird was recorded singing, re-expanded into playable bouts. Trill lengths are sampled from the measured repeat rates."
							>Song types</button>
						</div>

						{#if composeTokens.length}
							<div class="chips">
								{#each composeTokens as token, i (token)}
									<button
										class="chip"
										class:wordbreak={Boolean(token.gapBefore)}
										onclick={(e) => removeToken(i, e.shiftKey)}
										title="{token.typeId} — {syllableLabelOf(token.typeId)} · added from {token.source}{token.gapBefore ? ' · starts a new word (0.12 s gap)' : ''}. Click to remove, shift-click to move earlier."
									>{token.typeId}</button>
								{/each}
							</div>
							{#if composePreview}
								<div class="callout">
									<span class="badge {composePreview.confidence}">
										{confidenceLabel(composePreview.confidence).text}
									</span>
									<p class="note">{composePreview.function}</p>
									<p class="note faint">{composePreview.note}</p>
								</div>
							{/if}
							<div class="row">
								<button
									class="primary"
									disabled={!engine}
									onclick={singCompose}
									title="Play the strip through the same engine as every other bout. The galaxy draws the thread for the syllables it can place and skips the rest."
								>Sing it</button>
								<button onclick={clearCompose} title="Empty the strip.">Clear</button>
								{#if composeCoverage && composeCoverage.placed < composeCoverage.total}
									<span
										class="tally mono"
										class:none={composeCoverage.placed < 2}
										title="{composeCoverage.placed} of this sequence's {composeCoverage.total} syllables have a place in the galaxy. A chip with no cluster still plays; the galaxy just can't draw it."
									>{composeCoverage.placed}/{composeCoverage.total}</span>
								{/if}
							</div>
						{:else}
							<p class="note faint">
								{#if composeMode === 'types'}
									Pick a song type below — the strip shows what played.
								{:else}
									The strip is empty. Add chips below, or let a text set the rhythm.
								{/if}
							</p>
						{/if}

						{#if composeMode === 'types'}
							{#if composeTyping}
								<p class="note faint">
									{composeTyping.inTypes} of {composeTyping.bouts} recorded bouts fall into
									{composeTyping.types} types; {composeTyping.unplaced} were heard once.
									Type ids renumber on every refit.
								</p>
							{/if}
							{#if composeTypes.length}
								<div class="typelist">
									{#each composeTypes as st (st.id)}
										<button
											class="typerow"
											disabled={!engine}
											onclick={() => playSongType(st)}
											title="Collapsed medoid: {st.sequence.join(' ')}. Playing re-expands runs from the measured repeat rates, so two plays differ honestly in trill length; the gaps are placeholders."
										>
											<span class="mono">{st.id}</span>
											<span class="note">{st.sequence.join(' ')}</span>
											<span class="note mono faint">×{st.count} · {(st.share * 100).toFixed(0)}%</span>
										</button>
									{/each}
								</div>
							{:else}
								<p class="note faint">No song types were fitted for this bird.</p>
							{/if}
						{:else if currentSpecies}
							{#if composeMode === 'guided' && composeNext}
								{#if composeNext.options.length}
									<div class="suggestions">
										{#each composeNext.options.slice(0, 8) as option (option.typeId)}
											<button
												class="suggestion"
												onclick={() => appendToken(option.typeId, 'suggested')}
												title="{syllableLabelOf(option.typeId)}{option.chunk ? ` · continues a motif heard ${option.chunk.count} times` : ''}"
											>
												<span class="bar"
													><span style:width={`${(option.p ?? 0) * 100}%`}></span></span
												>
												<span class="note">{option.typeId}</span>
												{#if option.chunk}<span class="note faint">motif ×{option.chunk.count}</span>{/if}
												<span class="note mono">{option.p === null ? 'start' : `${(option.p * 100).toFixed(0)}%`}</span>
											</button>
										{/each}
										{#if composeNext.endP !== null}
											<button
												class="suggestion"
												disabled={!engine || !composeTokens.length}
												onclick={() => { singCompose(); clearCompose(); }}
												title="The measured probability the bout ends here. Sing the strip and start a new one."
											>
												<span class="bar"
													><span style:width={`${composeNext.endP * 100}%`}></span></span
												>
												<span class="note faint">ends here</span>
												<span class="note mono">{(composeNext.endP * 100).toFixed(0)}%</span>
											</button>
										{/if}
									</div>
								{:else}
									<p class="note faint">
										{composeTokens.length
											? 'No measured transition continues from here — the bout ends, or pick any chip below.'
											: 'No grammar fitted for this bird — the chips below are unranked.'}
									</p>
								{/if}
								{#if composeChunks.length}
									<div class="suggestions">
										{#each composeChunks as offer (offer.chunk.sequence.join(' '))}
											<button
												class="suggestion"
												onclick={() => appendChunk(offer.insert)}
												title="A repeated motif mined from the bouts: {offer.chunk.sequence.join(' ')} — heard {offer.chunk.count} times (pmi {offer.chunk.pmi.toFixed(2)}). One click inserts {offer.insert.join(' ')}."
											>
												<span class="note">+ {offer.insert.join(' ')}</span>
												<span class="note mono faint">heard ×{offer.chunk.count}</span>
											</button>
										{/each}
									</div>
								{/if}
								<button
									class="wide"
									disabled={!engine}
									onclick={singImprovisation}
									title="Let the measured grammar walk itself — the same sampler as the Sing tab's Improvise."
								>Auto: let the grammar walk</button>
							{/if}
							<!--
								The keyboard is every fitted type, suggestion or not: the grammar is
								first-order and incomplete, so the ranked row is advice, not a gate. The
								dot says how close a render of the fit sits to its type's cluster in
								the descriptor space — a clustering match, not an audible-fidelity
								guarantee (docs/19).
							-->
							<div class="chips">
								{#each currentSpecies.syllables as s (s.id)}
									{@const cosine = resynthesisOf(s.id)}
									<button
										class="chip"
										onclick={() => appendToken(s.id, 'free')}
										title="{s.label}{cosine !== undefined ? ` · render sits at cosine ${cosine.toFixed(2)} from its type's cluster in the descriptor space — a clustering match; audible fidelity is measured separately (MCD, on the bench)` : ''}"
									>
										{s.id}{#if cosine !== undefined}<span
												class="quality"
												class:low={cosine < 0.4}
												class:mid={cosine >= 0.4 && cosine < 0.7}
											></span>{/if}
									</button>
								{/each}
							</div>
							<!--
								Text survives as rhythm only. splitSyllables yields the token count and
								word boundaries; syllable choice comes from the suggestions, never from
								the hash, and fitted contours are never transposed. The documented
								keyword path below is unchanged and still renders the real call.
							-->
							<label class="field">
								<span class="lbl">Phrase rhythm from words</span>
								<textarea bind:value={text} placeholder="danger — come here"></textarea>
							</label>
							<button
								class="wide"
								disabled={!currentSpecies || !text.trim()}
								onclick={applyRhythm}
								title="Fill the strip to this text's rhythm: its syllable count and word breaks. The words choose nothing else — syllables come from the measured syntax."
							>Set the rhythm from the words</button>
							{#if preview?.source === 'documented'}
								<div class="callout">
									<span class="badge {preview.confidence}">{confidenceLabel(preview.confidence).text}</span>
									<p class="note">
										Matched <span class="mono">{preview.matched.join(', ')}</span> → {preview.label}
									</p>
									<p class="note faint">{preview.note}</p>
									<button
										class="primary wide"
										disabled={!engine}
										onclick={singWords}
										title="Render the playback-verified call, unchanged by the composer."
									>Sing the documented call</button>
								</div>
							{:else if preview?.documentedElsewhere?.length}
								<p class="note faint">
									A documented call for this exists, but not for this bird:
									{#each preview.documentedElsewhere as other (other)}
										<button class="link" onclick={() => (speciesId = other)}>
											{assets.speciesCommon(other)}
										</button>
									{/each}
								</p>
							{/if}
						{/if}
					</section>
				{:else if tab === 'listen'}
					<section class="block">
						<h3 class="blocktitle">Input</h3>
						<div class="segmented">
							<button class:on={inputSource === 'microphone'} onclick={() => setInputSource('microphone')}>
								Microphone
							</button>
							<button class:on={inputSource === 'system'} onclick={() => setInputSource('system')}>
								Computer audio
							</button>
						</div>
						{#if inputSource === 'microphone'}
							<label class="field">
								<span class="lbl">Device</span>
								<select
									bind:value={inputDeviceId}
									onchange={(e) => {
										inputDeviceId = e.currentTarget.value;
										void restartInput();
									}}
								>
									<option value="">system default</option>
									{#each inputDevices as d (d.deviceId)}
										<option value={d.deviceId}>{d.label || `input ${d.deviceId.slice(0, 6)}`}</option>
									{/each}
								</select>
							</label>
							{#if !inputDevices.length}
								<p class="note faint">
									No input devices reported yet. They appear once the browser has been granted
									microphone access — start the input once, or check that one is plugged in.
								</p>
							{:else if !inputDevices[0].label}
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
							<button
								class:on={micOn}
								disabled={!engine}
								onclick={toggleMic}
								title="The same analysis the synthetic bird gets: one 28-d descriptor per frame, matched to the nearest cluster. Audio stays on your device. Below about 25 % match, nothing is reported."
							>
								{micOn ? 'Stop input' : 'Start input'}
							</button>
							<button class:on={recording} disabled={!engine || !micOn} onclick={toggleRecording}>
								{recording ? 'Stop recording' : 'Record'}
							</button>
						</div>
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
									title="Fetched, analysed and deleted one at a time. Only the measurements are kept."
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
						</section>

						<section class="block">
							<h3
								class="blocktitle help"
								title="Renders {pipelineStatus.learned.exists
									? `${learnedTypeCount} fitted + 44 documented`
									: '44 documented'} syllables and folds in the whole harvest. Both always."
							>
								Rebuild the galaxy
							</h3>
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

						</details>
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
		font-weight: 600;
		letter-spacing: -0.01em;
	}

	.strap {
		margin: 0;
		font-family: var(--font-mono);
		color: var(--ink-faint);
		font-size: 0.6rem;
		letter-spacing: 0.06em;
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
	}

	.viewbtn.open {
		border-color: var(--signal);
		color: var(--signal);
	}

	/* The map switcher is the Learn tab's segmented control moved onto the view: same
	   labels, same `.on` active language, compact enough to sit above the icon buttons. */
	.mapctl button {
		flex: initial;
		padding: 0.28rem 0.55rem;
		font-size: 0.68rem;
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
		/* Long unbroken strings — citation dois, file paths, mono ids — must wrap at the
		   panel's edge rather than run under its `overflow: hidden` and read as cut off. */
		overflow-wrap: break-word;
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
		overflow-wrap: break-word;
	}

	.tabs {
		display: flex;
		border-bottom: 1px solid var(--rule);
	}

	.tabs button {
		flex: 1;
		padding: 0.65rem 0.3rem 0.55rem;
		font-size: 0.62rem;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.12em;
		color: var(--ink-faint);
		background: none;
		border: none;
		border-bottom: 2px solid transparent;
		border-radius: 0;
		margin-bottom: -1px;
	}

	.tabs button:hover {
		color: var(--ink-dim);
	}

	.tabs button.active {
		color: var(--ink);
		border-bottom-color: var(--signal);
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

	/* Wrapping is load-bearing, not tidiness. These sit inside a panel that is a fixed
	   16rem wide and clips its overflow, so a row that refuses to wrap does not merely
	   look cramped — it stretches the panel's content box past the clip and takes the
	   prose under it along, which is how a third checkbox left every paragraph in the
	   Display panel cut off down the right-hand edge. */
	.checks {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem 1rem;
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

	.check .swatch {
		width: 0.6rem;
		height: 0.6rem;
		border-radius: 50%;
	}

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

	.legend b {
		font-weight: 500;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.legend span {
		font-size: 0.7rem;
		color: var(--ink-faint);
	}

	/* An empty class keeps its row: knowing the pool exists and is empty is a different
	   fact from the colour simply being missing, and only one of them is a bug. */
	.legend li.absent {
		opacity: 0.5;
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

	@keyframes breath {
		50% {
			opacity: 0.9;
		}
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

	/* The learning run, reporting in the right-hand panel while the Learn tab is up. */
	.loopstatus {
		display: grid;
		gap: 0.6rem;
		padding: 0.9rem 1rem;
		align-content: start;
	}

	.standfirst {
		padding: 0.9rem 1rem;
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

	.disc-name {
		flex: 1;
		min-width: 0;
		overflow: hidden;
		white-space: nowrap;
		text-overflow: ellipsis;
		font-size: 0.74rem;
		color: var(--ink);
	}

	.disc-pts {
		font-size: 0.64rem;
		color: var(--ink-faint);
	}

	/* How far a discovered bird has got, as a soft tinted pill: the colour carries the
	   stage, so no border is needed — an outlined bubble at this size reads as noise. */
	.disc-chip {
		font-size: 0.56rem;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.08em;
		padding: 0.14rem 0.45rem;
		border-radius: 999px;
	}

	.disc-chip.fitted {
		color: var(--documented);
		background: color-mix(in srgb, var(--documented) 9%, transparent);
	}

	.disc-chip.collecting {
		color: var(--signal);
		background: var(--signal-soft);
	}

	.disc-chip.waiting {
		color: var(--invented);
		background: color-mix(in srgb, var(--invented) 10%, transparent);
	}

	.discovered li.live {
		animation: disc-breathe 1.6s ease-in-out infinite;
	}

	@keyframes disc-breathe {
		0%,
		100% {
			background: transparent;
		}
		50% {
			background: var(--signal-soft);
		}
	}

	/* Coverage below 98 % means some types cannot be played at all, which is worth a colour
	   rather than a number a reader has to divide in their head. */
	.facts dd.warn {
		color: var(--invented);
		font-weight: 600;
	}

	/* Folded away by default: leaving a half out of the corpus is how you read a
	   measurement, not how you build a galaxy to use. */
	.diag {
		border-top: 1px dotted var(--rule);
		padding-top: 0.35rem;
	}

	.diag summary {
		cursor: pointer;
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

	/* --- Compose tab -------------------------------------------------------------- */
	button.chip {
		cursor: pointer;
	}

	/* A text word boundary on the strip: the one place a gap is not the flat placeholder. */
	.chip.wordbreak {
		border-left: 2px solid var(--ink-dim);
	}

	/* Fit-quality dot: how close a render of this type sits to the type's cluster in the
	   descriptor space — a clustering match, not audible fidelity (docs/19). */
	.quality {
		display: inline-block;
		width: 0.35rem;
		height: 0.35rem;
		margin-left: 0.25rem;
		border-radius: 50%;
		background: var(--signal);
		vertical-align: middle;
	}

	.quality.mid { background: var(--ink-dim); }
	.quality.low { background: var(--rule); }

	.suggestions {
		display: grid;
		gap: 0.15rem;
	}

	.suggestion {
		display: grid;
		grid-template-columns: 3rem auto 1fr auto;
		gap: 0.5rem;
		align-items: center;
		text-align: left;
		cursor: pointer;
	}

	.typelist {
		display: grid;
		gap: 0.15rem;
		max-height: 14rem;
		overflow-y: auto;
	}

	.typerow {
		display: grid;
		grid-template-columns: 2.5rem 1fr auto;
		gap: 0.5rem;
		align-items: baseline;
		text-align: left;
		cursor: pointer;
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

	/* The steps sit inside a `.block`, so their own block padding would double the
	   parent's. Strip the sides and let the rules between them do the separating. */
	.rollup.block > .block {
		padding-left: 0;
		padding-right: 0;
	}

	.rollup.block > .block:first-of-type {
		padding-top: 0.7rem;
	}

	/* A title whose explanation lives on hover. */
	.blocktitle.help {
		cursor: help;
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

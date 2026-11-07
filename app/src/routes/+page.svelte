<script lang="ts">
	import { base } from '$app/paths';
	import { biplotAxes } from '$lib/galaxy/biplot';
	import { doubtRange, type DoubtSource } from '$lib/galaxy/doubt';
	import { onMount, untrack } from 'svelte';
	import Galaxy from '$lib/galaxy/Galaxy.svelte';
	import SpeciesPicker from '$lib/SpeciesPicker.svelte';
	import InfoPage from '$lib/pages/InfoPage.svelte';
	import LearnPage from '$lib/pages/LearnPage.svelte';
	import {
		buildClusterLookup,
		buildSpeciesIndex,
		buildSyllablePointIndex,
		CLASS_COUNT,
		PROVENANCE,
		clusterIndexFor,
		clusterIndicesFor,
		detectGalaxyMaps,
		LOAD_STAGES,
		loadAssets,
		pointProvenance,
		songSyllables,
		speciesById,
		syllableCoverage,
		type ClusterLookup,
		type GalaxyMap
	} from '$lib/data/assets';
	import { LyrebirdEngine, type ScheduledSyllable } from '$lib/audio/engine';
	import { Listener } from '$lib/audio/listener';
	import { SoundingLog } from '$lib/audio/sounding';
	import {
		initialPerformance,
		reduce as reducePerformance,
		type Command as PerformanceCommand,
		type Event as PerformanceEvent
	} from '$lib/state/performance';
	import InventoryTable from '$lib/InventoryTable.svelte';
	import { buildInventoryRows, indexRows } from '$lib/data/inventory-rows';
	import { createIndividual } from '$lib/audio/individual';
	import { compilePhrase, improvise, songPhrase, type Phrase } from '$lib/lang/grammar';
	import { BOUT_GLOSS } from '$lib/lang/glossary';
	import {
		applyTextRhythm,
		chunkCompletions,
		expandSongType,
		nextOptions,
		tokensToPhrase,
		type Provenance,
		type Token
	} from '$lib/lang/compose';
	import { citationsFor, confidenceLabel, sourceLabel, type Reading } from '$lib/lang/translate';
	import {
		CATEGORIES,
		callsFor,
		categoriesFor,
		classify,
		intensityNote,
		refusal,
		speciesWithFunctions,
		type FunctionCategory
	} from '$lib/lang/functions';
	import { createSignal, type ContextPath, type VisualSignal } from '$lib/galaxy/shaders';
	import { createStats, type GalaxyStats } from '$lib/galaxy/stats';
	import {
		DOUBT_AGREE,
		DOUBT_QUIET,
		DOUBT_SNR,
		MONO_HOT,
		UNCLAIMED_TINT,
		PROV_NAMES,
		provenanceColour,
		speciesColour as speciesHue
	} from '$lib/galaxy/palette';
	import favicon from '$lib/assets/favicon.svg';
	import { AccentDriver } from '$lib/accent';
import { PipelineClient, type PipelineStatus } from '$lib/data/pipeline';
	import type { LyrebirdAssets, SongType, Species, SpeciesRelation } from '$lib/data/types';

	// $state.raw, not $state: a deep reactive proxy of the corpus cannot be structured-cloned
	// into the AudioWorklet, and there is nothing here that benefits from deep reactivity.
	let assets = $state.raw<LyrebirdAssets | null>(null);
	let loadError = $state<string | null>(null);
	/**
	 * What the asset loader is doing, for the first-load screen.
	 *
	 * A step counter rather than a byte count, for the reason `LOAD_STAGES` gives: most of the
	 * wait is JSON parsing of files already received, so bytes would read 90 % for the whole of
	 * it. Seeded with the first stage's own name so the screen never shows an empty label.
	 */
	let loadStage = $state<string>(LOAD_STAGES[0]);
	let loadDone = $state(0);
	// Annotated, because `LOAD_STAGES` is `as const` and its `.length` is the literal 10 — an
	// unannotated `$state` would take that literal as its type and refuse the callback's number.
	let loadTotal = $state<number>(LOAD_STAGES.length);
	let engine = $state<LyrebirdEngine | null>(null);
	let listener = $state<Listener | null>(null);
	// The renderer reads `signal` every frame and mutates it in place, so it must not be a
	// reactive proxy; the meters the UI shows come from the listener's callback instead.
	let signal = $state.raw<VisualSignal>(createSignal(1));
	/**
	 * The page accent: black at rest, the chosen bird's colour, moving with what sings. It reads
	 * `signal` directly each frame, so loudness never passes through a reactive value.
	 */
	const accent = new AccentDriver(
		{ level: () => signal.level, f0Hz: () => signal.f0 },
		document.documentElement
	);
	let pulseEl = $state<HTMLElement | null>(null);
	$effect(() => {
		accent.start();
		return () => accent.stop();
	});
	$effect(() => {
		accent.pulse = pulseEl;
	});
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
	/** Drop the held reading now: its subject has been superseded. */
	function releaseHeldReading() {
		heldReading = null;
		if (holdTimer) {
			clearTimeout(holdTimer);
			holdTimer = null;
		}
	}
	/** What the panel draws: the live reading if there is one, else the last one. */
	const panelReading = $derived(reading?.best ? reading : heldReading);
	const readingIsLive = $derived(Boolean(reading?.best));
	let audioError = $state<string | null>(null);
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

	/**
	 * Which of the left column's three panels is showing.
	 *
	 * **Learn used to be a fourth, and it is a `page` now.** Owner: *"we have a learn tab, I
	 * want to move it into the top."* The three that remain are all about making a sound —
	 * sing one, compose one, listen for one — and Learn was never that: it drives the
	 * pipeline, it reports a run that outlives any selection, and it wanted twice the width
	 * of a 20 rem column for its store figures and its inventory. The tab strip reads as one
	 * kind of thing again.
	 */
	let tab = $state<'sing' | 'words' | 'listen'>('sing');
	/**
	 * **The one value the chorus and the selection are, and the only thing that writes it.**
	 *
	 * This was thirteen pieces of state, eleven functions and seven effects in this scope, and
	 * two bugs came out of that in one session — a `setChorus` that toggled because a button
	 * called it, and two flags that both meant "did the aviary have the air". Both are
	 * structural, so `state/performance.ts` is a pure reducer over `(state, event)` and every
	 * transition is checked by `verify:performance` in milliseconds rather than by a
	 * four-minute browser probe.
	 *
	 * The six values below are `$derived` projections of it, so the two hundred places that
	 * *read* `chorus` or `speciesId` are unchanged and **nothing but `dispatch` can write
	 * them.** That is the property the old code could not have: any of those places could
	 * assign, and several did.
	 */
	let perf = $state(initialPerformance());
	// Empty on purpose: the app opens on the whole corpus rather than on one bird, and
	// the camera frames all of it. Choosing a bird is what narrows the view.
	const speciesId = $derived(perf.speciesId);
	/**
	 * Which call the Sing tab is on, or `''` for **all songs** — the first row of the
	 * dropdown and what every bird opens on.
	 *
	 * One control, two states, and everything follows from which one it is in. All
	 * songs: the chorus draws from the whole repertoire and the camera frames all of
	 * it. One song: the chorus sings only that, and the camera frames only its knots.
	 * There is nothing else to set — the pair of toggles that used to sit under this
	 * dropdown ("Frame this call", "Only this call") said the same thing twice more
	 * and could contradict it.
	 */
	const songId = $derived(perf.songId);
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
	const chorus = $derived(perf.chorus);
	let micOn = $state(false);
	// Computer audio is the default: the common use of Listen is pointing it at a recording
	// already playing on this machine, and the microphone is the deliberate choice. The
	// engine reaches it through the output's monitor device where one exists, so choosing
	// this default does not mean choosing a screen-share prompt.
	let inputSource = $state<'microphone' | 'system'>('system');
	/** Which route the open input actually took, so the panel can say so. */
	let inputVia = $state<'microphone' | 'monitor' | 'display' | null>(null);
	let inputDeviceId = $state('');
	let inputDevices = $state<MediaDeviceInfo[]>([]);
	let recording = $state(false);
	let recordings = $state<{ url: string; name: string }[]>([]);
	let viewOpen = $state(false);
	/**
	 * **The phone layout, and the one number that turns it on.**
	 *
	 * The bench was drawn for a 1600 px screen: a 20 rem control column pinned to the top-left,
	 * a reading card under it, a display panel hanging off the top-right corner, and a history
	 * strip running in the lane between them. On a 375 px phone all four of those wanted the
	 * same rectangle, and the CSS that used to handle it did so by *deleting* things — the
	 * readings row and the whole reading card were `display: none`, which also removed the only
	 * two openers the Info and Learn pages have. Neither page was reachable on a phone at all.
	 *
	 * So below this width the arrangement is a different one rather than a squeezed one: the
	 * stage keeps the screen, and the panels are drawers over it that open one at a time from a
	 * dock along the bottom edge. 860 px because that is where the 20 rem column plus the
	 * 16 rem display panel plus a readable gap between them stop fitting side by side; a tablet
	 * in landscape stays on the bench layout, which is what it has room for.
	 *
	 * Read from `window` at creation rather than defaulting: `ssr = false`, so this runs in the
	 * browser, and seeding it with a desktop width would draw one bench frame on a phone before
	 * the binding corrected it.
	 */
	const NARROW_PX = 860;
	let winW = $state(typeof window === 'undefined' ? 1600 : window.innerWidth);
	const narrow = $derived(winW <= NARROW_PX);
	/**
	 * Which drawer the dock has open, or `''` for the bare stage.
	 *
	 * The first three are the control panel's own tabs, so the dock *is* the tab strip on a
	 * phone and the strip inside the panel is hidden — two identical rows of Sing/Compose/Listen
	 * a finger's width apart read as two different controls. `reading` is the fourth because on
	 * a phone the reading card has nowhere to live beside the stage, and it is the one card that
	 * answers "what am I hearing".
	 *
	 * Only consulted while `narrow`. On the bench both cards are simply always on screen, which
	 * is the whole point of a bench.
	 */
	type Sheet = '' | 'sing' | 'words' | 'listen' | 'reading';
	let sheet = $state<Sheet>('');
	/**
	 * Tapping a dock item opens its drawer; tapping the open one closes it and gives the galaxy
	 * the whole screen back. One at a time, always: a phone has room for one drawer, and two
	 * stacked would leave neither readable.
	 */
	function openSheet(next: Sheet) {
		sheet = sheet === next ? '' : next;
		if (sheet && sheet !== 'reading') tab = sheet;
		if (sheet) {
			viewOpen = false;
			costOpen = false;
		}
	}
	/**
	 * The two corner icons obey the same one-at-a-time rule on a phone, and keep their bench
	 * behaviour otherwise — on the bench the Display panel and the cost readout are a stack of
	 * two small cards in a corner, and making them exclusive there would remove a working
	 * arrangement to fix a problem the bench does not have.
	 */
	function toggleView() {
		viewOpen = !viewOpen;
		if (!viewOpen || !narrow) return;
		costOpen = false;
		sheet = '';
	}
	function toggleCost() {
		costOpen = !costOpen;
		if (!costOpen || !narrow) return;
		viewOpen = false;
		sheet = '';
	}
	/** Whatever is open, shut it: the lid of every drawer calls this. */
	function closeSheet() {
		sheet = '';
		viewOpen = false;
		costOpen = false;
	}
	/**
	 * **How much room the open drawer is taking, so the stage can give it rather than lose it.**
	 *
	 * A bottom sheet that floats over the picture is the usual phone idiom and it is the wrong
	 * one here: the corpus is drawn centred, so a drawer over the bottom 60 % covers the middle
	 * of the cloud — you open Sing, press Chorus, and the knots that answer light up underneath
	 * the panel you pressed it from. The instrument's whole subject would be behind the control.
	 *
	 * So the drawer's measured height becomes padding on `.stage-wrap`, whose padding box is
	 * what `.stage` is `inset: 0` against — canvas, label layer and ruler together. The picture
	 * re-centres into the band that is left, the camera's aspect follows (threlte resizes on its
	 * own), and the ruler keeps measuring the picture actually on screen rather than a picture
	 * that is half behind a card. It costs one canvas resize per open, which is the honest price
	 * of the panel having somewhere to be.
	 *
	 * Both axes are measured because a phone on its side puts the drawer at the left instead;
	 * which of the two is spent is the orientation query's business, in the stylesheet.
	 */
	let sheetH = $state(0);
	let sheetW = $state(0);
	/**
	 * The header's height, measured rather than assumed.
	 *
	 * A landscape drawer runs the full height of the stage and is `position: fixed`, so its top
	 * is the top of the *window* unless it is told otherwise — which put its lid, grab bar and
	 * close behind the title bar. The header's height changes with the root font size and with
	 * whether the strap is showing, so it is read from the element.
	 */
	let hudH = $state(0);
	/** A page replaces the stage, so a drawer over it would be a card floating on a document. */
	function openPage(which: '' | 'info' | 'learn') {
		page = page === which ? '' : which;
		if (page && narrow) closeSheet();
	}
	/** What the dock's four items are, in the order a phone reader meets them. */
	const DOCK: { key: Sheet; label: string }[] = [
		{ key: 'sing', label: 'Sing' },
		{ key: 'words', label: 'Compose' },
		{ key: 'listen', label: 'Listen' },
		{ key: 'reading', label: 'Reading' }
	];
	/**
	 * Which Display sections are open. One bit each, so folding one leaves the others alone.
	 *
	 * `filter` starts shut and the rest start open: it is the longest list in the panel and
	 * the one a reader least often needs, which is the same thing the owner asked for from
	 * two directions ("minimize each and every panel", "we want the filters to be a drawer").
	 *
	 * Not persisted. A fold is a reading posture rather than a setting — restoring yesterday's
	 * collapsed panel would hide a control the reader has no memory of closing.
	 */
	let viewFold = $state({ view: true, colour: true, filter: false, unclaimed: true });
	/**
	 * Which full-stage page is open, or `''` for the galaxy.
	 *
	 * These are pages, not panels. The legend used to live in a 16 rem popover hanging off a
	 * question-mark icon on the right edge — too small for the material and named after
	 * nothing. It reads as a page because it is one: it replaces the stage instead of
	 * covering a corner of it.
	 *
	 * `learn` joined it for the same reason from the other direction — it was a tab in a
	 * 20 rem column, and what it has to show is a pipeline's state and every fitted
	 * syllables. Both openers sit in the header's readings row, at the end, because that row
	 * is already where a viewer looks for what the build is.
	 */
	let page = $state<'' | 'info' | 'learn'>('');
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
	/**
	 * **The two-level arrangement, and it is on by default because the one-level one was
	 * drawing knots in two places.**
	 *
	 * On: a knot sits where the projection put its most typical member, and its members
	 * are laid out by a local projection of their own feature space around that point
	 * (`localShapes` in layouts.ts). Off: the raw global projection, which is what every
	 * build before this one drew.
	 *
	 * **Always on, and the switch is gone.** It existed so the two arrangements could be
	 * compared side by side rather than argued about, and the comparison is settled: knots
	 * drawn in two blobs fall from **379 to 245** (severe 77 → 37), the widest split inside
	 * one knot from **1.27 to 0.80 box units**, and the median knot's extent is unchanged
	 * (0.134 → 0.1336), so everything calibrated against it — KNOT_GAP, the wave's reach, the
	 * ruler's unit — stays where it was. A control whose answer is known is a way to make the
	 * picture worse.
	 *
	 * It was also the one Display checkbox that rebuilt the cloud, because the arrangement is
	 * read once at build time — so flipping it blanked and remounted the canvas, which read as
	 * the points turning off and on rather than as a layout change. `Galaxy` and `PointCloud`
	 * keep the parameter: `localShapes` is still switchable in code, which is how those numbers
	 * were measured, and is where a future comparison would happen.
	 */
	/**
	 * The points' colour language: off is neutral ink, on tints every point by where
	 * its sound came from (the provenance classes). Default off — the corpus is one
	 * cloud first, and the class tint is a layer you ask for.
	 *
	 * The third language — every point in its species' hue — is back as `birdColours`
	 * below, and the finding that removed it still stands: at thousands of species on a dense
	 * scatter the hues cannot be told apart, which is why "who" normally lives where hue
	 * can be read (the tags, and the response, which lights in the singing bird's hue).
	 * It is opt-in for that reason and never the default. The tags and threads follow this
	 * switch too, because two hue readings of one stage invite the idea that they are
	 * related.
	 *
	 * **One checkbox, not a two-row radio group inside a rollup.** It is a binary, and
	 * it was dressed as a mode chooser folded behind a disclosure — three clicks and a
	 * paragraph to flip one bit, with the class colours listed underneath whether or
	 * not the points were wearing them.
	 */
	let provColours = $state(false);
	/**
	 * The third colour language: every resting point in its own bird's hue.
	 *
	 * Revived on the owner's ask, and it costs nothing it used to. The mode that was removed
	 * carried a **per-point hue attribute**, which took the point program to fifteen vertex
	 * attributes and failed to link on Mesa's Intel driver in Firefox — that was the reason it
	 * could not simply be left in. It does not need one now: the knot's species hue already
	 * rides the cluster texture's A channel, because the accent reads it to light a singing
	 * knot in its own bird's colour, so the resting point reads a value the shader already has.
	 *
	 * **Mutually exclusive with the provenance tint**, and that is the legend's own rule rather
	 * than a convenience — "colour says one thing at a time". Hue cannot answer "what kind of
	 * thing" and "which bird" in one picture without the reader having to know which question
	 * was asked.
	 *
	 * The legibility finding that removed it is unchanged and is why it is off by default: a
	 * hue circle shared by thousands of species is not a key anybody can read at this density. What it
	 * is good for is the shape of one *genus* against the rest, since the hue is the genus's.
	 */
	let birdColours = $state(false);

	/**
	 * One language at a time: whichever switch was just pressed wins and the other clears.
	 *
	 * Written as a pair of handlers rather than as an effect on both flags. An effect that
	 * cleared `birdColours` whenever `provColours` was set looks equivalent and is not — it
	 * makes the bird mode *unreachable* while provenance is on, because turning it on
	 * immediately satisfies the condition that turns it off again.
	 */
	function useProvColours() {
		if (provColours) {
			birdColours = false;
			clearDoubt();
		}
	}
	function useBirdColours() {
		if (birdColours) {
			provColours = false;
			clearDoubt();
		}
	}
	function clearDoubt() {
		trustAgree = false;
		trustSnr = false;
	}
	/**
	 * The doubt ramps joined this set on 2026-08-06, when they stopped being a saturation drain
	 * and became the third identity colour (see `palette.ts`, `doubtColourScaled`). A drain
	 * could sit on top of either of the other two because it spent a different channel; a ramp
	 * cannot, because it spends hue.
	 *
	 * **The two doubts do NOT clear each other**, which is the one exception to the rule above.
	 * They shared a single vertex attribute and so had to take turns; `aTrust` is a vec2 now, so
	 * both are resident and together they compose into a bivariate scheme with a defined worst
	 * corner rather than two languages competing for the same mark. Owner asked for the overlay
	 * and it cost nothing.
	 *
	 * Called after the bind has already written the box's new value, so an untick simply leaves
	 * both other modes as they were — turning doubt off must not silently turn provenance on.
	 */
	function useDoubtColour() {
		if (trustAgree || trustSnr) {
			provColours = false;
			birdColours = false;
		}
	}
	/**
	 * Per-class point visibility in PROVENANCE order (documented, learned, field,
	 * unlabelled, candidate). The arrivals live view is the two-class isolate —
	 * "only the unidentified": everything a bird never made, gone from the picture.
	 * Hiding removes points from the picture, never from the corpus.
	 */
	let provShown = $state<boolean[]>([true, true, true, true, true]);
	/**
	 * How many provenance classes are hidden right now, printed on the filter's own fold
	 * header — the one thing a shut drawer has to be able to say, because a filter that is
	 * hiding four fifths of the cloud from behind a closed header is indistinguishable from
	 * a corpus that does not hold those points.
	 */
	const hiddenClasses = $derived(provShown.filter((v) => !v).length);
	/**
	 * What the stage costs, and whether to show it.
	 *
	 * This is here because the renderer's cost has twice scaled with the corpus in a way
	 * nobody could see from inside the app — most recently the label layer, which built a
	 * DOM tag for every one of the debug build's 4 298 knots and moved all of them every
	 * frame to draw at most 26, and a production build has several times that. "It feels slow"
	 * does not name a cause; `points 4 298 / 214 154 · tags 3 · 58 fps` does, and so does the GPU line, because on a laptop with two of them the
	 * browser routinely picks the integrated one and then the whole fill-rate budget is a
	 * fraction of the machine's.
	 *
	 * Off by default — it is an instrument, not part of the picture. The renderer writes a
	 * plain object every frame (see stats.ts); this copies it four times a second, so
	 * drawing the readout cannot itself become the thing being measured.
	 */
	let costOpen = $state(false);
	/** Whether a drawer is over the stage right now — the strip along the bottom hides under it. */
	const sheetOpen = $derived(narrow && (sheet !== '' || viewOpen || costOpen));
	/**
	 * Give the room back the moment the last drawer shuts.
	 *
	 * `bind:clientHeight` writes on mount and on resize; it does not write on *unmount*, so a
	 * shut drawer would leave its last height standing and the stage would keep paying for a
	 * panel that is no longer there. An effect on the one derived that knows whether anything
	 * is open covers every path into that state — the lid, the dock, a page opening, and the
	 * window simply being made wide again.
	 */
	$effect(() => {
		if (!sheetOpen) {
			sheetH = 0;
			sheetW = 0;
		}
	});
	/**
	 * The density governor's switch: on, the measured frame time may hold the level of detail
	 * back; off, the camera alone decides how much draws.
	 *
	 * **Off by default since 2026-08-06** (owner: "we dont want adaptive details active as
	 * default"). It was on because the answer for an integrated GPU is on — and it still is, but
	 * a governor that starts enabled means the first thing a reader sees is a *thinned* corpus
	 * with no indication that anything was withheld. Off, the arrival frame is the whole corpus
	 * the camera allows; a reader whose machine cannot hold it has one switch, and the
	 * Statistics panel names the cost in frames per second either way.
	 */
	let adaptiveDetail = $state(false);
	/**
	 * The ceiling the governor may rise to, as a share of the corpus — the reader's own limit
	 * rather than the frame timer's (owner: "on the adaptive details can we also have a slider
	 * when activated to say how dense").
	 *
	 * 1 by default, which is the behaviour the governor had before the slider existed: it may
	 * rise all the way when frames are cheap. Shown only while `adaptiveDetail` is on, because
	 * off, the cap is pinned at 1 and a visible ceiling that changed nothing would imply a
	 * measurement.
	 */
	let detailCeiling = $state(1);
	/**
	 * Figure and ground, swapped on the density verdict: the sounds a second, independent
	 * clustering *confirmed* take the ink and their own hue, and the ones it refused fall back
	 * to faint ground.
	 *
	 * **It promotes the confirmed minority rather than the refused majority, and the flip is a
	 * fix.** See `refusedSize` in `shaders.ts` for the arithmetic — 79.5 % of this corpus is
	 * refused, so promoting the refused set promoted almost the whole cloud and singled out
	 * nothing.
	 */
	let unheardFigure = $state(false);
	/**
	 * How many points a density clustering refused, counted from the joined channel rather
	 * than read from the manifest.
	 *
	 * The manifest's own `unassigned` is 0 on this build and correctly so — the `label`
	 * clustering assigns everything — so the number the panel needs is not there to read.
	 * `null` means the channel is absent, which the control shows as disabled rather than
	 * as zero: "we did not ask" and "we asked and nothing was refused" are different
	 * claims, and only one of them is true here.
	 */
	const unheardCount = $derived(
		assets?.points.unassigned
			? assets.points.unassigned.reduce((sum: number, v: number) => sum + (v ? 1 : 0), 0)
			: null
	);
	const unheardShare = $derived(
		unheardCount !== null && assets ? unheardCount / assets.points.n : null
	);
	/** Colour every mark by how few of its ten drawn neighbours share its type. Rose ramp. */
	let trustAgree = $state(false);
	/** Colour every mark by how noisy its recording was, on a p5..p95 ramp. Amber. */
	let trustSnr = $state(false);
	/**
	 * How many sounds a density clustering placed — the complement of `unheardCount`, and the
	 * number the unclaimed control is actually about now that it marks the confirmed set.
	 */
	const placedCount = $derived(
		unheardCount !== null && assets ? assets.points.n - unheardCount : null
	);
	/**
	 * The per-point agreement, summarised over the points themselves rather than read from
	 * the manifest — and the difference matters, because the manifest's mean is the only
	 * form this number has ever been shown in and a mean cannot say how many marks are at
	 * zero. `null` means the build shipped no per-point channel, which the control shows
	 * as disabled rather than as agreement of nothing.
	 */
	/**
	 * The SNR ramp's ends, in dB, from `doubtRange` — **the same function PointCloud fills
	 * the attribute with**, so the number this panel prints and the number the shader draws
	 * cannot drift apart. That mattering is not hypothetical: a clamped scale whose printed
	 * ends disagree with its drawn ends is a picture that lies with a caption.
	 */
	const snrStats = $derived(assets?.points.snr ? doubtRange(assets.points.snr) : null);
	const trustStats = $derived.by<{ mean: number; alone: number; share: number } | null>(() => {
		const agreement = assets?.points.knnAgreement;
		if (!agreement || !assets) return null;
		let total = 0;
		let alone = 0;
		for (let i = 0; i < agreement.length; i++) {
			const v = agreement[i] ?? 0;
			total += v;
			if (v <= 0) alone++;
		}
		return {
			mean: total / agreement.length,
			alone,
			share: alone / agreement.length
		};
	});
	const galaxyStats = $derived(
		assets ? createStats(assets.points.n, assets.centroids.items.length) : null
	);
	let cost = $state<GalaxyStats | null>(null);
	$effect(() => {
		const source = galaxyStats;
		if (!costOpen || !source) {
			cost = null;
			return;
		}
		const sample = () => (cost = { ...source });
		sample();
		const id = setInterval(sample, 250);
		return () => clearInterval(id);
	});
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
	/**
	 * How many songs each chorus class can actually draw on, over the inventory as
	 * loaded — so a toggle that cannot change what the chorus plays says so instead of
	 * looking live.
	 *
	 * **These are songs by claim strength, and the points' classes are sounds by origin.
	 * They are two axes, and on this corpus they nearly invert.** Every song but 21 is
	 * `invented` — our arrangement — while 94 % of the *points* are `field`, real
	 * recorded audio. An invented song made of recorded syllables is the normal case
	 * here, not a contradiction: we chose the order, the bird made the sounds. Sharing
	 * one vocabulary across both filters was meant to remove a parallel taxonomy and
	 * instead implied the two were the same question. Both filters now name their axis.
	 *
	 * Measured over the 2 509 songs the shipped inventory holds: **invented 2 488,
	 * documented 10, experimental 6, inferred 5, unlabelled 0.** So `documented` draws on
	 * 16 and `synthesized` on 2 493. The 5 `inferred` songs are a real claim category that
	 * this vocabulary buckets under `synthesized`, which is why the count above is 21 and
	 * not 16 — the number a reader gets from "all but the documented ones" is wrong by the
	 * inferred five.
	 *
	 * **The panel counts more songs than the asset holds, and that is correct.** It reports
	 * 2 867, because `withDetectedSongs` mines **358** further song types in the browser from
	 * `grammar.songTypes` across 102 species — sequences measured from a bird's own bouts that
	 * exist only at runtime. They land in `synthesized`, so the live figure is 2 851 of 2 867
	 * rather than 2 493 of 2 509. A count over the asset and a count over the pool the chorus
	 * can actually draw are different numbers, and this control has to report the second.
	 *
	 * `null` while the inventory is unread — in shard mode `species` starts empty and a
	 * count of zero would be a statement about the loader, not about the corpus.
	 */
	const chorusClassSongs = $derived.by<{
		counts: Record<string, number>;
		songs: number;
		/** True while only some shards have arrived, so a zero means "not yet" not "none". */
		partial: boolean;
	} | null>(() => {
		// **`inventoryVersion`, or this never recomputes and the panel shows nothing.**
		// `assets` is `$state.raw` and `inventory.species` is a plain array that
		// `loadSpecies`/`ensureSpecies` mutate in place, so a derived that reads only
		// `assets.inventory.species` runs exactly once — at load, in shard mode, when the
		// array is still empty. It returned `null` forever: no counts beside any checkbox,
		// `settled` never true, so the permanently-empty `recorded` class never disabled and
		// three live controls looked identical to three dead ones. The filter underneath was
		// working the whole time; what was missing was every signal that it had.
		void inventoryVersion;
		const species = assets?.inventory.species ?? [];
		if (!species.length) return null;
		const out: Record<string, number> = { documented: 0, synthesized: 0, recorded: 0 };
		let songs = 0;
		for (const sp of species) {
			for (const song of sp.songs ?? []) {
				songs++;
				for (const [cls, values] of Object.entries(CHORUS_CLASS_CONFIDENCE)) {
					if (values.includes(song.confidence)) out[cls]++;
				}
			}
		}
		// **A count over the shards that happen to be loaded is not a count over the corpus**,
		// and treating it as one disabled a live class: load one bird whose only song is
		// `invented` and `documented` read 0, so the checkbox for the sixteen documented songs
		// in the corpus went unclickable until something else was fetched. The flag is what
		// lets a zero mean "none" only when everything has actually been read.
		const total = assets?.inventoryIndex.length ?? 0;
		return { counts: out, songs, partial: species.length < total };
	});
	let tempo = $state(1);
	// How often the chorus starts a song, as a multiplier on its Poisson rate. Read by
	// the scheduler per gap, so the slider retunes the next pause live (engine.songRate).
	let songRate = $state(1);
	let lastPhrase = $state<Phrase | null>(null);
	let nowSinging = $state<ScheduledSyllable[]>([]);
	let voices = $state(0);
	const pinnedCluster = $derived(perf.knot);

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
	/**
	 * Whether the pointer is inside the history strip, in which case the drawn list is held
	 * still. See the strip's own note: the chips shift right as each new phrase is prepended,
	 * so an unfrozen strip hands a click to whichever phrase slid under the cursor.
	 */
	let historyFrozen = $state(false);
	/** The list the strip actually draws — the live one, or the last one before the freeze. */
	let frozenHistory = $state<Sung[]>([]);
	const shownHistory = $derived(historyFrozen ? frozenHistory : history);
	$effect(() => {
		// Snapshot on the way in, not on the way out: what the user is reaching for is what
		// was on screen when the pointer arrived.
		if (historyFrozen) frozenHistory = untrack(() => history);
	});
	const selectedSung = $derived(perf.sungId);
	let sungCounter = 0;
	/** Enough to overflow any window; the strip clips the rest at the far end. */
	const HISTORY_CAP = 24;

	/**
	 * **The "Now singing" roster is gone, and its state with it.** It was a strip of
	 * chips across the top of the stage naming the species heard in the last ten
	 * seconds — the same chips, in the same shape, that the history strip along the
	 * bottom already carries, one lane apart. Two rows saying nearly the same thing
	 * read as two different claims and are one; the history is the honest one,
	 * because it says *what* was sung and not only *who* sang, and it is where the
	 * eye already is. Deleting the roster also deletes a `setInterval` prune tick and
	 * a Map rebuilt on every scheduled note.
	 */

	/**
	 * Which acoustic quantity each direction in the picture carries, and how much of it.
	 *
	 * Fitted over the knots' shipped positions rather than the drawn ones: this is a
	 * property of the build, and it must not change as the camera moves or the cloud
	 * rearranges. The Info page is the only reader — it was in the ruler caption and read as
	 * clutter there, because a share of 19 % beside a name is an explanation, not a label.
	 */
	const axes = $derived(assets ? biplotAxes(assets, Float32Array.from(assets.centroids.items.flatMap((c) => c.position))) : []);
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
			// A shard that has landed is a species the inventory table can now show rows for.
			if (sp) inventoryVersion++;
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
	/** Undefined on "all songs", which is a state and not a missing selection. */
	const currentSong = $derived(songId ? songs.find((s) => s.id === songId) : undefined);

	/**
	 * How many *distinct knots* each of this bird's songs passes through.
	 *
	 * Without it the dropdown is misleading in the one way that matters: a repeat class
	 * is by definition a single collapsed token, so `S01 · heard 6×` is one knot sung
	 * six times, while `ho → ho2 → kyo` is three. Both render as one line of text, so
	 * the only way to find out which you picked was to play it and wonder why the galaxy
	 * did not move. That happened, and it was reported as a bug in the galaxy.
	 *
	 * Distinct, not sequence length: a song that returns to a syllable draws a thread
	 * back to the same knot, and counting it twice would promise two places to look.
	 * Unplaced syllables (`clusterIndexFor` → -1) are simply not there — the same
	 * omission the trajectory makes, and the coverage tally beside the label is what
	 * says how many were dropped.
	 */
	const songKnots = $derived.by(() => {
		const map = new Map<string, number[]>();
		const bird = currentSpecies;
		if (!bird || !clusters) return map;
		for (const song of bird.songs) {
			const resolved = songSyllables(bird, song.id);
			const seen: number[] = [];
			for (const syl of resolved?.syllables ?? []) {
				const knot = clusterIndexFor(clusters, bird.id, syl.id);
				if (knot >= 0 && !seen.includes(knot)) seen.push(knot);
			}
			map.set(song.id, seen);
		}
		return map;
	});
	/** The first row: the bird as a whole. One line, because `<option>` cannot wrap. */
	const allSongsOption = $derived(`All calls (${songs.length})`);
	function songOption(song: { label: string; gloss: string }): string {
		return `${song.label}${song.gloss ? ` — ${song.gloss}` : ''}`;
	}

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
	 * **This was a 38-line effect and it is a transition now.** It read four variables —
	 * `chorus`, `speciesId`, `resumeGlobal`, `lastSpeciesChoice` — decided between four
	 * outcomes, and shared the resume question with a second flag in `clearSelection`. Both of
	 * this session's chorus bugs lived in that overlap. `state/performance.ts` holds the whole
	 * decision as `chooseBird` / `releaseSelection`, and `verify:performance` asserts each of
	 * the four outcomes the effect used to reach implicitly.
	 *
	 * The one part that stays here is the tab guard: handing the air to a solo chorus is a
	 * Sing-tab behaviour, and the Compose tab has a species picker with no chorus controls, so
	 * a pick there must not start — or hijack — a chorus the user cannot see. That is a fact
	 * about this screen's layout rather than about the performance, so it guards the dispatch
	 * rather than living inside the reducer.
	 */
	function chooseBird(id: string) {
		// Off the Sing tab the choice is recorded without taking the air.
		dispatch({ k: tab === 'sing' ? 'chooseBird' : 'noteBird', id });
	}
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
	 * history, a pinned node, a chosen call, the selected bird's whole repertoire, or —
	 * with nothing selected, which is how the app opens — the entire galaxy.
	 *
	 * The call sits below the pin and above the bird: picking a knot is a narrower
	 * question than picking a call, and picking a call is narrower than picking a bird.
	 * A call whose syllables all went unplaced frames nothing of its own and falls
	 * through to the repertoire, which is the honest answer — there is no place to fly
	 * to, and flying to the origin would invent one.
	 */
	const frameNodes = $derived.by(() => {
		if (selectedSung !== null) {
			const nodes = history.find((h) => h.id === selectedSung)?.nodes;
			if (nodes?.length) return nodes;
		}
		if (pinnedCluster >= 0) return [pinnedCluster];
		if (currentSpecies) {
			if (songId) {
				const knots = songKnots.get(songId);
				if (knots?.length) return knots;
			}
			return clustersOfSpecies.get(currentSpecies.id) ?? allClusters;
		}
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
		loadAssets(fetch, '', '', (stage, done, total) => {
			loadStage = stage;
			loadDone = done;
			loadTotal = total;
		})
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
			LyrebirdEngine.inputDevices().then((d) => (inputDevices = d));
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
	/** True if the new galaxy is in. A failure leaves the one on screen working. */
	async function reloadGalaxy(stamp: string): Promise<boolean> {
		if (reloading) return false;
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
			recording = false;
			reading = null;
			// The held reading outlives the live one by design, and a reload is the one moment
			// that is wrong: it names a cluster from a galaxy that no longer exists.
			heldReading = null;
			if (holdTimer) {
				clearTimeout(holdTimer);
				holdTimer = null;
			}
			history = [];
			// Scheduled windows belong to an audio clock that has just been disposed of, and
			// their keys to an inventory that may not hold them any more. Both make the table's
			// cursor point at the wrong row rather than at none.
			sounding.clear();
			assets = loaded;
			inventoryVersion++;
			// A new inventory can drop a species — `--learned-only` does exactly that — and a
			// selection pointing at one that is gone leaves `currentSpecies` null, which reads
			// as "all birds" while the dropdown still shows the missing name. The whole
			// performance is reset here anyway: a galaxy reload invalidates the knot indices
			// and the phrase ids as well as the species list.
			const keepBird =
				perf.speciesId && loaded.inventoryIndex.some((sp) => sp.id === perf.speciesId)
					? perf.speciesId
					: '';
			perf = { ...initialPerformance(), speciesId: keepBird, soloMode: perf.soloMode };
			signal = createSignal(loaded.centroids.items.length, loaded.points.n);
			galaxyVersion += 1;
			// Only if audio was already running: `enter` needs a user gesture the first time,
			// and by here there has been one. It restores the whole-corpus chorus itself.
			if (wasSinging !== 'off' || hadMic) {
				await enter();
				// `enter` starts the aviary, which clears the selection. Put back what was there:
				// the same bird singing, or a stopped chorus staying stopped. Asking for solo
				// directly came back as a solo chorus with no bird in it.
				if (wasSinging === 'solo' && keepBird) dispatch({ k: 'chooseBird', id: keepBird });
				else if (wasSinging === 'off') {
					dispatch({ k: 'stop' });
					if (keepBird) dispatch({ k: 'noteBird', id: keepBird });
				}
			}
			return true;
		} catch (err) {
			// Not `loadError`, which replaces the whole app: the old galaxy is still in place,
			// because nothing above touches it until the new one has arrived.
			audioError = `Could not load the new galaxy: ${err instanceof Error ? err.message : String(err)}`;
			return false;
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
		const before = mapDir;
		mapDir = kind;
		// No stamp: the sub-build's own manifest supplies it, the same way the initial
		// load's does.
		if (!(await reloadGalaxy(''))) mapDir = before;
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
	let entering = false;
	async function enter() {
		// A second click during the await would build a second engine, and the first would
		// never be disposed.
		if (!assets || engine || entering) return;
		entering = true;
		try {
			const created = await LyrebirdEngine.create(assets);
			await created.resume();
			created.setDistance(distance);
			created.setVolume(volume);
			created.onState = (s) => {
				voices = s.voices;
			};
			created.onInputEnded = () => void closeInput();
			// The chorus schedules its own songs, so the picture follows the engine rather
			// than the menus: whatever sings next draws its own trajectory.
			created.onScheduled = ({ speciesId: singing, songId, scheduled, voice }) => {
				singer = voice?.label ?? null;
				accent.singerId = singing;
addLive(singing, scheduled, voice?.label ?? '');
				recordSung(singing, songId, scheduled, voice?.label ?? '');
				// **A new song makes the held reading stale.** The hold exists so a name stays
				// readable for six seconds after the sound that produced it stops — but it was
				// only ever cleared on a reload, so during a chorus the panel could keep
				// showing the PREVIOUS song's match while a new one was already sounding.
				// That is the "it is not showing the newest sound" the owner reported: not a
				// missed update, a stale one outliving its subject. The moment something else
				// is scheduled, the last thing we heard is no longer the last thing we heard.
				// The live reading is untouched — if the matcher places this new song, it
				// takes over on its own; if it cannot, the panel goes quiet, which is the
				// honest answer rather than another bird's name.
				releaseHeldReading();
				if (chorus !== 'global' && singing !== contextSpecies) {
					contextSpecies = singing;
					showContext(singing);
				}
			};
			const live = new Listener(created, assets);
			live.onReading = (r) => {
				reading = r;
				if (r.best) holdReading(r);
				// Live input has no schedule to name a singer, so the match stands in for the colour.
				// Unmatched room noise with no chorus is nobody, so it must not wear the last singer.
				if (micOn) {
					if (r.best) accent.singerId = r.best.centroid.speciesId;
					else if (chorus === 'off') accent.singerId = '';
				}
};
			live.onMeters = (m) => {
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
			dispatch({ k: 'setChorus', mode: 'global' });
			if (created.sampleRateMismatch) {
				rateNote = `This browser is running audio at ${Math.round(created.ctx.sampleRate)} Hz, but the corpus was analysed at ${assets.featureSpace.sampleRate} Hz. Matching still works, slightly less precisely.`;
			}
		} catch (err) {
			audioError = err instanceof Error ? err.message : String(err);
		} finally {
			entering = false;
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
		const next = [
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
		];
		// The oldest goes first, unless it is the phrase being looked at: dropping that one
		// left the selection naming a chip that no longer existed.
		while (next.length > HISTORY_CAP) {
			const oldest = next.findLastIndex((h) => h.id !== selectedSung);
			next.splice(oldest, 1);
		}
		history = next;
	}


	/**
	 * Selecting a past phrase draws its path as a static thread and focuses its bird, so
	 * you can go back to something you heard go past. Selecting it again, or clicking
	 * empty space in the view, clears it.
	 */
	function selectSung(entry: Sung) {
		const wasSelected = selectedSung === entry.id;
		dispatch({ k: 'selectSung', sungId: entry.id, speciesId: entry.speciesId });
		// The reducer treats the same chip twice as a release, so the preview thread follows:
		// drawn for a new phrase, dropped when the phrase is let go.
		if (wasSelected) listener?.clearPreview();
		else listener?.setPreview(entry.nodes, entry.speciesId, entry.label);
	}

	/**
	 * Clicking empty space in the view clears whatever the view is about: a phrase
	 * picked from the history, a pinned knot — or simply the bird chosen in the
	 * dropdown, which is a selection like the others. Releasing it returns to all
	 * birds, and the `speciesId` effect then hands the chorus back the way it came.
	 */
	function clearSelection() {
		dispatch({ k: 'releaseSelection' });
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

	/**
	 * Every note that has been scheduled, so the inventory table can follow playback.
	 *
	 * `addLive` is the one funnel every sounding phrase passes through — the chorus arrives
	 * via `onScheduled`, "Sing it" and the composer call it directly — which is why the log
	 * is filled here and not in three places. Recorded before `addLive`'s own early return,
	 * because a syllable that resolves to no knot draws no thread and still sounds: its row
	 * should mark, and the table is the only surface that admits such a type exists.
	 */
	const sounding = new SoundingLog();

	/** Adds the trajectory a phrase takes through the galaxy, in time with the audio. */
	function addLive(speciesId: string, scheduled: ScheduledSyllable[], label = '') {
		sounding.add(
			scheduled.map((s) => ({
				key: `${speciesId}/${s.syllableId}`,
				start: s.at,
				end: s.at + s.dur
			}))
		);
		const live = listener;
		if (!clusters || !live || !scheduled.length) return;
		live.addLive(
			scheduled.map((s) => clusterIndexFor(clusters, speciesId, s.syllableId)),
			scheduled.map((s) => ({ start: s.at, end: s.at + s.dur })),
			speciesId,
			label,
			// A split type owns a second knot that is the same sound. It lights and is
			// tagged with the first; the thread above still runs through the primary only.
			scheduled.map((s) => clusterIndicesFor(clusters, speciesId, s.syllableId).slice(1))
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
	function songPathsOf(id: string): ContextPath[] {
		if (!assets || !clusters) return [];
		const bird = speciesById(assets.inventory, id);
		if (!bird) return [];
		return bird.songs.map((song) => {
			const resolved = songSyllables(bird, song.id);
			return {
				nodes: resolved
					? resolved.syllables.map((syl) => clusterIndexFor(clusters, id, syl.id))
					: [],
				kind: 'song' as const,
				weight: 1
			};
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
	 *
	 * Each pair **carries its measured probability out to the draw**. It used to be read
	 * here, compared against the floor and then dropped, so a transition this bird makes
	 * nine times in ten was drawn exactly like one it makes once in twelve — the picture
	 * discarded the one number that made it a reading rather than a diagram.
	 */
	function grammarPathsOf(id: string): ContextPath[] {
		if (!assets || !clusters) return [];
		const bird = speciesById(assets.inventory, id);
		const transitions = bird?.grammar?.transitions;
		if (!transitions) return [];
		const out: ContextPath[] = [];
		for (const [from, nexts] of Object.entries(transitions)) {
			const a = clusterIndexFor(clusters, id, from);
			if (a < 0) continue;
			for (const [to, p] of Object.entries(nexts)) {
				if (to === 'end' || p < GRAMMAR_FLOOR) continue;
				const b = clusterIndexFor(clusters, id, to);
				if (b >= 0 && b !== a) out.push({ nodes: [a, b], kind: 'grammar', weight: p });
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
	function nodePathsOf(id: string, cluster: number): ContextPath[] {
		const touching = (p: ContextPath) => p.nodes.includes(cluster);
		const songs = songPathsOf(id)
			.map((p) => ({ ...p, nodes: p.nodes.filter((n) => n >= 0) }))
			.filter((p) => p.nodes.length > 1 && touching(p));
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
		if (!engine || !currentSpecies) return;
		// On "all songs" the button means what the row means: one of them, drawn the same
		// way the chorus draws — the alternative is a disabled button in the state every
		// bird opens in.
		const song =
			currentSong ?? songs[Math.floor(Math.random() * songs.length)];
		if (!song) return;
		nowSinging = engine.playSong(currentSpecies.id, song.id, {
			voice: soloVoice ?? undefined,
			distance
		});
		// Register the phrase as a live path, which is what draws the thread through its
		// knots and runs the bead along it. Without this "Sing it" made a sound and left
		// the galaxy completely static — `singImprovisation` did it and this did not, so
		// improvising drew a trajectory and playing a documented call drew nothing.
		singer = soloVoice?.label ?? null;
		addLive(currentSpecies.id, nowSinging, singer ?? '');
		recordSung(currentSpecies.id, song.id, nowSinging, singer ?? '');
		lastPhrase = {
			speciesId: currentSpecies.id,
			label: song.label,
			gloss: song.gloss,
			function: song.function,
			confidence: song.confidence,
			refs: song.refs,
			syllables: [],
			gaps: [],
			// **A `learned_bout` is not a documented sequence and must not be rendered as
			// one.** `learn.py` writes one per fitted species with `confidence: 'invented'`
			// precisely because "the sequence is ours even though the syllables are
			// measured", and 2 488 of the 2 509 songs in this build are that. Hardcoding
			// `documented` here credited every one of them to a literature the corpus does
			// not hold, and the note underneath said "documented syllable inventory" over
			// syllables that are all `unlabelled`.
			source: song.confidence === 'invented' ? 'invented' : 'documented',
			matched: [],
			note:
				song.confidence === 'invented'
					? 'Sampled from a first-order syntax measured from this species’ field recordings. The syllables are measured; the order is ours.'
					: song.confidence === 'documented' || song.confidence === 'experimental'
						? 'Rendered from this species’ documented syllable inventory.'
						: 'Rendered from this species’ syllable inventory. The function of this call is not documented.'
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

	/** Play one authored call chosen by the functional reading, exactly as authored. */
	function singCall(songId: string) {
		if (!assets || !currentSpecies) return;
		singPhrase(songPhrase(assets.inventory, speciesId, songId, autoReading?.matched ?? []));
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
	 * The text-first path: fill the strip to the words' rhythm and play it in one
	 * click. The strip stays editable afterwards — this is a starting point, not a
	 * locked rendering.
	 */
	function singWordsRhythm() {
		if (!currentSpecies || !text.trim()) return;
		applyRhythm();
		singCompose();
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

	/** Ends the input, keeping what was being recorded. Also runs when a device goes away. */
	async function closeInput() {
		if (!engine) return;
		if (engine.recording) await toggleRecording();
		engine.stopInput();
		micOn = false;
	}

	async function toggleMic() {
		if (!engine) return;
		audioError = null;
		try {
			if (engine.micActive) {
				await closeInput();
			} else {
				// False when something else closed the input during the browser's prompt.
				if (!(await engine.startInput(inputSource, inputDeviceId || undefined))) return;
				micOn = true;
				inputVia = engine.inputVia;
				// Device labels are withheld until permission has been granted once, so the
				// list is worth re-reading the moment it has been.
				inputDevices = await LyrebirdEngine.inputDevices();
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
			if (!(await engine.startInput(inputSource, inputDeviceId || undefined))) return;
			inputVia = engine.inputVia;
			inputDevices = await LyrebirdEngine.inputDevices();
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
				recordings = [...recordings, { url, name: `lyrebird-${recordings.length + 1}.webm` }];
			}
		} else if (engine.startRecording()) {
			recording = true;
		}
	}

	/**
	 * The confidence values the chorus checkboxes currently allow, as one derivation
	 * rather than three copies — every start of a solo chorus reads the same list, so
	 * the filter can no longer apply to a chorus started by the tempo slider and not to
	 * one started by picking a bird (it used to: two of the three call sites passed no
	 * filter at all, and a checkbox only took effect at the next restart).
	 */
	const chorusConfidence = $derived(
		Object.entries(chorusClasses)
			.filter(([, v]) => v)
			.flatMap(([k]) => CHORUS_CLASS_CONFIDENCE[k] ?? [])
	);
	/**
	 * The one call the chorus may draw, or nothing at all on "all songs".
	 *
	 * A named call is a stronger statement than the confidence checkboxes, so it
	 * replaces them rather than being filtered by them (see `startAmbient`): asking for
	 * exactly this call and then having a class veto it would be one control silently
	 * overruling a more specific one.
	 */
	const soloSongIds = $derived(songId ? [songId] : undefined);
	/**
	 * What a one-bird chorus sings.
	 *
	 * `songs` draws from the repertoire — the calls and bouts this bird is recorded or
	 * documented singing, which is the chorus this app has always had. `improvise` walks the
	 * bird's **measured grammar** instead: the transition probabilities counted from its own
	 * field recordings, sampled fresh every time, so no two phrases are the same and none of
	 * them is a phrase anybody recorded. The two are different claims, which is why they are
	 * two modes and not a checkbox — one plays back a repertoire, the other generates from a
	 * statistic. The `Improvise` button beside them does the same walk once.
	 */
	const soloMode = $derived(perf.soloMode);

	/**
	 * The one writer of `perf`, and the bridge from a decision to the engine.
	 *
	 * `reducePerformance` decides *what is true now* and returns the commands that make it so.
	 * This runs them. The split is the point: the decisions are checkable without an audio
	 * context, and the only code that needs one is `perform` below.
	 */
	function dispatch(event: PerformanceEvent) {
		const step = reducePerformance(perf, event);
		perf = step.state;
		for (const command of step.commands) void perform(command);
	}

	/**
	 * Carries out one command.
	 *
	 * The two asynchronous ones re-check `perf.epoch` after their await. The old code guarded
	 * the same waits by re-reading `chorus`, which is right until the state has moved *and
	 * moved back* — a fast double click on a chorus button does exactly that, and the stale
	 * fetch then started a chorus nobody had asked for. An epoch cannot be confused with
	 * itself.
	 */
	async function perform(command: PerformanceCommand) {
		if (!engine || !assets) return;
		switch (command.k) {
			case 'panic':
				engine.panic();
				return;
			case 'stopAmbient':
				engine.stopAmbient();
				return;
			case 'clearPaths':
				listener?.clearPaths();
				return;
			case 'showContext': {
				// `contextSpecies` is a cache, not state: half a dozen things refresh the
				// backdrop and redrawing the same one is wasted work at corpus knot counts.
				const want = command.speciesId || null;
				if (contextSpecies === want) return;
				contextSpecies = want;
				showContext(command.speciesId);
				return;
			}
			case 'refreshSelection':
				refreshSelection();
				return;
			case 'startGlobal': {
				const loaded = assets;
				// Every bird's songs is the one thing a whole-corpus chorus cannot get lazily,
				// and exactly what the whole file is for: one fetch, then every shard lookup
				// is a cache hit.
				const held = loaded.inventory.species.length;
				await loaded.ensureSpecies();
				// Only when it grew: this bump rebuilds the Learn table, and re-pooling lands here.
				if (loaded.inventory.species.length !== held) inventoryVersion++;
				if (perf.epoch !== command.epoch) return;
				engine.startAmbient(
					loaded.inventoryIndex.map((s) => s.id),
					22 * tempo,
					2,
					chorusConfidence
				);
				return;
			}
			case 'startSolo': {
				// In improvise mode the ambient scheduler stays off and the effect below drives
				// it: `startAmbient` can only pick phrases that exist, and the point of that
				// mode is the ones that do not.
				if (perf.soloMode === 'improvise') return;
				if (!command.speciesId) return;
				const bird = await assets.loadSpecies(command.speciesId);
				if (!bird || perf.epoch !== command.epoch) return;
				contextSpecies = bird.id;
				showContext(bird.id);
				engine.startAmbient([bird.id], 12 * tempo, 3, chorusConfidence, soloSongIds);
				return;
			}
		}
	}
	/**
	 * The improvised chorus.
	 *
	 * An effect rather than a timer started and stopped by hand, because it has to end on
	 * every one of: the chorus stopping, the mode changing, the bird changing, the tempo
	 * changing, and the galaxy reloading. An effect's teardown covers all five; four
	 * `clearInterval` calls scattered through the state machine is how the last round's
	 * chorus bug happened.
	 *
	 * Floored at 1.5 s between phrases: an improvised bout runs about a second, and asking
	 * for them faster than they finish stacks voices instead of making a chorus.
	 */
	const improviseGapSeconds = $derived(
		Math.max(1.5, 60 / (12 * Math.max(0.05, tempo) * Math.max(0.05, songRate)))
	);
	$effect(() => {
		if (chorus !== 'solo' || soloMode !== 'improvise') return;
		if (!engine || !currentSpecies) return;
		// A chain rather than an interval, with the pace read at each phrase. In the interval
		// the Gap slider did nothing here, and moving Tempo tore the timer down, which sang a
		// new first phrase for every step of the drag.
		let id: ReturnType<typeof setTimeout>;
		const next = () =>
			untrack(() => {
				singImprovisation();
				id = setTimeout(next, improviseGapSeconds * 1000);
			});
		next();
		return () => clearTimeout(id);
	});
	/**
	 * The chorus buttons.
	 *
	 * Asking for the mode already running stops it, which is what a pressed button should do.
	 * **That behaviour used to live inside `setChorus`, which is what made it a bug**: four
	 * effects called that function with a mode they merely wanted to be *in*, two raced on the
	 * same transition, and the second arrival asked for the running mode — read as *stop*. The
	 * reducer keeps `pressChorus` and `setChorus` as two events for exactly this reason, and
	 * `verify:performance` sweeps 512 programmatic sequences to assert none of them can reach
	 * silence.
	 */
	function toggleChorus(mode: 'global') {
		dispatch({ k: 'pressChorus', mode });
	}

	/**
	 * Choosing a row of the dropdown, which is the whole of this control: the camera
	 * goes to the call's knots (or back to the repertoire on "all songs") and the
	 * chorus pool follows through `soloSongIds`.
	 *
	 * The pin and the history phrase both outrank a call in `frameNodes`, so leaving
	 * either in place would make choosing a call do visibly nothing. Both are cleared —
	 * the subject has changed, and this is the same reasoning that lets picking a knot
	 * override the bird.
	 */
	function chooseSong(id: string) {
		dispatch({ k: 'chooseSong', id });
	}

	/**
	 * Silence means silence. Killing the voices without dropping the trajectories leaves
	 * their travelling highlights animating through notes that will never sound.
	 */
	function silence() {
		dispatch({ k: 'stop' });
	}

	// A tab with no chorus controls must not hold a running chorus: entering Compose stops one
	// the way an explicit stop does — voices cut, trajectories cleared, and the resume flag
	// spent, so nothing comes back behind the user. Returning to Sing stays silent, which is
	// the `stop` event's contract and is asserted in `verify:performance`.
	$effect(() => {
		if (tab === 'words' && chorus !== 'off') silence();
	});

	/** Redraws the selected call's thread and its species backdrop. */
	function refreshSelection() {
		// A phrase picked out of the history owns the preview thread until it is cleared.
		if (selectedSung !== null) return;
		// Pinned to a local: the shard effect reassigns currentSpecies, so the guard's
		// narrowing does not reach inside the closures below.
		const bird = currentSpecies;
		if (!assets || !bird || !listener || chorus === 'global') return;
		// "All songs" has no one thread to preview, and the last call's thread must not
		// outlive the choice that drew it: the backdrop below already shows the whole
		// repertoire, which is what the row means.
		if (!currentSong) {
			listener.clearPreview();
			if (contextSpecies !== bird.id) {
				contextSpecies = bird.id;
				showContext(bird.id);
			}
			return;
		}
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
	/**
	 * The first song of `speciesId` that runs through `syllableId`, or `''`.
	 *
	 * First and not "best", because a syllable can appear in several songs and this has no
	 * basis for preferring one — the picker still lists them all, and the point is to land on
	 * a song that actually contains the sound that was clicked rather than on "all songs".
	 * Empty while the bird's shard is still loading, which is the honest answer: the songs are
	 * in the shard, so before it arrives there is nothing to choose.
	 */
	function songThrough(speciesId: string, syllableId: string): string {
		if (!assets || !speciesId || !syllableId) return '';
		const bird = speciesById(assets.inventory, speciesId);
		if (!bird) return '';
		for (const song of bird.songs) {
			const resolved = songSyllables(bird, song.id);
			if (resolved?.syllables.some((syl) => syl.id === syllableId)) return song.id;
		}
		return '';
	}

	function pickCluster(index: number) {
		if (!assets) return;
		const centroid = assets.centroids.items[index];
		// A knot the corpus has no bird for still pins; it just takes no species with it.
		const owner =
			centroid && species.some((sp) => sp.id === centroid.speciesId) ? centroid.speciesId : '';
		// Clicking a knot is a Sing-tab question, and `pickCluster` is reachable from Listen.
		if (owner && tab === 'listen') tab = 'sing';
		// Clicking the pinned knot again *releases* it, and a release must not then go and
		// select a song — that would make the second click do the opposite of nothing.
		const releasing = pinnedCluster === index;
		dispatch({ k: 'pickKnot', knot: index, speciesId: owner });
		// **A knot names a sound, and clicking one selects the song that sound belongs to.**
		// Owner's ask: clicking a label in the cloud should land on this song and this bird.
		// `pickKnot` already takes the bird — a narrower question implies the broader one —
		// and this adds the song, as a second event rather than by widening that transition:
		// `chooseSong` already owns everything that has to follow a song change (the pin
		// released, the sung phrase cleared, the epoch bumped, a running solo chorus
		// re-pooled), and reproducing any of that inside `pickKnot` would be the second copy
		// of a rule that this machine exists to have exactly one of.
		//
		// After the bird's shard: `songThrough` found nothing on a bird not loaded yet, so the
		// first click on a new bird pinned while the same click on a loaded bird chose a song.
		if (releasing || !owner) return;
		void assets.loadSpecies(owner).then(() => {
			// A later click has already moved on, and this answer is about the old one.
			if (perf.knot !== index || perf.speciesId !== owner) return;
			const song = songThrough(owner, centroid?.syllableId ?? '');
			if (song) dispatch({ k: 'chooseSong', id: song });
		});
	}

	// --- the optional local pipeline control surface ---

	const pipeline = new PipelineClient();
	let pipelineStatus = $state<PipelineStatus | null>(null);
	let pipelineChecked = $state(false);
	let pipelineBusy = $state(false);

	// --- The inventory table on the Learn page --------------------------------------
	/**
	 * Every syllable type in the loaded build, as rows.
	 *
	 * Recomputed when a species' shard arrives, which is what `inventoryVersion` is for:
	 * `assets.inventory.species` is a plain array mutated in place by `loadSpecies`, and
	 * `assets` is `$state.raw`, so nothing here would ever re-run on its own. The whole
	 * corpus lands in one fetch when the global chorus starts (`ensureSpecies()`), so in
	 * practice this fills once and then holds every row.
	 */
	const inventoryRows = $derived.by(() => {
		void inventoryVersion;
		if (!assets) return [];
		const lookup = clusters;
		return buildInventoryRows(assets.inventory, assets.inventoryIndex, (sp, syl) =>
			lookup ? clusterIndexFor(lookup, sp, syl) : -1
		);
	});
	const inventoryRowIndex = $derived(indexRows(inventoryRows));
	/**
	 * Bumped whenever the set of loaded species may have changed.
	 *
	 * A counter rather than a derived length, because `inventory.species.length` is not
	 * reactive either — the only honest signal is "something asked for a shard and it has
	 * landed", and that is what the chorus effect and every selection report.
	 */
	let inventoryVersion = $state(0);
	/** The key of the note sounding now, ticked only while the Learn page is open. */
	let soundingKey = $state('');
	const soundingRow = $derived(soundingKey ? (inventoryRowIndex.get(soundingKey) ?? -1) : -1);
	/**
	 * The cursor's clock.
	 *
	 * 60 ms, which is under the shortest syllable this corpus holds (35 ms exists, but the
	 * median is an order of magnitude longer) and coarse enough that a table of a hundred
	 * drawn rows is not re-laid-out sixty times a second. It runs **only while the page is
	 * open**: a timer polling the audio clock behind a closed page is cost with no reader,
	 * and this one would run for as long as the app does.
	 */
	$effect(() => {
		if (page !== 'learn' || !engine) {
			soundingKey = '';
			return;
		}
		const ctx = engine.ctx;
		const tick = () => (soundingKey = sounding.at(ctx.currentTime));
		tick();
		const id = setInterval(tick, 60);
		return () => clearInterval(id);
	});

	/** Clicking a row goes to that type's knot, the same as clicking it in the cloud. */
	function pickRow(row: { speciesId: string; syllableId: string; knot: number }) {
		if (row.knot < 0) return;
		page = '';
		pickCluster(row.knot);
	}
	/**
	 * What the projection is worth, from the loaded build's own manifest.
	 *
	 * Every one of these numbers has been written by `build` since the projection
	 * existed and **none of them had ever been read by the app**, which is why the key
	 * could say "distance is acoustic similarity" as a flat fact while the build's own
	 * measurement of that claim was 0.667. The key quotes the loaded build now, so a
	 * rebuild that projects better or worse says so on screen.
	 */
	const projQuality = $derived.by(() => {
		const m = assets?.manifest;
		if (!m) return null;
		return {
			pearson: m.faithfulness?.pearson ?? null,
			knnK: m.knnAgreement?.k ?? 10,
			knn: m.knnAgreement?.value ?? null,
			torn: m.tearing?.torn ?? null,
			tornOf: m.tearing?.measured ?? null,
			// The local half, added when the projector was chosen on it. `pearson` is a
			// correlation over random pairs and so is dominated by far ones; these two say
			// whether a point's *own* neighbours are its neighbours, which is what a viewer
			// reads when two marks sit together. Absent on builds before 2026-08-03.
			trust: m.neighbourhood?.trustworthiness ?? null,
			continuity: m.neighbourhood?.continuity ?? null
		};
	});
	/**
	 * The corpus's own length unit, measured by the renderer and handed back: the
	 * median nearest-neighbour distance between knot centres. Everything the key says
	 * about how wide a knot is has to be quoted against it, because a distance in
	 * projection units is a number about nothing.
	 */
	let knotSpacing = $state(0.135);
	/**
	 * **How wide the average knot is, in units of the gap to its neighbour.**
	 *
	 * This is the measured answer to "I cannot see the structure of the knots", and
	 * nothing in the interface had ever said it. On the shipped v6 build the median
	 * knot's mean member distance is 0.129 against a median knot spacing of 0.040 —
	 * so an average knot is over three times wider than the distance to the next one,
	 * and the knots interpenetrate everywhere. That is not a rendering fault and no
	 * amount of point styling fixes it: with `label` clustering a knot is every sound
	 * carrying one type's name, and a type's sounds are under no obligation to land
	 * together in the projection.
	 *
	 * `radius` is the pipeline's own per-knot mean member distance, so this cannot
	 * drift from what the build measured.
	 */
	const knotOverlap = $derived.by(() => {
		const items = assets?.centroids.items ?? [];
		if (!items.length || !(knotSpacing > 0)) return null;
		const radii = items
			.map((it) => (it as { radius?: number }).radius ?? 0)
			.filter((r) => r > 0)
			.sort((a, b) => a - b);
		if (!radii.length) return null;
		return { radius: radii[radii.length >> 1], ratio: radii[radii.length >> 1] / knotSpacing };
	});
	/** From the loaded manifest, so both describe the galaxy currently on screen. */
	const coverage = $derived(assets?.manifest?.typeCoverage ?? null);
	const relationHeadline = $derived(assets?.manifest?.relations?.headline ?? '');

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
	 * Poll the control process always, quickly with the Learn page open and slowly otherwise.
	 *
	 * **It used to stop the moment you left the Learn tab, which is the moment you would
	 * leave it.** You start a loop, go back to Sing to listen while it works, and from then
	 * on `pipelineStatus` is frozen at whatever it held when you switched: the effect below
	 * that swaps in a finished build never re-evaluates, so the app cannot notice its own
	 * galaxy has been replaced. The whole point of learning while the app runs is that you
	 * are somewhere else in the app while it happens.
	 *
	 * Slower with the page shut because the reason to poll is different. Open, it is the job
	 * log, which is a progress indicator and wants to move; closed, it is one question — has
	 * the build stamp changed — and asking that every six seconds is enough.
	 */
	const POLL_MS = { learn: 1500, elsewhere: 6000 };
	$effect(() => {
		const fast = page === 'learn';
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

	// --- what the info page quotes -----------------------------------------------------
	/**
	 * How much of the corpus is measured field audio and how much is this synthesiser's own
	 * render of the documented repertoire.
	 *
	 * On the page because "no samples" and "measurements of real recordings, never the audio" are both
	 * true and sound contradictory: what is kept is the measurement, never the audio. A page
	 * that says the first without the second invites the reader to discover the second and
	 * conclude they were misled.
	 */
	const sourceMix = $derived.by(() => {
		const mix = assets?.manifest?.sourceMix;
		if (!mix) return null;
		const field = mix.field ?? 0;
		let rendered = 0;
		for (const [key, n] of Object.entries(mix)) if (key !== 'field') rendered += n ?? 0;
		return { field, rendered };
	});
	/**
	 * The ramp the match meter is drawn against, from the build that shipped it.
	 *
	 * Quoted rather than the constants, because the constants are only the fallback for an
	 * asset set that ships no ramp — and the whole point of the ramp travelling with the
	 * assets is that a page describing it cannot go stale against the corpus.
	 */
	const matchFloor = $derived(assets?.manifest?.matchRamp?.floor ?? null);
	const matchCeiling = $derived(assets?.manifest?.matchRamp?.ceiling ?? null);
	/**
	 * How many of the loaded types were fitted from field audio rather than documented.
	 *
	 * Counted off `learned` on the syllable, never off the shape of the id. `L07` looks like
	 * a fitted id and `feebee` looks like a documented one, and the app happens to be right
	 * about both — but a rule that reads a name to decide what kind of claim a row is making
	 * is one rename away from being wrong, and the field is right there.
	 */
	const fittedTypes = $derived(inventoryRows.filter((r) => r.fitted).length);


	$effect(() => {
		engine?.setDistance(distance);
	});
	$effect(() => {
		engine?.setVolume(volume);
	});
	/**
	 * A call the loaded bird does not sing falls back to the whole repertoire.
	 *
	 * **This effect used to do two jobs and only one of them is left.** It also cleared the
	 * call on every change of bird, because `learned_bout` is a universal id — every fitted
	 * bird has one, so a selection stays *valid* across a change of bird and the camera would
	 * keep framing one call of a repertoire the user just asked to see whole. `chooseBird`
	 * clears `songId` in the reducer now, which is where a rule about what a selection *means*
	 * belongs. What remains is a repair for a rebuild landing under a live selection, and that
	 * genuinely is an effect: it depends on a shard arriving.
	 */
	$effect(() => {
		const bird = currentSpecies;
		if (!bird || !perf.songId) return;
		if (!bird.songs.some((song) => song.id === perf.songId)) {
			untrack(() => dispatch({ k: 'chooseSong', id: '' }));
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
		chorus === 'solo' && soloMode === 'improvise'
			? improviseGapSeconds
			: 60 / ((chorus === 'solo' ? 12 : 22) * Math.max(0.05, tempo) * Math.max(0.05, songRate))
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

	/**
	 * The provenance filter's rows, **ordered by the share each class actually carries**.
	 *
	 * The list was an inline literal in the markup, in class-strength order, under a sibling
	 * `provLegend` that claimed to sort "strongest-carrying class first" and **was rendered
	 * nowhere** — so the sort was dead code and the visible list led with `documented` at 2 %
	 * while `recorded`, which is 94 % of the corpus, came third. Measured in a browser, which
	 * is the only reason it was caught: the first attempt at this fixed the unused array and
	 * changed nothing on screen.
	 *
	 * `synthesized` is empty on this build by construction — a fitted type with member
	 * observations renders no synthetic copy — so sorting by share is also what stops an
	 * unreachable class from being introduced first. It stays in the list because a build *can*
	 * emit it; it just goes where its weight puts it. Ties keep declaration order, which is
	 * class strength, so an unloaded corpus still reads sensibly.
	 */
	const provFilterOrder = $derived(
		[
			PROVENANCE.documented,
			PROVENANCE.learned,
			PROVENANCE.field,
			PROVENANCE.unlabelled,
			PROVENANCE.candidate
		].sort((a, b) => (provShare[b] ?? 0) - (provShare[a] ?? 0))
	);
	/** What the running chorus was last pooled from. Not state: only that effect reads it. */
	let pooled: { rate: number; allowed: unknown; songs: unknown } = {
		rate: NaN,
		allowed: null,
		songs: null
	};
	$effect(() => {
		// Tempo is one control over the whole aviary: the drift, the pulse, how long each
		// syllable lasts and how often a bird starts. Restarting the scheduler is what
		// applies the new arrival rate.
		//
		// **This used to re-implement both chorus starts inline** — the solo pool, the global
		// pool, the improvise special case and a re-check after the corpus fetch — so there
		// were two copies of "how a chorus begins" and they had already drifted (this one
		// passed the confidence filter to the aviary; `setChorus` did not). Re-pooling is a
		// re-entry into the mode already running, which is exactly the event `setChorus` is:
		// the reducer re-emits the start command and the executor is the single copy.
		//
		// Only when one of the pool's inputs moved. A start is issued by the reducer already,
		// and this effect used to read `perf` too, so every dispatch of any kind restarted the
		// scheduler and, for the aviary, fetched the whole inventory again.
		const rate = tempo;
		const allowed = chorusConfidence;
		const songs = soloSongIds;
		if (engine) engine.tempo = rate;
		const moved = rate !== pooled.rate || allowed !== pooled.allowed || songs !== pooled.songs;
		pooled = { rate, allowed, songs };
		if (!moved || untrack(() => perf.chorus) === 'off') return;
		// **Re-issue the start command; do not dispatch a transition.** Re-pooling is not a
		// state change, and routing it through `setChorus` moved the epoch — which invalidated
		// the very start command the transition had just emitted, because that one was still
		// awaiting a species shard. Measured: the solo chorus voiced 1 sample in 56 where it
		// had managed 18. The epoch exists to discard *superseded* work, so a re-pool has to
		// carry the current one.
		untrack(() =>
			perf.chorus === 'global'
				? void perform({ k: 'startGlobal', epoch: perf.epoch })
				: void perform({ k: 'startSolo', speciesId: perf.speciesId, epoch: perf.epoch })
		);
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

	// --- Words: the functional reading ------------------------------------------------
	// The chain is two links with different evidence, and the interface shows both:
	// typed English -> category is ours and always `invented`; category -> this species'
	// call is the corpus's and carries the call's own confidence and citations
	// (`lang/functions.ts` opens with why). `categoryOverride` is set only by the user
	// clicking a different category, and it is cleared whenever the text or the bird
	// changes — an override is a correction of *this* reading, not a standing preference.
	let categoryOverride = $state<FunctionCategory | null>(null);
	const autoReading = $derived(text.trim() ? classify(text) : null);
	const readCategory = $derived<FunctionCategory | null>(
		categoryOverride ?? autoReading?.category ?? null
	);
	const readCalls = $derived(
		assets && currentSpecies && readCategory ? callsFor(assets.inventory, speciesId, readCategory) : []
	);
	const speciesHasFunctions = $derived(assets ? speciesWithFunctions(assets.inventory) : new Set<string>());
	const speciesCategories = $derived(
		assets && currentSpecies ? categoriesFor(assets.inventory, speciesId) : []
	);
	const readRefusal = $derived(
		assets && currentSpecies && text.trim() && !readCalls.length
			? refusal(assets.inventory, speciesId, categoryOverride ? { category: categoryOverride, matched: [], alternatives: [] } : autoReading)
			: null
	);
	const readIntensity = $derived(readCategory ? intensityNote(speciesId, readCategory) : null);
	$effect(() => {
		// Depend on both so either one clears a stale override.
		text;
		speciesId;
		categoryOverride = null;
	});

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
	$effect(() => {
		accent.birdId = currentSpecies?.id ?? '';
	});
</script>

<!--
	**There is no `<svelte:head>` in this file, and that is not an omission.**

	`+layout.ts` sets `ssr = false`, so `<svelte:head>` is never rendered into the prerendered
	document. A full head block written here — title, canonical, OG card, JSON-LD — produced a
	built `index.html` with no title at all: invisible to every crawler that does not execute
	JavaScript, with nothing failing to say so. Every SEO surface therefore lives in `src/app.html`,
	which is the one file emitted verbatim, and `npm run verify:seo` reconciles its figures against
	the shipped manifest.

	The `<noscript>` fallback moved there for the same reason.
-->

<!-- The one measurement the layout branches on. See `NARROW_PX`. -->
<svelte:window bind:innerWidth={winW} />

<!--
	The live figures, defined once: the header on a bench, the Reading drawer on a phone.
	Figures about the build (points, knots, map quality) are in the Statistics panel.
-->
{#snippet liveReadings()}
	{#if assets}
		<div><dt>voices</dt><dd>{voices}</dd></div>
		<div><dt>pitch</dt><dd>{pitch > 20 ? Math.round(pitch) : '—'}<span class="unit">Hz</span></dd></div>
		<div class="meter" title="How closely the sound matches a knot in the map.">
			<dt>match</dt>
			<dd>
				<span class="level"><span style:width={`${strength * 100}%`}></span></span>
			</dd>
		</div>
	{/if}
{/snippet}

<!--
	A drawer's lid: the grab bar every phone reader already knows, the drawer's name where the
	panel has no header of its own, and a close that is a real target rather than a hairline ×.

	The whole bar is the button, for the reason the fold headers in the Display panel are
	buttons — "minimize when clicking in it anywhere" is the owner's rule for this app's panels,
	and a drawer on a phone is the case where it matters most, because the alternative is
	hunting a 12 px glyph with a thumb.
-->
{#snippet sheetHandle(title: string)}
	<button class="sheethead" onclick={closeSheet} aria-label="Close this panel">
		<i class="grabber" aria-hidden="true"></i>
		{#if title}<span class="axis mono sheetname">{title}</span>{/if}
		<span class="sheetx" aria-hidden="true">close</span>
	</button>
{/snippet}

{#if loadError}
	<div class="centred">
		<div class="card">
			<h1>Lyrebird needs its galaxy built</h1>
			<p>{loadError}</p>
			<p>
				The 3D map, the cluster centroids and the syrinx calibration table are generated offline by
				the Python pipeline. From the repository root:
			</p>
			<pre class="mono">cd pipeline
uv sync
uv run lyrebird-pipeline build</pre>
			<p class="faint">That writes <code>app/static/lyrebird/</code>. Reload afterwards.</p>
		</div>
	</div>
{:else if !assets}
	<!--
		**The first load is slow enough that a single grey line reads as a failure** (owner,
		2026-08-06: "at the start it takes a while till the first load, it looks like a mistake").

		It is slow for a reason nothing was saying: this build ships about 60 MB of asset —
		444 213 points, 15 341 knots, an inventory, two binary sidecars — and every byte of it is
		fetched and parsed in the browser, because there is no server here to do it (`ssr = false`,
		`adapter-static`). So the wait is real work rather than a stall, and the screen now says
		which of the ten stages it is on.

		Same materials as the rest of the interface and no new ones: the brand block from the HUD,
		the `axis mono` label the panels use for their headers, and a rule-thin bar in the signal
		colour. The mark spins slowly — the one moving thing, so "working" is visible without a
		spinner ornament — and the stage list is the loader's own `LOAD_STAGES`, so the words here
		cannot drift from the steps they name.
	-->
	<div class="centred">
		<div class="loading">
			<img class="loadmark" src={favicon} alt="" width="44" height="44" />
			<div class="loadtext">
				<h1>Lyrebird</h1>
</div>
			<div class="loadbar" role="progressbar" aria-valuenow={loadDone} aria-valuemin="0" aria-valuemax={loadTotal}>
				<span style:width={`${(loadTotal ? loadDone / loadTotal : 0) * 100}%`}></span>
			</div>
			<p class="axis mono loadstage">{loadStage}</p>
		</div>
	</div>
{:else}
	<div class="bench" style:--hud-h={`${hudH}px`}>
		<header class="hud" bind:clientHeight={hudH}>
		<div
				class="brand"
				title="{assets.points.n.toLocaleString()} syllables measured from wild recordings, {assets.centroids.items.length.toLocaleString()} call types, and a physical syrinx model that sings them in this browser. No audio is sampled or shipped."
			>
				<i class="brandmark" aria-hidden="true"></i>
				<h1>Lyrebird</h1>
			</div>
			<!-- The figures render in the Reading drawer on a phone; the two page doors stay here. -->
			<dl class="readings mono">
				{#if !narrow}{@render liveReadings()}{/if}
				<button
					class="reading-open"
					class:on={page === 'info'}
					aria-pressed={page === 'info'}
					title="The paper, and what every mark on the stage means."
					onclick={() => openPage('info')}
				>
					Info
				</button>
				<!-- A learning run outlives any selection, so its clock shows here on the opener. -->
				<button
					class="reading-open"
					class:on={page === 'learn'}
					aria-pressed={page === 'learn'}
					title="Harvest, fit and rebuild, and every fitted syllable type."
					onclick={() => openPage('learn')}
				>
					Learn
					{#if jobRunning}
						<span class="joblive" aria-hidden="true"></span>{job?.seconds ?? 0}s
					{/if}
				</button>
			</dl>
			<!-- The loudness of what is sounding, as a line under the header, in the accent. -->
			<span class="pulse" aria-hidden="true" bind:this={pulseEl}></span>
		</header>

		<!--
			The drawer's own size, handed to the stage as padding. See `sheetH` for why the
			picture gives the room rather than being covered by it.
		-->
		<div
			class="stage-wrap"
			style:--sheet-h={narrow && sheetH ? `${sheetH}px` : '0px'}
			style:--sheet-w={narrow && sheetW ? `${sheetW}px` : '0px'}
		>
			{#key galaxyVersion}
			<Galaxy
				{assets}
				{signal}
				{pointSize}
				{spin}
				{focus}
				{spread}
				paused={page !== ''}
				speed={tempo}
				labels={showLabels}
				plain={!provColours}
				{birdColours}
				adaptive={adaptiveDetail}
				unheard={unheardFigure}
				{trustAgree}
				{trustSnr}
				{detailCeiling}
				selectedSpecies={focus >= 0 ? (currentSpecies?.id ?? '') : ''}
				{provShown}
				pinned={pinnedCluster}
				frame={frameNodes}
				learning={learningClusters}
				stats={galaxyStats ?? undefined}
				onpick={pickCluster}
				onbackground={backgroundClicked}
				bind:knotSpacing
			/>

		<!--
			A page over the stage, not a panel beside it.
			Grid-ruled like the cloud it replaces, so opening it reads as turning the same
			instrument over rather than leaving it. Two columns at width: the paper and the
			summary read as prose, the legend reads as a reference, and neither has to be
			scrolled past to reach the other.
		-->
		{#if page === 'info'}
			<InfoPage
				{assets}
				{axes}
				{projQuality}
				{faithfulness}
				{coverage}
				{corpusHealth}
				{sourceMix}
				{matchFloor}
				{matchCeiling}
				{fittedTypes}
				loadedTypes={inventoryRows.length}
				{knotOverlap}
				{mapDir}
				onclose={() => (page = '')}
			/>
		{/if}

		{#if page === 'learn'}
			<LearnPage
				{assets}
				{pipeline}
				{pipelineStatus}
				{pipelineChecked}
				{pipelineBusy}
				{pipelineWaited}
				{job}
				{jobRunning}
				{jobDoing}
				{learningSpecies}
				{species}
				{speciesColourOf}
				{coverage}
				{corpusHealth}
				{relationHeadline}
				{reloading}
				{inventoryRows}
				{soundingRow}
				{runPipeline}
				{refreshPipeline}
				startGraceSeconds={PIPELINE_START_GRACE_S}
				onpick={pickRow}
				onclose={() => (page = '')}
			/>
		{/if}
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
				<!--
					**Two icon buttons, not one panel with a performance section inside it.**

					The frame cost is a different KIND of thing from every other control here: those
					change what the picture says, this one reports what drawing it costs. It sat as a
					checkbox at the bottom of the display panel, which meant reading the frame rate
					required opening the panel that was covering the thing whose frame rate you wanted.
					Owner, 2026-08-06: "the costs should be its own icon besides the view".
				-->
				<div class="viewbtns">
					<button
						class="viewbtn"
						class:open={viewOpen}
						aria-label="Display settings"
						aria-expanded={viewOpen}
						onclick={toggleView}
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
					<!-- Three ascending bars: a measurement, not a setting. -->
					<button
						class="viewbtn"
						class:open={costOpen}
						aria-label="What this costs"
						aria-expanded={costOpen}
						title="Frame rate, how many points and tags the stage actually drew, and which GPU the browser gave us."
						onclick={toggleCost}
					>
						<svg viewBox="0 0 16 16" width="15" height="15" aria-hidden="true">
							<path
								d="M3 13V9.5M8 13V6M13 13V3.5"
								stroke="currentColor"
								stroke-width="1.5"
								stroke-linecap="round"
							/>
						</svg>
					</button>
				</div>
				{#if viewOpen}
					<div
						class="panel viewpanel"
						class:sheet={narrow}
						bind:clientHeight={sheetH}
						bind:clientWidth={sheetW}
					>
						{#if narrow}{@render sheetHandle('display')}{/if}
						<h2>Display</h2>
						<div class="cardbody">
							<section class="block fold" class:shut={!viewFold.view}>
								<button class="foldhead" aria-expanded={viewFold.view} onclick={() => (viewFold.view = !viewFold.view)}>
									<span class="axis mono">view</span>
									<i class="chev" aria-hidden="true"></i>
								</button>
								{#if viewFold.view}
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
										<label
											class="check"
											title="Hold the level of detail back when the measured frame time says the GPU cannot keep up. On an integrated chip this is what keeps the close view smooth."
										>
											<input type="checkbox" bind:checked={adaptiveDetail} /> Adaptive detail
										</label>
									</div>
									{#if adaptiveDetail}
										<label class="field indent">
											<span class="lbl"
												>Density ceiling <b class="mono">{Math.round(detailCeiling * 100)}%</b></span
											>
											<input
												type="range"
												min="0.1"
												max="1"
												step="0.05"
												bind:value={detailCeiling}
												title="The most of the corpus the governor may draw when frames are cheap. It may still draw less than this when they are not — the Statistics panel reports what it settled on."
											/>
										</label>
									{/if}
								{/if}
							</section>
							<section class="block fold" class:shut={!viewFold.colour}>
								<button class="foldhead" aria-expanded={viewFold.colour} onclick={() => (viewFold.colour = !viewFold.colour)}>
									<span class="axis mono">colour</span>
									<i class="chev" aria-hidden="true"></i>
								</button>
								{#if viewFold.colour}
									<div class="checks">
										<label
											class="check"
											title="Colour every point and path by where its sound came from. Nearly all points are field recordings, so one class dominates."
										>
											<input type="checkbox" bind:checked={provColours} onchange={useProvColours} />
											Provenance colours
										</label>
										<label
											class="check"
											title="Colour every point by its bird. Hue is the genus, shade the species."
										>
											<input type="checkbox" bind:checked={birdColours} onchange={useBirdColours} />
											Bird colours
										</label>
										<!-- The two doubts may be on together; `palette.ts` has the arithmetic. -->
										<label
											class="check"
											title="Colour every point and path by how few of its ten drawn neighbours share its type. Combines with the noise ramp."
										>
											<input
												type="checkbox"
												bind:checked={trustAgree}
												disabled={trustStats === null}
												onchange={useDoubtColour}
											/>
											<i class="swatch ramp agree" class:hollow={!trustAgree}></i>
											Neighbours disagree
										</label>
										<label
											class="check"
											title="Colour every point and path by how noisy its recording was. Combines with the neighbour ramp."
										>
											<input
												type="checkbox"
												bind:checked={trustSnr}
												disabled={snrStats === null}
												onchange={useDoubtColour}
											/>
											<i class="swatch ramp snr" class:hollow={!trustSnr}></i>
											Recording is noisy
										</label>
									</div>
									<!-- A clamped ramp needs its ends named, or "rose" reads as a category. -->
									{#if trustAgree && trustStats}
										<p class="note faint rampkey">
											<b style:color={DOUBT_AGREE}>disagrees</b> → <b style:color={DOUBT_QUIET}
												>agrees</b
											>
											· mean <b>{(trustStats.mean * 100).toFixed(0)} %</b>,
											<b>{trustStats.alone.toLocaleString()}</b> among ten strangers
										</p>
									{/if}
									{#if trustSnr && snrStats}
										<p class="note faint rampkey">
											<b style:color={DOUBT_SNR}>noisy</b> → <b style:color={DOUBT_QUIET}>clean</b>
											· <b>{snrStats.lo.toFixed(1)}</b>–<b>{snrStats.hi.toFixed(1)} dB</b> (p5–p95),
											{snrStats.absent.toLocaleString()} unmeasured
										</p>
									{/if}
									{#if trustAgree && trustSnr}
										<p class="note faint rampkey">
											Both: the darkest marks are the ones where the map is unsure <i>and</i> the
											recording was poor.
										</p>
									{/if}
								{/if}
							</section>
							<!-- Hiding a class removes its points from the picture, never from the corpus. -->
							<section class="block fold" class:shut={!viewFold.filter}>
								<button class="foldhead" aria-expanded={viewFold.filter} onclick={() => (viewFold.filter = !viewFold.filter)}>
									<span class="axis mono">sources</span>
									{#if hiddenClasses > 0}
										<span class="mono faint tally">{hiddenClasses} hidden</span>
									{/if}
									<i class="chev" aria-hidden="true"></i>
								</button>
								{#if viewFold.filter}
									<div class="checks">
										{#each provFilterOrder as cls (cls)}
											{@const share = provShare[cls] ?? 0}
											<label class="check" class:absent={share === 0}>
												<input type="checkbox" bind:checked={provShown[cls]} disabled={share === 0} />
												<i
													class="swatch"
													class:hollow={!provColours}
													style:background={provColours ? provenanceColour(cls) : 'transparent'}
												></i>
												{PROV_NAMES[cls]}
												<span class="mono faint"
													>{share === 0
														? '—'
: `${(share * 100).toFixed(share < 0.01 ? 2 : 0)}%`}</span
												>
											</label>
										{/each}
									</div>
									{#if hiddenClasses > 0}
										<button
											class="link"
											onclick={() => {
												provShown = [true, true, true, true, true];
											}}>show everything</button
										>
									{/if}
								{/if}
							</section>
							<!-- Joined from a separate density clustering, since this map assigns every point. -->
							<section class="block fold" class:shut={!viewFold.unclaimed}>
								<button
									class="foldhead"
									aria-expanded={viewFold.unclaimed}
									onclick={() => (viewFold.unclaimed = !viewFold.unclaimed)}
								>
									<span class="axis mono">unclaimed</span>
									{#if unheardShare !== null}
										<span class="mono faint tally">{(unheardShare * 100).toFixed(1)} %</span>
									{/if}
									<i class="chev" aria-hidden="true"></i>
								</button>
								{#if viewFold.unclaimed}
									<div class="checks">
										<label
											class="check"
											title="A second clustering placed {placedCount?.toLocaleString() ?? 'some'} of these sounds in a dense region and refused {unheardCount?.toLocaleString() ?? 'the rest'}. Coloured marks are placed, faint marks are unclaimed."
										>
											<input type="checkbox" bind:checked={unheardFigure} disabled={unheardShare === null} />
											<i
												class="swatch"
												class:hollow={!unheardFigure}
												style:background={unheardFigure ? UNCLAIMED_TINT : 'transparent'}
											></i>
											Mark the dense regions
										</label>
									</div>
									{#if unheardFigure}
										<p class="note faint rampkey">
											Coloured: in a dense region. Faint: unclaimed.
										</p>
									{/if}
								{/if}
							</section>
						</div>
					</div>
				{/if}
				{#if costOpen}
					<div
						class="panel viewpanel statspanel"
						class:sheet={narrow}
						bind:clientHeight={sheetH}
						bind:clientWidth={sheetW}
					>
						{#if narrow}{@render sheetHandle('statistics')}{/if}
						<h2>Statistics</h2>
						<div class="cardbody">
							<section class="block">
								<p class="axis mono">the frame</p>
								{#if cost}
									<dl class="cost mono">
										<div>
											<dt>rate</dt>
											<dd>{cost.fps.toFixed(0)} fps · {cost.frameMs.toFixed(1)} ms</dd>
										</div>
										<div>
											<dt>drawn</dt>
											<dd
												title="The level of detail's answer, not the corpus size: back away and the cloud draws one point per knot."
											>
												{cost.pointsDrawn.toLocaleString()} of {cost.pointsTotal.toLocaleString()} points{#if cost.pointsResponding > 0}
													· {cost.pointsResponding.toLocaleString()} responding{/if}{#if cost.pointsRevealed > 0}
												· {cost.pointsRevealed.toLocaleString()} revealed{/if}
											</dd>
										</div>
										<div>
											<dt>detail</dt>
											<dd>
												<!-- stats.lod is the continuous frontier (0..1 of the corpus), not a level -->
												{cost.lod < 0 ? 'settling' : `${Math.round(cost.lod * 100)} % of the points`}
											</dd>
										</div>
										{#if cost.densityCap < 0.99}
											<div>
												<dt>held</dt>
												<!-- Two reasons the cap can be below 1 and they are different facts: the reader
												     set a ceiling, or the frame timer took one. Saying "for framerate" in the
												     first case would blame the GPU for the reader's own slider. -->
												<dd>
													at {Math.round(cost.densityCap * 100)} %
													{detailCeiling < 0.99 && cost.densityCap >= detailCeiling - 0.02
														? 'by the density ceiling'
														: 'for framerate'}
												</dd>
											</div>
										{/if}
										<div>
											<dt>tags</dt>
											<dd>{cost.tagsDrawn} of {cost.clusters.toLocaleString()} knots</dd>
										</div>
										<div>
											<dt>gpu</dt>
											<dd
												class="gpu"
												title="If this names an integrated chip on a machine that has a discrete one, the browser chose it, and the fill rate is a fraction of what it could be."
											>
												{cost.renderer || 'not reported'}
											</dd>
										</div>
									</dl>
								{:else}
									<p class="note faint">Waiting for the first frame.</p>
								{/if}
							</section>
							<section class="block">
								<p class="axis mono">the corpus</p>
								<dl class="cost mono">
									<div>
										<dt>sounds</dt>
										<dd>{assets.points.n.toLocaleString()}</dd>
									</div>
									<div>
										<dt>knots</dt>
										<dd>{assets.centroids.items.length.toLocaleString()} call types</dd>
									</div>
									<div>
										<dt>map</dt>
										<dd
											title={assets.manifest.clustering === 'label'
												? 'One knot per type, taken from the type each sound already carries. The knots are the labels, not a second finding, so this view cannot report an unidentified sound.'
												: mapKind === 'known'
													? 'One knot per type, every sound assigned. This view cannot report an unidentified sound.'
													: 'Dense regions only. Sounds in no region are unidentified: real acoustics, no documented function.'}
										>
											{assets.manifest.clustering === 'label'
												? 'knots are the labels'
												: mapKind === 'known'
													? 'one knot per type'
													: `dense regions, ${assets.manifest.unassigned?.toLocaleString() ?? 'some'} unassigned`}
										</dd>
									</div>
									{#if faithfulness !== undefined}
										<div>
											<dt>distance</dt>
											<dd title="Correlation between distances on screen and in the feature space.">
												r {faithfulness.toFixed(3)}
											</dd>
										</div>
									{/if}
									{#if assets.featureSpace.embedding?.mapQuality?.centroidAgreement !== undefined}
										{@const mq = assets.featureSpace.embedding.mapQuality}
										<div>
											<dt>live</dt>
											<dd
												title="How often a live sound lights the same knot through the browser's map as through the critic. Knot-level answers mean nearest of several close knots."
											>
												knot {((mq.centroidAgreement as number) * 100).toFixed(0)} %{#if mq.speciesAgreement !== undefined}
													· species {((mq.speciesAgreement as number) * 100).toFixed(0)} %{/if}
											</dd>
										</div>
									{/if}
{#if trustStats}
										<div>
											<dt>agree</dt>
											<dd
												title="Averaged over every point: how many of its ten nearest marks on screen share its type. Chance on this corpus is far under one percent."
											>
												{(trustStats.mean * 100).toFixed(0)} % of neighbours ·
												{trustStats.alone.toLocaleString()} alone
											</dd>
										</div>
									{/if}
									{#if unheardShare !== null}
										<div>
											<dt>dense</dt>
											<dd
												title="How many of these same points a second, independent density clustering placed in a region. This map places everything by the type it already carries, so it cannot answer that itself."
											>
												{placedCount?.toLocaleString()} in a region ·
												{unheardCount?.toLocaleString()} unclaimed
											</dd>
										</div>
									{/if}
								</dl>
							</section>
						</div>
					</div>
				{/if}
			</div>

			{#if history.length}
				<!--
					The rendered list freezes while the pointer is inside, because the newest chip shifts
					every other one and a click would otherwise land on whatever slid under the cursor.
				-->
				<div
					class="history"
					class:tucked={sheetOpen}
					role="group"
					aria-label="Phrases already sung — select one to go back to it"
					onpointerenter={() => (historyFrozen = true)}
					onpointerleave={() => (historyFrozen = false)}
				>
					{#each shownHistory as entry (entry.id)}
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

			<div class="leftcol">
			{#if !narrow || sheet === 'reading'}
			<aside
				class="panel readout"
				class:sheet={narrow}
				bind:clientHeight={sheetH}
				bind:clientWidth={sheetW}
			>
				{#if narrow}{@render sheetHandle('')}{/if}
				<h2>
					Reading
					{#if selectedSung !== null || pinnedCluster >= 0}
						<button class="link" onclick={clearSelection}>clear selection</button>
					{/if}
				</h2>
				<div class="cardbody">
				{#if narrow}
					<dl class="readings mono inpanel">{@render liveReadings()}</dl>
				{/if}
				{#if pinned}
					<section class="block">
						<div class="pinhead">
							<span class="badge {pinned.confidence}">{confidenceLabel(pinned.confidence).text}</span>
							<button
								class="link"
								onclick={() => dispatch({ k: 'pickKnot', knot: pinnedCluster, speciesId: '' })}
								>Unpin</button
							>
						</div>
						<p class="strong">{pinned.label}</p>
						{#if pinned.function}<p class="note">{pinned.function}</p>{/if}
						<dl class="facts mono">
							<div><dt>points</dt><dd>{pinned.count}</dd></div>
							{#if pinned.cohesion !== undefined}<div><dt>cohesion</dt><dd>{pinned.cohesion.toFixed(3)}</dd></div>{/if}
							{#if pinned.meanDuration}<div><dt>duration</dt><dd>{Math.round(pinned.meanDuration * 1000)} ms</dd></div>{/if}
							{#if pinned.functionClass}<div><dt>class</dt><dd>{pinned.functionClass}</dd></div>{/if}
							<!-- Whether the mark is in one piece. Unmeasured is printed as unmeasured. -->
							<div>
								<dt>drawn in</dt>
								<dd>
									{#if pinned.tearing === undefined}
										not measured
									{:else if pinned.tearing > 5}
										two places
									{:else}
										one place
									{/if}
								</dd>
							</div>
						</dl>
					</section>
				{/if}
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
						<h3 class="strong">Off the map</h3>
						<p class="accent">Positions are guesses. Nothing here is a documented call.</p>
<p
							class="note faint"
							title={assets.featureSpace.embedding?.sessionGate?.calibration ?? ''}
						>
							Score {sessionGate.score.toFixed(2)}, line {sessionGate.threshold.toFixed(2)}.
						</p>
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
							<details class="rollup">
								<summary class="mono faint">sources</summary>
								<ul class="refs">
									{#each citationsFor(assets.inventory, best.centroid.refs) as ref (ref)}
										<li class="note faint">{ref}</li>
									{/each}
								</ul>
							</details>
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
							<!-- A shared call shape is a candidate, never a documented relationship (§8.5). -->
							<p
								class="note faint"
								title="Measured in the embedding. Candidates, not documented relationships."
							>
								Similar calls: {rels
									.map((p) => relationPartner(p, best.centroid.speciesId))
									.join(', ')} (candidates)
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
						<h3 class="strong">Not in this corpus</h3>
<p class="accent">unlabelled: real acoustics, no documented function</p>
						{#if nearest}
							<p class="note faint">
								Nearest: {nearest.centroid.label}, {(nearest.similarity * 100).toFixed(0)} %, below the
								match floor.
							</p>
						{/if}
					</div>
				{:else if lastPhrase}
					<div class="best">
						<!-- Two badges, because a phrase makes two claims and they can disagree.
						     The first is about the sounds (how strong the documented function is),
						     the second about the order (whether any bird sang this sequence). An
						     improvisation is 'unlabelled' + 'invented': real audio, our bout. One
						     badge alone printed "field recording" over a phrase nobody has sung. -->
						<span class="badge {lastPhrase.confidence}">
							{confidenceLabel(lastPhrase.confidence).text}
						</span>
						{#if sourceLabel(lastPhrase.source)}
							<span class="badge invented" title={sourceLabel(lastPhrase.source)?.hint}>
								{sourceLabel(lastPhrase.source)?.text}
							</span>
						{/if}
						<h3 class="strong">{lastPhrase.label}</h3>
						{#if singer}<p class="accent">sung by {singer}</p>{/if}
						<p class="accent">“{lastPhrase.gloss}”</p>
						<p class="note">{lastPhrase.function}</p>
						{#if lastPhrase.note || lastPhrase.refs.length}
							<details class="rollup">
								<summary class="mono faint">sources</summary>
								{#if lastPhrase.note}<p class="note faint">{lastPhrase.note}</p>{/if}
								{#if lastPhrase.refs.length}
									<ul class="refs">
										{#each citationsFor(assets.inventory, lastPhrase.refs) as ref (ref)}
											<li class="note faint">{ref}</li>
										{/each}
									</ul>
								{/if}
							</details>
						{/if}
					</div>
				{:else if namedTypes === 0}
					<!-- A field-only build has no named cluster, so nothing can light. Say so instead of looking broken. -->
					<p class="note">
						This build has no named clusters, so a sung phrase cannot light anything. Rebuild it with
						the inventory on the Learn page.
					</p>
				{:else if voices > 0}
					<p class="note quiet">
						{singer ?? 'A bird'} is singing. Rendered from its inventory, so nothing is being matched.
					</p>
				{:else}
					<p class="note faint quiet">Nothing sounding.</p>
				{/if}
				{#if panelReading?.best || reading?.active || lastPhrase}
					<!-- The standing caveat, one click away while there is a claim for it to qualify. -->
					<details class="rollup caveat">
						<summary class="mono faint">what this can claim</summary>
						<p class="note faint">
							{reading?.caveat ??
								'Lyrebird reports documented call functions with a confidence label. Machine learning can characterise repertoires and link calls to behaviour. It cannot translate them into sentences.'}
						</p>
					</details>
				{/if}
				</div>
			</aside>
			{/if}

			<!--
				On a phone the dock along the bottom is this panel's tab strip, so the strip inside
				it is hidden and the panel is mounted only for the tab the dock chose. Mounted, not
				merely hidden: an unmounted Compose tab is a canvas and two indexes the phone does
				not have to keep.
			-->
			{#if !narrow || (sheet !== '' && sheet !== 'reading')}
			<aside
				class="panel controls"
				class:sheet={narrow}
				bind:clientHeight={sheetH}
				bind:clientWidth={sheetW}
			>
			{#if narrow}{@render sheetHandle(DOCK.find((d) => d.key === sheet)?.label ?? '')}{/if}
			<!-- Three, and all three are ways of making or hearing a sound. Learn was the odd
			     one and is a page off the header now. -->
			<nav class="tabs">
				<button class:active={tab === 'sing'} onclick={() => (tab = 'sing')}>Sing</button>
				<button class:active={tab === 'words'} onclick={() => (tab = 'words')}>Compose</button>
				<button class:active={tab === 'listen'} onclick={() => (tab = 'listen')}>Listen</button>
			</nav>

			<div class="tabbody">
				{#if tab === 'sing'}
					<section class="block">
						<div class="field">
							<SpeciesPicker
								options={speciesOptions}
								value={speciesId}
								onchange={chooseBird}
							/>
						</div>
						{#if currentSpecies}
							<p class="note">{currentSpecies.summary}</p>
							{#if assets.relations}
								{@const rels = relationsOf(currentSpecies.id, 6)}
								{#if rels.length}
									<!-- A shared call shape is a distance, never a claim of kinship (§8.5). -->
									<p
										class="note faint sounds-like"
										title="Nearer than two types of one bird usually are. A distance, not a claim of borrowing or kinship."
									>
										Sounds like
{#each rels as p (p.a + '/' + p.b)}
											{@const partner = p.a === currentSpecies.id ? p.b : p.a}
											<button
												class="chip"
												style:color={speciesColourOf(partner)}
												title="Select {relationPartner(p, currentSpecies.id)}"
												onclick={() => chooseBird(partner)}
											>{relationPartner(p, currentSpecies.id)}</button>
										{/each}
									</p>
								{/if}
							{/if}
							<label class="field">
								<span class="lbl">
									Call
									{#if songCoverage && songCoverage.placed < 2}
										<span class="tally mono none" title={songCoverageHint}>not on the map</span>
									{/if}
								</span>
								<select value={songId} onchange={(e) => chooseSong(e.currentTarget.value)}>
									<option value="">{allSongsOption}</option>
									{#each songs as s (s.id)}
										<option value={s.id}>{songOption(s)}</option>
									{/each}
								</select>
							</label>
							<div class="row">
								<button
									class="primary"
									disabled={!engine || !songs.length}
									onclick={sing}
									title={currentSong
										? 'Play the chosen call once.'
										: 'Play one of this bird’s calls once — drawn at random, the way the chorus draws. Choose a call above to fix which.'}
									>Sing once</button
								>
								<button
									disabled={!engine}
									onclick={singImprovisation}
									title={grammarCoverage
										? `Walk this bird's measured grammar — the transitions fitted to its own field recordings. ${grammarCoverage.placed} of its ${grammarCoverage.total} fitted types won a cluster, so the thread shows those and skips the rest.`
										: "Walk this bird's measured grammar — the transitions fitted to its own field recordings."}
								>
									Improvise once
								</button>
							</div>
							<!-- Two claims about what is heard: its repertoire, or phrases sampled from its grammar.
							     Each stops the chorus when it is the one already running. -->
							<span class="lbl">Keep singing</span>
							<div class="segmented">
								<button
									class:on={chorus === 'solo' && soloMode === 'songs'}
									disabled={!engine}
									onclick={() => dispatch({ k: 'pressSolo', mode: 'songs' })}
									title="Three individuals of this bird answer each other, drawing from its repertoire."
									>Songs</button
								>
								<button
									class:on={chorus === 'solo' && soloMode === 'improvise'}
									disabled={!engine}
									onclick={() => dispatch({ k: 'pressSolo', mode: 'improvise' })}
									title="The same three voices, walking this bird's measured grammar. Every phrase is sampled fresh."
									>Improvised</button
>
							</div>
						{:else}
							<div class="row">
								<button
									class:on={chorus === 'global'}
									disabled={!engine}
									onclick={() => toggleChorus('global')}
									title="The whole aviary at once. Press again to stop."
								>
									Chorus
								</button>
							</div>
						{/if}
						{#if chorus !== 'off'}
							<!-- Songs by claim strength, a different axis and population from the Display sources. -->
							<details class="rollup">
								<summary class="mono faint">which songs</summary>
								<div class="checks column">
									{#each ['documented', 'synthesized', 'recorded'] as cls (cls)}
										{@const have = chorusClassSongs === null ? null : chorusClassSongs.counts[cls]}
										{@const settled = chorusClassSongs !== null && !chorusClassSongs.partial}
										{#if !(settled && have === 0)}
											<label
												class="check"
												title={cls === 'documented'
													? 'Songs described in the literature or established by playback.'
													: cls === 'synthesized'
														? 'Our own ordering of syllables fitted from recordings. Not a claim about real birds.'
														: 'Songs with no documented function attached.'}
											>
												<input type="checkbox" bind:checked={chorusClasses[cls]} />
												{cls === 'documented'
													? 'From the literature'
													: cls === 'synthesized'
														? 'Our arrangement'
														: 'Unlabelled audio'}
												{#if have}<span class="mono faint">{have}</span>{/if}
											</label>
										{/if}
									{/each}
								</div>
							</details>
						{/if}
					</section>

					<section class="block">
						<div class="sliders two">
							<label class="field">
								<span class="lbl">Distance <b class="mono">{distance.toFixed(2)}</b></span>
								<input
									type="range"
									min="0"
									max="1"
									step="0.01"
									bind:value={distance}
									title="How far away the birds sound and look."
								/>
							</label>
							<label class="field">
								<span class="lbl">Volume <b class="mono">{volume.toFixed(2)}</b></span>
								<input type="range" min="0" max="3" step="0.02" bind:value={volume} />
							</label>
							<label class="field">
								<span class="lbl">Tempo <b class="mono">{tempo.toFixed(2)}×</b></span>
								<input
									type="range"
									min="0.1"
									max="2"
									step="0.05"
									bind:value={tempo}
									title="How fast the birds sing. Pitch does not change."
								/>
							</label>
							<label class="field">
								<span class="lbl">Gap <b class="mono">~{songGapSeconds.toFixed(1)} s</b></span>
								<input
									type="range"
									min="0.25"
									max="3"
									step="0.05"
									bind:value={songRate}
									title="Mean pause between songs."
								/>
							</label>
						</div>
					</section>
				{:else if tab === 'words'}
					<section class="block">
						<label class="field">
							<span
								class="lbl"
								title="• marks the {speciesHasFunctions.size} species with a call whose function is described in the literature. The others have measured syllables and no documented function."
								>Species</span
							>
							<select value={speciesId} onchange={(e) => chooseBird(e.currentTarget.value)}>
								{#each species as s (s.id)}
									<option value={s.id}>{speciesHasFunctions.has(s.id) ? '• ' : ''}{s.common}</option>
								{/each}
							</select>
						</label>
						<!--
							Text survives as rhythm only. splitSyllables yields the token count and
							word boundaries; syllable choice comes from the measured grammar, never
							from the words, and fitted contours are never transposed. The documented
							keyword path below is unchanged and still renders the real call.
						-->
						<label class="field">
							<span class="lbl">Words</span>
							<textarea bind:value={text} placeholder="danger — come here"></textarea>
						</label>
						<!-- The reading of the words is ours; each call under it keeps its own evidence badge. -->
						{#if text.trim()}
							<div class="callout reading">
								{#if readCategory}
									<p class="note">
										We read this as <strong>{readCategory}</strong>
										{#if autoReading?.matched.length && !categoryOverride}
											<span class="mono faint">({autoReading.matched.join(', ')})</span>
										{/if}
										<span class="badge invented">{confidenceLabel('invented').text}</span>
									</p>
								{:else}
									<p class="note">No function matches these words.</p>
{/if}
								<p class="note faint">
									Change:
									{#each CATEGORIES as c (c.id)}
										<button
											class="link"
											class:on={readCategory === c.id}
											title="{c.blurb}{speciesCategories.includes(c.id) ? '' : ' — this species has no documented call here'}"
											onclick={() => (categoryOverride = c.id)}
										>{c.label}{speciesCategories.includes(c.id) ? '' : '*'}</button>
									{/each}
								</p>
								<p class="note faint">* no documented call in that category</p>

								{#if readCalls.length}
									{#each readCalls as call (call.song.id)}
										<div class="callout nested">
											<span class="badge {call.confidence}">{confidenceLabel(call.confidence).text}</span>
											<p class="note">
												{call.song.label} — {call.song.function}
											</p>
											{#if call.song.refs.length && assets}
												{#each citationsFor(assets.inventory, call.song.refs) as ref (ref)}
													<p class="note faint">{ref}</p>
												{/each}
											{/if}
											<button
												class="primary wide"
												disabled={!engine}
												onclick={() => singCall(call.song.id)}
												title="Render this call exactly as authored — the composer does not touch it."
											>Sing this call</button>
										</div>
									{/each}
									{#if readIntensity}
										<p class="note faint">{readIntensity}</p>
									{/if}
									<!-- Kept through the cull: this is the claim's own qualifier (docs/08 §8.5). -->
									<p class="note faint">
										The category is the bird's. The assignment of your words to it is ours, and
										these are not words the bird would say.
									</p>
								{:else if readRefusal}
									<p class="note faint">{readRefusal}</p>
								{/if}
							</div>
						{/if}
						{#if preview && preview.source !== 'documented' && !readCalls.length}
							{#if preview.documentedElsewhere?.length}
								<p class="note faint">
									Documented for:
{#each preview.documentedElsewhere as other (other)}
										<button class="link" onclick={() => chooseBird(other)}>
											{assets.speciesCommon(other)}
										</button>
									{/each}
								</p>
							{/if}
						{/if}
						<div class="row">
							<button
								class="primary"
								disabled={!engine || !currentSpecies || !text.trim()}
								onclick={singWordsRhythm}
								title="Only the words' rhythm is used. The syllables are this bird's own."
							>Sing the words</button>
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
									title="Play the strip through the same engine every other phrase here uses. The galaxy draws the thread for the syllables it can place and skips the rest."
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
						{/if}

						<details class="rollup block">
							<summary class="mono faint">build by hand</summary>
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
									title="The same chips, ranked by the transition probabilities counted from this bird's field recordings, with repeated motifs offered whole. Labelled: measured statistics, our ordering."
								>Guided</button>
								<button
									class:on={composeMode === 'types'}
									onclick={() => (composeMode = 'types')}
									title="Orderings this bird was recorded singing, re-expanded into playable bouts. {BOUT_GLOSS} Trill lengths are sampled from the measured repeat rates."
								>Song types</button>
							</div>

						{#if composeMode === 'types'}
							{#if composeTyping}
								<p class="note faint" title={BOUT_GLOSS}>
									{composeTyping.inTypes} of {composeTyping.bouts} bouts fall into {composeTyping.types} types.
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
												title="The measured probability the burst of singing ends here. Sing the strip and start a new one."
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
											? 'No measured transition continues from here.'
: 'No grammar fitted for this bird.'}
</p>
								{/if}
								{#if composeChunks.length}
									<div class="suggestions">
										{#each composeChunks as offer (offer.chunk.sequence.join(' '))}
											<button
												class="suggestion"
												onclick={() => appendChunk(offer.insert)}
												title="A repeated motif mined from the recorded bursts of singing: {offer.chunk.sequence.join(' ')} — heard {offer.chunk.count} times (pmi {offer.chunk.pmi.toFixed(2)}). One click inserts {offer.insert.join(' ')}."
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
								>Improvise</button>
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
						{/if}
						</details>
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
						{:else}
							{#if inputVia === 'monitor'}
								<p class="note faint">Using this computer's monitor device.</p>
							{:else if inputVia === 'display'}
								<p class="note faint">Using the share dialog. Video is discarded.</p>
							{/if}
						{/if}
						<div class="row">
							<button
								class:on={micOn}
								disabled={!engine}
								onclick={toggleMic}
								title="Audio stays on your device."
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
							{#if !pipelineStatus}
								<p class="note faint">Start <span class="mono">lyrebird-pipeline serve</span> to learn from these.</p>
							{/if}
						</section>
					{/if}
				{/if}
			</div>

			{#if rateNote}<p class="note faint pad">{rateNote}</p>{/if}
			{#if audioError}<p class="error note pad">{audioError}</p>{/if}
			</aside>
			{/if}
			</div>
		</div>

		<!--
			**The dock, and it is a row of the bench rather than a bar floating over it.**

			A floating bar would cover the bottom of the galaxy permanently, and the bottom of the
			galaxy is where this app already puts the history strip and the ruler. As a grid row it
			takes its 3.4 rem out of the layout once and the stage is told about it, so nothing is
			ever underneath it — which is the same reason the header is a row and not an overlay.

			Four items, all of them a way of making or hearing a sound, which is the split the tab
			strip already made on the bench. How the picture is drawn stays on the two corner icons
			over the stage, where it is on the bench too: one vocabulary, re-anchored, rather than a
			second one invented for small screens.
		-->
		{#if narrow}
			<nav class="dock" aria-label="Panels">
				{#each DOCK as item (item.key)}
					<button
						class:on={sheet === item.key}
						aria-pressed={sheet === item.key}
						onclick={() => openSheet(item.key)}
					>
						{item.label}
						<!-- A live match, on the closed drawer: the one thing the Reading card says that
						     a reader would want to know without opening it. -->
						{#if item.key === 'reading' && readingIsLive && sheet !== 'reading'}
							<i class="docklive" aria-hidden="true"></i>
						{/if}
					</button>
				{/each}
			</nav>
		{/if}
	</div>

	{#if !engine}
		<div class="centred overlay">
			<div class="card">
				<h1>Enter the aviary</h1>
				<p>Every note is synthesised from a physical model of the syrinx. Nothing is sampled.</p>
				<button class="primary" onclick={enter}>Start listening</button>
				{#if audioError}<p class="error">{audioError}</p>{/if}
			</div>
		</div>
	{/if}
{/if}

<!--
	The pipeline controls, as a snippet.

	A snippet rather than markup in place because the page that renders it is defined
	before the `{:else if !assets}` branches that hold the stage, and a five-hundred-line
	block of range sliders in the middle of the stage's markup buries the stage. It is
	rendered once, from the Learn page.
-->
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
		position: relative;
		padding: 0.6rem 1rem;
		background: var(--paper-raised);
		border-bottom: 1px solid var(--rule);
		z-index: 4;
	}

	.brand {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}

	.brandmark {
		width: 0.7rem;
		height: 0.7rem;
		border-radius: 50%;
		background: var(--signal);
	}

	.hud h1 {
		margin: 0;
		font-size: 1.05rem;
		font-weight: 600;
		letter-spacing: -0.01em;
	}

	/* The loudness of what is sounding, along the header's bottom edge. Scaled, never resized,
	   so it stays on the compositor. `accent.ts` writes the transform. */
	.pulse {
		position: absolute;
		left: 0;
		right: 0;
		bottom: -1px;
		height: 2px;
		background: var(--signal);
		transform: scaleX(0);
		will-change: transform;
		pointer-events: none;
	}

	.readings {
		display: flex;
		align-items: center;
		margin: 0;
		font-size: 0.72rem;
	}

	.readings > div {
		display: flex;
		align-items: baseline;
		gap: 0.4rem;
		padding: 0 0.8rem;
	}

	.readings dt {
		color: var(--ink-faint);
		font-family: var(--font-sans);
		font-size: 0.72rem;
	}

	.readings dd {
		margin: 0;
		min-width: 2.2rem;
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
		align-self: center;
		height: 1rem;
	}

	.stage-wrap {
		position: relative;
		overflow: hidden;
		/**
		 * How much of each edge the stage ruler owns. Everything that floats over the
		 * canvas clears it by this plus its own margin, so a panel never sits on the
		 * scale — and `Ruler` reads the same variable for the band size, so the two
		 * cannot drift apart. Change it here and the whole frame moves together.
		 */
		--ruler: 1.15rem;
	}

	/* --- display settings, on the view itself --- */

	.viewctl {
		position: absolute;
		top: calc(var(--ruler) + 1rem);
		right: 1rem;
		z-index: 4;
		display: grid;
		justify-items: end;
		gap: 0.4rem;
	}

	/* The two openers sit side by side above the panel they open. A row inside the grid
	   rather than two grid children, so `justify-items: end` keeps the pair flush right
	   and the panel below still spans the full width it wants. */
	.viewbtns {
		display: flex;
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

	/* Square, and big enough to hit. The element rule in controls.css gives every button a
	   2.6 rem floor on a touch screen, which on its own would have left these two 2 rem wide
	   and 2.6 rem tall — the one shape an icon button must not be. */
	@media (pointer: coarse) {
		.viewbtn {
			width: max(2.6rem, 44px);
			height: max(2.6rem, 44px);
		}
	}

	/* --- folding sections ---

	   The header is the entire click target, which is what "minimize when clicking in it
	   anywhere" asks for, and it is a button so the fold is keyboard-reachable and
	   announces its own state through aria-expanded. Full width, no button chrome: it has
	   to read as the section heading it replaced, not as a control sitting above one. */
	.foldhead {
		display: flex;
		align-items: baseline;
		gap: 0.4rem;
		width: 100%;
		padding: 0;
		border: 0;
		background: none;
		text-align: left;
		cursor: pointer;
		color: inherit;
	}

	.foldhead:hover .axis,
	.foldhead:focus-visible .axis {
		color: var(--ink-dim);
	}

	/* The share or the hidden count, pushed to the right of the header so a shut drawer
	   still reports the one number that says whether it is doing anything. */
	.foldhead .tally {
		margin-left: auto;
	}

	/* A chevron drawn in borders rather than shipped as an icon: two edges of a square,
	   rotated. Points down when the section is open and right when it is shut, which is
	   the direction the content will appear from. */
	.chev {
		flex: none;
		width: 0.36rem;
		height: 0.36rem;
		border-right: 1px solid var(--ink-faint);
		border-bottom: 1px solid var(--ink-faint);
		transform: rotate(45deg);
		transform-origin: center;
		transition: transform 140ms ease;
	}

	.fold.shut .chev {
		transform: rotate(-45deg);
	}

	/* A shut section is a header and nothing else, so it gives back the padding it was
	   using to separate content that is no longer there. */
	.fold.shut {
		padding-bottom: 0;
	}

	/* Same shell as the display panel — the rule above it sets position and width for both —
	   and it opens under it, so the two read as a stack of cards rather than as one panel with
	   a performance section inside it.

	   No `.cost { margin: 0 }` override here any more. That existed because the `dl` sat
	   directly in `.cardbody` and had to fake its own spacing; it is inside a `section.block`
	   now, which is where every other panel in this app gets its padding and its rules from,
	   so the shared rhythm applies and there is nothing to correct. */
	.statspanel .axis {
		margin-bottom: 0.1rem;
	}

	.viewbtn.open {
		border-color: var(--signal);
		color: var(--signal);
		transition: none;
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

	/* A running job, on the opener, while the galaxy is what you are looking at. */
	.joblive {
		display: inline-block;
		width: 5px;
		height: 5px;
		margin-right: 0.3rem;
		border-radius: 50%;
		background: var(--arrival);
		animation: joblive 1.6s ease-in-out infinite;
	}

	@keyframes joblive {
		0%,
		100% {
			opacity: 0.25;
		}
		50% {
			opacity: 1;
		}
	}

	/* A page door: text until it is open, so the row stays quiet. */
	.reading-open {
		flex: initial;
		margin-left: 0.2rem;
		padding: 0.3rem 0.65rem;
		border: 0;
		background: none;
		font-family: var(--font-sans);
		font-size: 0.8rem;
		font-weight: 500;
		color: var(--ink-dim);
	}

	.reading-open:first-of-type {
		margin-left: 0.8rem;
	}

	.reading-open:hover:not(:disabled) {
		background: var(--paper);
	}

	.reading-open.on {
		background: var(--signal-soft);
		color: var(--signal);
	}

	.level {
		display: block;
		width: 4.5rem;
		height: 3px;
		border-radius: 999px;
		background: var(--rule);
		overflow: hidden;
	}

	.level span {
		display: block;
		height: 100%;
		background: var(--signal);
		transition: width 80ms linear;
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
		max-height: calc(100% - 2rem - var(--ruler));
		background: var(--paper-raised);
		border: 1px solid var(--rule);
		border-radius: var(--radius);
		box-shadow: var(--lift);
		overflow: hidden;
	}

	/* On a bench the controls and the reading stack as one column, each as tall as what it
	   holds, and either scrolls when the two together outgrow the window. On a phone the
	   column dissolves and each card is a drawer. */
	.leftcol {
		display: contents;
	}

	@media (min-width: 861px) {
		.leftcol {
			position: absolute;
			top: calc(var(--ruler) + 1rem);
			left: calc(var(--ruler) + 1rem);
			bottom: 1rem;
			z-index: 3;
			display: flex;
			flex-direction: column;
			gap: 0.6rem;
			width: 20rem;
			pointer-events: none;
		}

		.leftcol > .panel {
			position: static;
			flex: 0 1 auto;
			min-height: 0;
			max-height: none;
			width: 100%;
			pointer-events: auto;
		}

		.leftcol > .controls {
			order: 0;
			flex-shrink: 2;
		}

		.leftcol > .readout {
			order: 1;
			max-height: 45%;
		}
	}

	.readout .quiet {
		padding: 0.6rem 1rem;
	}

	.pinhead {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.5rem;
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
		padding: 0.7rem 0.3rem 0.6rem;
		font-size: 0.8rem;
		font-weight: 500;
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
		transition: none;
	}

	.clip {
		display: grid;
		gap: 0.4rem;
	}

	.clip audio {
		width: 100%;
		height: 2rem;
	}

	h2 {
		display: flex;
		justify-content: space-between;
		align-items: baseline;
		gap: 0.5rem;
		margin: 0;
		font-size: 0.8rem;
		font-weight: 600;
		color: var(--ink);
		padding: 0.65rem 1rem;
		border-bottom: 1px solid var(--rule);
	}

	.readout h2 .link {
		font-size: 0.72rem;
		font-weight: 400;
	}

	/* Which question a filter answers. The chorus filter and the point filter share three
	   words and are two different axes; before this the only way to know was to read the
	   source. */
	.axis {
		margin: 0 0 0.3rem;
		font-family: var(--font-sans);
		font-size: 0.74rem;
		font-weight: 500;
		color: var(--ink-dim);
		text-transform: capitalize;
	}


	/* The cost readout. A label column and a figures column, like the meters in the
	   header, so it reads as an instrument rather than as part of the picture. */
	.cost {
		display: grid;
		gap: 0.2rem;
		margin: 0.35rem 0 0;
	}

	.cost div {
		display: grid;
		grid-template-columns: 3.6rem minmax(0, 1fr);
		gap: 0.5rem;
		align-items: baseline;
	}

	.cost dt {
		font-size: 0.7rem;
		color: var(--ink-faint);
	}

	.cost dd {
		margin: 0;
		font-size: 0.74rem;
		color: var(--ink);
	}

	/* Vendor strings run long ("ANGLE (Intel, Mesa Intel(R) Graphics (RPL-S), OpenGL
	   4.6)") and the panel is narrow, so this one wraps instead of widening it. */
	.cost dd.gpu {
		font-size: 0.6rem;
		line-height: 1.3;
		overflow-wrap: anywhere;
	}

	@keyframes breath {
		50% {
			opacity: 0.9;
		}
	}

	@keyframes drift {
		50% {
			transform: translate(2px, -1px);
		}
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

	.disc-chip.collecting {
		color: var(--signal);
		background: var(--signal-soft);
	}

	.disc-chip.waiting {
		color: var(--invented);
		background: color-mix(in srgb, var(--invented) 10%, transparent);
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

	pre {
		margin: 0;
		padding: 0.55rem 0.65rem;
		background: var(--paper);
		border: 1px solid var(--rule);
		border-radius: var(--radius);
		overflow-x: auto;
		font-size: 0.7rem;
	}

	.badge {
		justify-self: start;
		font-size: 0.66rem;
		font-weight: 500;
		padding: 0.08rem 0.45rem;
		border-radius: 999px;
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
		background: var(--signal);
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

	/* The "sounds like" partners: chips inline in a note, not a strip of their own. */
	.sounds-like {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.25rem;
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

	.quality.mid { background: color-mix(in srgb, var(--signal) 50%, var(--rule)); }
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
		padding: 0.5rem 1rem;
		border-top: 1px solid var(--rule);
	}

	/* --- what has been sung --- */

	.history {
		position: absolute;
		bottom: 1rem;
		/* **Anchored to the right edge now the reading card has left it** (owner,
		   2026-08-05). It used to run in the lane between two columns, reserving 23rem on
		   the right for a reading card that sat there; with that card moved under the
		   controls, the reserve was holding empty paper and squeezing the strip into the
		   middle of the stage. It still clips at the left rather than sliding under the left
		   column, and `row-reverse` already packs the newest chip at the right end, so the
		   strip now grows leftwards out of the corner and the mask fades its old end. */
		left: calc(var(--ruler) + 20rem + 2rem);
		right: 1rem;
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
		font-size: 0.72rem;
		color: var(--ink);
		white-space: nowrap;
	}

	.sung-label {
		font-size: 0.66rem;
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

	/* **The doubt swatch is the ramp itself, not one of its ends.** The provenance
	   swatches are categorical, so a single fill is the whole key; this mode is
	   sequential, and picking either end to stand for it would say the mode means one
	   thing rather than a scale. Same size and shape as the class swatches so the two
	   lists still read as one kind of control, and the same `hollow` rule: off, it
	   states only "a mode you can turn on". The gradient direction matches the key
	   printed under the pair — loud first, because that is the end you turn it on for. */
	/* One gradient per ramp, so the two rows are told apart by the same thing that tells their
	   marks apart on the stage. Loud end first, because that is the end you turn it on for. */
	.swatch.ramp.agree {
		background: linear-gradient(90deg, var(--doubt-agree), var(--doubt-quiet));
	}

	.swatch.ramp.snr {
		background: linear-gradient(90deg, var(--doubt-snr), var(--doubt-quiet));
	}

	.swatch.ramp.hollow {
		background: none;
	}

	/* A control that only exists while the one above it is on reads as subordinate to it, so
	   it is inset by the width of that checkbox rather than sitting at the section's margin
	   as a peer. */
	.field.indent {
		padding-left: 1.35rem;
	}

	/* The ramp's two ends named in words, tight under the toggles they belong to. */
	.rampkey {
		margin-top: 0.15rem;
		font-size: 0.68rem;
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

	/* --- the first-load screen ---

	   Built from parts the interface already has: the brand block from the HUD, `axis mono` for
	   the stage label, `note faint` for the sentence under it. The only new shapes are the bar
	   and the mark's rotation, and both are one rule each. */
	.loading {
		display: grid;
		grid-template-columns: auto 1fr;
		gap: 0.5rem 0.9rem;
		align-items: center;
		max-width: 25rem;
	}

	/* Slow, and counter-clockwise to nothing in particular — it is the one moving thing on the
	   screen, so "working" reads without a spinner ornament. 9s rather than 1s because a fast
	   spin says "this should already be done"; this load is a minute's honest work. */
	.loadmark {
		grid-row: span 2;
		animation: loadspin 9s linear infinite;
	}

	@keyframes loadspin {
		to {
			transform: rotate(360deg);
		}
	}

	.loadtext h1 {
		margin: 0;
		font-size: 1rem;
		font-weight: 600;
		letter-spacing: 0.01em;
	}

	/* Full width under the mark and the name, so the bar measures the whole card rather than
	   the column the text happens to occupy. */
	.loadbar {
		grid-column: 1 / -1;
		height: 2px;
		margin-top: 0.5rem;
		background: var(--rule);
		overflow: hidden;
	}

	.loadbar span {
		display: block;
		height: 100%;
		background: var(--signal);
		/* Eased, because the stages complete in bursts: three of the ten land within a few
		   hundred milliseconds of each other and an unanimated bar jumps past a third of its
		   length in one frame. */
		transition: width 320ms ease;
	}

	.loadstage {
		grid-column: 1 / -1;
		margin: 0;
	}

	/* No backdrop blur: it would re-blur the whole canvas every frame behind a card. */
	.overlay {
		background: rgba(250, 251, 252, 0.8);
		z-index: 6;
	}

	.card {
		max-width: 34rem;
		background: var(--paper-raised);
		border: 1px solid var(--rule);
		border-radius: var(--radius);
		box-shadow: var(--lift);
		padding: 1.6rem;
		display: grid;
		gap: 0.8rem;
	}

	.card h1 {
		font-size: 1.25rem;
	}

	/* --- the drawers ---------------------------------------------------------------

	   Everything from here down is the phone arrangement. It is a different layout rather
	   than a squeezed one: on the bench the panels are cards floating over a picture wide
	   enough to hold them, and on a phone there is no such width, so they become drawers
	   that open one at a time from the dock and shut again to give the galaxy the screen.

	   The lid, and it is only ever drawn on a phone — `.sheet` is bound to `narrow`. */

	.sheethead {
		display: flex;
		align-items: center;
		gap: 0.6rem;
		width: 100%;
		padding: 0.55rem 1rem 0.45rem;
		border: 0;
		border-bottom: 1px solid var(--rule);
		border-radius: 0;
		background: none;
		cursor: pointer;
	}

	/* The grab bar. It does not drag — the drawer has two sizes, open and shut, and a
	   height a thumb can set is a control nobody can return to a known state. It is here
	   because it is the one shape that says "this panel came up from the bottom edge and
	   goes back down", which is a thing to know before you start hunting for a close. */
	.grabber {
		flex: none;
		width: 2rem;
		height: 3px;
		border-radius: 999px;
		background: var(--rule-strong);
	}

	.sheetname {
		margin: 0;
	}

	.sheetx {
		margin-left: auto;
		font-size: 0.6rem;
		letter-spacing: 0.09em;
		text-transform: uppercase;
		color: var(--ink-faint);
	}

	/* The dock: the phone's tab strip, and a row of the bench rather than a bar over it. */

	.dock {
		display: flex;
		z-index: 5;
		background: var(--paper-raised);
		border-top: 1px solid var(--rule);
		padding-bottom: env(safe-area-inset-bottom, 0px);
	}

	.dock button {
		position: relative;
		flex: 1;
		min-width: 0;
		height: var(--dock-h);
		padding: 0 0.2rem;
		border: 0;
		border-radius: 0;
		background: none;
		font-size: 0.8rem;
		font-weight: 500;
		color: var(--ink-faint);
		/* The open drawer's item, marked on the edge the drawer comes from. */
		border-top: 2px solid transparent;
		margin-top: -1px;
	}

	.dock button.on {
		color: var(--ink);
		border-top-color: var(--signal);
		background: var(--signal-soft);
	}

	/* A live match on the shut Reading drawer. Same dot as the running-job one in the
	   header, same meaning: something is happening in a surface you are not looking at. */
	.docklive {
		display: inline-block;
		width: 5px;
		height: 5px;
		margin-left: 0.3rem;
		border-radius: 50%;
		background: var(--signal);
		vertical-align: middle;
		animation: joblive 1.6s ease-in-out infinite;
	}

	@media (max-width: 860px) {
		/* The dock's height, named once: the drawers sit on top of it and the stage above
		   them, so all three have to agree about one number. */
		.bench {
			--dock-h: 3.4rem;
			grid-template-rows: auto 1fr auto;
		}

		.hud {
			padding: 0.4rem 0.7rem;
			gap: 0.5rem;
		}

		.readings {
			flex: none;
		}

		/* A door, at a size a thumb can hit. */
		.readings > .reading-open {
			min-height: 2.6rem;
			padding: 0 0.6rem;
		}

		/* Every drawer, wherever its opener lives: the two dock cards, the two corner ones.
		   Fixed rather than absolute, because the corner pair hang inside `.viewctl`, which is
		   itself pinned to the top-right — positioning them against the viewport is what lets
		   one rule serve all four. They stop at the dock, which therefore always stays live:
		   the way out of a drawer is the item that opened it. */
		.panel.sheet,
		.viewctl .viewpanel.sheet {
			position: fixed;
			left: 0;
			right: 0;
			bottom: var(--dock-h);
			top: auto;
			width: auto;
			max-width: none;
			/**
			 * How much a drawer may take, now that what it takes is *the stage's* and not the
			 * stage's cover. 55 % leaves the galaxy about 200 px of a 667 px phone once the
			 * header and the dock are paid for — a band, but a band with the whole corpus
			 * centred in it, which is enough to watch knots answer while you drive them. The
			 * drawers scroll, so the cap costs a reader nothing but a swipe.
			 */
			max-height: min(55dvh, calc(100dvh - 12rem));
			border-radius: 14px 14px 0 0;
			border-bottom: 0;
			/* Flex, not the bench's two-row grid: a drawer has a lid, a header and a body,
			   and the body is the part that scrolls whichever of the other two are present. */
			display: flex;
			flex-direction: column;
		}

		.panel.sheet > .cardbody,
		.panel.sheet > .tabbody {
			flex: 1 1 auto;
		}

		/* The dock is this panel's tab strip on a phone; two identical rows of
		   Sing/Compose/Listen a finger's width apart read as two different controls. */
		.controls.sheet > .tabs {
			display: none;
		}

		/* The figures, in the drawer they moved into. A wrapping grid rather than the
		   header's single row: there is no width to run them along, and the divider rules
		   that separate cells in a row read as a table's when the row wraps. */
		.readings.inpanel {
			display: grid;
			grid-template-columns: repeat(auto-fit, minmax(6.5rem, 1fr));
			gap: 0.5rem 0.75rem;
			padding: 0.8rem 1rem;
			border-bottom: 1px solid var(--rule);
		}

		.readings.inpanel > div {
			padding: 0;
		}

		/* The corner pair keeps its place — how the picture is drawn is a property of the
		   picture, so its controls stay on it — but at a size a finger can hit. */
		.viewctl {
			top: calc(var(--ruler) + 0.5rem);
			right: 0.5rem;
		}

		.mapctl button {
			padding: 0.5rem 0.6rem;
		}

		/**
		 * **The open drawer's height, taken out of the stage rather than laid over it.**
		 *
		 * The stage shrinks to the band above the drawer, so the canvas, the label layer and the
		 * ruler move up together and the camera follows — threlte watches the canvas and updates
		 * the aspect on its own. The picture then re-centres into what is left instead of having
		 * its middle hidden under the panel that is driving it, which is the case that matters:
		 * you open Sing, press Chorus, and the knots that answer are exactly the ones a floating
		 * sheet would be sitting on.
		 *
		 * **`margin`, not `padding`, and the difference is the whole mechanism.** `.stage` is
		 * `inset: 0` inside this element, and an absolutely positioned box resolves its offsets
		 * against the containing block's *padding box* — which includes the padding. Padding
		 * therefore changed nothing at all: measured with 413 px of it, the wrap and the canvas
		 * were both still the full 564 px tall. A margin shrinks the grid item itself, and the
		 * canvas is stretched to the item.
		 *
		 * The value is the measured height of whichever drawer is open (see `sheetH`) rather
		 * than the 62 % cap: the Listen drawer is a third of that and should not cost the
		 * picture the difference.
		 */
		.stage-wrap {
			margin-bottom: var(--sheet-h, 0px);
			transition: margin-bottom 160ms ease;
		}

		/* Full width above the dock — or above the drawer, once the stage has shrunk to make
		   room for one. */
		.history {
			left: 0.5rem;
			right: 0.5rem;
			bottom: 0.5rem;
			mask-image: linear-gradient(to right, transparent, #000 1.5rem);
		}

		/* The band left over a drawer is about 250 px, and a 44 px strip of chips across the
		   bottom of it is a sixth of the picture spent on what was sung a minute ago. The
		   drawer is the thing being read while it is open. */
		.history.tucked {
			display: none;
		}

		.sung {
			max-width: 9rem;
		}

		/* The gate is the first thing a phone reader meets, so it is the first thing that
		   has to fit: full width less a margin, and its own scroll if the text runs long. */
		.centred {
			padding: 1rem;
		}

		.card {
			max-width: 100%;
			max-height: calc(100dvh - 2rem);
			overflow-y: auto;
			padding: 1.2rem;
		}

		.loading {
			max-width: 100%;
		}
	}

	/* A phone on its side is a different problem: 390 px of height, of which a bottom drawer
	   at 62 % would leave the galaxy about a centimetre. So the drawer goes to the side it has
	   room on, which is the arrangement the bench already uses — a column against the left
	   edge, full height, over the picture. The dock stays where it is: it is 3.4 rem, and
	   moving it too would mean two dock layouts to keep true. */
	@media (max-width: 860px) and (orientation: landscape) {
		.panel.sheet,
		.viewctl .viewpanel.sheet {
			right: auto;
			/* Under the header, not behind it. A side drawer is full height, and `top: 0` on a
			   fixed box is the top of the *window* — which put the drawer's own lid, with its
			   grab bar and its close, underneath the title bar where neither could be seen or
			   pressed. The header measures itself into `--hud-h`. */
			top: var(--hud-h, 0px);
			bottom: var(--dock-h);
			width: min(21rem, 62vw);
			/* `height: auto`, and it is the whole rule working. `.panel` is `height:
			   fit-content` so a card is as tall as what is in it — correct on a bench, and
			   here it means `top` and `bottom` are both set and the height obeys neither:
			   the Sing drawer measured 634 px inside a 390 px screen and ran off the bottom
			   with its own controls on the far side of the edge. `auto` is what lets the two
			   offsets decide, which is what a side drawer is. */
			height: auto;
			max-height: none;
			border-radius: 0 14px 14px 0;
			border-left: 0;
		}

		/* The same trade on the other axis: the drawer's measured width comes off the side of
		   the stage, so the picture sits beside the panel instead of under it. */
		.stage-wrap {
			margin-bottom: 0;
			margin-left: var(--sheet-w, 0px);
			transition: margin-left 160ms ease;
		}

		.history {
			left: 0.5rem;
		}

		/* There is room for both here — the strip runs along the bottom of a stage that has
		   already given up its left edge — and it is the one place a landscape phone can read
		   what a knot is called without opening anything. */
		.history.tucked {
			display: flex;
		}
	}

</style>

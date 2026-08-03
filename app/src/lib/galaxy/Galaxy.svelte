<script lang="ts">
	import { untrack } from 'svelte';
	import { Canvas, T } from '@threlte/core';
	import { OrbitControls } from '@threlte/extras';
	import type * as THREE from 'three';
	import type { OrbitControls as OrbitControlsInstance } from 'three/examples/jsm/controls/OrbitControls.js';
	import type { BirdyAssets } from '$lib/data/types';
	import { biplotAxes, type ScreenReading } from './biplot';
	import { TARGET_PX, gridOffsetPx, tickStep } from './ticks';
	import ContextPaths from './ContextPaths.svelte';
	import Framing from './Framing.svelte';
	import GridBurst from './GridBurst.svelte';
	import NodeLabels from './NodeLabels.svelte';
	import NodeProjector from './NodeProjector.svelte';
	import PointCloud from './PointCloud.svelte';
	import RelationThreads from './RelationThreads.svelte';
	import Ruler from './Ruler.svelte';
	import Scale from './Scale.svelte';
	import Spinner from './Spinner.svelte';
	import Stats from './Stats.svelte';
	import Trajectory from './Trajectory.svelte';
	import { LABEL_SLOTS } from './labels';
	import { createLayoutView } from './layouts';
	import { relationPartners } from '$lib/data/assets';
	import { type VisualSignal } from './shaders';
	import type { GalaxyStats } from './stats';

	interface Props {
		assets: BirdyAssets;
		signal: VisualSignal;
		pointSize?: number;
		spin?: boolean;
		labels?: boolean;
		/** Species index to keep at full strength; -1 shows every species equally. */
		focus?: number;
		pinned?: number;
		/**
		 * Clusters to fly the camera to and hold in frame — the nodes of a phrase picked
		 * out of the history. Empty releases the camera back to the viewer.
		 */
		frame?: number[];
		/** Cloud scale, driven by the listening distance. */
		spread?: number;
		/**
		 * Multiplies the per-point pulse rate, which follows the sound and so belongs with the
		 * tempo. It no longer reaches the cloud's rotation — see `Spinner`.
		 */
		speed?: number;
		/** Clusters the learning pipeline is working on, pulsed live in the cloud. */
		learning?: number[];
		/**
		 * Neutral ink instead of the provenance class tint. Owned by the page's display
		 * settings (the point-colour switch).
		 *
		 * It switches the whole stage's colour *language*, not just the cloud: the points,
		 * the tags and the trajectory threads move together, because two languages on
		 * screen at once invite the reading that their hues are related. On (ink), the
		 * points and threads are neutral and hue answers "which bird" where it can be
		 * read — on the tags, and on the response itself, which lights in the singing
		 * bird's hue. Off (provenance), hue answers "what kind of thing" everywhere. No
		 * activation rule changes either way, and the accent keeps meaning exactly one
		 * thing in both.
		 */
		plain?: boolean;
		/**
		 * A third colour language for the points: each one in its own bird's hue. A toggle and
		 * never the default — 2 423 species share one hue circle, so at this density it reads
		 * as confetti rather than as an answer. Offered because "where does this species sit"
		 * is a real question and nothing else answers it for the whole corpus at once.
		 *
		 * Only the *points* take it. The tags already carry the bird's hue and the accent
		 * already lights in it, so this is the resting field joining a language the rest of
		 * the stage was already speaking.
		 */
		birdColours?: boolean;
		/** Per-class point visibility in PROVENANCE order; false hides the class. */
		provShown?: boolean[];
		/**
		 * The density governor: the measured frame time may hold the LOD frontier back.
		 * The Display panel's "adaptive detail" switch; default on.
		 */
		adaptive?: boolean;
		/**
		 * The two-level arrangement (layouts.ts `localShapes`): knot centres from the
		 * global projection, members from a local projection of their own features.
		 * Read once at build time — the page remounts the canvas when it changes.
		 */
		localKnots?: boolean;
		/**
		 * The selected species' id ('' for none): draws the relation threads to the
		 * species relations.json says share call shapes with it, and lets the partners'
		 * knots into the label pool while the selection stands.
		 */
		selectedSpecies?: string;
		onpick?: (cluster: number) => void;
		/** Fired on a click that hit no node, so the page can clear its selection. */
		onbackground?: () => void;
		/**
		 * The corpus's own length unit — the median nearest-neighbour distance between
		 * knot centres, in layout box units — measured by PointCloud and handed back
		 * out. The ruler ticks in it, and the key quotes the knot width against it.
		 */
		knotSpacing?: number;
		/**
		 * Written by the renderer, read by whoever wants to draw it. Plain object, not
		 * state: it is written inside the render loop. See stats.ts.
		 */
		stats?: GalaxyStats;
	}

	let {
		assets,
		signal,
		pointSize = 3,
		spin = true,
		labels = true,
		focus = -1,
		pinned = -1,
		spread = 1,
		speed = 1,
		frame = [],
		learning = [],
		plain = true,
		birdColours = false,
		provShown = [true, true, true, true, true],
		adaptive = true,
		localKnots = true,
		selectedSpecies = '',
		onpick,
		onbackground,
		knotSpacing = $bindable(0.135),
		stats
	}: Props = $props();

	// The slot elements, written once per slot at mount by NodeLabels and only read
	// afterwards — the per-frame positioning writes go straight to `node.style` and
	// never touch this array, so $state here buys the bind: its reactivity without
	// paying proxy writes per frame. (DOM nodes are not plain objects; $state stores
	// them raw.) The bind: exists because Svelte 5 warns on an unbound prop mutation.
	let labelElements = $state<(HTMLElement | null)[]>([]);
	/**
	 * Which knot each tag slot holds, or -1. This one *is* reactive, because a rebind has
	 * to re-render the tag's text — and only a rebind does, which is a few times a second
	 * at most. The pool is fixed-size, so neither the DOM nor the per-frame write cost
	 * moves when the corpus grows; see labels.ts for the measurement behind that.
	 */
	let labelSlots = $state<number[]>(Array.from({ length: LABEL_SLOTS }, () => -1));
	// The corpus does not change while this is mounted, so the view is sized once.
	const view = untrack(() => createLayoutView(assets));

	/**
	 * The partner knots the label pool may consider while a species is selected:
	 * every knot a relation thread ends at, resolved once per selection from the
	 * cached relations graph. The threads themselves are RelationThreads' business;
	 * this is the same set as knot indices, so a lit partner knot can also be named.
	 */
	const relatedKnots = $derived.by(() => {
		if (!selectedSpecies) return [];
		const knots = new Set<number>();
		for (const partner of relationPartners(assets).get(selectedSpecies) ?? []) {
			for (const t of partner.threads) knots.add(t.to);
		}
		return [...knots];
	});

	/**
	 * A click on empty space clears the selection — but only a *click*. Orbiting is a
	 * click-and-drag on the same surface, and losing the phrase you were studying because
	 * a drag ended a few pixels from where it started is a bad trade, so the report only
	 * fires when the pointer barely moved and was not held: a slow, tiny drag is still a
	 * drag.
	 *
	 * The page also uses it to end a camera flight: grabbing the view always beats
	 * whatever the camera was doing on its own.
	 */
	let downAt: { x: number; y: number; t: number } | null = null;
	function onpointerdown(e: PointerEvent) {
		downAt = { x: e.clientX, y: e.clientY, t: e.timeStamp };
	}
	function onpointerup(e: PointerEvent) {
		if (!downAt) return;
		const moved = Math.hypot(e.clientX - downAt.x, e.clientY - downAt.y);
		const held = e.timeStamp - downAt.t;
		downAt = null;
		if (moved < 4 && held < 400) onbackground?.();
	}

	/**
	 * The stage's scale, in the corpus's own unit: how many pixels one knot spacing
	 * covers on screen right now. Written by `Scale` inside the canvas — only when it
	 * actually changes — and read by the ruler bands outside it.
	 */
	let pxPerKnot = $state(0);
	let widthKnots = $state(0);
	/**
	 * What the screen's directions currently mean, from `biplot.ts` — rewritten whenever
	 * the camera settles, so the ruler's caption can name a direction instead of leaving
	 * "left" and "up" as the only two channels a viewer has and neither of them readable.
	 */
	let reading = $state<ScreenReading[]>([]);
	/**
	 * Fitted once per build: the direction each nameable acoustic quantity increases
	 * fastest in, and how much of it that direction explains. Over knots, because the 28-d
	 * descriptor ships per knot and a knot is the unit the picture places.
	 */
	const axes = $derived(biplotAxes(assets, view.centroids));

	let controls = $state<OrbitControlsInstance | undefined>();
	let cloud = $state<THREE.Group | undefined>();
	/** Bumped on every grab of the view, which is what ends a camera flight. */
	let grabbed = $state(0);

	/**
	 * The background grid, in the ruler's own divisions.
	 *
	 * One square is one labelled tick, so the lattice behind the cloud is the same measure the
	 * numbers along the edges are counting, and it re-scales with the zoom because the step
	 * does. A gap of two squares is two ticks at any zoom, which is what a grid on a plot is
	 * for. One lattice only — see the `.stage` rule for why the fifth-divisions came out.
	 *
	 * Falls back to the ruler's target spacing before `Scale` has reported, so the stage never
	 * flashes an enormous or a zero-sized lattice on the first frame.
	 */
	const gridStep = $derived(tickStep(pxPerKnot));
	const gridCoarsePx = $derived(pxPerKnot > 0 ? gridStep * pxPerKnot : TARGET_PX);
</script>

<!-- svelte-ignore a11y_no_static_element_interactions -->
<div
	class="stage"
	{onpointerdown}
	{onpointerup}
	style:--grid-coarse-px={`${gridCoarsePx}px`}
	style:--grid-coarse-at={`${gridOffsetPx(gridCoarsePx)}px`}
>
	<Canvas>
		<!--
			Opened from above the equator rather than on it. At the old near-level elevation
			the ground plane was edge-on and collapsed to a line, so the one reference that
			was supposed to establish the volume showed nothing; a three-quarter view gives
			its lines somewhere to converge and the corpus somewhere to sit.
		-->
		<T.PerspectiveCamera makeDefault position={[0.5, 1.15, 2.4]} fov={55} near={0.01} far={400}>
			<!--
				The reach has to cover the whole distance range: at the far end the cloud is
				several times its own radius across, and a camera that cannot back away from
				it turns the control into a wall.
			-->
			<OrbitControls
				bind:ref={controls}
				enableDamping
				dampingFactor={0.08}
				enablePan={false}
				minDistance={0.15}
				maxDistance={60}
				autoRotate={false}
				onstart={() => (grabbed += 1)}
			/>
		</T.PerspectiveCamera>

		<T.AmbientLight intensity={0.4} />
		<!--
			Framing mounts before the cloud on purpose: Threlte runs dependency-free
			tasks in registration order, and Framing's task lerps the camera target and
			calls controls.update() every frame. Mounted after the cloud it ran *after*
			NodeProjector had already projected the labels — the canvas then rendered
			the post-Framing camera while the tags kept the pre-Framing one, which is
			the one-frame drag the labels had whenever the view moved. First in the
			subtree, its camera writes settle before Spinner rotates and before the
			labels project.
		-->
		<Framing {view} {frame} group={cloud} {controls} interrupt={grabbed} />

		<!--
			The cloud, the trajectories and the label anchors share one group: the rotation
			has to apply to all of them or the lines and the tags drift off their points.
		-->
		{#if stats}
			<Stats {stats} />
		{/if}

		<Scale
			{knotSpacing}
			{spread}
			{controls}
			{axes}
			onscale={(s) => {
				pxPerKnot = s.pxPerKnot;
				widthKnots = s.widthKnots;
				reading = s.reading ?? [];
			}}
		/>

		<Spinner {spin} scale={spread} bind:group={cloud}>
			<GridBurst {assets} {signal} {view} prov={!plain} />
			<ContextPaths {assets} {signal} {view} prov={!plain} />
			<RelationThreads {assets} {view} speciesId={selectedSpecies} />
			<PointCloud {assets} {signal} {pointSize} {focus} {speed} {view} {spread} {learning} {plain} {birdColours} {provShown} {adaptive} {localKnots} bind:knotSpacing {stats} />
			<Trajectory {assets} {signal} {view} {spread} {pointSize} prov={!plain} />
			{#if labels}
				<NodeProjector {assets} {signal} elements={labelElements} bind:slots={labelSlots} {focus} {pinned} {view} prov={!plain} related={relatedKnots} {stats} />
			{/if}
		</Spinner>
	</Canvas>

	{#if labels}
		<NodeLabels
			{assets}
			slots={labelSlots}
			bind:elements={labelElements}
			prov={!plain}
			{pxPerKnot}
			{onpick}
		/>
	{/if}

	<!--
		The scale, outside the canvas: DOM ticks cost nothing per frame and stay crisp,
		and the numbers only re-render when the zoom has actually moved.
	-->
	{#if pxPerKnot > 0}
		<Ruler {pxPerKnot} {knotSpacing} />
	{/if}
</div>

<style>
	.stage {
		position: absolute;
		inset: 0;
		background: var(--paper);
		/* One lattice, in the ruler's divisions: a square is a labelled tick.

		   It was `120px 120px` — fixed pixels, changing with nothing — while the ruler's
		   divisions changed as you zoomed. Two scales on one picture, and only one of them
		   meant anything: at one zoom a square was three knot spacings and at another a fifth
		   of one. A reader reads a grid as a measure whether or not it is one, so the squares
		   were answering "how big is that gap" with a number that had no referent.

		   **One lattice and not two, and that is a correction.** The first version of this drew
		   fifth-divisions under the ticks in `--grid-fine`, which produced exactly the
		   "irregular line thickness" it was reported as — and by arithmetic rather than by
		   rasterisation. `--grid-fine` is 0.035 of ink against `--grid-coarse`'s 0.03, so the
		   *finer* lines were the heavier ones; and every fifth fine line sits under a coarse
		   line by construction, so those positions were painted twice, at about 0.065. Every
		   fifth line was double the ink of its neighbours. Two lattices anchored to one origin
		   cannot avoid that overlap, so the subdivision is gone rather than re-weighted.

		   Offset half a tile so a line lands on the ruler's zero at the centre of the view: the
		   ruler counts outward from the middle, so `50%` alone would put every line exactly
		   *between* two ticks.

		   The first layer is a vignette — 4 % of ink at the corners, none past 55 % of the way
		   out — so the stage reads as a printed sheet rather than a lit screen. Pure CSS on the
		   paper under the canvas: zero GPU, and the hairlines stay visible through it. */
		background-image:
			radial-gradient(ellipse at center, transparent 55%, rgba(16, 22, 31, 0.04) 100%),
			linear-gradient(var(--grid-coarse) 1px, transparent 1px),
			linear-gradient(90deg, var(--grid-coarse) 1px, transparent 1px);
		background-size:
			100% 100%,
			var(--grid-coarse-px) var(--grid-coarse-px),
			var(--grid-coarse-px) var(--grid-coarse-px);
		background-position:
			center,
			calc(50% + var(--grid-coarse-at)) calc(50% + var(--grid-coarse-at)),
			calc(50% + var(--grid-coarse-at)) calc(50% + var(--grid-coarse-at));
		opacity: 1;
	}
</style>

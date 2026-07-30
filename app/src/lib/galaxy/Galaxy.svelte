<script lang="ts">
	import { untrack } from 'svelte';
	import { Canvas, T } from '@threlte/core';
	import { OrbitControls } from '@threlte/extras';
	import type * as THREE from 'three';
	import type { OrbitControls as OrbitControlsInstance } from 'three/examples/jsm/controls/OrbitControls.js';
	import type { BirdyAssets } from '$lib/data/types';
	import ContextPaths from './ContextPaths.svelte';
	import Framing from './Framing.svelte';
	import GridBurst from './GridBurst.svelte';
	import NodeLabels from './NodeLabels.svelte';
	import NodeProjector from './NodeProjector.svelte';
	import PointCloud from './PointCloud.svelte';
	import Spinner from './Spinner.svelte';
	import Trajectory from './Trajectory.svelte';
	import { createLayoutView } from './layouts';
	import { type VisualSignal } from './shaders';

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
		onpick?: (cluster: number) => void;
		/** Fired on a click that hit no node, so the page can clear its selection. */
		onbackground?: () => void;
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
		onpick,
		onbackground
	}: Props = $props();

	// Plain array, deliberately not reactive: NodeLabels writes the elements into it and
	// NodeProjector moves them every frame. Routing that through Svelte state would mean
	// thousands of proxy writes a second to position some text.
	const labelElements: (HTMLElement | null)[] = [];
	// The corpus does not change while this is mounted, so the view is sized once.
	const view = untrack(() => createLayoutView(assets));

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

	let controls = $state<OrbitControlsInstance | undefined>();
	let cloud = $state<THREE.Group | undefined>();
	/** Bumped on every grab of the view, which is what ends a camera flight. */
	let grabbed = $state(0);
</script>

<!-- svelte-ignore a11y_no_static_element_interactions -->
<div class="stage" {onpointerdown} {onpointerup}>
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
			The cloud, the trajectories and the label anchors share one group: the rotation
			has to apply to all of them or the lines and the tags drift off their points.
		-->
		<Spinner {spin} scale={spread} bind:group={cloud}>
			<GridBurst {signal} {view} />
			<ContextPaths {assets} {signal} {view} />
			<PointCloud {assets} {signal} {pointSize} {focus} {speed} {view} {spread} {learning} />
			<Trajectory {assets} {signal} {view} {spread} {pointSize} />
			{#if labels}
				<NodeProjector {assets} {signal} elements={labelElements} {focus} {pinned} {view} />
			{/if}
		</Spinner>

		<Framing {view} {frame} group={cloud} {controls} interrupt={grabbed} />
	</Canvas>

	{#if labels}
		<NodeLabels {assets} elements={labelElements} {onpick} />
	{/if}
</div>

<style>
	.stage {
		position: absolute;
		inset: 0;
		background: var(--paper);
		/* Only the decade grid survives here, at a fraction of its old weight. The
		   measured field the cloud is read against is now the 3D cage inside the scene,
		   which turns with it; this is just enough tone on the paper that the window does
		   not read as a void, and it must stay well under the cage or the flat lattice
		   wins the depth argument again. */
		background-image:
			linear-gradient(var(--grid-coarse) 1px, transparent 1px),
			linear-gradient(90deg, var(--grid-coarse) 1px, transparent 1px);
		background-size:
			120px 120px,
			120px 120px;
		opacity: 1;
	}
</style>

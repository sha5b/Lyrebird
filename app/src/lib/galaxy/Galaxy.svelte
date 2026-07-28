<script lang="ts">
	import { untrack } from 'svelte';
	import { Canvas, T } from '@threlte/core';
	import { OrbitControls } from '@threlte/extras';
	import type { BirdyAssets } from '$lib/data/types';
	import ContextPaths from './ContextPaths.svelte';
	import NodeLabels from './NodeLabels.svelte';
	import NodeProjector from './NodeProjector.svelte';
	import PointCloud from './PointCloud.svelte';
	import Spinner from './Spinner.svelte';
	import Trajectory from './Trajectory.svelte';
	import { createLayoutView, type LayoutId } from './layouts';
	import type { VisualSignal } from './shaders';

	interface Props {
		assets: BirdyAssets;
		signal: VisualSignal;
		pointSize?: number;
		spin?: boolean;
		labels?: boolean;
		/** Species index to keep at full strength; -1 shows every species equally. */
		focus?: number;
		pinned?: number;
		/** COLOUR_RESPONSE or COLOUR_MEANING. */
		colourMode?: number;
		/** Cloud scale, driven by the listening distance. */
		spread?: number;
		/** Multiplies every animation rate. */
		speed?: number;
		/** Which arrangement to show; changing it animates the cloud into the new one. */
		layout?: LayoutId;
		onpick?: (cluster: number) => void;
		/** Fired on a click that hit no node, so the page can clear its selection. */
		onbackground?: () => void;
	}

	let {
		assets,
		signal,
		pointSize = 7,
		spin = true,
		labels = true,
		focus = -1,
		pinned = -1,
		colourMode = 0,
		spread = 1,
		speed = 1,
		layout = 'acoustic',
		onpick,
		onbackground
	}: Props = $props();

	// Plain array, deliberately not reactive: NodeLabels writes the elements into it and
	// NodeProjector moves them every frame. Routing that through Svelte state would mean
	// thousands of proxy writes a second to position some text.
	const labelElements: (HTMLElement | null)[] = [];
	// The corpus does not change while this is mounted, so the view is sized once.
	const view = untrack(() => createLayoutView(assets));

	// A click that is not a drag and did not land on a node clears the selection. The
	// distance test is what keeps orbiting the camera from counting as a click.
	let downAt: { x: number; y: number } | null = null;
	function onpointerdown(e: PointerEvent) {
		downAt = { x: e.clientX, y: e.clientY };
	}
	function onpointerup(e: PointerEvent) {
		if (!downAt) return;
		const moved = Math.hypot(e.clientX - downAt.x, e.clientY - downAt.y);
		downAt = null;
		if (moved < 4) onbackground?.();
	}
</script>

<!-- svelte-ignore a11y_no_static_element_interactions -->
<div class="stage" {onpointerdown} {onpointerup}>
	<Canvas>
		<T.PerspectiveCamera makeDefault position={[0, 0.35, 2.6]} fov={55} near={0.01} far={100}>
			<OrbitControls
				enableDamping
				dampingFactor={0.08}
				enablePan={false}
				minDistance={0.6}
				maxDistance={8}
				autoRotate={false}
			/>
		</T.PerspectiveCamera>

		<T.AmbientLight intensity={0.4} />
		<!--
			The cloud, the trajectories and the label anchors share one group: the rotation
			has to apply to all of them or the lines and the tags drift off their points.
		-->
		<Spinner {spin} {speed} scale={spread}>
			<ContextPaths {assets} {signal} {view} />
			<PointCloud {assets} {signal} {pointSize} {focus} {colourMode} {speed} {layout} {view} />
			<Trajectory {assets} {signal} {view} />
			{#if labels}
				<NodeProjector {assets} {signal} elements={labelElements} {focus} {pinned} {view} />
			{/if}
		</Spinner>
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
		/* A faint engineering grid, so the cloud is read against a measured field rather
		   than floating in nothing. Two scales: a fine one and a decade one. */
		background-image:
			linear-gradient(var(--grid-fine) 1px, transparent 1px),
			linear-gradient(90deg, var(--grid-fine) 1px, transparent 1px),
			linear-gradient(var(--grid-coarse) 1px, transparent 1px),
			linear-gradient(90deg, var(--grid-coarse) 1px, transparent 1px);
		background-size:
			24px 24px,
			24px 24px,
			120px 120px,
			120px 120px;
	}
</style>

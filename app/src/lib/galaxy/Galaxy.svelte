<script lang="ts">
	import { Canvas, T } from '@threlte/core';
	import { OrbitControls } from '@threlte/extras';
	import type { BirdyAssets } from '$lib/data/types';
	import PointCloud from './PointCloud.svelte';
	import Spinner from './Spinner.svelte';
	import Trajectory from './Trajectory.svelte';
	import type { VisualSignal } from './shaders';

	interface Props {
		assets: BirdyAssets;
		signal: VisualSignal;
		pointSize?: number;
		spin?: boolean;
	}

	let { assets, signal, pointSize = 7, spin = true }: Props = $props();
</script>

<div class="stage">
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
			The cloud and the trajectory share one group: the rotation has to apply to both
			or the line drifts off the points it connects.
		-->
		<Spinner {spin}>
			<PointCloud {assets} {signal} {pointSize} />
			<Trajectory {assets} {signal} />
		</Spinner>
	</Canvas>
</div>

<style>
	.stage {
		position: absolute;
		inset: 0;
		background: radial-gradient(circle at 50% 40%, #10182c 0%, #060911 60%, #03050a 100%);
	}
</style>

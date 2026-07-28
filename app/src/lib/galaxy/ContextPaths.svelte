<script lang="ts">
	import { T, useTask } from '@threlte/core';
	import { untrack } from 'svelte';
	import * as THREE from 'three';
	import type { BirdyAssets } from '$lib/data/types';
	import type { LayoutView } from './layouts';
	import type { VisualSignal } from './shaders';

	interface Props {
		assets: BirdyAssets;
		signal: VisualSignal;
		/** Where the centroids are right now; moves while the cloud rearranges. */
		view: LayoutView;
	}

	let { assets, signal, view }: Props = $props();

	const centroids = untrack(() => assets.centroids.items);

	// Disconnected segments rather than one polyline, so separate songs are not joined to
	// each other. Overlap is the point: where two songs share a transition the segment is
	// drawn twice and the accumulated alpha reads darker, so the bird's reused paths stand
	// out — on a light ground that means normal blending, not additive.
	const geometry = new THREE.BufferGeometry();
	const material = new THREE.LineBasicMaterial({
		color: new THREE.Color('#8595ae'),
		transparent: true,
		opacity: 0.28,
		depthWrite: false,
		blending: THREE.NormalBlending
	});

	let builtVersion = -1;
	let builtLayout = -1;

	function rebuild(paths: number[][]): void {
		const points: number[] = [];
		for (const path of paths) {
			const nodes = path.filter((i) => i >= 0 && i < centroids.length);
			for (let n = 0; n < nodes.length - 1; n++) {
				const a = nodes[n] * 3;
				const b = nodes[n + 1] * 3;
				points.push(
					view.centroids[a], view.centroids[a + 1], view.centroids[a + 2],
					view.centroids[b], view.centroids[b + 1], view.centroids[b + 2]
				);
			}
		}
		geometry.setAttribute('position', new THREE.Float32BufferAttribute(points, 3));
		geometry.computeBoundingSphere();
	}

	useTask(() => {
		if (signal.contextVersion !== builtVersion || view.version !== builtLayout) {
			builtVersion = signal.contextVersion;
			builtLayout = view.version;
			rebuild(signal.context);
		}
	});

	$effect(() => () => {
		geometry.dispose();
		material.dispose();
	});
</script>

<T.LineSegments {geometry} {material} frustumCulled={false} />

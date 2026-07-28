<script lang="ts">
	import { T, useTask } from '@threlte/core';
	import { untrack } from 'svelte';
	import * as THREE from 'three';
	import type { BirdyAssets } from '$lib/data/types';
	import type { VisualSignal } from './shaders';

	interface Props {
		assets: BirdyAssets;
		signal: VisualSignal;
	}

	let { assets, signal }: Props = $props();

	const centroids = untrack(() => assets.centroids.items);

	// Disconnected segments rather than one polyline, so separate songs are not joined to
	// each other. Additive blending is the point: where two songs share a transition the
	// segment is drawn twice and reads brighter, so the bird's reused paths stand out.
	const geometry = new THREE.BufferGeometry();
	const material = new THREE.LineBasicMaterial({
		color: new THREE.Color('#7f97dd'),
		transparent: true,
		opacity: 0.16,
		depthWrite: false,
		blending: THREE.AdditiveBlending
	});

	let builtVersion = -1;

	function rebuild(paths: number[][]): void {
		const points: number[] = [];
		for (const path of paths) {
			const nodes = path.filter((i) => i >= 0 && i < centroids.length);
			for (let n = 0; n < nodes.length - 1; n++) {
				const a = centroids[nodes[n]].position;
				const b = centroids[nodes[n + 1]].position;
				points.push(a[0], a[1], a[2], b[0], b[1], b[2]);
			}
		}
		geometry.setAttribute('position', new THREE.Float32BufferAttribute(points, 3));
		geometry.computeBoundingSphere();
	}

	useTask(() => {
		if (signal.contextVersion !== builtVersion) {
			builtVersion = signal.contextVersion;
			rebuild(signal.context);
		}
	});

	$effect(() => () => {
		geometry.dispose();
		material.dispose();
	});
</script>

<T.LineSegments {geometry} {material} frustumCulled={false} />

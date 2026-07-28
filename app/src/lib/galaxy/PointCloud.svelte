<script lang="ts">
	import { T, useTask } from '@threlte/core';
	import { untrack } from 'svelte';
	import * as THREE from 'three';
	import type { BirdyAssets } from '$lib/data/types';
	import { fragmentShader, vertexShader, type VisualSignal } from './shaders';

	interface Props {
		assets: BirdyAssets;
		signal: VisualSignal;
		pointSize?: number;
		spin?: boolean;
	}

	let { assets, signal, pointSize = 7, spin = true }: Props = $props();

	// The corpus never changes while the component is alive, so the buffers are built once
	// from the initial props rather than tracked.
	const clusterCount = untrack(() => Math.max(1, assets.centroids.items.length));

	const geometry = untrack(() => {
		const g = new THREE.BufferGeometry();
		g.setAttribute('position', new THREE.BufferAttribute(assets.positions, 3));
		const cluster = new Float32Array(assets.points.n);
		const seed = new Float32Array(assets.points.n);
		for (let i = 0; i < assets.points.n; i++) {
			cluster[i] = assets.points.clusterId[i] ?? 0;
			// deterministic per-point phase offset, so the pulse is not synchronised
			seed[i] = ((i * 2654435761) % 1000) / 1000;
		}
		g.setAttribute('aCluster', new THREE.BufferAttribute(cluster, 1));
		g.setAttribute('aSeed', new THREE.BufferAttribute(seed, 1));
		g.computeBoundingSphere();
		return g;
	});

	const material = new THREE.ShaderMaterial({
		vertexShader: vertexShader(clusterCount),
		fragmentShader,
		uniforms: {
			uActivation: { value: new Float32Array(clusterCount) },
			uTime: { value: 0 },
			uLevel: { value: 0 },
			uPointSize: { value: untrack(() => pointSize) },
			uPixelRatio: { value: typeof window === 'undefined' ? 1 : Math.min(2, window.devicePixelRatio) },
			uHighlight: { value: -1 },
			uSizeScale: { value: 2.6 },
			uColdColor: { value: new THREE.Color('#6c86cf') },
			uHotColor: { value: new THREE.Color('#ffd479') }
		},
		transparent: true,
		depthWrite: false,
		blending: THREE.AdditiveBlending
	});

	$effect(() => {
		material.uniforms.uPointSize.value = pointSize;
	});

	let group = $state<THREE.Group | undefined>();

	useTask((delta) => {
		const u = material.uniforms;
		u.uTime.value += delta;
		u.uLevel.value = signal.level;
		u.uHighlight.value = signal.best;
		const target = u.uActivation.value as Float32Array;
		target.set(signal.activations.subarray(0, target.length));
		if (spin && group) group.rotation.y += delta * 0.035;
	});

	$effect(() => () => {
		geometry.dispose();
		material.dispose();
	});
</script>

<T.Group bind:ref={group}>
	<T.Points {geometry} {material} frustumCulled={false} />
</T.Group>

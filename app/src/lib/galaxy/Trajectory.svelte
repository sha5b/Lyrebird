<script lang="ts">
	import { T, useTask } from '@threlte/core';
	import { untrack } from 'svelte';
	import * as THREE from 'three';
	import type { BirdyAssets } from '$lib/data/types';
	import {
		trajectoryFragmentShader,
		trajectoryPointsFragmentShader,
		trajectoryPointsVertexShader,
		trajectoryVertexShader,
		type VisualSignal
	} from './shaders';

	interface Props {
		assets: BirdyAssets;
		signal: VisualSignal;
	}

	let { assets, signal }: Props = $props();

	/** Samples per segment: enough that the travelling highlight moves smoothly. */
	const SUBDIVISIONS = 14;
	const MAX_NODES = 64;

	const centroids = untrack(() => assets.centroids.items);
	// Preallocated to the longest path we will ever draw, then a draw range is set per
	// path — reallocating buffers on every selection would churn GPU memory.
	const maxVertices = (MAX_NODES - 1) * SUBDIVISIONS + 1;
	const positions = new Float32Array(maxVertices * 3);
	const indices = new Float32Array(maxVertices);

	const geometry = untrack(() => {
		const g = new THREE.BufferGeometry();
		g.setAttribute('position', new THREE.BufferAttribute(positions, 3).setUsage(THREE.DynamicDrawUsage));
		g.setAttribute('aIndex', new THREE.BufferAttribute(indices, 1).setUsage(THREE.DynamicDrawUsage));
		g.setDrawRange(0, 0);
		return g;
	});

	const material = new THREE.ShaderMaterial({
		vertexShader: trajectoryVertexShader,
		fragmentShader: trajectoryFragmentShader,
		uniforms: {
			uProgress: { value: -1 },
			uAlpha: { value: 0 },
			uColdColor: { value: new THREE.Color('#93a9e8') },
			uHotColor: { value: new THREE.Color('#ffd479') }
		},
		transparent: true,
		depthWrite: false,
		blending: THREE.AdditiveBlending
	});

	const beadMaterial = new THREE.ShaderMaterial({
		vertexShader: trajectoryPointsVertexShader,
		fragmentShader: trajectoryPointsFragmentShader,
		uniforms: {
			uProgress: { value: -1 },
			uAlpha: { value: 0 },
			uPixelRatio: { value: typeof window === 'undefined' ? 1 : Math.min(2, window.devicePixelRatio) },
			uSizeScale: { value: 2.6 },
			uColdColor: { value: new THREE.Color('#93a9e8') },
			uHotColor: { value: new THREE.Color('#ffd479') }
		},
		transparent: true,
		depthWrite: false,
		blending: THREE.AdditiveBlending
	});

	let builtVersion = -1;

	/** Lays the path out as a subdivided polyline between cluster centroids. */
	function rebuild(path: number[]): void {
		const nodes = path.filter((i) => i >= 0 && i < centroids.length).slice(0, MAX_NODES);
		if (nodes.length < 2) {
			geometry.setDrawRange(0, 0);
			return;
		}
		let v = 0;
		for (let n = 0; n < nodes.length - 1; n++) {
			const a = centroids[nodes[n]].position;
			const b = centroids[nodes[n + 1]].position;
			// the last segment carries its endpoint, earlier ones stop short of it so
			// vertices are not duplicated at the joins
			const steps = n === nodes.length - 2 ? SUBDIVISIONS : SUBDIVISIONS - 1;
			for (let s = 0; s <= steps; s++) {
				const t = s / SUBDIVISIONS;
				positions[v * 3] = a[0] + (b[0] - a[0]) * t;
				positions[v * 3 + 1] = a[1] + (b[1] - a[1]) * t;
				positions[v * 3 + 2] = a[2] + (b[2] - a[2]) * t;
				indices[v] = n + t;
				v++;
			}
		}
		geometry.attributes.position.needsUpdate = true;
		geometry.attributes.aIndex.needsUpdate = true;
		geometry.setDrawRange(0, v);
		geometry.computeBoundingSphere();
	}

	useTask(() => {
		if (signal.pathVersion !== builtVersion) {
			builtVersion = signal.pathVersion;
			rebuild(signal.path);
		}
		material.uniforms.uProgress.value = signal.pathProgress;
		material.uniforms.uAlpha.value = signal.pathAlpha;
		beadMaterial.uniforms.uProgress.value = signal.pathProgress;
		beadMaterial.uniforms.uAlpha.value = signal.pathAlpha;
	});

	$effect(() => () => {
		geometry.dispose();
		material.dispose();
		beadMaterial.dispose();
	});
</script>

<T.Line {geometry} {material} frustumCulled={false} />
<T.Points {geometry} material={beadMaterial} frustumCulled={false} />

<script lang="ts">
	import { T, useTask } from '@threlte/core';
	import { untrack } from 'svelte';
	import * as THREE from 'three';
	import { buildSpeciesIndex } from '$lib/data/assets';
	import type { BirdyAssets } from '$lib/data/types';
	import {
		CLAIM_OF_FUNCTION,
		CLAIM_STRUCTURAL,
		COLOUR_MEANING,
		COLOUR_RESPONSE,
		PALETTE_SLOTS,
		fragmentShader,
		vertexShader,
		type VisualSignal
	} from './shaders';
	import { CLAIM_HOT, CLAIM_REST, speciesPalette } from './palette';

	interface Props {
		assets: BirdyAssets;
		signal: VisualSignal;
		pointSize?: number;
		/** Species index to keep at full strength; -1 shows every species equally. */
		focus?: number;
		/** COLOUR_RESPONSE or COLOUR_MEANING. */
		colourMode?: number;
		/** Multiplies the animation clock, so the pulse can be slowed down. */
		speed?: number;
	}

	let {
		assets,
		signal,
		pointSize = 7,
		focus = -1,
		colourMode = COLOUR_RESPONSE,
		speed = 1
	}: Props = $props();

	// The corpus never changes while the component is alive, so the buffers are built once
	// from the initial props rather than tracked.
	const clusterCount = untrack(() => Math.max(1, assets.centroids.items.length));

	// One float per point, rewritten every frame from the listener's per-point response.
	// A dynamic attribute rather than a texture: 4287 floats is 17 kB, and going through
	// a data texture would cost a fetch per vertex to save an upload that is already free.
	const activation = untrack(() => new Float32Array(assets.points.n));
	const activationAttribute = new THREE.BufferAttribute(activation, 1).setUsage(
		THREE.DynamicDrawUsage
	);

	const geometry = untrack(() => {
		const g = new THREE.BufferGeometry();
		g.setAttribute('position', new THREE.BufferAttribute(assets.positions, 3));
		const cluster = new Float32Array(assets.points.n);
		const seed = new Float32Array(assets.points.n);
		const species = new Float32Array(assets.points.n);
		const claim = new Float32Array(assets.points.n);
		const speciesIndex = buildSpeciesIndex(assets);
		// A point inherits its cluster's claim class; assets built before the pipeline
		// classified functions fall back to structural, which claims the least.
		const claimOf = assets.centroids.items.map(
			(c) => CLAIM_OF_FUNCTION[c.functionClass ?? ''] ?? CLAIM_STRUCTURAL
		);
		for (let i = 0; i < assets.points.n; i++) {
			cluster[i] = assets.points.clusterId[i] ?? 0;
			// deterministic per-point phase offset, so the pulse is not synchronised
			seed[i] = ((i * 2654435761) % 1000) / 1000;
			species[i] = speciesIndex.get(assets.points.speciesId[i] ?? '') ?? -1;
			claim[i] = claimOf[cluster[i]] ?? CLAIM_STRUCTURAL;
		}
		g.setAttribute('aCluster', new THREE.BufferAttribute(cluster, 1));
		g.setAttribute('aSeed', new THREE.BufferAttribute(seed, 1));
		g.setAttribute('aSpecies', new THREE.BufferAttribute(species, 1));
		g.setAttribute('aClaim', new THREE.BufferAttribute(claim, 1));
		g.setAttribute('aAct', activationAttribute);
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
			uFocus: { value: -1 },
			// Enough that an unselected species still reads as part of the same corpus,
			// little enough that the selected one is unmistakably the subject.
			uFocusDim: { value: 0.16 },
			uOpacity: { value: 1 },
			uMode: { value: COLOUR_RESPONSE },
			uRest: { value: Array.from({ length: PALETTE_SLOTS }, () => new THREE.Color()) },
			uHot: { value: Array.from({ length: PALETTE_SLOTS }, () => new THREE.Color()) },
			uSurface: { value: new THREE.Color('#fafbfc') }
		},
		transparent: true,
		depthWrite: false,
		blending: THREE.NormalBlending
	});

	$effect(() => {
		material.uniforms.uPointSize.value = pointSize;
	});

	$effect(() => {
		material.uniforms.uFocus.value = focus;
	});

	const species = speciesPalette();

	// Both palettes occupy the same uniforms; switching mode rewrites them rather than
	// shipping four arrays and branching in the fragment shader for every pixel.
	$effect(() => {
		const meaning = colourMode === COLOUR_MEANING;
		const rest = meaning ? CLAIM_REST : species.rest;
		const hot = meaning ? CLAIM_HOT : species.hot;
		const uRest = material.uniforms.uRest.value as THREE.Color[];
		const uHot = material.uniforms.uHot.value as THREE.Color[];
		for (let i = 0; i < PALETTE_SLOTS; i++) {
			uRest[i].set(rest[i % rest.length]);
			uHot[i].set(hot[i % hot.length]);
		}
		material.uniforms.uMode.value = colourMode;
	});

	useTask((delta) => {
		const u = material.uniforms;
		u.uTime.value += delta * speed;
		u.uLevel.value = signal.level;
		u.uHighlight.value = signal.best;
		const target = u.uActivation.value as Float32Array;
		target.set(signal.activations.subarray(0, target.length));

		activation.set(signal.pointActivation.subarray(0, activation.length));
		activationAttribute.needsUpdate = true;
	});

	$effect(() => () => {
		geometry.dispose();
		material.dispose();
	});
</script>

<T.Points {geometry} {material} frustumCulled={false} />

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
		COLOUR_MONO,
		COLOUR_RESPONSE,
		PALETTE_SLOTS,
		fragmentShader,
		vertexShader,
		type VisualSignal
	} from './shaders';
	import { CLAIM_HOT, CLAIM_REST, MONO_HOT, MONO_REST, speciesPalette } from './palette';
	import { buildLayouts, type LayoutId, type LayoutView } from './layouts';

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
		/** Which arrangement to show. Changing it animates the cloud into the new one. */
		layout?: LayoutId;
		/** Written into as the cloud rearranges, so lines and labels follow their knots. */
		view: LayoutView;
	}

	let {
		assets,
		signal,
		pointSize = 7,
		focus = -1,
		colourMode = COLOUR_RESPONSE,
		speed = 1,
		layout = 'acoustic',
		view
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

	// A point inherits its cluster's claim class; assets built before the pipeline
	// classified functions fall back to structural, which claims the least.
	const claimOfCluster = untrack(() =>
		assets.centroids.items.map(
			(c) => CLAIM_OF_FUNCTION[c.functionClass ?? ''] ?? CLAIM_STRUCTURAL
		)
	);

	// `position` holds where the cloud is coming *from* and is rewritten at the start of
	// each rearrangement; `aTarget` is where it is going. The shader interpolates.
	const current = untrack(() => Float32Array.from(assets.positions));
	const target = untrack(() => Float32Array.from(assets.positions));
	const positionAttribute = new THREE.BufferAttribute(current, 3).setUsage(
		THREE.DynamicDrawUsage
	);
	const targetAttribute = new THREE.BufferAttribute(target, 3).setUsage(THREE.DynamicDrawUsage);

	const geometry = untrack(() => {
		const g = new THREE.BufferGeometry();
		g.setAttribute('position', positionAttribute);
		g.setAttribute('aTarget', targetAttribute);
		const cluster = new Float32Array(assets.points.n);
		const seed = new Float32Array(assets.points.n);
		const species = new Float32Array(assets.points.n);
		const claim = new Float32Array(assets.points.n);
		const speciesIndex = buildSpeciesIndex(assets);
		const claimOf = claimOfCluster;
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
			uMorph: { value: 1 },
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
		const rest =
			colourMode === COLOUR_MONO
				? [MONO_REST]
				: colourMode === COLOUR_MEANING
					? CLAIM_REST
					: species.rest;
		const hot =
			colourMode === COLOUR_MONO
				? [MONO_HOT]
				: colourMode === COLOUR_MEANING
					? CLAIM_HOT
					: species.hot;
		const uRest = material.uniforms.uRest.value as THREE.Color[];
		const uHot = material.uniforms.uHot.value as THREE.Color[];
		for (let i = 0; i < PALETTE_SLOTS; i++) {
			uRest[i].set(rest[i % rest.length]);
			uHot[i].set(hot[i % hot.length]);
		}
		material.uniforms.uMode.value = colourMode;
	});

	const layouts = untrack(() =>
		buildLayouts(assets, buildSpeciesIndex(assets), claimOfCluster)
	);
	/** Seconds a rearrangement takes. Long enough to follow a point across it. */
	const MORPH_SECONDS = 1.5;
	let morph = 1;
	let fromLayout: LayoutId = 'acoustic';
	let toLayout: LayoutId = 'acoustic';

	$effect(() => {
		if (layout === toLayout) return;
		// Freeze wherever the cloud is right now and start again from there, so
		// interrupting a rearrangement half way does not snap.
		const a = layouts[fromLayout].positions;
		const b = layouts[toLayout].positions;
		const t = Math.min(1, morph);
		for (let i = 0; i < current.length; i++) current[i] = a[i] + (b[i] - a[i]) * t;
		target.set(layouts[layout].positions);
		positionAttribute.needsUpdate = true;
		targetAttribute.needsUpdate = true;
		fromLayout = toLayout;
		toLayout = layout;
		morph = 0;
	});

	useTask((delta) => {
		const u = material.uniforms;
		u.uTime.value += delta * speed;

		if (morph < 1) {
			morph = Math.min(1, morph + delta / MORPH_SECONDS);
			// smoothstep, so it eases out of the old arrangement and into the new one
			const eased = morph * morph * (3 - 2 * morph);
			u.uMorph.value = eased;
			// The centroids travel with their points. Forty-four lerps a frame, against
			// the four thousand the GPU is doing anyway.
			const a = layouts[fromLayout].centroids;
			const b = layouts[toLayout].centroids;
			for (let i = 0; i < view.centroids.length; i++) {
				view.centroids[i] = a[i] + (b[i] - a[i]) * eased;
			}
			view.version++;
			view.morphing = morph < 1;
		}
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

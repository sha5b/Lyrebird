<script lang="ts">
	/**
	 * One small marker per membered knot, at the knot's drawn centre.
	 *
	 * A centroid is arithmetic, not a member: the nearest real point sits a mean of
	 * 0.079 box units away (and the blossom spreads members further on approach), so
	 * every thread, label anchor and wave origin terminated in empty space. The
	 * marker is the visible anchor those things land on. It is a *waypoint, not
	 * data* — smaller and dimmer than a real point at rest (1.5 px floor against the
	 * cloud's 2-3 px, 0.35 alpha against the wash's ~0.5), so the galaxy does not
	 * gain 14 003 new blobs; at whole-galaxy zoom they read as the faint pin a map
	 * leaves under a region.
	 *
	 * **It reacts to everything its knot reacts to**, by construction rather than by
	 * a second state channel: the vertex stage reads the SAME cluster-state texture
	 * the point cloud drives (R = activation, G = sung, B = learn — the shared
	 * `clusterState` prop, bound out of PointCloud), so a marker brightens and grows
	 * when its knot answers, swells with pipeline work, and goes quiet exactly when
	 * the quiet gate zeroes the texture. There is no per-frame CPU here at all: the
	 * geometry is static (positions are the seeded layout centroids, knot gap
	 * included), the colour per knot is baked, and only the texture moves.
	 *
	 * Colour follows the tags' rule (NodeProjector's --accent): the knot's identity
	 * hue — the species hue in ink mode, the class colour in provenance — resting as
	 * a quarter-strength tint over a neutral slate and taking over as the knot
	 * answers. Memberless knots get no marker: their centroid is (0,0,0), the centre
	 * of the box, a documented lie (layouts.ts), and a pin there would anchor threads
	 * to nowhere.
	 */
	import { T, useTask } from '@threlte/core';
	import { untrack } from 'svelte';
	import * as THREE from 'three';
	import { clusterProvenance } from '$lib/data/assets';
	import type { BirdyAssets } from '$lib/data/types';
	import type { LayoutView } from './layouts';
	import { provenanceColourScaled, speciesColourScaled } from './palette';
	import { SIZE_REFERENCE } from './shaders';

	interface Props {
		assets: BirdyAssets;
		/** Where the centroids are right now; seeded once by PointCloud. */
		view: LayoutView;
		/** The point cloud's live cluster-state texture, shared by bind:. */
		clusterState?: THREE.DataTexture;
		/** The scale the whole group is drawn at, from the listening distance. */
		spread?: number;
		/** Ink mode (species hue per knot) vs provenance (class colour per knot). */
		plain?: boolean;
	}

	let { assets, view, clusterState, spread = 1, plain = true }: Props = $props();

	const clusterCount = untrack(() => Math.max(1, assets.centroids.items.length));
	// The texture's grid, computed by the same rule the point cloud used to build it,
	// so an index means the same texel in both programs.
	const texWidth = Math.min(1024, clusterCount);
	const texHeight = Math.max(1, Math.ceil(clusterCount / texWidth));

	const geometry = new THREE.BufferGeometry();

	/**
	 * (Re)build the static half: positions and per-knot identity colours. Runs once
	 * the layout is seeded, and again only on a mode switch — the identity hue is
	 * the one thing the colour language changes, and 14 000 colour strings on a
	 * toggle is the same price the tags pay.
	 */
	$effect(() => {
		void plain;
		void view.version;
		const items = assets.centroids.items;
		const classes = plain ? null : clusterProvenance(assets);
		const positions: number[] = [];
		const clusters: number[] = [];
		const colours: number[] = [];
		const c = new THREE.Color();
		for (let i = 0; i < clusterCount; i++) {
			if (!(view.counts[i] ?? 0)) continue;
			positions.push(view.centroids[i * 3], view.centroids[i * 3 + 1], view.centroids[i * 3 + 2]);
			clusters.push(i);
			c.setStyle(
				plain
					? speciesColourScaled(items[i]?.speciesId ?? '', 1.0)
					: provenanceColourScaled(classes?.[i] ?? 4, 1.0)
			);
			colours.push(c.r, c.g, c.b);
		}
		geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
		geometry.setAttribute('aCluster', new THREE.Float32BufferAttribute(clusters, 1));
		geometry.setAttribute('aColour', new THREE.Float32BufferAttribute(colours, 3));
		geometry.computeBoundingSphere();
	});

	const material = new THREE.ShaderMaterial({
		vertexShader: /* glsl */ `
			attribute float aCluster;
			attribute vec3 aColour;
			uniform sampler2D uClusterState;
			uniform vec2 uClusterTexSize;
			uniform float uPixelRatio;
			uniform float uSizeScale;
			varying vec3 vColour;
			varying float vHot;
			vec3 clusterState(int index) {
				float i = float(index);
				float x = (mod(i, uClusterTexSize.x) + 0.5) / uClusterTexSize.x;
				float y = (floor(i / uClusterTexSize.x) + 0.5) / uClusterTexSize.y;
				return texture2D(uClusterState, vec2(x, y)).rgb;
			}
			void main() {
				vec3 state = clusterState(int(aCluster + 0.5));
				// The same weights the cloud gives the three channels: the response in
				// full, the learning swell at the 0.55 the points use, sung riding on
				// top so a scheduled note shows even where the match is weak.
				vHot = clamp(max(state.r, state.b * 0.55) + state.g * 0.5, 0.0, 1.0);
				vColour = aColour;
				vec4 mv = modelViewMatrix * vec4(position, 1.0);
				gl_Position = projectionMatrix * mv;
				// The same softened perspective the cloud quotes (uSizeScale / -mv.z
				// to the 0.7), so a marker follows the same size law as the points it
				// anchors. The floor is 1.5 px — under the cloud's 2-3 px resting
				// floor, because a waypoint must stay under the data; the ceiling
				// keeps a hard-answering knot's pin under the marks around it.
				float persp = pow(uSizeScale / max(0.001, -mv.z), 0.7);
				gl_PointSize = clamp((2.0 + vHot * 3.0) * uPixelRatio * persp, 1.5, 9.0);
			}
		`,
		fragmentShader: /* glsl */ `
			varying vec3 vColour;
			varying float vHot;
			void main() {
				vec2 uv = gl_PointCoord - 0.5;
				float d = length(uv);
				if (d > 0.5) discard;
				// The cloud's own rule: a hard disc with a one-pixel feather measured
				// by the derivative, so a distant pin is a small crisp dot.
				float aa = max(fwidth(d), 0.0015);
				float disc = 1.0 - smoothstep(0.40 - aa, 0.40 + aa, d);
				// Rest is a neutral slate with a quarter of the identity hue — enough
				// that the pin is visibly a marker, not a stray datum, and the hue is
				// only fully claimed when the knot answers. Alpha stays under the
				// resting wash's ~0.5 even at full response.
				vec3 colour = mix(vec3(0.52, 0.58, 0.68), vColour, 0.25 + 0.75 * vHot);
				gl_FragColor = vec4(colour, disc * (0.30 + 0.55 * vHot));
			}
		`,
		uniforms: {
			uClusterState: { value: null },
			uClusterTexSize: { value: new THREE.Vector2(texWidth, texHeight) },
			uPixelRatio: { value: typeof window === 'undefined' ? 1 : Math.min(2, window.devicePixelRatio) },
			uSizeScale: { value: SIZE_REFERENCE }
		},
		transparent: true,
		depthWrite: false,
		blending: THREE.NormalBlending
	});

	// The texture arrives by bind: after PointCloud's init, so it lands by effect,
	// not at construction.
	$effect(() => {
		if (clusterState) material.uniforms.uClusterState.value = clusterState;
	});

	$effect(() => {
		material.uniforms.uSizeScale.value = SIZE_REFERENCE * spread;
	});

	useTask(() => {
		// One compare per frame, the same DPR honesty the cloud keeps.
		const pr = Math.min(2, window.devicePixelRatio || 1);
		if (material.uniforms.uPixelRatio.value !== pr) material.uniforms.uPixelRatio.value = pr;
	});

	$effect(() => () => {
		geometry.dispose();
		material.dispose();
	});
</script>

<T.Points {geometry} {material} frustumCulled={false} />

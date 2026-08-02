<script lang="ts">
	import { T, useTask } from '@threlte/core';
	import { untrack } from 'svelte';
	import * as THREE from 'three';
	import { clusterProvenance } from '$lib/data/assets';
	import type { BirdyAssets } from '$lib/data/types';
	import { provenanceColourScaled } from './palette';
	import type { LayoutView } from './layouts';
	import type { VisualSignal } from './shaders';

	interface Props {
		assets: BirdyAssets;
		signal: VisualSignal;
		/** Where the centroids are right now; moves while the cloud rearranges. */
		view: LayoutView;
		/** Provenance language: each segment takes its knot's class colour. */
		prov?: boolean;
	}

	let { assets, signal, view, prov = false }: Props = $props();

	const centroids = untrack(() => assets.centroids.items);
	const klass = untrack(() => clusterProvenance(assets));

	// Disconnected segments rather than one polyline, so separate songs are not joined to
	// each other. Overlap is the point: where two songs share a transition the segment is
	// drawn twice and the accumulated alpha reads darker, so the bird's reused paths stand
	// out — on a light ground that means normal blending, not additive.
	// Colours follow the stage's language: neutral slate in ink mode (the backdrop the
	// accent reads against — the bird's hue lives on the tags and the response, not on
	// every thread), the class colour in provenance mode — per-vertex, so a thread
	// never speaks two languages at once.
	const NEUTRAL = new THREE.Color('#8595ae');
	const geometry = new THREE.BufferGeometry();
	const material = new THREE.LineBasicMaterial({
		transparent: true,
		opacity: 0.28,
		depthWrite: false,
		blending: THREE.NormalBlending,
		vertexColors: true
	});

	let builtVersion = -1;
	let builtLayout = -1;

	function rebuild(paths: number[][]): void {
		const points: number[] = [];
		const colors: number[] = [];
		const c = new THREE.Color();
		for (const path of paths) {
			const nodes = path.filter((i) => i >= 0 && i < centroids.length);
			for (let n = 0; n < nodes.length - 1; n++) {
				const a = nodes[n] * 3;
				const b = nodes[n + 1] * 3;
				points.push(
					view.centroids[a], view.centroids[a + 1], view.centroids[a + 2],
					view.centroids[b], view.centroids[b + 1], view.centroids[b + 2]
				);
				for (const knot of [nodes[n], nodes[n + 1]]) {
					if (prov) c.setStyle(provenanceColourScaled(klass[knot] ?? 4, 1.0));
					else c.copy(NEUTRAL);
					colors.push(c.r, c.g, c.b);
				}
			}
		}
		geometry.setAttribute('position', new THREE.Float32BufferAttribute(points, 3));
		geometry.setAttribute('color', new THREE.Float32BufferAttribute(colors, 3));
		geometry.computeBoundingSphere();
	}

	useTask(() => {
		if (signal.contextVersion !== builtVersion || view.version !== builtLayout) {
			builtVersion = signal.contextVersion;
			builtLayout = view.version;
			rebuild(signal.context);
		}
	});

	$effect(() => {
		// A language switch does not bump the context version; force the repaint.
		void prov;
		builtVersion = -1;
	});

	$effect(() => () => {
		geometry.dispose();
		material.dispose();
	});
</script>

<T.LineSegments {geometry} {material} frustumCulled={false} />

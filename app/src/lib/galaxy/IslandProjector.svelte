<script lang="ts">
	/**
	 * Puts each island's heading over the middle of its island, once per frame.
	 *
	 * The position is the mean of the knots that belong to the group, read from the shared
	 * view — which is the whole reason it needs no state of its own. `view.centroids` is
	 * rewritten every frame of a rearrangement, so a heading derived from it travels with
	 * its island through the morph automatically, and lands exactly where the island lands
	 * without anything having to interpolate it separately.
	 */
	import { T, useTask, useThrelte } from '@threlte/core';
	import * as THREE from 'three';
	import type { LayoutView } from './layouts';
	import type { VisualSignal } from './shaders';

	interface Props {
		/** Cluster indices per group, index-aligned with the elements. */
		groups: { key: string; members: number[] }[];
		elements: (HTMLElement | null)[];
		/** Hidden entirely when the arrangement has no islands. */
		show?: boolean;
		view: LayoutView;
		signal: VisualSignal;
	}

	let { groups, elements, show = true, view, signal }: Props = $props();

	/**
	 * Smoothed response per island: the strongest activation among its knots.
	 *
	 * A heading that only names a region is inert, and the one question you ask of a
	 * region while something is playing is whether it is *this* one. Taking the maximum
	 * rather than the mean is deliberate: one knot answering strongly is the island
	 * answering, and averaging it across three thousand quiet points would erase exactly
	 * the event worth showing.
	 */
	const heat = new Float32Array(64);

	const { camera, size } = useThrelte();
	let anchor = $state<THREE.Object3D | undefined>();
	const world = new THREE.Vector3();

	useTask(() => {
		const cam = camera.current;
		if (!cam || !anchor || !elements.length) return;
		anchor.updateWorldMatrix(true, false);
		const matrix = anchor.matrixWorld;
		const width = size.current.width;
		const height = size.current.height;

		for (let g = 0; g < groups.length; g++) {
			const node = elements[g];
			if (!node) continue;
			if (!show) {
				node.style.opacity = '0';
				node.style.visibility = 'hidden';
				continue;
			}
			const members = groups[g].members;
			let x = 0;
			let y = 0;
			let z = 0;
			let n = 0;
			for (const c of members) {
				if (c < 0 || c * 3 + 2 >= view.centroids.length) continue;
				x += view.centroids[c * 3];
				y += view.centroids[c * 3 + 1];
				z += view.centroids[c * 3 + 2];
				n++;
			}
			if (!n) {
				node.style.visibility = 'hidden';
				continue;
			}
			let peak = 0;
			for (const c of members) {
				const a = signal.activations[c] ?? 0;
				if (a > peak) peak = a;
			}
			if (g < heat.length) {
				heat[g] = heat[g] * 0.85 + peak * 0.15;
				node.style.setProperty('--act', heat[g].toFixed(3));
			}

			world.set(x / n, y / n, z / n).applyMatrix4(matrix).project(cam);
			const behind = world.z > 1 || world.z < -1;
			const px = (world.x * 0.5 + 0.5) * width;
			const py = (-world.y * 0.5 + 0.5) * height;
			// Centred on the island rather than hanging off it, and nudged up so the
			// heading sits above the densest part rather than buried in it.
			node.style.transform = `translate3d(${px.toFixed(1)}px, ${py.toFixed(1)}px, 0) translate(-50%, -160%)`;
			node.style.visibility = behind ? 'hidden' : 'visible';
			node.style.opacity = behind ? '0' : '1';
		}
	});
</script>

<T.Object3D bind:ref={anchor} />

<script lang="ts">
	/**
	 * Flies the camera to a phrase and keeps it framed.
	 *
	 * Picking something out of the history should take you to it. The knot it lives in is
	 * one of forty in a cloud you may have orbited away from, and "it is highlighted
	 * somewhere behind you" is not a way to find anything.
	 *
	 * Two separate motions, because they end at different times:
	 *
	 * - the **flight**, which closes the distance to the phrase, and ends as soon as it
	 *   arrives or the moment you touch the controls — a camera that keeps pulling after
	 *   you have grabbed it feels broken;
	 * - the **lock**, which keeps the orbit target on the phrase for as long as it stays
	 *   selected. That one survives your dragging on purpose: the cloud is drifting, and
	 *   without it the thing you just asked to see rotates back out of the frame while
	 *   you look at it. Orbiting and zooming stay yours throughout — the lock only ever
	 *   writes the point they happen around.
	 */
	import { untrack } from 'svelte';
	import { useTask, useThrelte } from '@threlte/core';
	import * as THREE from 'three';
	import type { LayoutView } from './layouts';

	interface Props {
		/** Where the centroids are right now; moves while the cloud rearranges. */
		view: LayoutView;
		/** Cluster ids to keep in frame. Empty releases the camera. */
		frame: number[];
		/** The rotating, scaled group the centroids live in. */
		group?: THREE.Object3D;
		/** The OrbitControls instance to steer. */
		controls?: { target: THREE.Vector3; update: () => void } | undefined;
		/** Bumped by the page whenever the viewer grabs the controls, which ends a flight. */
		interrupt?: number;
	}

	let { view, frame, group, controls, interrupt = 0 }: Props = $props();

	const { camera, invalidate } = useThrelte();
	const wanted = new THREE.Vector3();
	const offset = new THREE.Vector3();
	/** Scratch, reused every frame: this runs at 60 Hz and must not allocate. */
	const reaches: number[] = [];

	let flying = $state(false);
	let seenInterrupt = untrack(() => interrupt);

	$effect(() => {
		flying = frame.length > 0;
	});
	$effect(() => {
		// Only a *change* ends the flight, so this does not fight the effect above on mount.
		if (interrupt === seenInterrupt) return;
		seenInterrupt = interrupt;
		flying = false;
	});

	/**
	 * How much of the frame the thing being framed should fill. Below 1 it has air around
	 * it, which is what stops a single cluster from becoming a wall of points.
	 */
	const FILL = 0.82;
	/**
	 * Fit to this quantile of the reach rather than to the furthest member. A species is
	 * not a region in the acoustic layout — a couple of its calls sound like some other
	 * bird's and sit across the cloud — so fitting to the maximum frames the two outliers
	 * and shows you the whole galaxy again. This frames where the bird mostly is and lets
	 * the strays fall outside.
	 */
	const REACH_QUANTILE = 0.85;
	/** Points spill past their centroids; the frame has to allow for the knot's own size. */
	const POINT_MARGIN = 1.18;

	useTask((delta) => {
		const cam = camera.current;
		if (!frame.length || !group || !controls || !cam) return;

		wanted.set(0, 0, 0);
		let n = 0;
		for (const c of frame) {
			if (c < 0 || c * 3 + 2 >= view.centroids.length) continue;
			wanted.x += view.centroids[c * 3];
			wanted.y += view.centroids[c * 3 + 1];
			wanted.z += view.centroids[c * 3 + 2];
			n++;
		}
		if (!n) return;
		wanted.multiplyScalar(1 / n);

		// How far the framed set reaches from its own centre, in the group's space. One
		// cluster gives a small number and the whole galaxy a large one, which is what
		// makes the same code frame a phrase, a bird's whole repertoire, or everything.
		reaches.length = 0;
		for (const c of frame) {
			if (c < 0 || c * 3 + 2 >= view.centroids.length) continue;
			const dx = view.centroids[c * 3] - wanted.x;
			const dy = view.centroids[c * 3 + 1] - wanted.y;
			const dz = view.centroids[c * 3 + 2] - wanted.z;
			reaches.push(Math.sqrt(dx * dx + dy * dy + dz * dz));
		}
		reaches.sort((a, b) => a - b);
		const reach =
			(reaches.length <= 4
				? reaches[reaches.length - 1]
				: reaches[Math.min(reaches.length - 1, Math.floor(reaches.length * REACH_QUANTILE))]) *
			POINT_MARGIN;
		// The centroids are in the group's own space: it is rotating and scaled, so the
		// same phrase is somewhere else in the world every frame.
		group.updateWorldMatrix(true, false);
		group.localToWorld(wanted);

		controls.target.lerp(wanted, Math.min(1, delta * (flying ? 4 : 9)));

		if (flying) {
			offset.copy(cam.position).sub(controls.target);
			const radius = offset.length();
			// Fit the reach into the *narrower* of the two view angles, so a wide-screen
			// window does not crop the top of the cloud.
			const scale = (group as THREE.Object3D).scale?.x ?? 1;
			const perspective = cam as THREE.PerspectiveCamera;
			const vertical = ((perspective.fov ?? 55) * Math.PI) / 360;
			const horizontal = Math.atan(Math.tan(vertical) * (perspective.aspect ?? 1.6));
			const spanned = (reach + 0.12) * scale;
			const want = Math.max(0.3, spanned / (Math.tan(Math.min(vertical, horizontal)) * FILL));
			const next = radius + (want - radius) * Math.min(1, delta * 2.2);
			cam.position.copy(controls.target).add(offset.setLength(next));
			if (Math.abs(next - want) < 0.02 * want) flying = false;
		}

		controls.update();
		invalidate();
	});
</script>

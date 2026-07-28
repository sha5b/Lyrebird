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

	/** How close to sit to the phrase, as a share of the cloud's current radius. */
	const FRAME_RADIUS = 0.8;

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
		// The centroids are in the group's own space: it is rotating and scaled, so the
		// same phrase is somewhere else in the world every frame.
		group.updateWorldMatrix(true, false);
		group.localToWorld(wanted);

		controls.target.lerp(wanted, Math.min(1, delta * (flying ? 4 : 9)));

		if (flying) {
			offset.copy(cam.position).sub(controls.target);
			const radius = offset.length();
			const scale = (group as THREE.Object3D).scale?.x ?? 1;
			const want = FRAME_RADIUS * scale + 0.35;
			const next = radius + (want - radius) * Math.min(1, delta * 2.2);
			cam.position.copy(controls.target).add(offset.setLength(next));
			if (Math.abs(next - want) < 0.02) flying = false;
		}

		controls.update();
		invalidate();
	});
</script>

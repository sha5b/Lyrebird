<script lang="ts">
	/**
	 * How much of the galaxy one screen pixel covers, reported out of the scene.
	 *
	 * The scale bar is HTML sitting over the canvas, so it cannot see the camera; this
	 * lives inside the scene and hands the one number across. Quoted in the cloud's *own*
	 * units rather than world units — the group is scaled by the listening distance, and a
	 * ruler that changed its reading when you moved a slider that does not move anything
	 * would be measuring the slider.
	 *
	 * Distance is taken to the orbit target, not to the group's origin, because the target
	 * is by definition what is being looked at. Framing a single knot flies the camera to
	 * that knot; measuring from the centre of the corpus instead would report the scale of
	 * something off screen.
	 */
	import { useTask, useThrelte } from '@threlte/core';
	import * as THREE from 'three';

	interface Props {
		/** The rotating, scaled group the cloud lives in. */
		group?: THREE.Object3D;
		/** OrbitControls, for the point the view is actually about. */
		controls?: { target: THREE.Vector3 } | undefined;
		onchange?: (unitsPerPixel: number) => void;
	}

	let { group, controls, onchange }: Props = $props();

	const { camera, size } = useThrelte();
	const centre = new THREE.Vector3();
	/**
	 * Last value reported. The bar is Svelte state and the label is text, so pushing a
	 * changed number every frame would re-render the overlay sixty times a second to move
	 * a ruler by a hundredth of a pixel. A deadband means it updates while you scroll and
	 * then stops.
	 */
	let reported = 0;

	useTask(() => {
		const cam = camera.current as THREE.PerspectiveCamera | undefined;
		if (!cam || !group) return;
		group.updateWorldMatrix(true, false);
		const scale = group.matrixWorld.getMaxScaleOnAxis() || 1;
		if (controls) centre.copy(controls.target);
		else centre.setFromMatrixPosition(group.matrixWorld);
		const distance = cam.position.distanceTo(centre);
		const height = Math.max(1, size.current.height);
		// Visible height at that distance, in world units, divided by the pixels it spans —
		// then out of world units and into the cloud's own.
		const visible = 2 * distance * Math.tan((((cam.fov ?? 55) * Math.PI) / 180) / 2);
		const perPixel = visible / height / scale;
		if (!(perPixel > 0) || !Number.isFinite(perPixel)) return;
		if (reported > 0 && Math.abs(perPixel - reported) < reported * 0.004) return;
		reported = perPixel;
		onchange?.(perPixel);
	});
</script>

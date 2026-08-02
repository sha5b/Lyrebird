<script lang="ts">
	/**
	 * How big the picture currently is, in the corpus's own units.
	 *
	 * The stage had no scale at all: the same cloud at two zoom levels looked like two
	 * different corpora, and nothing on screen said whether the gap between two knots
	 * you were looking at was a large distance or a small one. A scale needs a unit,
	 * and the projection's axes do not have one — they are the three leading directions
	 * of a landmark cMDS, in arbitrary units, and their absolute origin means nothing.
	 * **The one honest unit the build owns is its own knot spacing**: the median
	 * nearest-neighbour distance between knot centres, measured in PointCloud and
	 * passed in here. "Two knot-spacings across" is a sentence about this corpus; "0.27
	 * box units across" is a sentence about nobody.
	 *
	 * What it computes each frame is a pixels-per-unit figure at the depth of the orbit
	 * target — the same convention a scale bar in any 3-D viewer uses, exact at the
	 * centre of the view and approximate for anything nearer or farther. The caller is
	 * told only when the number has actually moved (0.5 %), so orbiting at a fixed
	 * distance costs nothing and a zoom repaints the ruler smoothly.
	 *
	 * It draws nothing.
	 */
	import { useTask, useThrelte } from '@threlte/core';
	import * as THREE from 'three';

	interface Props {
		/** Median nearest-neighbour knot distance, in layout box units. */
		knotSpacing: number;
		/** The scale the cloud group is drawn at (the listening-distance spread). */
		spread?: number;
		/** The OrbitControls target — the point the view is about. */
		controls?: { target: THREE.Vector3 } | undefined;
		/** Device pixels per knot spacing, and the view's width in knot spacings. */
		onscale?: (scale: { pxPerKnot: number; widthKnots: number; heightKnots: number }) => void;
	}

	let { knotSpacing, spread = 1, controls, onscale }: Props = $props();

	const { camera, size } = useThrelte();
	const eye = new THREE.Vector3();
	const target = new THREE.Vector3();
	let last = 0;

	useTask(() => {
		const cam = camera.current as THREE.PerspectiveCamera | undefined;
		if (!cam?.isPerspectiveCamera || !onscale) return;
		const height = $size.height;
		if (!height) return;
		cam.getWorldPosition(eye);
		target.copy(controls?.target ?? new THREE.Vector3());
		// Along the view direction, not straight-line to the target: the visible height
		// of a perspective frustum is a function of depth, and depth is the projection
		// of the eye-to-target vector onto the forward axis. They agree when the camera
		// looks at its target, which it does here, and this stays right if that changes.
		const depth = Math.max(0.001, eye.distanceTo(target));
		const worldHeight = 2 * depth * Math.tan((cam.fov * Math.PI) / 360);
		// The cloud is drawn inside a scaled group, so a box unit is `spread` world
		// units on screen. Undo it here and the ruler ticks in the layout's own space,
		// which is where the knot spacing was measured.
		const pxPerBoxUnit = (height / worldHeight) * Math.max(0.001, spread);
		const pxPerKnot = pxPerBoxUnit * Math.max(1e-6, knotSpacing);
		if (!Number.isFinite(pxPerKnot) || pxPerKnot <= 0) return;
		// A relative gate rather than an absolute one: the useful resolution is the same
		// fraction of the number at every zoom, and an absolute epsilon would either
		// spam at galaxy distance or freeze up close.
		if (last > 0 && Math.abs(pxPerKnot - last) / last < 0.005) return;
		last = pxPerKnot;
		onscale({
			pxPerKnot,
			widthKnots: $size.width / pxPerKnot,
			heightKnots: height / pxPerKnot
		});
	});
</script>

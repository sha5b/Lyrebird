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
	const axis: [number[], number[], number[]] = [[], [], []];

	/** In-place; the caller owns the array and does not need the original order. */
	function median(values: number[]): number {
		values.sort((a, b) => a - b);
		const mid = values.length >> 1;
		return values.length % 2 ? values[mid] : (values[mid - 1] + values[mid]) / 2;
	}

	let flying = $state(false);
	let seenInterrupt = untrack(() => interrupt);
	/**
	 * First-load snap. The opening view of the app is the whole galaxy (`frame` falls
	 * back to every cluster), and easing toward it from the default camera means the
	 * first thing every visitor sees is a cloud that is not framed yet — they read it
	 * as broken before the flight ever arrives. The first time this component sees a
	 * non-empty frame it places the camera at the fitted radius directly; every later
	 * flight still eases, because those are answers to clicks and a click can wait.
	 */
	let snapped = false;

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
	 * Fit to a quantile of the reach rather than to the furthest member, and to a tighter
	 * one the more clusters there are.
	 *
	 * A species is not a region in the acoustic layout — a couple of its calls sound like
	 * some other bird's and sit across the cloud — so fitting to the maximum frames the
	 * two outliers and shows you the whole galaxy again. A fixed 0.85 was not enough:
	 * under UMAP a bird's forty-odd clusters are genuinely scattered everywhere, so
	 * eighty-five percent of them still spans nearly the whole box and selecting a bird
	 * zoomed to the same view as selecting nothing.
	 *
	 * Twelve nodes or fewer is a phrase or a small repertoire and every one of them
	 * matters; beyond that it is a bird's whole output and the job is to find where it
	 * mostly lives.
	 *
	 * Framing *everything* is the exception and has to be excluded by name. "Show me the
	 * whole galaxy" means the whole galaxy — cropping to where the corpus mostly is would
	 * cut off the outlying islands, which are the part of a UMAP layout most worth seeing.
	 */
	function reachQuantile(count: number, total: number): number {
		if (total > 0 && count >= total * 0.9) return 0.97;
		if (count <= 4) return 1;
		if (count <= 12) return 0.85;
		return 0.55;
	}
	/** Points spill past their centroids; the frame has to allow for the knot's own size. */
	const POINT_MARGIN = 1.18;

	useTask((delta) => {
		const cam = camera.current;
		if (!frame.length || !group || !controls || !cam) return;

		// The centre is a per-axis median, not a mean. One cluster stranded on the far side
		// of the galaxy drags a mean a long way toward itself and the camera then centres
		// on empty space between the bird and its stray; a median ignores it entirely.
		//
		// A knot with no members has no position — its centroid is (0,0,0), the centre of
		// the box, which `layouts.ts` documents as a lie and says every positional effect
		// must check `counts` before using. This one did not, so on a build with memberless
		// knots the camera aimed at a weighted average of the corpus and the origin.
		axis[0].length = 0;
		axis[1].length = 0;
		axis[2].length = 0;
		for (const c of frame) {
			if (c < 0 || c * 3 + 2 >= view.centroids.length) continue;
			if (!view.counts[c]) continue;
			axis[0].push(view.centroids[c * 3]);
			axis[1].push(view.centroids[c * 3 + 1]);
			axis[2].push(view.centroids[c * 3 + 2]);
		}
		if (!axis[0].length) return;
		// `median` sorts in place, so the extremes are the ends afterwards.
		const mx = median(axis[0]);
		const my = median(axis[1]);
		const mz = median(axis[2]);

		/**
		 * **Framing everything centres on the extent, not on the median.**
		 *
		 * The median is the right centre for a bird — that is what it was written for, and
		 * it is why one stray call cannot drag the view off the repertoire. It is the wrong
		 * centre for "the whole galaxy", because the median of the *knots* is not the middle
		 * of the *cloud*: knot density is skewed, so half the knots sitting in one lobe puts
		 * the median in that lobe. Measured on the built assets, the median lands **14 % of
		 * the cloud's span off centre on the debug-100 build and 27 % off on the production
		 * build (now the shipped one)** — the projection itself is centred on the origin to within 0.001, and the
		 * camera was aiming a quarter of the way out from it. That is the "it does not centre
		 * on the centre of the point cloud" the owner reported, and it shows up worst on
		 * autoload because autoload is exactly the whole-galaxy case.
		 *
		 * `reachQuantile` below already excludes framing-everything by name for the *reach*,
		 * for the same reason; the exception was simply never applied to the centre.
		 */
		const total = view.centroids.length / 3;
		if (total > 0 && axis[0].length >= total * 0.9) {
			wanted.set(
				(axis[0][0] + axis[0][axis[0].length - 1]) / 2,
				(axis[1][0] + axis[1][axis[1].length - 1]) / 2,
				(axis[2][0] + axis[2][axis[2].length - 1]) / 2
			);
		} else {
			wanted.set(mx, my, mz);
		}

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
		const q = reachQuantile(reaches.length, view.centroids.length / 3);
		const reach =
			reaches[Math.min(reaches.length - 1, Math.floor((reaches.length - 1) * q))] * POINT_MARGIN;
		// The centroids are in the group's own space: it is rotating and scaled, so the
		// same phrase is somewhere else in the world every frame.
		group.updateWorldMatrix(true, false);
		group.localToWorld(wanted);

		const moved = controls.target.distanceToSquared(wanted);
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
			if (!snapped) {
				// First load: land framed, no flight — see the `snapped` note above.
				snapped = true;
				flying = false;
				controls.target.copy(wanted);
				offset.copy(cam.position).sub(controls.target);
				cam.position.copy(controls.target).add(offset.setLength(want));
				controls.update();
				invalidate();
				return;
			}
			const next = radius + (want - radius) * Math.min(1, delta * 2.2);
			cam.position.copy(controls.target).add(offset.setLength(next));
			if (Math.abs(next - want) < 0.02 * want) flying = false;
			controls.update();
			invalidate();
			return;
		}

		// OrbitControls' own task already calls update() every frame for damping, so a
		// second one here applied damping twice per frame (the effective damping time
		// was half the configured 0.08). Spend it only when the aim actually moved —
		// a spin-driven target counts as moved, idle does not.
		if (moved > 1e-8) {
			controls.update();
			invalidate();
		}
	});
</script>

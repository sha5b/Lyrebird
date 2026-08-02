<script lang="ts">
	import { untrack } from 'svelte';
	import { T, useTask } from '@threlte/core';
	import type * as THREE from 'three';
	import type { Snippet } from 'svelte';

	interface Props {
		spin?: boolean;
		/**
		 * Scales the whole cloud. The listening distance drives it, so a bird across the
		 * field is further away in the picture as well as in the filters — and because
		 * everything that has to line up (points, trajectories, context paths, the label
		 * anchors) lives in this group, they all move together. Scaling about the origin
		 * leaves every relative distance intact, so the projection stays exactly as
		 * faithful as it was; only the viewing scale changes.
		 */
		scale?: number;
		/** The group itself, for anything that has to convert a point in it to world space. */
		group?: THREE.Group;
		children?: Snippet;
	}

	let { spin = true, scale = 1, group = $bindable(), children }: Props = $props();
	/**
	 * **Starts at the requested scale, not at 1.**
	 *
	 * The ease exists for the distance slider, and it used to run on the first frame
	 * too — from 1 up to the opening 6.2 over about a second. That was not a cosmetic
	 * warm-up: `Framing` fits the camera on the first frame it sees a frame set, reads
	 * this group's scale to convert the reach into world units, and then marks itself
	 * `snapped` and never refits. Its task is also registered *before* this one, so on
	 * that frame the scale it read was the initial 1 — the camera landed about six
	 * times too close and the opening "whole galaxy" view showed roughly **40 % of the
	 * corpus's width**, with the rest off-screen and no margin anywhere to suggest
	 * anything was missing. Measured with the stage ruler: 33 knot-spacings across a
	 * corpus about 80 wide.
	 *
	 * `untrack` because only the *initial* value belongs here; every later change is
	 * the slider's and is still eased.
	 */
	let current = untrack(() => scale);
	$effect(() => {
		// Before any task runs, so Framing's first-frame fit sees the real scale.
		if (group) group.scale.setScalar(current);
	});

	/**
	 * Slow drift, so the cloud reads as a volume rather than a flat picture.
	 *
	 * **The drift rate is fixed and no longer follows the tempo.** Tempo used to multiply it,
	 * on the reasoning that it "slows the whole aviary" — but tempo is a property of the
	 * birds, and the rotation is a property of the view. Coupling them meant slowing the
	 * birds down to hear a call also froze the picture you were trying to read it in, and
	 * speeding them up spun the cloud out from under the cursor. `Rotate` is the control for
	 * the rotation.
	 */
	useTask((delta) => {
		if (!group) return;
		if (spin) group.rotation.y += delta * 0.035;
		// eased rather than snapped, so dragging the distance slider glides the cloud
		current += (scale - current) * Math.min(1, delta * 4);
		group.scale.setScalar(current);
	});
</script>

<T.Group bind:ref={group}>
	{@render children?.()}
</T.Group>

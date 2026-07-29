<script lang="ts">
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
	let current = 1;

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

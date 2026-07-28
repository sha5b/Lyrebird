<script lang="ts">
	import { T, useTask } from '@threlte/core';
	import type * as THREE from 'three';
	import type { Snippet } from 'svelte';

	interface Props {
		spin?: boolean;
		/** Multiplies the drift rate; 0 stops it without snapping the rotation back. */
		speed?: number;
		/**
		 * Scales the whole cloud. The listening distance drives it, so a bird across the
		 * field is further away in the picture as well as in the filters — and because
		 * everything that has to line up (points, trajectories, context paths, the label
		 * anchors) lives in this group, they all move together. Scaling about the origin
		 * leaves every relative distance intact, so the projection stays exactly as
		 * faithful as it was; only the viewing scale changes.
		 */
		scale?: number;
		children?: Snippet;
	}

	let { spin = true, speed = 1, scale = 1, children }: Props = $props();

	let group = $state<THREE.Group | undefined>();
	let current = 1;

	/** Slow drift, so the cloud reads as a volume rather than a flat picture. */
	useTask((delta) => {
		if (!group) return;
		if (spin) group.rotation.y += delta * 0.035 * speed;
		// eased rather than snapped, so dragging the distance slider glides the cloud
		current += (scale - current) * Math.min(1, delta * 4);
		group.scale.setScalar(current);
	});
</script>

<T.Group bind:ref={group}>
	{@render children?.()}
</T.Group>

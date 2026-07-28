<script lang="ts">
	import { T, useTask } from '@threlte/core';
	import type * as THREE from 'three';
	import type { Snippet } from 'svelte';

	interface Props {
		spin?: boolean;
		children?: Snippet;
	}

	let { spin = true, children }: Props = $props();

	let group = $state<THREE.Group | undefined>();

	/** Slow drift, so the cloud reads as a volume rather than a flat picture. */
	useTask((delta) => {
		if (spin && group) group.rotation.y += delta * 0.035;
	});
</script>

<T.Group bind:ref={group}>
	{@render children?.()}
</T.Group>

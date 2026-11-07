<script lang="ts">
	/**
	 * Stops the whole frame loop while a page covers the stage.
	 *
	 * The Info and Learn pages are opaque, so every task and draw behind them was full cost for
	 * nothing anybody could see, and a phone paid for it in heat while someone read. The audio
	 * and the listener do not depend on this loop, so the chorus keeps singing behind a page.
	 *
	 * No effect cleanup, on purpose: Threlte's own teardown clears the loop and disposes the
	 * renderer, and a cleanup that restored the loop could run after that.
	 */
	import { useThrelte } from '@threlte/core';

	let { paused = false }: { paused?: boolean } = $props();

	const { renderer, scheduler, invalidate } = useThrelte();
	let stopped = false;

	$effect(() => {
		if (paused === stopped) return;
		stopped = paused;
		if (paused) {
			renderer.setAnimationLoop(null);
			return;
		}
		renderer.setAnimationLoop((time) => scheduler.run(time));
		invalidate();
	});
</script>

<script lang="ts">
	/**
	 * Times the frame and names the GPU, into the shared stats object.
	 *
	 * It draws nothing. It exists because the two renderer regressions this project has
	 * had were both invisible from inside the app: a cost that scaled with the corpus, and
	 * a browser quietly choosing the integrated GPU on a machine with a discrete one.
	 * Neither is diagnosable from "it feels slow", and both are one number.
	 *
	 * The writes go to a plain object rather than to Svelte state — see stats.ts. Nothing
	 * re-renders because of this component; the page reads the object on a slow timer.
	 */
	import { useTask, useThrelte } from '@threlte/core';
	import type { GalaxyStats } from './stats';

	interface Props {
		stats: GalaxyStats;
	}

	let { stats }: Props = $props();

	const { renderer } = useThrelte();

	/**
	 * Which GPU the browser gave us.
	 *
	 * Read once, and through `WEBGL_debug_renderer_info` because the plain `RENDERER`
	 * string is masked to a generic value in most browsers. That extension is
	 * deprecated in Firefox, and `getExtension` can answer null there, so the
	 * unmasked string is used when the extension is present and the plain string
	 * when it is not — a vague answer still distinguishes a software rasteriser from
	 * a real one, and a missing extension is not an error.
	 */
	$effect(() => {
		const gl = renderer?.getContext();
		if (!gl) return;
		try {
			const ext = gl.getExtension('WEBGL_debug_renderer_info');
			stats.renderer = String(
				ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER)
			);
		} catch {
			stats.renderer = 'unavailable';
		}
	});

	/**
	 * Smoothing half-life for the two frame figures.
	 *
	 * Long enough that the number is readable — an unsmoothed frame time flickers through
	 * every digit and cannot be compared against anything — and short enough that turning
	 * a setting on shows its cost within about half a second.
	 */
	const SMOOTH = 0.12;

	useTask((delta) => {
		// A stalled tab hands back one enormous delta on resume. Reporting it as the frame
		// time would read as a permanent regression, so the first frame after a stall is
		// dropped rather than averaged in.
		if (delta <= 0 || delta > 0.5) return;
		const ms = delta * 1000;
		stats.frameMs = stats.frameMs ? stats.frameMs + (ms - stats.frameMs) * SMOOTH : ms;
		stats.fps = stats.frameMs > 0 ? 1000 / stats.frameMs : 0;
	});
</script>

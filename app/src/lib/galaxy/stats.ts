/**
 * What the stage costs, measured rather than guessed.
 *
 * This exists because a renderer whose cost scales with the corpus was shipped twice
 * without anyone being able to see which part scaled. The point cloud has a level of
 * detail; the label layer had none, and at the debug build's 4 298 knots that was the
 * whole frame budget spent on DOM nobody could read — the shipped production build has
 * 14 003. A number on screen is what would have caught it in the first minute instead of
 * the first production build.
 *
 * A plain mutable object, deliberately not reactive: it is written inside the render
 * loop, and a reactive write per frame per field is exactly the kind of cost this is
 * here to find. The page reads it on a slow timer and copies what it wants to draw.
 */
export interface GalaxyStats {
	/** Frames per second, smoothed over roughly the last half second. */
	fps: number;
	/** Milliseconds between the last two frames, smoothed the same way. */
	frameMs: number;
	/** Points the resting pass drew last frame — the LOD's answer, not the corpus size. */
	pointsDrawn: number;
	/** Points the corpus holds. */
	pointsTotal: number;
	/** Points the responding pass drew last frame; 0 on a silent frame. */
	pointsResponding: number;
	/**
	 * Points in the active pass carried by the wavefront's skirt rather than by a
	 * response (REVEAL_FRONT): the local cloud the wave shows as it passes. 0 on a
	 * silent frame. Reported apart so "responding" keeps meaning "answering".
	 */
	pointsRevealed: number;
	/**
	 * Share of the corpus in front of the level-of-detail frontier, 0..1 — a live
	 * fraction, not a level: the representatives' share at galaxy distance, 1 close
	 * up. -1 until the first frame reports.
	 */
	lod: number;
	/**
	 * The density governor's cap on the frontier, 0..1: 1 means the camera alone
	 * decides how much draws, anything less means the frame rate asked for less and
	 * got it. Written every frame; see the governor in PointCloud.
	 */
	densityCap: number;
	/**
	 * Camera distance in cloud radii, written every frame by PointCloud's fog fit —
	 * the same number the LOD frontier is quoted against, so anything that gates on
	 * "far out" vs "close up" reads it here instead of re-deriving it. -1 until the
	 * first frame reports.
	 */
	viewRadii: number;
	/** Name tags positioned last frame. Bounded by the pool, never by the corpus. */
	tagsDrawn: number;
	/** Knots the build holds. */
	clusters: number;
	/**
	 * The GPU the browser actually gave us, via `WEBGL_debug_renderer_info`.
	 *
	 * Worth showing, because on a laptop with two GPUs the browser routinely picks the
	 * integrated one and the fill-rate budget is then an order of magnitude smaller
	 * than the machine's. That is not something a frame counter alone would explain.
	 */
	renderer: string;
}

export function createStats(pointsTotal: number, clusters: number): GalaxyStats {
	return {
		fps: 0,
		frameMs: 0,
		pointsDrawn: 0,
		pointsTotal,
		pointsResponding: 0,
		pointsRevealed: 0,
		lod: -1,
		densityCap: 1,
		viewRadii: -1,
		tagsDrawn: 0,
		clusters,
		renderer: ''
	};
}

/**
 * What the stage costs, measured rather than guessed.
 *
 * This exists because a renderer whose cost scales with the corpus was shipped twice
 * without anyone being able to see which part scaled. The point cloud has a level of
 * detail; the label layer had none, and at 4 298 knots that was the whole frame budget
 * spent on DOM nobody could read. A number on screen is what would have caught it in
 * the first minute instead of the first production build.
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
	/** Level of detail in force: 0 one point per knot, 1 a quarter, 2 everything. */
	lod: number;
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
		lod: -1,
		tagsDrawn: 0,
		clusters,
		renderer: ''
	};
}

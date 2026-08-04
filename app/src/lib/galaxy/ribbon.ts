/**
 * Song threads as ribbons with a real width, instead of one-pixel GL lines.
 *
 * **The owner's "the song lines are hard to see at all" is a WebGL limitation, not a
 * styling choice.** `THREE.LineSegments` rasterises `gl.LINES`, and `lineWidth` is
 * ignored by every desktop driver worth naming — a thread is exactly one pixel however
 * close the camera gets, and one pixel at 0.55 alpha over a corpus-scale point cloud is
 * invisible. The bead run beside it exists only to compensate, and its own comment says
 * so: *"a GL line is capped at one pixel wide, which disappears against the cloud, so the
 * path is also drawn as a run of small sprites"*.
 *
 * The fix is the standard one: draw each segment as two triangles and offset the corners
 * perpendicular to the segment **in screen space**, in the vertex shader, so the width is
 * in pixels and does not change with depth. That is what `trajectoryRibbon*Shader` does;
 * this module builds the buffers it reads.
 *
 * It is a separate file because it is the half that can be tested. A shader that fails to
 * compile draws nothing and reports only to the console — this project has already lost a
 * whole grid that way — and nothing in the repo can see inside a shader string. The buffer
 * construction *can* be checked, and `verify:trajectory` checks it.
 */

/** Vertices per segment: two triangles. */
export const RIBBON_VERTICES_PER_SEGMENT = 6;

/**
 * Corner layout, as `[which endpoint, which side]`.
 *
 * 0 is the segment's start and 1 its end; side is which way to step perpendicular. The
 * two triangles are (start-, start+, end+) and (start-, end+, end-), which is one
 * consistent winding — the material draws both faces anyway, but a ribbon that flips
 * winding along its length is the kind of thing that looks fine until someone turns on
 * back-face culling.
 */
const CORNERS: readonly (readonly [0 | 1, -1 | 1])[] = [
	[0, -1],
	[0, 1],
	[1, 1],
	[0, -1],
	[1, 1],
	[1, -1]
];

export interface RibbonBuffers {
	/** This vertex's own endpoint, in world space. */
	position: Float32Array;
	/** The segment's *other* endpoint — the shader needs both to find the direction. */
	other: Float32Array;
	/** -1 or +1: which way this corner steps from the centre line. */
	side: Float32Array;
	/** Position along the path in node units, so the travelling peak can be found. */
	index: Float32Array;
	/** Which path this belongs to, indexing the per-path uniform arrays. */
	path: Float32Array;
	/** The gradient's colour at this vertex: its own knot's hue. */
	colour: Float32Array;
}

export function allocateRibbon(maxSegments: number): RibbonBuffers {
	const n = maxSegments * RIBBON_VERTICES_PER_SEGMENT;
	return {
		position: new Float32Array(n * 3),
		other: new Float32Array(n * 3),
		side: new Float32Array(n),
		index: new Float32Array(n),
		path: new Float32Array(n),
		colour: new Float32Array(n * 3)
	};
}

/** One knot's drawn centre and its thread colour, as `buildRibbon` needs them. */
export interface RibbonPath {
	nodes: number[];
	pathId: number;
}

/**
 * Fills the buffers for every segment of every path and returns the vertex count.
 *
 * `centroid(i)` gives a knot's current drawn position — it moves while the cloud
 * rearranges, which is why this is rebuilt rather than cached — and `colour(i)` its hue.
 * Both are passed in rather than reached for, so the geometry can be tested without an
 * asset set.
 */
export function buildRibbon(
	buffers: RibbonBuffers,
	paths: readonly RibbonPath[],
	centroid: (knot: number) => readonly [number, number, number],
	colour: (knot: number) => readonly [number, number, number],
	maxSegments: number
): number {
	let v = 0;
	for (const { nodes, pathId } of paths) {
		for (let n = 0; n < nodes.length - 1; n++) {
			if (v / RIBBON_VERTICES_PER_SEGMENT >= maxSegments) return v;
			const ends = [centroid(nodes[n]), centroid(nodes[n + 1])];
			const hues = [colour(nodes[n]), colour(nodes[n + 1])];
			// A segment whose knots coincide has no direction to be perpendicular to, and
			// the shader would normalise a zero vector into NaN — which takes the whole
			// draw call with it, not just this quad. Skipping is correct rather than
			// defensive: a zero-length segment has nothing to draw.
			if (
				ends[0][0] === ends[1][0] &&
				ends[0][1] === ends[1][1] &&
				ends[0][2] === ends[1][2]
			) {
				continue;
			}
			for (const [end, side] of CORNERS) {
				const self = ends[end];
				const away = ends[end === 0 ? 1 : 0];
				const hue = hues[end];
				buffers.position[v * 3] = self[0];
				buffers.position[v * 3 + 1] = self[1];
				buffers.position[v * 3 + 2] = self[2];
				buffers.other[v * 3] = away[0];
				buffers.other[v * 3 + 1] = away[1];
				buffers.other[v * 3 + 2] = away[2];
				buffers.colour[v * 3] = hue[0];
				buffers.colour[v * 3 + 1] = hue[1];
				buffers.colour[v * 3 + 2] = hue[2];
				buffers.side[v] = side;
				buffers.index[v] = n + end;
				buffers.path[v] = pathId;
				v++;
			}
		}
	}
	return v;
}

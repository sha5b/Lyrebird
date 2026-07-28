/**
 * Point-cloud shaders for the embedding galaxy (docs/05-embedding-galaxy.md §5.3-5.4).
 *
 * All animation is uniform-driven: the only thing that changes per frame is a small
 * array of per-cluster activations, so nothing is uploaded per point per frame. The
 * flare of active clusters is done with additive soft sprites rather than a
 * postprocessing bloom pass, which keeps the look at a fraction of the cost.
 */

export function vertexShader(clusterCount: number): string {
	return /* glsl */ `
		attribute float aCluster;
		attribute float aSeed;

		uniform float uActivation[${Math.max(1, clusterCount)}];
		uniform float uTime;
		uniform float uLevel;
		uniform float uPointSize;
		uniform float uPixelRatio;
		uniform float uHighlight;
		uniform float uSizeScale;

		varying float vAct;
		varying float vSeed;

		void main() {
			int index = int(aCluster + 0.5);
			float act = uActivation[index];
			vAct = act;
			vSeed = aSeed;

			// Active clusters breathe outward and jump with the input level — the "it jumps"
			// behaviour of the reference visualisation.
			float pulse = act * (0.5 + 0.5 * sin(uTime * 9.0 + aSeed * 6.2831853));
			vec3 p = position + normalize(position + vec3(1e-4)) * pulse * 0.07;
			p.y += pulse * 0.06 * (0.5 + uLevel * 4.0);

			vec4 mv = modelViewMatrix * vec4(p, 1.0);
			gl_Position = projectionMatrix * mv;

			float size = uPointSize * (1.0 + act * 3.5);
			if (abs(uHighlight - aCluster) < 0.5) size *= 1.5;
			// uPointSize is in pixels at the default camera distance (uSizeScale), which
			// keeps the cloud readable: the corpus is normalised to |coord| <= 1, so the
			// usual large perspective constant turns every point into a screen-wide blob.
			gl_PointSize = clamp(size * uPixelRatio * (uSizeScale / max(0.001, -mv.z)), 1.5, 96.0);
		}
	`;
}

export const fragmentShader = /* glsl */ `
	uniform vec3 uColdColor;
	uniform vec3 uHotColor;

	varying float vAct;
	varying float vSeed;

	void main() {
		vec2 uv = gl_PointCoord - 0.5;
		float d = length(uv);
		if (d > 0.5) discard;

		float core = smoothstep(0.5, 0.0, d);
		// A broad body plus a tight centre: the body is what makes the cloud read as
		// structure at this scale, the centre is what flares when a cluster activates.
		float glow = pow(core, 0.9) * 0.85 + pow(core, 3.0) * 0.6;
		vec3 colour = mix(uColdColor, uHotColor, clamp(vAct * 2.5, 0.0, 1.0));
		// Kept below saturation on purpose: pushed further, an active cluster clips to a
		// flat white blob and loses both its gold and the shape that identifies it.
		float alpha = glow * (0.8 + vAct * 0.8);
		gl_FragColor = vec4(colour * (1.0 + vAct * 0.8), alpha);
	}
`;

/** Per-frame signal shared between the audio loop and the renderer. Mutated in place. */
export interface VisualSignal {
	activations: Float32Array;
	level: number;
	f0: number;
	/** Index of the most active cluster, or -1. */
	best: number;
	/** Cluster indices a phrase visits, in order — the trajectory through the galaxy. */
	path: number[];
	/** Bumped whenever `path` changes, so the renderer knows to rebuild its geometry. */
	pathVersion: number;
	/** Position along the path in node units while singing; -1 when nothing is playing. */
	pathProgress: number;
	/** Overall visibility of the trajectory, 0..1. */
	pathAlpha: number;
}

export function createSignal(clusterCount: number): VisualSignal {
	return {
		activations: new Float32Array(Math.max(1, clusterCount)),
		level: 0,
		f0: 0,
		best: -1,
		path: [],
		pathVersion: 0,
		pathProgress: -1,
		pathAlpha: 0
	};
}

/**
 * Trajectory through the galaxy: the ordered path a phrase takes between clusters.
 *
 * The whole path is drawn faintly as soon as a call is selected, the part already sung is
 * a little brighter, and a travelling peak marks the syllable sounding right now. This is
 * the "trajectory line" of the Sainburg-style figures in docs/05-embedding-galaxy.md §5.3.
 */
export const trajectoryVertexShader = /* glsl */ `
	attribute float aIndex;
	varying float vIndex;

	void main() {
		vIndex = aIndex;
		gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
	}
`;

export const trajectoryFragmentShader = /* glsl */ `
	uniform float uProgress;
	uniform float uAlpha;
	uniform vec3 uColdColor;
	uniform vec3 uHotColor;

	varying float vIndex;

	void main() {
		bool singing = uProgress >= 0.0;
		// while idle the whole path reads as one faint thread; while singing the part
		// already sung stays lit so the order of the phrase remains visible
		float passed = singing ? step(vIndex, uProgress) : 1.0;
		float peak = singing ? exp(-pow((vIndex - uProgress) / 0.45, 2.0)) : 0.0;

		float base = 0.5 + 0.3 * passed;
		vec3 colour = mix(uColdColor, uHotColor, clamp(peak, 0.0, 1.0));
		float alpha = uAlpha * (base + peak * 0.5);
		gl_FragColor = vec4(colour * (0.9 + peak * 1.1), alpha);
	}
`;

/**
 * Beads along the same polyline. A GL line is capped at one pixel wide, which disappears
 * against the cloud, so the path is also drawn as a run of small sprites — and the
 * travelling highlight becomes a bead running along the thread.
 */
export const trajectoryPointsVertexShader = /* glsl */ `
	attribute float aIndex;
	uniform float uProgress;
	uniform float uPixelRatio;
	uniform float uSizeScale;
	varying float vIndex;
	varying float vPeak;

	void main() {
		vIndex = aIndex;
		bool singing = uProgress >= 0.0;
		vPeak = singing ? exp(-pow((aIndex - uProgress) / 0.45, 2.0)) : 0.0;

		vec4 mv = modelViewMatrix * vec4(position, 1.0);
		gl_Position = projectionMatrix * mv;
		gl_PointSize = clamp(
			(2.6 + vPeak * 7.0) * uPixelRatio * (uSizeScale / max(0.001, -mv.z)),
			1.5,
			64.0
		);
	}
`;

export const trajectoryPointsFragmentShader = /* glsl */ `
	uniform float uProgress;
	uniform float uAlpha;
	uniform vec3 uColdColor;
	uniform vec3 uHotColor;

	varying float vIndex;
	varying float vPeak;

	void main() {
		vec2 uv = gl_PointCoord - 0.5;
		float d = length(uv);
		if (d > 0.5) discard;
		float core = smoothstep(0.5, 0.0, d);

		bool singing = uProgress >= 0.0;
		float passed = singing ? step(vIndex, uProgress) : 1.0;
		vec3 colour = mix(uColdColor, uHotColor, clamp(vPeak, 0.0, 1.0));
		float alpha = uAlpha * core * (0.35 + 0.25 * passed + vPeak * 0.7);
		gl_FragColor = vec4(colour * (0.9 + vPeak * 1.2), alpha);
	}
`;

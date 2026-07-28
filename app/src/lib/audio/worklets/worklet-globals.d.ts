/**
 * The AudioWorklet global scope is not part of the DOM type library, so the few globals
 * `syrinx-processor.js` relies on are declared here. Keep this in sync with the spec:
 * https://webaudio.github.io/web-audio-api/#AudioWorkletGlobalScope
 */
declare class AudioWorkletProcessor {
	readonly port: MessagePort;
	constructor(options?: unknown);
	process(
		inputs: Float32Array[][],
		outputs: Float32Array[][],
		parameters: Record<string, Float32Array>
	): boolean;
}

declare function registerProcessor(
	name: string,
	processorCtor: new (options?: unknown) => AudioWorkletProcessor
): void;

/** Sample rate of the enclosing AudioContext. */
declare const sampleRate: number;
/** Current time of the enclosing AudioContext, in seconds. */
declare const currentTime: number;
/** Number of frames rendered by the enclosing AudioContext so far. */
declare const currentFrame: number;

/**
 * Minimal radix-2 FFT, written here on purpose: the offline Python extractor and this
 * one must agree bit-for-bit in structure (docs/08-implementation.md §8.2), so neither
 * side may inherit a library's windowing or normalisation defaults.
 */
export class RealFft {
	private readonly n: number;
	private readonly levels: number;
	private readonly cos: Float64Array;
	private readonly sin: Float64Array;
	private readonly re: Float64Array;
	private readonly im: Float64Array;

	constructor(n: number) {
		if (n < 2 || (n & (n - 1)) !== 0) throw new Error(`FFT size must be a power of two, got ${n}`);
		this.n = n;
		this.levels = Math.log2(n) | 0;
		this.cos = new Float64Array(n / 2);
		this.sin = new Float64Array(n / 2);
		for (let i = 0; i < n / 2; i++) {
			this.cos[i] = Math.cos((2 * Math.PI * i) / n);
			this.sin[i] = Math.sin((2 * Math.PI * i) / n);
		}
		this.re = new Float64Array(n);
		this.im = new Float64Array(n);
	}

	/**
	 * Magnitude spectrum of a real signal, bins [0, n/2) — i.e. |rfft(x)| with no
	 * normalisation, matching `numpy.abs(numpy.fft.rfft(x))[:n/2]`.
	 */
	magnitude(input: Float32Array, out: Float32Array): Float32Array {
		const { n, re, im, cos, sin, levels } = this;
		for (let i = 0; i < n; i++) {
			// bit-reversal permutation
			let rev = 0;
			for (let b = 0; b < levels; b++) rev |= ((i >>> b) & 1) << (levels - 1 - b);
			re[rev] = input[i] ?? 0;
			im[rev] = 0;
		}
		for (let size = 2; size <= n; size *= 2) {
			const half = size / 2;
			const step = n / size;
			for (let i = 0; i < n; i += size) {
				for (let j = i, k = 0; j < i + half; j++, k += step) {
					const l = j + half;
					const tRe = re[l] * cos[k] + im[l] * sin[k];
					const tIm = -re[l] * sin[k] + im[l] * cos[k];
					re[l] = re[j] - tRe;
					im[l] = im[j] - tIm;
					re[j] += tRe;
					im[j] += tIm;
				}
			}
		}
		for (let k = 0; k < n / 2; k++) out[k] = Math.hypot(re[k], im[k]);
		return out;
	}
}

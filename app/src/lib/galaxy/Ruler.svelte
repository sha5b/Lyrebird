<script lang="ts">
	/**
	 * A scale along the top and the left of the stage, in the corpus's own unit.
	 *
	 * **The galaxy had no scale at all.** The same cloud at two zoom levels looked like
	 * two different corpora; nothing said whether the gap you were looking at between
	 * two knots was a big distance or a small one, and "zoomed in" and "zoomed out" were
	 * feelings rather than numbers. A 3-D scatter without a scale bar is a picture, not
	 * a plot.
	 *
	 * **The unit is one knot spacing** — the median nearest-neighbour distance between
	 * knot centres on the loaded build, measured in PointCloud and quoted here. The
	 * projection's own axes cannot supply a unit: they are the three leading directions
	 * of a landmark cMDS in arbitrary units, and their origin means nothing, so
	 * absolute coordinates would be numbers with no referent. A knot spacing is a fact
	 * about this corpus: how far apart two neighbouring call types sit. It also happens
	 * to be the unit the wave's reach is already quoted in (four of them), so a front
	 * crossing the screen can now be read off the ruler.
	 *
	 * Two honest limits, both said in the caption's tooltip: the scale is exact at the
	 * depth of the view centre and approximate nearer or farther, as any scale bar in a
	 * perspective view is; and the numbers count outward from the centre of the view,
	 * because the projection has no meaningful zero to count from.
	 *
	 * The bands sit under the floating panels (z-index 1 against their 2) rather than
	 * being inset away from them: the ticks have to be geometrically true against the
	 * canvas, which spans the whole stage, so they are drawn full width and simply
	 * disappear behind the columns.
	 */
	import type { GalaxyStats } from './stats';

	interface Props {
		/** Device-independent pixels per knot spacing, from Scale. */
		pxPerKnot: number;
		/** The knot spacing itself, in layout box units — for the tooltip. */
		knotSpacing: number;
		/** The view's width in knot spacings. */
		widthKnots: number;
		/** The live stats object, sampled slowly for the caption. */
		stats?: GalaxyStats;
	}

	let { pxPerKnot, knotSpacing, widthKnots, stats }: Props = $props();

	/** Roughly how far apart labelled ticks should sit, in pixels. */
	const TARGET_PX = 78;

	/**
	 * A tick step from the 1-2-5 sequence, in knot spacings, so the labels stay round
	 * at every zoom. Below one spacing it keeps going in tenths — up close a single
	 * knot fills the screen and a ruler whose smallest division is the whole knot has
	 * nothing to say.
	 */
	const step = $derived.by(() => {
		if (!(pxPerKnot > 0)) return 1;
		const raw = TARGET_PX / pxPerKnot;
		const mag = Math.pow(10, Math.floor(Math.log10(raw)));
		const norm = raw / mag;
		const nice = norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 5 ? 5 : 10;
		return nice * mag;
	});
	/** How the step is written: 0.5 needs a decimal, 20 must not have one. */
	const label = (v: number) => (step < 1 ? v.toFixed(1) : String(Math.round(v)));

	let width = $state(0);
	let height = $state(0);

	/** Tick offsets in pixels from the centre, out to the edge, both directions. */
	function ticks(extent: number): { at: number; value: number }[] {
		const px = step * pxPerKnot;
		if (!(px > 4)) return [];
		const out: { at: number; value: number }[] = [{ at: extent / 2, value: 0 }];
		for (let k = 1; k * px <= extent / 2 + px; k++) {
			out.push({ at: extent / 2 + k * px, value: k * step });
			out.push({ at: extent / 2 - k * px, value: k * step });
		}
		return out.filter((t) => t.at >= 0 && t.at <= extent);
	}
	const topTicks = $derived(ticks(width));
	const leftTicks = $derived(ticks(height));

	/**
	 * The caption is read on a slow timer for the same reason the cost readout is: the
	 * stats object is written inside the render loop, and making the instrument
	 * reactive would make reading it part of what it measures.
	 */
	let live = $state<{ radii: number; lod: number } | null>(null);
	$effect(() => {
		const source = stats;
		if (!source) return;
		const sample = () => (live = { radii: source.viewRadii, lod: source.lod });
		sample();
		const id = setInterval(sample, 400);
		return () => clearInterval(id);
	});

	/**
	 * `stats.viewRadii` is deliberately not quoted here even though it is the obvious
	 * candidate. It is the camera's distance over the cloud's bounding radius, and on
	 * the opening view it read **0.4** while the framing bug had the camera inside the
	 * cloud, and about 2.4 now that Spinner hands Framing the real scale. It is a
	 * correct number and an unreadable one: "2.4 cloud radii" means nothing without
	 * knowing what the build's bounding radius is, and it went silently wrong for as
	 * long as the framing did. A width in the corpus's own unit needs no such
	 * explanation and cannot drift from what is on screen.
	 */
	const caption = $derived.by(() => {
		const parts = [`${widthKnots < 10 ? widthKnots.toFixed(1) : Math.round(widthKnots)} across`];
		if (live && live.lod >= 0) parts.push(`${Math.round(live.lod * 100)} % of points drawn`);
		return parts.join(' · ');
	});
</script>

<div class="ruler ruler-top" bind:clientWidth={width} aria-hidden="true">
	{#each topTicks as t (t.at)}
		<span class="tick" class:zero={t.value === 0} style:left={`${t.at}px`}></span>
		<span class="num" style:left={`${t.at}px`}>{label(t.value)}</span>
	{/each}
</div>

<div class="ruler ruler-left" bind:clientHeight={height} aria-hidden="true">
	{#each leftTicks as t (t.at)}
		<span class="tick" class:zero={t.value === 0} style:top={`${t.at}px`}></span>
		<span class="num" style:top={`${t.at}px`}>{label(t.value)}</span>
	{/each}
</div>

<p
	class="ruler-caption mono"
	title={`Distance from the centre of the view, in knot spacings — the median gap between two neighbouring knots on this build (${knotSpacing.toFixed(3)} projection units). One tick is ${label(step)}. The scale is exact at the depth of the view centre and approximate nearer or farther, as in any perspective view, and it counts from the centre because the projection has no meaningful origin.`}
>
	<span class="unit">1 tick = {label(step)} knot-spacing{step === 1 ? '' : 's'}</span>
	<span class="faint">{caption}</span>
</p>

<style>
	/* Under the floating panels, over the canvas: the ticks are true against the whole
	   stage and only the lane between the columns shows them. */
	.ruler {
		position: absolute;
		z-index: 1;
		pointer-events: none;
		color: var(--ink-faint);
		font-size: 0.55rem;
	}

	.ruler-top {
		top: 0;
		left: 0;
		right: 0;
		height: var(--ruler, 1.15rem);
		/* No rule under the band. It drew a full-width line across the top of the stage
		   that read as a border on the picture rather than as part of the scale — the
		   ticks are the scale, and they say it without cutting the view in half. */
		background: linear-gradient(var(--paper) 55%, transparent);
	}

	/* Against the left edge of the stage, the same full-bleed treatment as the top band:
	   a ruler that starts after the controls column is not a ruler down the left side,
	   it is a line in the middle of the picture. It runs under the panels (z-index 1
	   against their 2) and shows wherever they do not cover it — the same bargain the
	   horizontal band already makes.

	   Top 0, not below the horizontal band: the ticks are measured from the middle of
	   the element, so insetting it would move the zero off the middle of the view. The
	   two bands crossing in the corner is what a ruler corner looks like. */
	.ruler-left {
		top: 0;
		bottom: 0;
		left: 0;
		width: var(--ruler, 1.15rem);
		background: linear-gradient(90deg, var(--paper) 55%, transparent);
	}

	.tick {
		position: absolute;
		background: var(--rule);
	}

	.ruler-top .tick {
		bottom: 0;
		width: 1px;
		height: 0.3rem;
	}

	.ruler-left .tick {
		right: 0;
		height: 1px;
		width: 0.3rem;
	}

	/* The centre tick is the only one with a fixed meaning — it is what everything else
	   is counted from — so it is the only one drawn at full length. */
	.tick.zero {
		background: var(--ink-faint);
	}

	.ruler-top .tick.zero {
		height: 0.6rem;
	}

	.ruler-left .tick.zero {
		width: 0.7rem;
	}

	.num {
		position: absolute;
		font-variant-numeric: tabular-nums;
	}

	.ruler-top .num {
		top: 0.05rem;
		transform: translateX(-50%);
	}

	.ruler-left .num {
		left: 0.12rem;
		transform: translateY(-50%);
	}

	/* The lane between the two columns, clear of both — the same offsets the history
	   strip uses, so nothing in the middle of the stage is ever covered twice. */
	.ruler-caption {
		position: absolute;
		top: calc(var(--ruler, 1.15rem) + 0.2rem);
		left: calc(var(--ruler, 1.15rem) + 20rem + 2.6rem);
		z-index: 1;
		margin: 0;
		display: flex;
		gap: 0.5rem;
		font-size: 0.56rem;
		letter-spacing: 0.02em;
		color: var(--ink-faint);
		cursor: help;
		pointer-events: auto;
	}

	.ruler-caption .unit {
		color: var(--ink-dim);
	}

	.ruler-caption .faint {
		opacity: 0.75;
	}
</style>

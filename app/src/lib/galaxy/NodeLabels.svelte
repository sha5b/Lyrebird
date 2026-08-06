<script lang="ts">
	/**
	 * The floating specimen tag beside a responding cluster.
	 *
	 * Each tag carries the things you would want written on a slide next to it: what the
	 * cluster is, whose repertoire it belongs to, how many corpus points fell into it, how
	 * tight it is, and — while audio is playing — how strongly the live sound matches it.
	 * The tag stays terse until its cluster activates, then it opens up and shows the
	 * documented function and the live figures.
	 *
	 * **This is a fixed pool of tags, not one tag per knot** — see labels.ts for the
	 * measurement that forced it. `slots[s]` is the centroid index bound into slot `s`,
	 * or -1 for a slot nothing is using; NodeProjector owns that array and rebinds a slot
	 * only when the set of tags on screen actually changes, which is a few times a second
	 * rather than sixty. The `{#each}` is keyed by slot, so the outer element is built
	 * once and lives for the session while Svelte re-renders only the text inside a slot
	 * that changed hands.
	 *
	 * Positioning is done by NodeProjector, which writes transforms straight onto these
	 * elements. This component owns only the markup and the styling.
	 */
	import { untrack } from 'svelte';
	import { confidenceLabel } from '$lib/lang/translate';
	import { clusterProvenance, knotDoubt, knotHeat } from '$lib/data/assets';
	import { doubtColourScaled, provenanceColourScaled, speciesColourScaled } from './palette';
	import type { DoubtRange } from './doubt';
	import { describeForm } from '$lib/data/syllable-name';
	import type { LyrebirdAssets, Centroid } from '$lib/data/types';

	interface Props {
		assets: LyrebirdAssets;
		/**
		 * Centroid index bound into each slot, or -1. Owned by Galaxy, written by
		 * NodeProjector, read here. Reactive, because a rebind has to re-render the tag's
		 * text — and only a rebind does.
		 */
		slots: number[];
		/**
		 * Written into by this component, read by NodeProjector. **Slot-aligned, not
		 * centroid-aligned.** Plain array, not state. `$bindable` because the write
		 * happens here: Svelte 5 warns when a child mutates an unbound prop.
		 */
		elements: (HTMLElement | null)[];
		/**
		 * Colour the tags by the knot's provenance class instead of by its bird, to match
		 * the point cloud while the provenance mode is on. Reactive, not baked: this is a
		 * switch the viewer flips, so the tags have to follow it live.
		 */
		prov?: boolean;
	/**
	 * Colour the tags by neighbour agreement (rose) and/or recording SNR (amber), matching the
	 * points. Either overrides `prov` and the species hue; both together compose into the
	 * bivariate scheme in `palette.ts`, whose worst corner is bad on both counts.
	 */
	doubtAgree?: boolean;
	doubtSnr?: boolean;
	/** The SNR ramp's ends, so a tag clamps before averaging exactly as the buffer does. */
	doubtRange?: DoubtRange;

		/**
		 * The stage's scale — pixels per knot spacing — so the ring on a knot can be the size
		 * of the knot rather than a fixed number of pixels.
		 *
		 * A knot's drawn extent is about one knot spacing wide on the shipped build (extent
		 * 0.0417 against spacing 0.0419), so `pxPerKnot` *is*, near enough, the knot's diameter
		 * on screen. That makes the ring a measured mark: it circles the thing it names at every
		 * zoom instead of being a dot that means one size close up and another far out.
		 */
		pxPerKnot?: number;
		onpick?: (cluster: number) => void;
	}

	let {
		assets,
		slots,
		elements = $bindable(),
		prov = false,
		doubtAgree = false,
		doubtSnr = false,
		doubtRange = undefined,
		pxPerKnot = 0,
		onpick
	}: Props = $props();

	/**
	 * The ring's diameter in pixels, tracking the zoom and clamped at both ends.
	 *
	 * Floor 5 px: below that it stops reading as a ring around a 3 px particle and becomes a
	 * second particle. Ceiling 22 px: framed on a single knot `pxPerKnot` runs into the
	 * hundreds, and a ring that large stops annotating the cloud and starts hiding it — which
	 * is the objection that removed the filled version.
	 */
	const RING_MIN = 5;
	const RING_MAX = 22;
	const ringPx = $derived(Math.min(RING_MAX, Math.max(RING_MIN, pxPerKnot)));

	// The corpus does not change while this is mounted, so the lookups are built once.
	// Names come from the inventory index: a tag must name its bird without fetching
	// that bird's shard first.
	const centroids = untrack(() => assets.centroids.items);
	const speciesName = (id: string) => assets.speciesCommon(id);
	// What a knot's extent is made of: real field syllables, or our own renders. The
	// ρ and r figures next to it measure that extent, so the tag says which it is.
	const evidenceLabel = (c: Centroid): string =>
		c.sources ? ((c.sources['field'] ?? 0) > 0 ? 'measured' : 'invented') : '';

	/**
	 * Whether this knot's own tag should admit that the projection draws it in two places.
	 *
	 * **Shown only above the pipeline's "torn" threshold of 5, and as a word rather than a
	 * number.** The ratio's range on this build is 1.361 to 4 001.2 because the extremes are
	 * driven by knots with near-zero internal spread, so a figure on a tag would read as
	 * precision it does not have. And a value near the null of 2 is the ordinary case for
	 * two thirds of the map — printing it on every tag would spend the reader's attention on
	 * the marks that are fine.
	 *
	 * Empty when unmeasured, which is 9 025 of 15 341 knots. Absence here says nothing about
	 * the knot; the pinned panel is where that distinction is stated in words.
	 */
	const tearingLabel = (c: Centroid): string => {
		if (c.tearing === undefined) return '';
		if (c.tearing > 8) return 'torn: two places, far apart';
		if (c.tearing > 5) return 'torn: two places';
		return '';
	};

	/**
	 * The tag's hue is the bird's hue — labels are where "which bird" is answered, and
	 * the points no longer carry it. The per-knot lightness is the heat rule moved off
	 * the points: the species' core knot carries the hue a touch darker (0.9), its far
	 * edge a touch lighter (1.1), same hue and saturation throughout — a slight
	 * gradient of the label colour, never a different one.
	 *
	 * Ink mode keeps the hue on the tag even though the points under it are neutral:
	 * the tag is exactly where a hue can be read (the name sits right beside the dot),
	 * and it is the same hue the response accent lights in, so a singing knot and its
	 * tag agree. With the provenance mode on, the same tag answers the other question
	 * instead: the hue becomes the knot's class, matching the points under it. Two
	 * languages at once put a violet tag over an amber knot and invite the reading
	 * that the colours are related — so the whole picture speaks one language at a
	 * time. Either way the tag still *names* the bird in words right beside the dot,
	 * which is why hue is free to carry the other axis.
	 *
	 * Both per-knot arrays are one pass over the corpus, so they stay lazy: on a build
	 * with 14 000 knots the provenance tally is not work to do before the first frame
	 * when the mode it serves may never be switched on.
	 */
	let heat: Float32Array | null = null;
	let knotClass: Float32Array | null = null;
	/**
	 * Each knot's mean doubt per channel, built lazily and kept: two passes over the corpus
	 * at most, and only for a channel the reader actually switched on.
	 */
	let knotAgree: Float32Array | null = null;
	let knotSnr: Float32Array | null = null;
	const doubtOf = (i: number) => {
		if (doubtAgree) knotAgree ??= knotDoubt(assets, assets.points.knnAgreement);
		if (doubtSnr) knotSnr ??= knotDoubt(assets, assets.points.snr, doubtRange);
		return {
			agree: doubtAgree ? (knotAgree?.[i] ?? 1) : undefined,
			snr: doubtSnr ? (knotSnr?.[i] ?? 1) : undefined
		};
	};
	const knotColour = (c: Centroid, i: number): string => {
		heat ??= knotHeat(assets);
		const light = 0.9 + (heat[i] ?? 0.5) * 0.2;
		// First, because doubt is a mode rather than a tint: with it on, the tag says what
		// the points under it say, and neither the class nor the bird hue is on screen to
		// be confused with it.
		if (doubtAgree || doubtSnr) return doubtColourScaled(doubtOf(i), light);
		if (prov) {
			knotClass ??= clusterProvenance(assets);
			return provenanceColourScaled(knotClass[i] ?? 4, light);
		}
		return speciesColourScaled(c.speciesId, light);
	};

	/**
	 * What to write on the tag.
	 *
	 * **A fitted type's stored label is a serial number and three figures** — `learned L01 ·
	 * 1468 Hz · 69 ms` — which names the sound after the order it was fitted in. The tag has
	 * room for one line and that line was spending it on `L01`. It carries the description of
	 * the waveform instead, the same words the inventory table shows: `buzzy trilled rise`.
	 * The figures were never lost, they are on the line under it.
	 *
	 * Built lazily and rebuilt when the inventory grows, because **a tag must be able to name
	 * its knot without fetching that bird's shard**: the description needs the syllable's
	 * measured fields, which only the shard has, so a knot whose bird has not loaded yet
	 * falls back to the stored label. In practice the whole-corpus chorus fetches every
	 * species in one request before any tag appears.
	 */
	let described: Map<string, string> | null = null;
	let describedFor = -1;
	const tagName = (c: Centroid): string => {
		const loaded = assets.inventory.species;
		if (describedFor !== loaded.length) {
			described = new Map();
			for (const sp of loaded) {
				for (const syl of sp.syllables) {
					if (syl.learned) described.set(`${sp.id}/${syl.id}`, describeForm(syl));
				}
			}
			describedFor = loaded.length;
		}
		return described?.get(`${c.speciesId}/${c.syllableId}`) ?? c.label;
	};
</script>

<div class="layer" aria-hidden="true" style:--ring={`${ringPx}px`}>
	{#each slots as ci, s (s)}
		<!-- `--hot` (0 or 1) and `--act` (0..1) are written per frame by NodeProjector.
		     The wrapper is keyed by slot, so it is created once and only its contents
		     change when a different knot is bound into it. -->
		<div class="tag" bind:this={() => elements[s], (v) => (elements[s] = v)}>
			{#if ci >= 0}
				{@const centroid = centroids[ci]}
				<button
					class="dot"
					style:color={knotColour(centroid, ci)}
					type="button"
					tabindex="-1"
					aria-label={centroid.label}
					onclick={() => onpick?.(ci)}
				></button>
				<div class="card">
					<!--
						**The bird first, then the sound.** It used to lead with the syllable and put
						the species on the line below, which is the wrong way round for the question
						a viewer actually has when a knot lights up: they want to know who that was.
						The sound moves down beside the counts, where it is still the first thing on
						that line.
					-->
					<div class="head">
						<span class="id mono">C{String(centroid.id).padStart(2, '0')}</span>
						<span class="name">{speciesName(centroid.speciesId)}</span>
					</div>
					<div class="meta mono">
						<!-- full stored label on hover, so a fitted type's id is one gesture away -->
						<span class="sound" title={centroid.label}>{tagName(centroid)}</span>
						<span>n={centroid.count}</span>
						{#if centroid.meanDuration}<span>{Math.round(centroid.meanDuration * 1000)} ms</span>{/if}
					</div>
					<div class="detail">
						<div class="bar"><span></span></div>
						<div class="figures mono">
							<!-- written by NodeProjector, and only when the rounded value changes -->
							<span class="match" data-match>—</span>
							{#if centroid.cohesion !== undefined}<span>ρ {centroid.cohesion.toFixed(2)}</span>{/if}
							{#if centroid.radius !== undefined}<span>r {centroid.radius.toFixed(2)}</span>{/if}
							{#if evidenceLabel(centroid)}<span class="evidence">{evidenceLabel(centroid)}</span>{/if}
							{#if tearingLabel(centroid)}<span
									class="torn"
									title="This knot's members are drawn in two separate places, so its tag sits between them rather than on its points. Gap between its halves over their own spread: {centroid.tearing?.toFixed(
										1
									)} (about 2 is what one blob scores)."
								>{tearingLabel(centroid)}</span
								>{/if}
							<span class="conf">{confidenceLabel(centroid.confidence).text}</span>
						</div>
						{#if centroid.function}
							<p class="function">{centroid.function}</p>
						{/if}
					</div>
				</div>
			{/if}
		</div>
	{/each}
</div>

<style>
	.layer {
		position: absolute;
		inset: 0;
		overflow: hidden;
		pointer-events: none;
		z-index: 1;
	}

	.tag {
		position: absolute;
		top: 0;
		left: 0;
		display: flex;
		align-items: flex-start;
		gap: 0.4rem;
		/* The tag's own type size, declared so the dot can be sized in `em` against it.
		   It matches `.name`, which is the tag's dominant text; every other part of the card
		   sets its size in rem and so is unaffected by this. */
		font-size: 0.72rem;
		/* moved every frame by NodeProjector; the element sits at the node and the card
		   hangs off to its right */
		will-change: transform, opacity;
		transition: opacity 140ms linear;
	}

	/**
	 * The tag with its card on the other side, for a knot too near the right edge to hang one
	 * to the right. NodeProjector decides — see `tagWidthPx` there — and moves the box left by
	 * its own width; this turns the row around inside it so the ring stays on the knot.
	 *
	 * The card's rule moves with it. That hairline is the card's tether to the mark, and left
	 * on the far side it points away from the thing the card is about.
	 */
	/* `:global(.flip)` because NodeProjector adds the class from JavaScript, per frame, and
	   Svelte's scoped-CSS pass prunes any selector it cannot see used in this component's
	   markup. Written as a plain `.tag.flip` these two rules compiled to nothing — and the
	   failure is not a missing decoration: without `row-reverse` the box still moves left by
	   its own width and the ring goes with it, so the mark ends up a card's width away from
	   the knot it is naming. */
	.tag:global(.flip) {
		flex-direction: row-reverse;
	}

	/**
	 * The ring's own centring, mirrored.
	 *
	 * `translate(-50%, -50%)` puts the ring's centre on the tag box's *left* edge, which is the
	 * knot in the ordinary case. Flipped, the knot is the box's right edge and the ring's layout
	 * position is already at that edge less its own width, so the same −50 % walks it a full
	 * ring-width inland — measured at 5 px off its knot, on every flipped tag. The sign is what
	 * makes the mark true, and the mark being true is the only reason the ring exists.
	 */
	.tag:global(.flip) .dot {
		transform: translate(50%, -50%) scale(calc(1 + var(--ring-on) * 0.9));
	}

	.tag:global(.flip) .card {
		border-left: 0;
		border-right: 1px solid
			color-mix(in srgb, var(--accent, var(--signal)) calc(var(--hot, 0) * 100%), var(--rule));
	}

	/* Everything that reacts is driven by the two custom properties NodeProjector writes per
	   frame — `--hot`, a binary for "this card is open", and `--act`, the eased 0..1 activation
	   — through calc/color-mix rather than by a class, so no per-frame state has to cross into
	   Svelte. The card's own opening is `--hot`'s; the ring on the knot is `--act`'s, because a
	   mark on the data has to ramp with the data.
	   The dot's colour comes from --accent (written per frame by the projector): the
	   identity hue — the bird's in ink mode, the class's in provenance — at every
	   state, carried on the ring's border since nothing fills; the inline style is only
	   the first frame's fallback. */
	/* An outline the size of a particle, not a disc.

	   Tried at 1.8em (about 21 px, three times the old 7 px) on a literal reading of "three
	   times the size", and it was wrong twice over: a filled circle that large is a bigger mark
	   than anything in the data it annotates, and the mark for a knot centre should read as a
	   ring *around* the point rather than as a blob covering it. Owner, on seeing it: *"the dots
	   are way [too big] — just make them a tad bigger than the particles or the same. I thought
	   it's a border colour and infill 0."*

	   So: hollow at every state, and 0.45em — about 5 px against a point cloud drawn at 3 px, so
	   it sits just outside a particle instead of replacing it. Still in `em`, which was the part
	   of the original ask that holds: the mark keeps its relation to the type beside it rather
	   than being the one thing on the tag that does not move when the label does.

	   The identity hue is now carried entirely by the border, and `--hot` is left to the scale
	   below. Nothing fills, so a lit knot grows and brightens its ring rather than blocking out
	   the sound it is naming. */
	.dot {
		flex: none;
		/* Sized from the zoom by `--ring`, so the ring is the knot's own diameter on screen
		   rather than a fixed number of pixels. */
		width: var(--ring, 5px);
		height: var(--ring, 5px);
		/**
		 * **The touch-target floor must not reach this element, and finding out why cost a
		 * round.** `.dot` is a `<button>`, so the `min-height: max(2.6rem, 44px)` that
		 * controls.css gives every button on a coarse pointer applied here too — and a
		 * minimum beats a height. Every knot ring on a phone became a 5 × 44 px capsule
		 * standing on the cloud: measured at 6.8 × 59.8 with the activation scale on it,
		 * and reported as "on mobile the centroids get squished bad".
		 *
		 * It is the right floor and the wrong element. A control's size is a matter of the
		 * hand; this ring's size is a *measurement* — it is the knot's own diameter at the
		 * current zoom, which is what lets a reader compare a ring against the particles
		 * under it. The target it needs is bought below instead, where it costs the drawing
		 * nothing.
		 */
		min-height: 0;
		/* The pad below is positioned against this. */
		position: relative;
		/* **No vertical offset, and that is a fix.** `.tag` is transformed so its origin sits
		   exactly on the knot's projected position, and `translate(-50%, -50%)` below puts the
		   ring's centre on that origin — but a `margin-top: 0.26em` (about 3 px) was pushing it
		   down first. At the old 7 px dot that left the knot near the ring's lower edge; at a
		   ring the size of a particle it left the point *outside* the ring altogether, which is
		   what "it seems like it's not the centre of the circle but the edge" was. The offset
		   existed to line the ring up with the first line of the card, which is the card's
		   business — `.card` has its own `margin-top` for exactly that, and it is the thing that
		   may move, because the ring is the mark that has to be true. */
		margin-top: 0;
		padding: 0;
		border-radius: 50%;
		/* **The ring answers the activation, not the card.**

		   It was driven by `--hot`, which is a *binary* — whether this tag's card is open — so
		   the one mark sitting on the knot snapped between two states while everything else on
		   the stage ramped. `--act` is the same eased 0..1 the points ramp on and the match
		   meter fills with, written per frame by NodeProjector, so the ring now rises and falls
		   with its knot instead of switching.

		   `--hot` still contributes, at 0.4: a pinned or selected knot has a card open without
		   necessarily sounding, and its ring should be findable. Whichever is greater wins, so
		   activation can always take it the rest of the way.

		   Transparent at rest because the ring is an annotation and the cloud is the data — it
		   must not be the strongest mark at the place it is pointing at. */
		--ring-on: max(var(--act, 0), calc(var(--hot, 0) * 0.4));
		border: 1px solid
			color-mix(
				in srgb,
				var(--accent, currentColor) calc(38% + var(--ring-on) * 62%),
				transparent
			);
		background: none;
		/* The nearest thing to "the particles stay in front".
		   These tags are DOM over a WebGL canvas, so a point can never actually occlude one —
		   the browser composites the whole layer above the canvas whatever the depth. Multiply
		   is what buys most of the effect back: the paper is near-white so the ring's colour
		   survives, while any particle under it darkens *through* the stroke instead of being
		   painted over. Drawing the ring inside the scene would give real occlusion and is a
		   different job — a depth-tested pass, with the tag's text still on top. */
		mix-blend-mode: multiply;
		pointer-events: auto;
		cursor: pointer;
		/* A little more growth than before, because the fill used to carry the state change
		   and now the size and the border are all there is. On `--ring-on`, so the growth is
		   the same ramp as the colour and both follow the knot. */
		transform: translate(-50%, -50%) scale(calc(1 + var(--ring-on) * 0.9));
		/* **No CSS transition, and that is deliberate.** `--act` is rewritten every frame and
		   is already eased upstream (`shown[i] += (act - shown[i]) * ease`, delta-corrected in
		   NodeProjector). A transition on top would smooth an already smoothed value and add
		   its own 120 ms of lag, so the ring would trail the points it sits among. This is the
		   same reason the match meter next to it sets `width` from `--act` with no transition. */
	}

	/**
	 * The ring's reach on a touch screen: a transparent disc, centred on the mark, that a
	 * thumb can land on. Nothing is painted, so the drawn ring stays the knot's diameter and
	 * the annotation still says what it measures.
	 *
	 * **It does take a bite out of the drag surface**, and that is the trade rather than an
	 * oversight: the tags sit above the canvas, so a gesture that starts inside one of these
	 * discs picks the knot instead of orbiting the galaxy. At most twenty-six tags exist at
	 * once (the label pool's cap) and each holds about 1 500 px² — roughly seven per cent of
	 * a phone screen — against the alternative, which is that a 5 px ring is the only way to
	 * reach a knot's card and no thumb can hit one.
	 *
	 * Sized in `px` and not `em`, because a fingertip is 9 mm wide whatever the zoom is
	 * doing to the ring inside it.
	 */
	@media (pointer: coarse) {
		.dot::after {
			content: '';
			position: absolute;
			top: 50%;
			left: 50%;
			width: 44px;
			height: 44px;
			transform: translate(-50%, -50%);
			border-radius: 50%;
		}
	}

	/**
	 * Near-paper, with the colour spent on the left rule and the name.
	 *
	 * **A filled version of this was tried and taken back out.** Filling the card with the
	 * knot's colour made the tag the loudest thing on the stage — owner: *"too dominant"* —
	 * and it was: a tag is an annotation on the cloud, and the cloud is the data. The colour
	 * saying "which bird" is not worth the largest block of ink on the screen, especially
	 * when a chorus puts a dozen of them up at once. `overflow: hidden` stays from that
	 * attempt, and so does the wrapping `.figures` below: the text was overflowing the card
	 * all along, and only a filled card made it visible.
	 */
	.card {
		/* Lifted so the first line reads level with the ring's centre, which is now the knot
		   itself. The card is what moves to meet the mark, never the other way round. */
		margin-top: -0.55rem;
		padding: 0.15rem 0.4rem;
		/* 15 rem is the card's measure; the share is what a narrow stage can actually hold.
		   On a 375 px phone a 15 rem card is more than half the glass, so a knot anywhere near
		   the middle has room for it on neither side and the flip in NodeProjector has nowhere
		   to put it. `TAG_SHARE` there is this number plus a little, so the decision to flip is
		   always taken before the clip would happen — the two are a pair. */
		max-width: min(15rem, 44vw);
		overflow: hidden;
		border-left: 1px solid
			color-mix(in srgb, var(--accent, var(--signal)) calc(var(--hot, 0) * 100%), var(--rule));
		background: color-mix(in srgb, var(--paper) calc(78% + var(--hot, 0) * 16%), transparent);
		transition:
			border-color 140ms ease,
			background 140ms ease;
	}

	.head {
		display: flex;
		align-items: baseline;
		gap: 0.35rem;
	}

	.id {
		flex: none;
		font-size: 0.6rem;
		color: var(--ink-faint);
		letter-spacing: 0.04em;
	}

	.name {
		font-size: 0.72rem;
		letter-spacing: 0.01em;
		/* The bird's hue, whispering at rest and full when the knot answers: the tag
		   names the species in words AND carries its colour, so hue is never the sole
		   carrier of "which bird". */
		color: color-mix(
			in srgb,
			var(--accent, var(--ink)) calc(30% + var(--hot, 0) * 70%),
			var(--ink-dim)
		);
		transition: color 140ms ease;
		/* Learned labels carry the whole provenance sentence ("fulica_atra - learned
		   L01 · 1468 Hz · 69 ms"): far past the 15rem card cap on one line. The old
		   nowrap let them spill out of the card's left-ruled box; wrapping inside the
		   cap keeps tag and text the same width, and `title` on the span still gives
		   the full string in one gesture. */
		overflow-wrap: anywhere;
	}

	.meta {
		display: flex;
		flex-wrap: wrap;
		gap: 0.45rem;
		font-size: 0.58rem;
		color: var(--ink-faint);
	}

	/* The sound's description shares the meta line but is the reason to read it, so it is
	   ink rather than the faint grey the counts are drawn in. */
	.meta .sound {
		color: var(--ink-dim);
	}

	/* Everything below only exists once the cluster responds — a resting galaxy stays a
	   readable diagram rather than 44 paragraphs. */
	.detail {
		display: grid;
		gap: 0.18rem;
		overflow: hidden;
		max-height: calc(var(--hot, 0) * 7rem);
		opacity: var(--hot, 0);
		transition:
			max-height 180ms ease,
			opacity 180ms ease;
	}

	.bar {
		height: 2px;
		margin-top: 0.2rem;
		background: var(--rule);
	}

	.bar span {
		display: block;
		height: 100%;
		width: calc(var(--act, 0) * 100%);
		background: var(--accent, var(--signal));
	}

	/* Wraps, and it has to. `nowrap` on a 15 rem card with five figures on it does not fit
	   and never did — it was running past the card's edge and being clipped mid-word
	   (`measured fiel`). Invisible on a near-transparent card, which is why it survived. */
	.figures {
		display: flex;
		flex-wrap: wrap;
		gap: 0.1rem 0.4rem;
		font-size: 0.58rem;
		color: var(--ink-faint);
	}

	.figures .match {
		color: var(--accent, var(--signal));
	}

	.figures .conf,
	.figures .evidence {
		color: var(--ink-faint);
		font-style: italic;
	}

	/* Not red and not a warning colour: a torn knot is a property of the picture, not a
	   fault in the sound. Same faint ink as the other qualifiers, upright so it reads as a
	   statement about the mark rather than as another measured figure. */
	.figures .torn {
		color: var(--ink-dim);
		font-style: normal;
	}

	.function {
		margin: 0;
		font-size: 0.62rem;
		line-height: 1.35;
		color: var(--ink-dim);
	}
</style>

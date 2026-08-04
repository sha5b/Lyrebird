/**
 * The learned inventory as a flat list of rows, and the arithmetic a windowed list needs
 * to draw a slice of it.
 *
 * **Why this is a module and not markup.** The table is 16 283 rows over 2 650 species on
 * the shipped build, drawn over a WebGL canvas that is already spending its frame budget
 * on 387 287 points. That rules out one DOM node per row, so the list is windowed — and
 * window arithmetic is exactly the kind of code that is wrong by one and looks right:
 * an off-by-one in `first` shows as a row that never highlights, and a `padTop` that
 * disagrees with `first` shows as a list that drifts as you scroll. Both are invisible in
 * a screenshot and both are trivially checkable here, which is what `verify:inventory-table`
 * does.
 *
 * The row order is the inventory's own — species in `inventoryIndex` order, syllables in
 * the order that species' entry lists them. Not sorted by anything measured, because the
 * point of the table is that the sounding row can be found again in the same place next
 * time, and a sort on a fitted number moves a row when the corpus is rebuilt.
 */
import type { Inventory, Syllable } from './types';
// The explicit `.ts` is deliberate and the tsconfig is set up for it
// (`moduleResolution: bundler`, `rewriteRelativeImportExtensions`). Without it node's
// strip-only mode cannot resolve the specifier, and `verify:inventory-table` imports this
// file directly — the same constraint that put `cluster-lookup.ts` in its own module.
import { describeForm, medianPitch } from './syllable-name.ts';

/** One syllable type of one species, as the table draws it. */
export interface InventoryRow {
	/** `speciesId/syllableId` — the same key the engine's scheduled notes carry. */
	key: string;
	speciesId: string;
	common: string;
	syllableId: string;
	/**
	 * What to call this sound.
	 *
	 * **Two different kinds of thing, and the row says which.** For a documented call it is
	 * the name the literature gave it — `jar`, `fee-bee` — and that name means something,
	 * with a citation behind it. For a type `learn` fitted from field audio nobody has ever
	 * named it, so this is a description of its waveform instead: `buzzy trilled rise`. It
	 * claims nothing about what the bird meant by it. See `syllable-name.ts`.
	 */
	name: string;
	/** The claim the literature supports, verbatim from the inventory. */
	confidence: Syllable['confidence'];
	/** Milliseconds, as designed — not as measured off a render. */
	durMs: number;
	/** Median of the pitch track, in Hz. 0 when the type carries no contour. */
	hz: number;
	/** How many sources the inventory cites for this call. 0 on every fitted type. */
	refs: number;
	/**
	 * Present only on a syllable `learn` fitted from field audio. Its absence is the
	 * honest difference between a documented call and a learned one, and it is why the
	 * table does not guess from the id shape.
	 */
	fitted: boolean;
	/** Cosine between the fit's resynthesis and its cluster, or null when not fitted. */
	cosine: number | null;
	/** Field syllables behind the fit, or null when not fitted. */
	members: number | null;
	/**
	 * The knot this row lights, or -1 for a type the build placed nowhere.
	 *
	 * -1 is not a defect in the table: `typeCoverage` can be short of 1, and a type with
	 * no knot sings without lighting anything. Drawing it as a row with no knot is the
	 * only place in the app that says so.
	 */
	knot: number;
}

/**
 * Flattens the inventory into rows, in the inventory's own order.
 *
 * `order` is `inventoryIndex` — the build's own species order — so the table agrees with
 * every picker in the app. A species in the index whose entry has not been fetched yet
 * contributes nothing rather than a placeholder row: the shard is the only thing that
 * knows what syllables it holds, and inventing rows for it would put a row under a
 * sounding note that does not correspond to it.
 *
 * `knotOf` is passed in rather than imported so this module has no runtime dependency at
 * all — the caller already holds the cluster lookup, and a pure function of an inventory is
 * the thing `verify:inventory-table` can plant rows into.
 */
export function buildInventoryRows(
	inventory: Inventory,
	order: readonly { id: string; common: string }[],
	knotOf: ((speciesId: string, syllableId: string) => number) | null
): InventoryRow[] {
	const held = new Map(inventory.species.map((s) => [s.id, s]));
	const rows: InventoryRow[] = [];
	for (const entry of order) {
		const species = held.get(entry.id);
		if (!species) continue;
		for (const syl of species.syllables) {
			rows.push({
				key: `${species.id}/${syl.id}`,
				speciesId: species.id,
				common: species.common || entry.common,
				syllableId: syl.id,
				// A fitted type gets its form described; a documented one keeps the name its
				// sources gave it. Never the other way round.
				name: syl.learned ? describeForm(syl) : syl.label,
				confidence: syl.confidence,
				durMs: Math.round(syl.dur * 1000),
				hz: Math.round(medianPitch(syl)),
				refs: syl.refs?.length ?? 0,
				fitted: !!syl.learned,
				cosine: syl.learned?.resynthesisCosine ?? null,
				members: syl.learned?.members ?? null,
				knot: knotOf ? knotOf(species.id, syl.id) : -1
			});
		}
	}
	return rows;
}

/** Row index by `speciesId/syllableId`, so a scheduled note can find its row in O(1). */
export function indexRows(rows: readonly InventoryRow[]): Map<string, number> {
	const index = new Map<string, number>();
	// First wins. A key cannot repeat within one species' entry, and if a rebuild ever
	// emitted a duplicate the first row is the one the earlier index already pointed at.
	rows.forEach((row, i) => {
		if (!index.has(row.key)) index.set(row.key, i);
	});
	return index;
}

/** The slice of rows a scroll position exposes, plus the padding that holds it in place. */
export interface RowWindow {
	/** Index of the first row to draw, inclusive. */
	first: number;
	/** Index one past the last row to draw. */
	end: number;
	/** Pixels of spacer above the slice. */
	padTop: number;
	/** Pixels of spacer below it. Together with padTop and the slice: total height. */
	padBottom: number;
}

/**
 * Which rows to draw for a scroll offset.
 *
 * `overscan` rows are drawn beyond each edge so a fast scroll does not show blank
 * space before the next frame lands. Everything is clamped to `[0, total]`, because
 * `scrollTop` can exceed the content height for one frame after the row count drops —
 * a species shard arriving mid-scroll does exactly that.
 */
export function rowWindow(
	scrollTop: number,
	viewportPx: number,
	rowPx: number,
	total: number,
	overscan = 8
): RowWindow {
	if (rowPx <= 0 || total <= 0) return { first: 0, end: 0, padTop: 0, padBottom: 0 };
	const top = Math.max(0, Math.min(scrollTop, total * rowPx));
	const firstVisible = Math.floor(top / rowPx);
	const visibleCount = Math.ceil(viewportPx / rowPx) + 1;
	const first = Math.max(0, firstVisible - overscan);
	const end = Math.min(total, firstVisible + visibleCount + overscan);
	return {
		first,
		end,
		padTop: first * rowPx,
		padBottom: Math.max(0, (total - end) * rowPx)
	};
}

/**
 * Where to scroll so the sounding row is readable, or `null` to leave the list alone.
 *
 * **The list may not move on every note.** A chorus fires several notes a second, and
 * centring the active row each time makes the table a blur that cannot be read — which
 * would defeat the reason for having it. So the row is only pulled back when it has left
 * the middle band of the viewport, and then it is centred, so the next few notes of the
 * same phrase land without moving anything.
 *
 * `band` is the fraction of the viewport treated as comfortable, centred: 0.5 means the
 * middle half. A band of 0 centres on every note; a band of 1 only scrolls when the row
 * is fully outside the viewport.
 */
export function followRow(
	activeIndex: number,
	scrollTop: number,
	viewportPx: number,
	rowPx: number,
	total: number,
	band = 0.5
): number | null {
	if (activeIndex < 0 || activeIndex >= total || rowPx <= 0 || viewportPx <= 0) return null;
	const rowTop = activeIndex * rowPx;
	const margin = (viewportPx * (1 - Math.min(1, Math.max(0, band)))) / 2;
	const comfortableTop = scrollTop + margin;
	const comfortableBottom = scrollTop + viewportPx - margin;
	if (rowTop >= comfortableTop && rowTop + rowPx <= comfortableBottom) return null;
	const centred = rowTop - (viewportPx - rowPx) / 2;
	const maxScroll = Math.max(0, total * rowPx - viewportPx);
	return Math.max(0, Math.min(centred, maxScroll));
}

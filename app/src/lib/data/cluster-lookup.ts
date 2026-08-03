/**
 * Which galaxy cluster a syllable belongs to.
 *
 * **Split out of `assets.ts` so it can be tested.** `assets.ts` uses a TypeScript
 * parameter property, which node's strip-only type stripping refuses, so nothing under
 * `scripts/` could import from it — and the existing harnesses work around that by
 * re-deriving the rules they check. That is fine for a rule with one obvious reading,
 * and wrong for this one: the bug it exists to prevent (a type\'s second knot silently
 * dropped) is a bug *in the lookup*, and a test that re-implements the lookup would
 * reproduce it rather than catch it. `verify:split-knots` imports this file directly.
 */
import type { Centroids } from './types';

/**
 * Which galaxy cluster a syllable belongs to. Built once, because a phrase has to be
 * turned into a path through the cloud on every selection.
 */
export interface ClusterLookup {
	/** The type's *primary* knot — `blobRank` 0, its largest blob. */
	bySyllable: Map<string, number>;
	/**
	 * Every knot the type owns, primary first.
	 *
	 * **A type can own more than one, and until 2026-08-03 the second was silently
	 * dropped.** The pipeline splits a type in two when its sounds are two groups —
	 * either side of the field/synthetic seam, or bimodal in the critic's space past
	 * `TYPE_SPLIT_SEPARATION`. That split exists precisely because a single centroid was
	 * landing in the empty space between two real blobs, which is the "one note shines
	 * and there is no label and no connection" report. Keeping only the first knot would
	 * answer it by making the other blob dark instead of unlabelled — the same bug with
	 * the sign flipped.
	 */
	allBySyllable: Map<string, number[]>;
}

export function buildClusterLookup(centroids: Centroids): ClusterLookup {
	const allBySyllable = new Map<string, number[]>();
	centroids.items.forEach((item, index) => {
		if (!item.syllableId) return;
		const key = `${item.speciesId}/${item.syllableId}`;
		const found = allBySyllable.get(key);
		if (found) found.push(index);
		else allBySyllable.set(key, [index]);
	});
	// Primary first. `blobRank` is the build's own answer — 0 is the larger blob — and
	// sorting on it rather than trusting file order means a rebuild that reorders
	// centroids cannot silently change which knot a song's thread runs through. Builds
	// before 2026-08-03 ship no rank, and there the sole knot is the primary anyway.
	const bySyllable = new Map<string, number>();
	for (const [key, list] of allBySyllable) {
		if (list.length > 1) {
			list.sort(
				(a, b) =>
					(centroids.items[a].blobRank ?? 0) - (centroids.items[b].blobRank ?? 0) ||
					(centroids.items[b].count ?? 0) - (centroids.items[a].count ?? 0)
			);
		}
		bySyllable.set(key, list[0]);
	}
	return { bySyllable, allBySyllable };
}

/**
 * Every knot a syllable owns, primary first — empty when the galaxy cannot place it.
 *
 * `clusterIndexFor` stays the answer for anything that needs *one* place (a thread, a
 * fly-to): a song is a sequence in time, and forking its line would say the bird sang one
 * syllable in two places at once. This is the answer for anything that lights, because
 * every one of these knots really is that sound.
 */
export function clusterIndicesFor(
	lookup: ClusterLookup,
	speciesId: string,
	syllableId: string
): number[] {
	return lookup.allBySyllable.get(`${speciesId}/${syllableId}`) ?? [];
}

/**
 * Where a syllable sits in the galaxy, or -1 if it does not sit anywhere.
 *
 * **It used to fall back to "any cluster of the same species", and that was a placement
 * claim the corpus could not support.** Clustering is fitted over the whole point cloud
 * and a syllable only wins a cluster if enough of its renders land together; on the
 * 176-cluster build of 2026-07, 83 of the inventory's 176 syllables did not, so nearly
 * half of them were
 * being resolved by that fallback. It returned `bySpecies`, which is the *first* cluster
 * of that bird in file order — an arbitrary knot, the same one for every unplaced
 * syllable the bird has. A phrase with three unplaced syllables therefore drew a
 * trajectory that kept returning to one node chosen by nothing, and it looked exactly
 * like a measured path.
 *
 * -1 propagates: `Listener.clean` drops the node and its scheduled time together, so the
 * thread joins the syllables whose position *is* known, at the times they actually sound,
 * and a phrase with fewer than two of those draws nothing. That silence is the honest
 * reading and it is not left silent — `syllableCoverage` below lets the interface say how
 * much of a call it can place, so a missing thread reads as a gap in the corpus rather
 * than as a rendering fault.
 */
export function clusterIndexFor(
	lookup: ClusterLookup,
	speciesId: string,
	syllableId: string
): number {
	return lookup.bySyllable.get(`${speciesId}/${syllableId}`) ?? -1;
}

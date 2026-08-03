/**
 * Terms the interface defines once and repeats everywhere.
 *
 * **A module rather than a constant in a page, and the reason is in the term's own note.**
 * `bout` is the unit the whole syntax layer is defined over, and it is unexplained jargon in
 * every place it appears — the key, the Compose tab, the info page, a dozen tooltips. It was
 * held as one string inside `+page.svelte` precisely so the gloss could not drift between
 * those places; that argument is what makes it a module now, because the moment a surface
 * moves out of the page into its own component the page-local constant stops being reachable
 * and the next person writes the sentence again, slightly differently.
 */

/**
 * What a bout is, said once.
 *
 * Not a synonym for "song": it is the unit `learn.py` segments on (`GAP_BOUT_SECONDS = 1.0`),
 * so every transition, every mined motif and every song type is counted *within* one. A
 * reader who does not know that reads "8 of 18 recorded bouts fall into 2 types" as a
 * sentence about nothing.
 */
export const BOUT_GLOSS =
	'A bout is one burst of singing: syllables separated by less than a second of silence. It is the unit everything measured here is counted within — transitions, motifs and song types are all within-bout.';

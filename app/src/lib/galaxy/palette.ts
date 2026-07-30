/**
 * The galaxy's colour: one ink, one paper, and one accent that means "this is what you
 * asked for".
 *
 * There used to be two published categorical schemes here — Paul Tol's muted set for
 * species, Okabe & Ito for how much meaning a cluster claims — and a switch in the
 * interface to choose between them. They were good palettes and they were solving a
 * problem this picture does not have. Twelve species cannot be told apart by hue on a
 * scatter where every pair appears together; under colour-vision deficiency about three
 * can. So the hues were never identifying, only orienting, and the arrangement now orients
 * far better than they did: `Bird` gives every species an island of its own. What colour was
 * gesturing at, position says outright.
 *
 * What is left is the distinction the view actually turns on, which was always a
 * *contrast* rather than a category:
 *
 * - **rest → ink** is response. A pale mark darkens as its cluster answers the sound.
 *   ΔL* between the two ends is about 55, which is more range than the pale-to-saturated
 *   walk of any single hue had.
 * - **accent** is the one coloured thing on the field, and it means exactly one thing at
 *   a time: with no bird chosen it marks the note *being sung right now*; with a bird
 *   chosen it marks that bird's points. Both are "this is what you asked for", which is
 *   what the accent means everywhere else in the interface too.
 *
 * Because the accent is never a category, spending it this way contradicts nothing. A
 * violet knot is not a kind of bird; it is the place the sound is.
 */

/**
 * The monochrome pair. Neutral rather than a desaturated hue, so nothing in the picture
 * suggests a category, and the two ends are far enough apart in lightness that response
 * is legible on value alone.
 */
export const MONO_REST = '#cdd3da';
export const MONO_HOT = '#1e2836';

/**
 * The interface accent, and the only colour in the galaxy.
 *
 * Kept in step with `--signal` in `app.css` by hand, because the shader needs a number
 * and a CSS custom property is a string resolved at paint time.
 */
export const ACCENT = '#5b3fd6';

/**
 * The provenance triplet, used by the "colour: provenance" mode and by the orphan
 * pulse. These are the interface's existing confidence hues (`--documented`,
 * `--unlabelled`, `--invented` in app.css) repeated as numbers for the shader, kept
 * in step by hand exactly like `ACCENT`: blue for the authored inventory, grey for
 * types fitted to field recordings, amber for field audio with no identity.
 */
export const PROV_DOCUMENTED = '#1f5fbf';
export const PROV_LEARNED = '#7b8794';
export const PROV_CANDIDATE = '#b45309';

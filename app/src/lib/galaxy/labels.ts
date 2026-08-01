/**
 * The label layer's size, shared by the three files that have to agree about it.
 *
 * **Why there is a pool at all.** The tag layer used to render one tag per knot and
 * move every one of them every frame. That was written when a build had 44 knots and
 * survived 176; the debug-100 build has 4 298 and the shipped production build has
 * 14 003. At 4 298 it is ~77 000 DOM elements, each carrying `will-change: transform`
 * — so the compositor is asked for 4 298 layers — and the projector wrote seven style
 * properties to every one of them per frame, which is ~30 000 style mutations a frame
 * for a picture that shows at most 26 tags. It is the reason the browser fell to about
 * one frame a second, and it is not the point cloud, which had a level of detail.
 *
 * So the layer is a fixed pool of tag elements that knots are bound into. The DOM cost
 * is the pool's, the per-frame cost is the pool's, and neither moves when the corpus
 * grows. `MAX_LABELS` was already the budget — collision culling alone tiles the middle
 * of the view with text — so nothing about the picture changes; only the elements that
 * were never on screen stop being built and written to.
 */

/**
 * At most this many tags on screen at once, whatever fits geometrically.
 *
 * A sheet is readable at a couple of dozen labels, so the budget is the constraint and
 * the projector's ordering decides who spends it: whatever is responding, then whatever
 * has something to say, then whatever is nearest.
 */
export const MAX_LABELS = 26;

/**
 * Tag elements the layer keeps. Two above the budget so the pinned knot and one
 * arriving tag always have somewhere to go without evicting a tag that is being read.
 */
export const LABEL_SLOTS = MAX_LABELS + 2;

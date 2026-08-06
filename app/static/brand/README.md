# Lyrebird — mark, logo and icons

The mark is a **syrinx**: one tracheal stem dividing into two unequal bronchi, each ending in a
vibrating membrane. Three strokes and two dots, flat, one ink and one paper.

**The subject is the sound source, not the bird.** A real bird's syrinx is bilateral — the
trachea divides and each side vibrates independently, which is why a bird can sing two notes at
once. That division is what every note in this app is synthesized from: the two-parameter
oscillator the whole instrument is built on. The mark draws the mechanism.

## The one thing to know before you edit it

**It reads as the letter Y.** At every size, including 512.

That was raised as a disqualifying defect when this was one of three candidates, because the
brief was a mark without type and the previous tail-and-curl mark had itself been pulled back
from 300 degrees of curl for reading as a digit **6** — the same failure. The owner chose this
one anyway (2026-08-06). It is written down so the next person reads it as a decision rather
than as something nobody noticed.

Three things push against the letter, and they are why the geometry is what it is. Keep all
three if you touch the paths:

- **The branches are unequal** — different lengths, different curvature, different tip radii. A
  capital Y is symmetric; this is a bifurcation.
- **The branches curve.** A Y is two straight diagonals. These are cubics leaving the stem
  tangentially, as a tube divides.
- **The tips are membranes, not stroke ends** — two filled circles of different radius, which no
  letterform has.

**Not mirrored, and that is load-bearing.** Two arms bowing outward from one point make a heart,
exactly and not approximately; the previous mark's notes recorded that after two attempts. The
asymmetry above is what keeps it from happening here as well.

## Files

| file | use |
|---|---|
| `lyrebird-mark-solid.svg` | paper strokes on an ink disc. **Use this for icons** — it holds at 16–32 px. |
| `lyrebird-mark.svg` | reversed: ink strokes on a paper disc, for dark surfaces. |
| `lyrebird-logo.svg` | horizontal lockup, 250×64. Solid mark plus wordmark. |
| `../favicon.svg` · `../favicon.ico` | a copy of the solid mark, and 16/32/48 bundled. |
| `../../src/lib/assets/favicon.svg` | the same file again — what `+layout.svelte` imports through Vite. |
| `favicon-16.png` · `-32` · `-48` · `apple-touch-icon.png` (180) · `icon-192.png` · `icon-512.png` | all from the solid mark. |
| `lyrebird-logo.png` (1000 px) · `mark-light-512.png` | rasters. |

There is no separate small variant, and that is the point: at 32 px this is three strokes and
two dots, so the reduction is already done.

**Three copies of the same SVG is deliberate.** `src/lib/assets/favicon.svg` is imported by
`+layout.svelte` and gets a hashed filename; `static/favicon.svg` is at a stable path for the
`<link>` in `src/app.html`; `static/brand/lyrebird-mark-solid.svg` is the source the rasters are
generated from. Changing the mark means writing all three — the copy commands are below.

## The other thing that will bite you

**The logo's wordmark is live text and must be converted to outlines before it leaves this
repository.** It is set in `Iowan Old Style, Palatino, Georgia, serif`. On a machine with none of
those it reflows, and a logo that reflows is not a logo. There is no font-embedding step here, so
the file is kept editable on purpose.

```bash
inkscape lyrebird-logo.svg --export-text-to-path --export-plain-svg=lyrebird-logo-outlined.svg
```

## Colour

Both marks draw in `currentColor` and take their field from `var(--paper, #fafbfc)`, so they
inherit the ink of wherever they are placed and there is one place to change it. The app's tokens
are `--ink: #10161f` and `--paper: #fafbfc`. On a dark surface, override `--paper` to the surface
colour: the disc needs to match its surroundings, because a white disc on off-white shows a seam.

## Regenerating everything

ImageMagick does not resolve `currentColor` or CSS custom properties, so flatten first. Run from
this directory:

```bash
sed 's/currentColor/#10161f/g; s|var(--paper, #fafbfc)|#fafbfc|g' lyrebird-mark-solid.svg > /tmp/solid.svg
sed 's/currentColor/#fafbfc/g; s|var(--paper, #fafbfc)|#10161f|g' lyrebird-mark.svg       > /tmp/light.svg
sed 's/currentColor/#10161f/g; s|var(--paper, #fafbfc)|#fafbfc|g' lyrebird-logo.svg       > /tmp/logo.svg

for spec in "16 favicon-16" "32 favicon-32" "48 favicon-48" \
            "180 apple-touch-icon" "192 icon-192" "512 icon-512"; do
  set -- $spec; magick -background none /tmp/solid.svg -resize ${1}x${1} $2.png
done
magick -background none /tmp/light.svg -resize 512x512  mark-light-512.png
magick -background none /tmp/logo.svg  -resize 1000x256 lyrebird-logo.png

cp lyrebird-mark-solid.svg ../favicon.svg
cp lyrebird-mark-solid.svg ../../src/lib/assets/favicon.svg
magick favicon-16.png favicon-32.png favicon-48.png ../favicon.ico
```

## Wiring

Done, unlike the previous mark's. `src/app.html` carries:

```html
<link rel="icon" href="/favicon.svg" type="image/svg+xml" />
<link rel="alternate icon" href="/favicon.ico" sizes="16x16 32x32 48x48" />
<link rel="apple-touch-icon" href="/brand/apple-touch-icon.png" />
```

and `src/routes/+layout.svelte` additionally imports the SVG through Vite. Both exist because the
`<link>` needs a stable path and the import needs to survive bundling; neither covers the other.

## What the previous mark was, and why it is gone

A lyrebird's tail: three plumes fanning and one longer feather curling over at the tip, after the
Australian ten-cent piece. Four strokes and a circle. It was replaced on 2026-08-06 on a brief for
something scientific and simple.

Its notes recorded four failures reached by rendering rather than by opinion, and three of them
still apply to anything drawn here:

- **Two mirrored arms bowing outward from one point make a heart** — exactly, not approximately.
- **A symmetric radial fan is a sunburst**, and reads as a palm frond.
- **A curl blobs when its radius approaches the stroke width.** Radius 6 at stroke 4.6 filled in
  solid; radius 7 against stroke 3.3 survived 32 px.
- **A curl past about 220 degrees reads as a letter or a digit.** Three hundred looked like a 6.

An earlier version of it computed about a hundred tangent-following barbs per frond to imitate the
coin's engraving. It photographed well at 512 px and was an even grey smudge at 32, which is the
size a favicon is actually seen at.

Two candidates lost to the current mark and are recorded because each has a defect worth knowing:
a **pitch contour** (an arch over a time axis) was the most legible at 16 px and the least
specific — also a bell curve, a bridge, a tunnel; and a **knot in the cloud** (a ring with a
filled centre) collides with the universal target/crosshair glyph and reads as a radio button when
small.

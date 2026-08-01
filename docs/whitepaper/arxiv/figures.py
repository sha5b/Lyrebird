#!/usr/bin/env python3
"""Every figure the Lyrebird arXiv manuscript uses, as vector PDF.

Run it from the pipeline venv, because the spectral figures import the repository's
own synthesiser rather than reimplementing it:

    cd pipeline && uv run python ../docs/whitepaper/arxiv/figures.py

Output goes to `docs/whitepaper/arxiv/figures/`, one PDF per figure plus
`MANIFEST.md`, which records for every figure what it shows, where its numbers come
from, the intended width, and the caption text. The manifest is the artefact that
lets `main.tex` and this file be reconciled; nothing here edits the manuscript.

RULES THIS FILE FOLLOWS
-----------------------
* **Vector.** Everything is PDF. The only rasterised marks are the spectrogram
  meshes, which carry `rasterized=True` so the axes, ticks and labels around them
  stay vector and the file stays small.
* **Two widths.** `W_COL` = 3.4 in (one column) and `W_FULL` = 7.0 in (full width).
  Font sizes are set for the final printed size; no figure expects to be scaled.
  NOTE: `main.tex` is a one-column `article` at 11 pt with 2.6 cm margins, so its
  `\\linewidth` is 6.22 in and a `W_FULL` figure will be scaled to 0.89. The sizes
  here leave headroom for that; see MANIFEST.md and WHITEPAPER-FINDINGS.md.
* **Deterministic.** Every data-summary chart is plotted from literals carried in
  the function that draws it, with the doc section it came from in the docstring.
  The spectral figures read fixed files and fixed record keys; nothing samples.
  No RNG is used anywhere, and the PDF creation date is pinned so a re-run is
  byte-identical.
* **Colour carries the verdict.** Violet is the project's own accent and marks what
  is ours or adopted; clay marks a refutation or a failed gate; slate is a baseline
  or a permutation control; moss and ochre are the two external models, and mean
  identity rather than judgement (`external-spaces.pdf` is the only figure where a
  hue is not a verdict, and its gate lines carry the verdict instead). The
  categorical set violet/moss/ochre/clay passes every all-pairs gate of the house
  data-viz validator on a white surface (worst pair CVD dE 7.8, normal-vision 15.2,
  all four above 3:1 contrast); every series is also directly labelled, which is
  what the 6-8 dE band requires.
* **Debug scale is said out loud.** Any figure whose numbers come from the
  100-species debug store, the 37-species store, or a 10-to-80-type sample says so
  in its own caption, per this repository's convention.

SOURCES
-------
`docs/08`, `docs/09`, `docs/10`, `docs/11`, `docs/12`, `docs/14`, `docs/16`,
`docs/17`, `docs/19`, `docs/20`, `docs/21`, `docs/22`, `docs/23`, `HANDOFF.md`,
and for the spectral figures: `pipeline/out/harvest-gan/{typing,syllables}`,
`data/learned-inventory.json`, `pipeline/out/audio-cache/`,
`app/static/birdy/syrinx-calibration.json`.
"""

from __future__ import annotations

import datetime
import json
import logging
import math
import sys
from pathlib import Path

import numpy as np

import matplotlib

matplotlib.use("Agg")

# Embedding a Type-42 font makes matplotlib subset it with fontTools, and the
# bundled cmr10.ttf carries a nonsense `head` timestamp, so fontTools logs
# "'created' timestamp seems very low" once per figure. It is a property of that
# font file, not of anything here, and it is not a missing-glyph report.
logging.getLogger("fontTools").setLevel(logging.ERROR)
logging.getLogger("fontTools.subset").setLevel(logging.ERROR)
logging.getLogger("fontTools.ttLib").setLevel(logging.ERROR)

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle
from scipy.signal import resample_poly, spectrogram

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OUT = HERE / "figures"
OUT.mkdir(parents=True, exist_ok=True)

# The syrinx renderer is the repository's own; never reimplement the synth.
sys.path.insert(0, str(ROOT / "pipeline" / "src"))
from birdy_pipeline.syrinx import (  # noqa: E402
    BETA_MAX,
    BETA_MIN,
    SAMPLE_RATE,
    Calibration,
    beta_for,
    clamp_incidence,
    peak_normalise,
    render_plan,
    render_syllable,
)

# --------------------------------------------------------------------------------
# Palette
# --------------------------------------------------------------------------------

INK = "#241f33"        # primary ink
BODY = "#494455"       # secondary ink
MUTED = "#7d798a"      # axis labels, footnotes
GRID = "#e6e4ea"       # hairline gridline
AXIS = "#bdb8c6"       # baseline / spine

VIOLET = "#7a4fa3"     # ours, adopted, the project's accent
CLAY = "#bc4b2f"       # refuted, failed gate, the worse arm
SLATE = "#5b6070"      # baseline, permutation control
MOSS = "#0b7d5f"       # external space 1 (Perch 2.0)
OCHRE = "#a8871a"      # external space 2 (BirdNET)

# Washes, for fills that must sit behind a directly-labelled value.
VIOLET_W = "#e5dcee"
CLAY_W = "#f3ded6"
SLATE_W = "#dfdfe4"
MOSS_W = "#d5e7e0"

# Ordinal violet ramp, dark to light; validated monotone with the light end at
# 2.45:1 against white.
RAMP = ["#3b2559", "#5f3d80", "#8a63ab", "#b49ccc"]

# Spectrograms are a continuous magnitude field, so they get a *sequential* ramp:
# one hue, monotone in lightness, with near-zero energy receding into the page
# rather than a dark slab of ink. It is the same violet the rest of the set uses,
# extended to white at the bottom and to the ink colour at the top.
SPEC_CMAP = matplotlib.colors.LinearSegmentedColormap.from_list(
    "lyrebird-violet",
    ["#ffffff", "#ece5f3", "#c9b6dc", "#a184c1", "#7a4fa3", "#4e2f73", "#241f33"],
)

W_COL = 3.4    # one column
W_FULL = 7.0   # full width

plt.rcParams.update(
    {
        # cmr10 is Computer Modern Roman, which is what the manuscript's lmodern is.
        # It has no bold face, so nothing in this file is bold: emphasis is carried
        # by colour and size. Every glyph used here was checked against it.
        "font.family": "serif",
        "font.serif": ["cmr10", "DejaVu Serif"],
        "mathtext.fontset": "cm",
        "axes.unicode_minus": False,
        # cmr10 has no U+2212, so tick labels must go through mathtext to get a
        # real minus sign rather than a hyphen.
        "axes.formatter.use_mathtext": True,
        "font.size": 9.0,
        "axes.titlesize": 9.0,
        "axes.labelsize": 8.5,
        "xtick.labelsize": 8.0,
        "ytick.labelsize": 8.0,
        "legend.fontsize": 8.0,
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "axes.edgecolor": AXIS,
        "axes.linewidth": 0.6,
        "axes.grid": False,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.titlelocation": "left",
        "axes.titlepad": 5.0,
        "axes.labelpad": 3.0,
        "grid.color": GRID,
        "grid.linewidth": 0.5,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "xtick.labelcolor": BODY,
        "ytick.labelcolor": BODY,
        "xtick.major.size": 2.2,
        "ytick.major.size": 2.2,
        "xtick.major.width": 0.6,
        "ytick.major.width": 0.6,
        "text.color": INK,
        "axes.labelcolor": BODY,
        "axes.titlecolor": INK,
        "legend.frameon": False,
        "lines.linewidth": 1.4,
        "lines.markersize": 4.0,
        "patch.linewidth": 0.6,
        "figure.dpi": 200,
        "savefig.dpi": 400,
        "pdf.fonttype": 42,
        "pdf.compression": 6,
    }
)

MANIFEST: list[dict[str, str]] = []

#: A fixed PDF creation date, so re-running this script produces byte-identical files.
PINNED_DATE = datetime.datetime(2026, 8, 1, 0, 0, 0, tzinfo=datetime.timezone.utc)


# --------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------


def save(fig, name: str, *, width: str, shows: str, source: str, caption: str) -> str:
    """Write one figure as PDF and record its manifest row."""
    path = OUT / f"{name}.pdf"
    fig.savefig(
        path,
        format="pdf",
        bbox_inches="tight",
        pad_inches=0.02,
        facecolor="white",
        # Pinning the date makes a re-run byte-identical.
        metadata={
            "CreationDate": PINNED_DATE,
            "ModDate": PINNED_DATE,
            "Producer": "figures.py",
            "Creator": "docs/whitepaper/arxiv/figures.py",
        },
    )
    plt.close(fig)
    MANIFEST.append(
        {
            "file": f"{name}.pdf",
            "width": width,
            "shows": shows,
            "source": source,
            "caption": caption,
            "bytes": str(path.stat().st_size),
        }
    )
    print(f"  {name}.pdf  ({path.stat().st_size / 1024:.0f} kB, {width})")
    return str(path)


def hgrid(ax, values=None, left_spine=False):
    """Faint horizontal reference lines behind the marks, and no left rail."""
    ax.set_axisbelow(True)
    ax.grid(axis="y", color=GRID, linewidth=0.5)
    if not left_spine:
        ax.spines["left"].set_visible(False)
        ax.tick_params(axis="y", length=0)
    if values is not None:
        ax.set_yticks(values)


def vgrid(ax, values=None):
    ax.set_axisbelow(True)
    ax.grid(axis="x", color=GRID, linewidth=0.5)
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="y", length=0)
    if values is not None:
        ax.set_xticks(values)


def blank(ax, xlim=(0, 100), ylim=(0, 100)):
    ax.set_xlim(*xlim)
    ax.set_ylim(*ylim)
    ax.axis("off")
    ax.grid(False)


def note(ax, text, y=-0.30, x=0.0, colour=MUTED, size=7.2):
    """A footnote in the axes' own x-fraction, below the axes."""
    ax.text(x, y, text, transform=ax.transAxes, fontsize=size, color=colour,
            va="top", ha="left", linespacing=1.35)


def gate_line(ax, y, label, *, colour=CLAY, side="right", pad=0.004, size=7.2,
              xmin=0.0, xmax=1.0):
    """A pre-registered bar, drawn as a dashed rule and labelled in place."""
    ax.axhline(y, color=colour, linewidth=0.8, linestyle=(0, (3.0, 2.2)),
               xmin=xmin, xmax=xmax, zorder=1)
    lim = ax.get_xlim()
    if side == "right":
        ax.text(lim[1], y + pad, label, fontsize=size, color=colour, ha="right",
                va="bottom")
    else:
        ax.text(lim[0], y + pad, label, fontsize=size, color=colour, ha="left",
                va="bottom")


def value_labels(ax, xs, vals, fmt="{:.3f}", colours=None, dy=None, size=7.6,
                 above=True):
    """Direct labels on bars — never a legend where a label will do."""
    lo, hi = ax.get_ylim()
    if dy is None:
        dy = (hi - lo) * 0.022
    for x, v in zip(xs, vals):
        c = colours[xs.index(x)] if isinstance(colours, list) else (colours or INK)
        if above:
            ax.text(x, v + dy, fmt.format(v), ha="center", va="bottom",
                    fontsize=size, color=c)
        else:
            ax.text(x, v - dy, fmt.format(v), ha="center", va="top",
                    fontsize=size, color=c)


def box(ax, x, y, w, h, *, ec=VIOLET, fc="white", lw=0.7, dashed=False, r=0.9):
    ax.add_patch(
        FancyBboxPatch(
            (x, y), w, h,
            boxstyle=f"round,pad=0,rounding_size={r}",
            linewidth=lw, edgecolor=ec, facecolor=fc,
            linestyle=(0, (3.0, 2.2)) if dashed else "-",
            mutation_aspect=1.0,
        )
    )


def arrow(ax, x1, y1, x2, y2, *, colour=None, dashed=False, both=False, lw=0.8):
    ax.add_patch(
        FancyArrowPatch(
            (x1, y1), (x2, y2),
            arrowstyle="<|-|>" if both else "-|>",
            mutation_scale=7.5, linewidth=lw, shrinkA=0, shrinkB=0,
            color=colour or (MUTED if dashed else BODY),
            linestyle=(0, (3.0, 2.2)) if dashed else "-",
            zorder=3,
        )
    )


def thousands(n: int) -> str:
    """The manuscript's own number style: a thin space as the group separator."""
    return f"{n:,}".replace(",", " ")


# ================================================================================
# A. SCHEMATICS
# ================================================================================


def fig_architecture():
    """FULL WIDTH. The five stages, offline against browser. docs/06, docs/08 §8.3."""
    fig, ax = plt.subplots(figsize=(W_FULL, 2.30))
    blank(ax, (0, 100), (0, 46))

    # the two enclosures
    box(ax, 0.4, 12.5, 74.6, 27.5, ec="#d8d4de", fc="#fbfafc", r=1.2)
    ax.text(1.6, 41.0, "offline, Python - the recording is decoded, described and deleted",
            fontsize=7.6, color=MUTED)
    box(ax, 76.6, 12.5, 23.0, 27.5, ec="#d8d4de", fc="#fbfafc", r=1.2)
    ax.text(77.8, 41.0, "browser - no weights ship", fontsize=7.6, color=MUTED)

    y, h, w = 20.0, 13.5, 15.6
    xs = [2.2, 20.4, 38.6, 56.8, 78.0]
    stages = [
        ("harvest", "xeno-canto, iNat\n28-d descriptor +\n32x23 mel patch", "white", SLATE),
        ("store", "340 079 syllables\n2 421 species\nno audio", "white", SLATE),
        ("learn", "types in the 32-d\nembedding, then\ngesture inversion", "white", VIOLET),
        ("build", "galaxy assets\nJSON and float32\n14 003 regions", VIOLET_W, VIOLET),
        ("app", "3-D galaxy, synth,\nmicrophone,\nsession gate", VIOLET_W, VIOLET),
    ]
    for i, (x, (name, body, fc, ec)) in enumerate(zip(xs, stages)):
        box(ax, x, y, w, h, ec=ec, fc=fc)
        ax.text(x + w / 2, y + h - 3.0, name, ha="center", va="center",
                fontsize=8.6, color=INK)
        ax.text(x + w / 2, y + 4.4, body, ha="center", va="center", fontsize=6.6,
                color=BODY, linespacing=1.42)
        ax.add_patch(plt.Circle((x + 1.7, y + h + 1.1), 1.45, facecolor=ec,
                                edgecolor="none"))
        ax.text(x + 1.7, y + h + 1.1, str(i + 1), ha="center", va="center",
                fontsize=6.4, color="white")
    for i in range(4):
        arrow(ax, xs[i] + w + 0.4, y + h / 2, xs[i + 1] - 0.5, y + h / 2)

    # the critic sits under `learn`, and is the only learned component
    box(ax, 36.0, 13.6, 20.8, 5.0, ec=VIOLET, r=0.7)
    ax.text(46.4, 16.1, "critic: realism / species / NT-Xent, one 32-d trunk",
            ha="center", va="center", fontsize=6.4, color=BODY)
    arrow(ax, 46.4, 18.8, 46.4, 19.8, both=True, colour=VIOLET)

    box(ax, 0.4, 2.4, 99.2, 7.0, ec="#d8d4de", fc="#f7f5f9", r=1.0)
    ax.text(50.0, 7.0, "every phrase stage 5 speaks carries one evidence label",
            ha="center", va="center", fontsize=7.4, color=INK)
    ladder = ["experimental", "documented", "inferred", "invented", "unlabelled"]
    cols = RAMP + [SLATE]
    for i, (lab, c) in enumerate(zip(ladder, cols)):
        cx = 16.0 + i * 17.0
        ax.add_patch(Rectangle((cx - 6.0, 3.6), 1.6, 1.6, facecolor=c,
                               edgecolor="none"))
        ax.text(cx - 3.9, 4.4, lab, ha="left", va="center", fontsize=6.6,
                color=BODY)

    return save(
        fig, "architecture", width="full",
        shows="the five pipeline stages, what each holds, the critic's position, "
              "and the evidence-label strip that sits over everything the app shows",
        source="docs/06 §6.1, docs/08 §8.3, corpus counts from HANDOFF.md 2026-08-01",
        caption="The system end to end. Stages 1--4 are offline; stage 5 is a browser "
                "application reading static JSON and float32 assets, with no Python "
                "process and no model weights. The critic is the only learned "
                "component and never generates. The five evidence labels sit over "
                "everything stage 5 displays.",
    )


def fig_signal_chain():
    """FULL WIDTH. docs/08 §8.1/§8.1a, docs/15 §1/§5, docs/16 §16.7."""
    fig, ax = plt.subplots(figsize=(W_FULL, 2.75))
    blank(ax, (0, 100), (0, 52))

    y, h, w = 22.0, 13.0, 16.0
    xs = [20.5, 38.5, 56.5, 74.5]

    box(ax, 0.5, y + 7.2, 18.0, 6.4, ec=SLATE, r=0.8)
    ax.text(9.5, y + 10.4, "$\\alpha(t)$  air-sac pressure\n$\\approx$ loudness",
            ha="center", va="center", fontsize=6.6, color=BODY, linespacing=1.4)
    box(ax, 0.5, y - 1.2, 18.0, 6.4, ec=SLATE, r=0.8)
    ax.text(9.5, y + 2.0, "$\\beta(t)$  labial tension\n$\\approx$ pitch",
            ha="center", va="center", fontsize=6.6, color=BODY, linespacing=1.4)
    ax.text(9.5, y - 3.4, "plus 140 Hz noise on $\\beta$", ha="center",
            fontsize=6.3, color=MUTED)

    blocks = [
        "syrinx oscillator\nnormal form, eq. 1\nHopf / SNIC",
        "turbulence\nat the labia\nproportional to flow",
        "$f_0$-tracking\nresonance\nthe tract retunes",
        "tracheal comb\nstopped tube\n$f_1$ per species",
    ]
    for x, body in zip(xs, blocks):
        box(ax, x, y, w, h, ec=VIOLET)
        ax.text(x + w / 2, y + h / 2, body, ha="center", va="center", fontsize=6.4,
                color=BODY, linespacing=1.45)
    arrow(ax, 18.7, y + 10.4, 21.0, y + 8.6)
    arrow(ax, 18.7, y + 2.0, 21.0, y + 4.4)
    for i in range(3):
        arrow(ax, xs[i] + w + 0.4, y + h / 2, xs[i + 1] - 0.5, y + h / 2)
    arrow(ax, xs[3] + w + 0.4, y + h / 2, 94.0, y + h / 2)
    ax.text(95.0, y + h / 2, "sound", fontsize=7.4, ha="left", va="center", color=INK)

    # the one extension that ships
    box(ax, 37.0, 41.0, 40.0, 8.0, ec=VIOLET, fc=VIOLET_W, r=0.9)
    ax.text(57.0, 45.0,
            "fricative route: turbulence bypasses the tracking band\n"
            "and is shaped by the type's own formants - ships per type,\n"
            "bench 0.584 to 0.656, 13 wins and 0 losses",
            ha="center", va="center", fontsize=6.3, color=BODY, linespacing=1.4)
    arrow(ax, 47.0, 40.8, 47.0, 35.4, colour=VIOLET)

    # the parked ones, each carrying its own refutation
    box(ax, 0.5, 4.0, 47.0, 8.4, ec=SLATE, dashed=True, r=0.9)
    ax.text(24.0, 8.2,
            "respiration: two-state air-sac dynamics replaces the envelope\n"
            "hand-set default 0.343 to 0.336 - the per-species fit won 445 types",
            ha="center", va="center", fontsize=6.3, color=MUTED, linespacing=1.4)
    box(ax, 51.5, 4.0, 48.0, 8.4, ec=SLATE, dashed=True, r=0.9)
    ax.text(75.5, 8.2,
            "second voice, coupled through the tracheal pressure\n"
            "hand-set default 0.343 to 0.294 - the fit won 2 027 of 5 922 screened",
            ha="center", va="center", fontsize=6.3, color=MUTED, linespacing=1.4)
    arrow(ax, 25.0, 12.6, 28.0, 21.6, dashed=True)
    arrow(ax, 68.0, 12.6, 63.0, 21.6, dashed=True)
    ax.text(0.5, 0.8,
            "Dashed: implemented and parity-tested, off by default. The published "
            "physics is not in doubt; the hand-set default parameter sets lost their "
            "pre-registered bake-offs.",
            fontsize=6.5, color=MUTED)

    return save(
        fig, "signal-chain", width="full",
        shows="the synthesis chain from the two gesture contours to sound, with the "
              "one extension that ships and the two that are parked, each annotated "
              "with the bake-off number that decided it",
        source="docs/08 §8.1, §8.1a; docs/15 §1, §5; docs/16 §16.4, §16.7",
        caption="The synthesis chain. Two gesture contours drive the oscillator; "
                "turbulence, the $f_0$-tracking resonance and the fixed tracheal comb "
                "shape the result. The dashed blocks are implemented, parity-tested "
                "and off by default: their published physics is not in doubt, but "
                "their hand-set default parameter sets lost their pre-registered "
                "bake-offs, and only the per-species fits ship, per type, where they "
                "win.",
    )


def fig_claim_ladder():
    """FULL WIDTH. The evidence labels with the production region counts.

    docs/08 §8.5 for the levels; HANDOFF 2026-08-01 for the v5 region mix
    (13 919 unlabelled, 27 documented, 10 experimental, 16 inferred, 31 invented
    over 14 003 regions).
    """
    rows = [
        ("experimental", RAMP[0], "a bird was played this sound and responded", 10),
        ("documented", RAMP[1], "the function is in the peer-reviewed literature", 27),
        ("inferred", RAMP[2], "measured in this corpus, function not established", 16),
        ("invented", RAMP[3], "a designed mapping, always named as designed", 31),
        ("unlabelled", SLATE, "real acoustics, no documented function", 13919),
    ]
    fig, (a1, a2) = plt.subplots(
        1, 2, figsize=(W_FULL, 2.05), gridspec_kw={"width_ratios": [2.15, 1]}
    )

    blank(a1, (0, 100), (-0.55, len(rows) - 0.15))
    a1.text(0, len(rows) - 0.35, "stronger evidence", fontsize=7.2, color=MUTED,
            style="italic")
    a1.annotate("", xy=(1.0, -0.30), xytext=(1.0, len(rows) - 0.72),
                arrowprops=dict(arrowstyle="-|>", color=AXIS, lw=0.8))
    for i, (name, colour, requires, _n) in enumerate(rows):
        yy = len(rows) - 1 - i
        a1.add_patch(Rectangle((4.5, yy - 0.15), 21.0, 0.56, facecolor=colour,
                               edgecolor="none"))
        a1.text(6.0, yy + 0.13, name, fontsize=8.0, color="white", va="center")
        a1.text(28.0, yy + 0.13, requires, fontsize=7.6, color=BODY, va="center")
    a1.text(4.5, -0.42,
            "Every phrase the application speaks carries one of these five labels. "
            "Nothing renders without one,\nand the weakest level is protected: "
            "detecting that a sound is new is not knowing what it means.",
            fontsize=6.7, color=MUTED, linespacing=1.4)

    ys = list(range(len(rows)))[::-1]
    a2.barh(ys, [r[3] for r in rows], height=0.56,
            color=[r[1] for r in rows], edgecolor="none")
    for yy, r in zip(ys, rows):
        a2.text(r[3] * 1.35, yy, thousands(r[3]), va="center", fontsize=7.6,
                color=r[1])
    a2.set_xscale("log")
    a2.set_xlim(4, 1.1e5)
    a2.set_ylim(-0.55, len(rows) - 0.15)
    a2.set_yticks([])
    a2.set_xticks([10, 100, 1000, 10000])
    a2.set_xticklabels(["10", "100", "1 000", "10 000"])
    a2.set_xlabel("map regions at this level (log scale)")
    a2.set_title("what the corpus actually reaches", color=INK)
    vgrid(a2)
    a2.text(0.0, -0.42,
            "14 003 regions in the production build. The honest answer for the\n"
            "overwhelming majority of the corpus is the bottom row.",
            transform=a2.transAxes, fontsize=6.7, color=MUTED, va="top",
            linespacing=1.4)

    return save(
        fig, "claim-ladder", width="full",
        shows="the five evidence labels, what each requires, and how many map "
              "regions the production build places at each level",
        source="docs/08 §8.5 for the levels; HANDOFF.md 2026-08-01 for the v5 "
               "region mix over 14 003 regions",
        caption="The five evidence labels, the requirement for each, and the "
                "production build's region counts. Every phrase the application "
                "speaks carries one of them; nothing renders without one. The "
                "distribution is the point: 13\\,919 of 14\\,003 regions are "
                "\\emph{unlabelled}, and the interface is required to keep saying so.",
    )


def fig_spaces_bridge():
    """FULL WIDTH. The two feature spaces, what changed, and the bridge.

    docs/10 §10.2 (controlled 625-syllable, 3-species subset: purity 70.9 to 90.9,
    type coverage 12/14 to 14/14, 3-D 10-NN agreement 64.5 to 83.2, distance
    faithfulness 0.874 to 0.940; render-free placement 41.3 to 38.5).
    docs/11 §11.3 and docs/20 for the bridge (linear 0.7997 fail, RFF 0.9623 pass
    against a 0.80 gate).
    """
    fig, (a1, a2) = plt.subplots(
        1, 2, figsize=(W_FULL, 2.55), gridspec_kw={"width_ratios": [1.35, 1]}
    )

    metrics = [
        ("cluster purity", 70.9, 90.9),
        ("type coverage", 85.7, 100.0),
        ("3-D 10-NN agreement", 64.5, 83.2),
        ("distance faithfulness", 87.4, 94.0),
        ("render-free placement", 41.3, 38.5),
    ]
    ys = list(range(len(metrics)))[::-1]
    for yy, (name, a, b) in zip(ys, metrics):
        worse = b < a
        c = CLAY if worse else VIOLET
        a1.plot([a, b], [yy, yy], color=c, linewidth=1.3, solid_capstyle="round",
                zorder=2)
        a1.plot([a], [yy], "o", color="white", markeredgecolor=SLATE,
                markeredgewidth=1.1, markersize=5.0, zorder=3)
        a1.plot([b], [yy], "o", color=c, markeredgecolor="white",
                markeredgewidth=0.8, markersize=5.6, zorder=4)
        a1.text(min(a, b) - 2.5, yy, f"{min(a, b):.1f}", ha="right", va="center",
                fontsize=7.2, color=MUTED)
        a1.text(max(a, b) + 2.5, yy, f"{max(a, b):.1f}", ha="left", va="center",
                fontsize=7.4, color=c)
    a1.set_yticks(ys)
    a1.set_yticklabels([m[0] for m in metrics], fontsize=7.6)
    a1.set_xlim(28, 112)
    a1.set_ylim(-0.9, len(metrics) - 0.35)
    a1.set_xticks([40, 60, 80, 100])
    a1.set_xlabel("per cent, one controlled subset, only the space changed")
    a1.set_title("28-d descriptor $\\rightarrow$ 32-d embedding", color=INK)
    vgrid(a1)
    a1.text(0.0, -0.235,
            "625 field syllables, three species, identical points, one seed. Hollow "
            "marker: the 28-d descriptor.\nFilled: the 32-d embedding. Clay is the "
            "counterweight: render-free placement moves the wrong way, and\nthe "
            "recordist confound lives in the embedding, not in the descriptor. "
            "Debug-scale.",
            transform=a1.transAxes, fontsize=6.7, color=MUTED, va="top",
            linespacing=1.42)

    # the bridge, as a gate chart
    arms = [("linear ridge\n19-species critic", 0.8585, SLATE),
            ("linear ridge\nfiner embedding", 0.7997, CLAY),
            ("RFF kernel ridge\nas shipped", 0.9623, VIOLET)]
    xs = [0, 1, 2]
    a2.bar(xs, [a[1] for a in arms], 0.46, color=[a[2] for a in arms],
           edgecolor="none")
    a2.set_ylim(0.70, 1.02)
    a2.set_xlim(-0.62, 2.62)
    a2.set_xticks(xs)
    a2.set_xticklabels([a[0] for a in arms], fontsize=7.0)
    a2.set_ylabel("median mapped-vs-true cosine")
    a2.set_title("the bridge the browser needs", color=INK)
    hgrid(a2, [0.7, 0.8, 0.9, 1.0])
    for x, (_n, v, c) in zip(xs, arms):
        a2.text(x, v + 0.006, f"{v:.4f}", ha="center", va="bottom", fontsize=7.6,
                color=c)
    gate_line(a2, 0.80, "ship gate 0.80", side="left")
    a2.text(0.0, -0.235,
            "28-d in, 32-d out: a kernel ridge over random Fourier features\n"
            "($D = 2048$, $\\sigma = 4$, $\\lambda = 1$), gated on held-out "
            "recordings, never\non held-out syllables. It ships as plain "
            "numbers; no weights reach\nthe browser. The linear map was replaced by "
            "measurement, not taste.",
            transform=a2.transAxes, fontsize=6.7, color=MUTED, va="top",
            linespacing=1.42)

    return save(
        fig, "spaces-bridge", width="full",
        shows="left: the four map-quality metrics and the one counterweight when the "
              "build moves from the 28-d descriptor to the 32-d embedding, on one "
              "controlled subset; right: the three bridge arms against the 0.80 "
              "ship gate",
        source="docs/10 §10.2 (625 syllables, 3 species); docs/11 §11.3 and "
               "docs/20 §20.1 for the bridge arms",
        caption="The two feature spaces and the bridge between them. Left: on one "
                "controlled subset --- 625 field syllables, three species, identical "
                "points, one seed, only the space changed --- the embedding improves "
                "every map-quality metric, and the one metric that moves the wrong "
                "way is drawn in clay. Right: the browser computes only the "
                "28-dimensional descriptor, so a kernel ridge over random Fourier "
                "features maps it into the 32-dimensional space the map lives in, "
                "behind a ship gate read on held-out recordings. Debug-scale.",
    )


# ================================================================================
# B. THE WALLS — the rewritten data charts
# ================================================================================


def fig_corpus():
    """FULL WIDTH. Corpus growth, corrected. docs/09 §9.7-9.8, docs/14 §14.1,
    docs/16 §16.1, HANDOFF 2026-07-31 (P0).

    The old figure overprinted the species counts on the store names; here breadth
    in syllables and breadth in species are two panels sharing one row of labels,
    which is what the two units require.
    """
    stores = [
        ("original 22-species store", 39976, 22, False),
        ("re-harvest carrying patches", 39993, 13, True),
        ("+ multi-source ingest", 39874, 121, False),
        ("+ iNatSounds 2024", 226264, 3811, False),
        ("+ depth harvest (P0)", 340079, 3811, False),
    ]
    fig, (a1, a2, a3) = plt.subplots(
        1, 3, figsize=(W_FULL, 2.35), gridspec_kw={"width_ratios": [1.35, 1.0, 0.95]}
    )
    ys = list(range(len(stores)))[::-1]

    shades = [SLATE_W, CLAY_W, SLATE_W, VIOLET_W, VIOLET]
    a1.barh(ys, [s[1] for s in stores], height=0.56, color=shades, edgecolor="none")
    for yy, s, c in zip(ys, stores, shades):
        a1.text(s[1] * 1.10, yy, thousands(s[1]), va="center", fontsize=7.4,
                color=VIOLET if c is VIOLET else BODY)
    a1.set_xscale("log")
    a1.set_xlim(2.4e4, 1.15e6)
    a1.set_yticks(ys)
    a1.set_yticklabels([s[0] for s in stores], fontsize=7.4)
    a1.set_xticks([1e5, 1e6])
    a1.set_xticklabels(["100 000", "1 000 000"])
    a1.set_xlabel("measured syllables (log scale)")
    a1.set_title("breadth: syllables", color=INK)
    vgrid(a1)

    a2.barh(ys, [s[2] for s in stores], height=0.56,
            color=[CLAY if s[3] else SLATE_W for s in stores][:-1] + [VIOLET],
            edgecolor="none")
    for yy, s in zip(ys, stores):
        a2.text(s[2] * 1.28, yy, thousands(s[2]), va="center", fontsize=7.4,
                color=CLAY if s[3] else BODY)
    a2.set_xscale("log")
    a2.set_xlim(7, 2.2e4)
    a2.set_yticks([])
    a2.set_xticks([10, 100, 1000])
    a2.set_xticklabels(["10", "100", "1 000"])
    a2.set_xlabel("species in the store (log scale)")
    a2.set_title("breadth: species", color=INK)
    vgrid(a2)
    a2.annotate("a store-trim bug\ndeleted twelve species;\nchance is 7.7 %, not 4.0 %",
                xy=(13, ys[1]), xytext=(30, ys[1] - 0.95), fontsize=6.5, color=CLAY,
                ha="left", va="center", linespacing=1.35,
                arrowprops=dict(arrowstyle="-", color=CLAY, lw=0.6))

    a3.barh([0], [71], color=VIOLET, height=0.40, edgecolor="white", linewidth=1.0)
    a3.barh([0], [29], left=[71], color=SLATE_W, height=0.40, edgecolor="white",
            linewidth=1.0)
    a3.text(35.5, 0, "71", ha="center", va="center", color="white", fontsize=9.0)
    a3.text(85.5, 0, "29", ha="center", va="center", color=BODY, fontsize=8.4)
    a3.set_xlim(0, 100)
    a3.set_ylim(-0.85, 0.55)
    a3.set_yticks([])
    a3.set_xticks([0, 50, 100])
    a3.set_xlabel("species of the target 100")
    a3.set_title("depth, after the P0 harvest", color=INK)
    a3.spines["left"].set_visible(False)
    a3.tick_params(axis="y", length=0)
    a3.text(0, -0.50, "71 reach the 20-recording bar the syntax work needs.\n"
                      "Median 29; tenth percentile 5. The 29 are what the archive\n"
                      "holds, not what the harvest missed.",
            fontsize=6.7, color=MUTED, linespacing=1.42)

    fig.tight_layout(w_pad=1.6)
    return save(
        fig, "corpus", width="full",
        shows="corpus growth in syllables and in species over the four documented "
              "harvest steps, and the depth reached on the 100 targeted species",
        source="docs/09 §9.7-9.8, docs/14 §14.1, docs/16 §16.1, HANDOFF.md "
               "2026-07-31 (P0). Replaces docs/whitepaper/figures/corpus.png, whose "
               "species labels overprinted the store names.",
        caption="The corpus grew in breadth and then in depth. Syllable counts and "
                "species counts are separate panels because they are separate units; "
                "the second row is drawn in clay because a store-trim bug deleted "
                "twelve of its 25 species, so any per-species figure measured on it "
                "has chance 7.7\\,\\% rather than 4.0\\,\\% and is not comparable to "
                "the rows around it. The right panel is the depth harvest: 71 of the "
                "100 targeted species reach the 20-recording bar, and the tenth "
                "percentile of 5 is the archive's ceiling rather than the harvest's.",
    )


def fig_ruler():
    """FULL WIDTH. Wall 1 — the objective cannot hear. docs/19 §19.2, §19.4, §19.5."""
    fig, (a1, a2) = plt.subplots(
        1, 2, figsize=(W_FULL, 2.45), gridspec_kw={"width_ratios": [1.5, 1]}
    )

    rows = [
        ("28-d cosine vs MCD", 0.106, 0.100, CLAY),
        ("28-d cosine vs STFT error", 0.102, 0.111, CLAY),
        ("mel-path target vs MCD", -0.305, -0.420, VIOLET),
    ]
    ys = list(range(len(rows)))[::-1]
    a1.axvline(0, color=BODY, linewidth=0.8, zorder=2)
    for v in (-0.4, 0.4):
        a1.axvline(v, color=SLATE, linewidth=0.7, linestyle=(0, (2.6, 2.2)),
                   zorder=1)
    a1.text(-0.4, len(rows) - 0.38, "a usable ruler starts here", fontsize=6.6,
            color=SLATE, ha="center", va="bottom")
    for yy, (name, pear, spear, c) in zip(ys, rows):
        a1.plot([0, pear], [yy + 0.14, yy + 0.14], color=c, alpha=0.45,
                linewidth=1.2, solid_capstyle="butt", zorder=3)
        a1.plot([pear], [yy + 0.14], "o", color=c, alpha=0.45, markersize=4.6,
                zorder=4)
        a1.plot([0, spear], [yy - 0.14, yy - 0.14], color=c, linewidth=1.6,
                solid_capstyle="butt", zorder=3)
        a1.plot([spear], [yy - 0.14], "o", color=c, markersize=5.2, zorder=4)
        off = 0.03 if spear >= 0 else -0.03
        ha = "left" if spear >= 0 else "right"
        a1.text(pear + off, yy + 0.14, f"{pear:+.3f}", ha=ha, va="center",
                fontsize=7.0, color=MUTED)
        a1.text(spear + off, yy - 0.14, f"{spear:+.3f}", ha=ha, va="center",
                fontsize=7.4, color=c)
    a1.set_yticks(ys)
    a1.set_yticklabels([r[0] for r in rows], fontsize=7.6)
    a1.set_xlim(-0.60, 0.42)
    a1.set_ylim(-0.85, len(rows) - 0.30)
    a1.set_xticks([-0.4, -0.2, 0.0, 0.2, 0.4])
    a1.set_xlabel("correlation with audible distortion")
    a1.set_title("the objective cannot hear", color=INK)
    a1.set_axisbelow(True)
    a1.grid(axis="x", color=GRID, linewidth=0.5)
    a1.spines["left"].set_visible(False)
    a1.tick_params(axis="y", length=0)
    a1.text(0.0, -0.225,
            "Pale, thin: Pearson. Solid, thick: Spearman. Both metrics point away "
            "from zero only for the\nreplacement. Not an instrument artefact: the "
            "recomputed cosine reproduces the stored one at\nPearson 0.921, and the "
            "two distortion metrics agree with each other at 0.925. "
            "$n = 200$ types.",
            transform=a1.transAxes, fontsize=6.7, color=MUTED, va="top",
            linespacing=1.42)

    a2.bar([0], [70.0], 0.44, color=SLATE_W, edgecolor="none")
    a2.bar([1], [31.0], 0.44, color=CLAY, edgecolor="none")
    a2.set_xlim(-0.65, 1.65)
    a2.set_ylim(0, 92)
    a2.set_xticks([0, 1])
    a2.set_xticklabels(["exploratory probe\n$n = 10$ types",
                        "pre-registered gate\n$n = 80$ types"], fontsize=7.2)
    a2.set_ylabel("types the mel target wins (%)")
    a2.set_title("and the replacement is not an optimiser", color=INK)
    hgrid(a2, [0, 20, 40, 60, 80])
    a2.text(0, 72.5, "70", ha="center", va="bottom", fontsize=8.0, color=BODY)
    a2.text(1, 33.5, "31", ha="center", va="bottom", fontsize=8.0, color=CLAY)
    gate_line(a2, 60.0, "gate 60 %", side="right")
    a2.text(0.0, -0.225,
            "Blended at weight 0.5 the mel target wins 25 of 80 types, with a\n"
            "median $\\Delta$MCD of exactly 0.0 dB and a maximum cosine loss of\n"
            "0.120. Seven of ten had won at probe scale.",
            transform=a2.transAxes, fontsize=6.7, color=MUTED, va="top",
            linespacing=1.42)

    fig.tight_layout(w_pad=2.4)
    return save(
        fig, "ruler", width="full",
        shows="left: how strongly the incumbent fit objective and its proposed "
              "replacement correlate with two independent audible-distance metrics; "
              "right: the replacement's win share at probe and at gate scale",
        source="docs/19 §19.2 (n = 200 types), §19.4-§19.5 (n = 80, pre-registered "
               "gate) — 100-species debug store against the iNat audio cache",
        caption="The fit objective does not rank audible fidelity. Left: correlation "
                "with mel-cepstral distortion and with multi-resolution log-spectral "
                "distance, for the incumbent 28-dimensional cosine and for the "
                "proposed mel-path replacement. Neither of the cosine's correlations "
                "is distinguishable from zero and both point estimates lean the wrong "
                "way. Right: the replacement is the better measurement and the worse "
                "optimiser --- it wins 31\\,\\% of types against a pre-registered "
                "60\\,\\% bar. Both panels are debug-scale.",
    )


def fig_confound():
    """FULL WIDTH. Wall 2 — the recordist, not the bird.

    docs/14 §14.4 (production store: recordist +0.488, species +0.196);
    docs/17 §17.2, §17.3, §17.5 for every swept arm of the two adversarial heads.
    """
    fig, (a1, a2) = plt.subplots(
        1, 2, figsize=(W_FULL, 2.60), gridspec_kw={"width_ratios": [1, 1.5]}
    )

    a1.bar([0], [0.488], 0.44, color=CLAY, edgecolor="none")
    a1.bar([1], [0.196], 0.44, color=VIOLET, edgecolor="none")
    a1.set_xlim(-0.65, 1.65)
    a1.set_ylim(0, 0.60)
    a1.set_xticks([0, 1])
    a1.set_xticklabels(["which recordist", "which species"], fontsize=7.6)
    a1.set_ylabel("nearest-neighbour lift over a\npermutation null, blocked by recording")
    a1.set_title("the problem", color=INK)
    hgrid(a1, [0.0, 0.2, 0.4])
    a1.text(0, 0.500, "+0.488", ha="center", va="bottom", fontsize=8.2, color=CLAY)
    a1.text(1, 0.208, "+0.196", ha="center", va="bottom", fontsize=8.2, color=VIOLET)
    a1.text(0.0, -0.235,
            "In the critic's embedding the strongest relation is\nnot the animal. "
            "Every consumer inherits it: typing,\nthe map, the relations document, "
            "novelty, and the\nunknown-bird path. Production store.",
            transform=a1.transAxes, fontsize=6.7, color=MUTED, va="top",
            linespacing=1.42)

    rec_head = [(-0.7, 3.0, "augmentation only"), (-14.7, -7.0, "w 0.1"),
                (-33.0, -28.9, "w 0.05"), (-61.4, -59.9, "w 0.3")]
    sp_head = [(1.1, 6.3, ""), (-1.4, 11.2, ""), (-3.2, 10.0, ""),
               (-6.1, 10.4, "species-factored, w 0.1")]

    a2.add_patch(Rectangle((-70, -8), 40, 30, facecolor=VIOLET_W, edgecolor=VIOLET,
                           linewidth=0.7, linestyle=(0, (3.0, 2.2)), zorder=0))
    a2.text(-50, 16.0, "what the gates asked for", fontsize=7.0, color=VIOLET,
            ha="center", style="italic")
    a2.text(-50, 11.0, "(no arm lands here)", fontsize=7.0, color=VIOLET,
            ha="center")
    a2.plot([-70, 20], [-70, 20], color=SLATE, linewidth=0.7,
            linestyle=(0, (2.4, 2.2)), zorder=1)
    a2.text(-36.5, -43.0, "one for one", fontsize=6.8, color=SLATE, rotation=42.0)
    a2.axhline(0, color=AXIS, linewidth=0.6, zorder=1)
    a2.axvline(0, color=AXIS, linewidth=0.6, zorder=1)

    a2.plot([p[0] for p in rec_head], [p[1] for p in rec_head], "o-", color=CLAY,
            markersize=4.2, linewidth=1.1, zorder=3)
    a2.plot([p[0] for p in sp_head], [p[1] for p in sp_head], "s-", color=VIOLET,
            markersize=4.0, linewidth=1.1, zorder=3)
    a2.text(-63.0, -55.0, "recordist-adversarial head", fontsize=7.0, color=CLAY,
            ha="left")
    a2.text(-4.0, 14.0, "species-factored head", fontsize=7.0, color=VIOLET,
            ha="right")
    for xx, yy, lbl in rec_head:
        if lbl:
            a2.annotate(lbl, (xx, yy), textcoords="offset points",
                        xytext=(-5, -10) if "augment" in lbl else (6, -9),
                        fontsize=6.6, color=CLAY,
                        ha="right" if "augment" in lbl else "left")
    a2.set_xlim(-72, 22)
    a2.set_ylim(-72, 24)
    a2.set_xlabel("change in recordist lift (%)")
    a2.set_ylabel("change in species lift (%)")
    a2.set_title("every loss that reaches the recorder takes the bird with it",
                 color=INK)
    a2.set_axisbelow(True)
    a2.grid(color=GRID, linewidth=0.5)
    a2.text(0.0, -0.225,
            "Every swept point of both adversarial heads. The species-factored head "
            "protects species completely\nand reaches only $-6$ % of the confound; "
            "the plain head moves the confound at an almost exactly\none-for-one "
            "cost. 37-species debug store; debug-scale.",
            transform=a2.transAxes, fontsize=6.7, color=MUTED, va="top",
            linespacing=1.42)

    fig.tight_layout(w_pad=2.6)
    return save(
        fig, "confound", width="full",
        shows="left: what the critic's embedding organises by; right: every swept "
              "arm of the two adversarial heads as relative change in recordist lift "
              "against relative change in species lift, with the pre-registered gate "
              "region and the one-for-one diagonal",
        source="docs/14 §14.4 (production store) for the two lifts; docs/17 §17.2, "
               "§17.3, §17.5 for the swept arms (37-species debug store)",
        caption="The recordist, not the bird. Left: in the critic's embedding the "
                "strongest relation is who recorded the sound, not which animal made "
                "it. Right: every swept point from both adversarial heads. The shaded "
                "region is what the pre-registered gates asked for and no arm reaches "
                "it; the diagonal is a one-for-one exchange of recordist structure "
                "for species structure, and the plain adversarial head tracks it. "
                "The right panel is 37-species debug-scale.",
    )


def fig_batch_exchange():
    """SINGLE COLUMN. Post-hoc batch correction lands on the same exchange rate.

    docs/23 §23.1.1, batcheffect.py — 20 000 syllables of the production embedding,
    885 species, 1 001 recordists, 3 265 recordings.
    """
    arms = [
        ("baseline", 0.1643, 0.1665, SLATE, (6, 4)),
        ("centre by recordist", 0.1113, 0.1687, CLAY, (6, -10)),
        ("whiten by recordist", 0.0955, 0.1540, CLAY, (7, -2)),
        ("Harmony by recordist", 0.0501, 0.0478, VIOLET, (7, -3)),
        ("centre by recording", 0.0432, 0.0408, SLATE, (-6, 5)),
        ("whiten by recording", 0.0342, 0.0331, SLATE, (-6, -9)),
        ("Harmony by recording", 0.0463, 0.0501, VIOLET, (-7, 5)),
    ]
    fig, ax = plt.subplots(figsize=(W_COL, 2.90))
    lim = 0.185
    ax.plot([0, lim], [0, lim], color=SLATE, linewidth=0.7,
            linestyle=(0, (2.4, 2.2)), zorder=1)
    ax.text(0.150, 0.156, "one for one", fontsize=6.8, color=SLATE, rotation=42.0)
    # the gate: recordist halved with species not falling at all
    ax.add_patch(Rectangle((0.0, 0.1643), 0.1665 / 2, lim - 0.1643,
                           facecolor=VIOLET_W, edgecolor=VIOLET, linewidth=0.7,
                           linestyle=(0, (3.0, 2.2)), zorder=0))
    ax.text(0.041, 0.176, "the gate\n(empty)", fontsize=6.8, color=VIOLET,
            ha="center", va="center", linespacing=1.35)
    for name, sp, rec, c, off in arms:
        ax.plot([rec], [sp], "o", color=c, markersize=5.0,
                markeredgecolor="white", markeredgewidth=0.8, zorder=4)
        ax.annotate(name, (rec, sp), textcoords="offset points", xytext=off,
                    fontsize=6.6, color=c,
                    ha="left" if off[0] > 0 else "right", va="center")
    ax.set_xlim(0, lim)
    ax.set_ylim(0, lim)
    ax.set_xlabel("recordist lift")
    ax.set_ylabel("species lift")
    ax.set_title("post-hoc correction pays the same price", color=INK)
    ax.set_axisbelow(True)
    ax.grid(color=GRID, linewidth=0.5)
    ax.set_xticks([0, 0.05, 0.10, 0.15])
    ax.set_yticks([0, 0.05, 0.10, 0.15])
    note(ax,
         "Every arm that halves one lift halves the other. Subtracting each\n"
         "recordist's mean leaves the recordist lift higher than it started\n"
         "(0.1665 to 0.1687) while costing a third of the species structure,\n"
         "so the confound is not a location shift. 20 000 syllables of the\n"
         "production embedding, 885 species, 1 001 recordists.",
         y=-0.20)

    return save(
        fig, "batch-exchange", width="single",
        shows="species lift against recordist lift for seven post-hoc batch-effect "
              "correction arms, with the one-for-one diagonal and the pre-registered "
              "gate region",
        source="docs/23 §23.1.1, batcheffect.py — 20 000 syllables of the "
               "production embedding",
        caption="Post-hoc batch correction of the production embedding reaches the "
                "confound and pays exactly the price a gradient-reversed adversarial "
                "head paid. The gate asked for the recordist lift halved with species "
                "lift not falling at all; no arm lands in it. Two unrelated "
                "mechanisms landing on the same exchange rate is evidence about the "
                "data rather than about either mechanism.",
    )


def fig_map_quality():
    """FULL WIDTH. Wall 4 — the map's own confusion. docs/20 §20.1, §20.3.1-2."""
    fig, (a1, a2) = plt.subplots(
        2, 1, figsize=(W_FULL, 2.95),
        gridspec_kw={"height_ratios": [1, 1.35], "hspace": 0.95},
    )

    segs = [
        ("boundary near-ties\nmargin < 0.05", 76.4, RAMP[3], INK),
        ("mid-margin 0.05-0.1\nmostly bad sessions", 18.5, SLATE_W, BODY),
        ("genuine map failure\nunseen recordist", 2.6, CLAY, CLAY),
        ("seen recordist\nmap cosine < 0.90", 1.7, "#d98a72", CLAY),
        ("residual", 0.8, GRID, MUTED),
    ]
    left = 0.0
    for name, share, colour, tc in segs:
        a1.barh([0], [share], left=[left], height=0.42, color=colour,
                edgecolor="white", linewidth=1.0)
        if share > 8:
            a1.text(left + share / 2, 0, f"{share:.1f} %", ha="center", va="center",
                    fontsize=8.0, color=tc)
        left += share
    a1.set_xlim(0, 100)
    a1.set_ylim(-1.30, 0.95)
    a1.set_yticks([])
    a1.set_xticks([])
    for s in a1.spines.values():
        s.set_visible(False)
    a1.set_title("what the browser bridge's 38.6 % region disagreement is made of",
                 color=INK)
    a1.annotate("4.3 % is genuine map failure", xy=(97.2, 0.22), xytext=(74.0, 0.72),
                fontsize=7.0, color=CLAY, ha="center",
                arrowprops=dict(arrowstyle="-", color=CLAY, lw=0.6))
    for i, (name, share, colour, _tc) in enumerate(segs[:4]):
        cx = [38.0, 85.5, 96.5, 98.6][i]
        a1.text([2.0, 60.0, 88.0, 99.5][i], -0.34, name, fontsize=6.5, color=MUTED,
                ha="left" if i < 3 else "right", va="top", linespacing=1.35)
    a1.text(0.0, -0.98,
            "1 439 flips over 3 731 held-out syllables. Tie-adjusted "
            "agreement 0.91; species-level agreement 0.781 against chance 0.033. "
            "The addressable loss is at most 2.6 % of rows, so no better map class "
            "was pursued.",
            fontsize=6.7, color=MUTED, va="top")

    signals = [("off-manifold\n5-NN distance", 0.953, VIOLET),
               ("mapped-norm\ndeviation", 0.922, SLATE_W),
               ("the two combined", 0.954, SLATE_W)]
    xs = [0, 1, 2]
    a2.bar(xs, [s[1] for s in signals], 0.44, color=[s[2] for s in signals],
           edgecolor="none")
    a2.set_xlim(-0.62, 2.62)
    a2.set_ylim(0.86, 0.99)
    a2.set_xticks(xs)
    a2.set_xticklabels([s[0] for s in signals], fontsize=7.2)
    a2.set_ylabel("AUC against the bad-session label")
    a2.set_title("eight of 45 held-out sessions carry 22.9 % of that loss, and "
                 "separate cleanly", color=INK)
    hgrid(a2, [0.88, 0.92, 0.96])
    for x, (_n, v, _c) in zip(xs, signals):
        a2.text(x, v + 0.0035, f"{v:.3f}", ha="center", va="bottom", fontsize=7.6,
                color=VIOLET if x == 0 else BODY)
    gate_line(a2, 0.90, "adoption gate 0.90", side="left", pad=0.002)
    a2.text(0.0, -0.40,
            "The browser can compute the winning signal from the 28-d side alone, "
            "and a shipped cloud of 256 random anchors holds AUC $\\geq$ 0.92 for "
            "28 kB. Using it as a lever - raising the remaining rows' "
            "agreement by 5 points - failed at $+3.5$, so the pre-registered "
            "fallback fired and it ships as an honesty gate. End-to-end debug "
            "build; debug-scale.",
            transform=a2.transAxes, fontsize=6.7, color=MUTED, va="top",
            linespacing=1.42)

    return save(
        fig, "map-quality", width="full",
        shows="top: the decomposition of the bridge's region disagreement over "
              "3 731 held-out syllables; bottom: how well each candidate live signal "
              "separates the eight pathological sessions, against the adoption gate",
        source="docs/20 §20.1, §20.2 for the decomposition; §20.3.1-§20.3.2 for the "
               "session signals — end-to-end debug build",
        caption="Top: the 38.6\\,\\% region disagreement between the browser's bridge "
                "and the critic itself, decomposed over 3\\,731 held-out syllables. "
                "Three quarters of it is boundary near-ties; genuine large-margin map "
                "failure is 4.3\\,\\% of the loss. Bottom: the eight pathological "
                "sessions separate at AUC 0.953 on a statistic the browser can "
                "compute from the 28-dimensional side alone, and the two-signal "
                "combination adds nothing. End-to-end debug build; debug-scale.",
    )


def fig_tonal_pin():
    """FULL WIDTH. Wall 5 — the fit parks at the tonal end.
    docs/08 §8.1a as read by docs/21 §21.2; the clamp count from
    cli.py report_reachability.
    """
    fig, (a1, a2, a3) = plt.subplots(
        1, 3, figsize=(W_FULL, 2.25), gridspec_kw={"width_ratios": [1.4, 1, 1]}
    )

    labels = ["SCI > 1.5", "SCI > 3"]
    ours = [1.4, 0.0]
    real = [15.6, 5.3]
    xs = [0, 1]
    bw = 0.32
    a1.bar([x - bw / 2 - 0.01 for x in xs], ours, bw, color=CLAY, edgecolor="none")
    a1.bar([x + bw / 2 + 0.01 for x in xs], real, bw, color=VIOLET, edgecolor="none")
    for x, o, r in zip(xs, ours, real):
        a1.text(x - bw / 2 - 0.01, o + 0.45, f"{o:.1f}", ha="center", va="bottom",
                fontsize=7.6, color=CLAY)
        a1.text(x + bw / 2 + 0.01, r + 0.45, f"{r:.1f}", ha="center", va="bottom",
                fontsize=7.6, color=VIOLET)
    a1.text(-0.42, 14.6, "real syllables", fontsize=7.4, color=VIOLET)
    a1.text(-0.42, 3.2, "our resynthesis", fontsize=7.4, color=CLAY)
    a1.set_xticks(xs)
    a1.set_xticklabels(labels, fontsize=7.8)
    a1.set_xlim(-0.62, 1.62)
    a1.set_ylim(0, 19)
    a1.set_ylabel("share of syllables (%)")
    a1.set_title("the spectrally rich tail is missing", color=INK)
    hgrid(a1, [0, 5, 10, 15])
    a1.text(0.0, -0.235,
            "Median spectral content is right: 1.099 against 1.092.\n"
            "The tail is not there at all. The model contains the\n"
            "pulse-like regime that produces it; the fit does not\nreach it.",
            transform=a1.transAxes, fontsize=6.7, color=MUTED, va="top",
            linespacing=1.42)

    a2.bar([0], [0.0005], 0.42, color=CLAY, edgecolor="none")
    a2.bar([1], [0.044], 0.42, color=VIOLET, edgecolor="none")
    a2.set_yscale("log")
    a2.set_ylim(1e-4, 4e-1)
    a2.set_xlim(-0.62, 1.62)
    a2.set_xticks([0, 1])
    a2.set_xticklabels(["resynthesis", "real"], fontsize=7.8)
    a2.set_ylabel("median spectral flatness")
    a2.set_title("three orders too pure", color=INK)
    a2.set_axisbelow(True)
    a2.grid(axis="y", color=GRID, linewidth=0.5)
    a2.spines["left"].set_visible(True)
    a2.text(0, 0.00075, "0.0005", ha="center", va="bottom", fontsize=7.6, color=CLAY)
    a2.text(1, 0.062, "0.044", ha="center", va="bottom", fontsize=7.6, color=VIOLET)
    a2.text(0.0, -0.235,
            "A whistle too clean to be an animal. Real labial\nmotion at low tension "
            "is pulse-like and\nharmonically dense.",
            transform=a2.transAxes, fontsize=6.7, color=MUTED, va="top",
            linespacing=1.42)

    a3.barh([0], [52.0], color=CLAY, height=0.40, edgecolor="white", linewidth=1.0)
    a3.barh([0], [48.0], left=[52.0], color=SLATE_W, height=0.40, edgecolor="white",
            linewidth=1.0)
    a3.text(26.0, 0, "6 617", ha="center", va="center", color="white",
            fontsize=8.4)
    a3.text(76.0, 0, "6 107", ha="center", va="center", color=BODY, fontsize=8.0)
    a3.set_xlim(0, 100)
    a3.set_ylim(-0.85, 0.55)
    a3.set_yticks([])
    a3.set_xticks([0, 50, 100])
    a3.set_xlabel("share of 12 724 fitted types (%)")
    a3.set_title("and half the corpus rides a limit", color=INK)
    a3.spines["left"].set_visible(False)
    a3.tick_params(axis="y", length=0)
    a3.text(0, -0.50,
            "The tension clamp bites in 6 617 of 12 724 types\nwhile the "
            "syllable is audible, so over half the\ncorpus has contour excursions "
            "riding a\nparameterisation limit rather than a fitted value.",
            fontsize=6.7, color=MUTED, linespacing=1.42)

    fig.tight_layout(w_pad=2.2)
    return save(
        fig, "tonal-pin", width="full",
        shows="the resynthesis reproduces the median spectral content index and none "
              "of its tail, is three orders of magnitude too pure, and rides the "
              "tension clamp in over half of all fitted types",
        source="docs/08 §8.1a, docs/21 §21.2; clamp incidence from "
               "cli.py report_reachability on the production learn (12 724 types)",
        caption="The tonal-regime pin. Pinning every syllable to $\\beta \\approx 1$ "
                "places it at the tonal end of the model: the median spectral content "
                "index is reproduced almost exactly, the rich tail is absent, and "
                "median spectral flatness is three orders of magnitude too pure. The "
                "right panel is the parameterisation's own limit: the tension clamp "
                "bites in 6\\,617 of 12\\,724 types while the syllable is audible. "
                "The model contains the pulse-like regime that produces the missing "
                "tail; the fit does not reach it.",
    )


# ================================================================================
# C. OUR METHODS AGAINST EACH OTHER
# ================================================================================


def fig_orders():
    """FULL WIDTH. Held-out order scaling — the strongest result in the paper.

    docs/23 §23.2.2, analysis/w2_heldout_orders.py. 34 696 bouts, 327 164 tokens,
    2 421 species; 217 species clear the 20-bout bar.
    """
    ks = [0, 1, 2, 3]
    realv = [3.284, 2.301, 2.546, 2.866]
    ctrl = [2.879, 3.634, 4.868, 5.313]

    fig, (a1, a2, a3) = plt.subplots(
        1, 3, figsize=(W_FULL, 2.60), gridspec_kw={"width_ratios": [1.6, 1, 1]}
    )

    a1.plot(ks, realv, "o-", color=VIOLET, linewidth=1.6, markersize=4.8,
            markeredgecolor="white", markeredgewidth=0.8, zorder=4)
    a1.plot(ks, ctrl, "s-", color=SLATE, linewidth=1.4, markersize=4.4,
            markeredgecolor="white", markeredgewidth=0.8, zorder=3)
    for k, v in zip(ks, realv):
        a1.text(k, v - 0.16, f"{v:.3f}", ha="center", va="top", fontsize=7.2,
                color=VIOLET)
    for k, v in zip(ks, ctrl):
        a1.text(k, v + 0.16, f"{v:.3f}", ha="center", va="bottom", fontsize=7.2,
                color=SLATE)
    a1.text(3.06, 2.866, "real corpus", fontsize=7.6, color=VIOLET, ha="left",
            va="center")
    a1.text(3.06, 5.313, "within-species\nshuffle", fontsize=7.6, color=SLATE,
            ha="left", va="center", linespacing=1.35)
    # the order-1 gap, annotated on both curves
    a1.annotate("", xy=(0.86, 2.301), xytext=(0.86, 3.284),
                arrowprops=dict(arrowstyle="-|>", color=VIOLET, lw=0.8))
    a1.text(0.80, 2.79, "$-$0.98 bits", fontsize=7.2, color=VIOLET, ha="right",
            va="center")
    a1.annotate("", xy=(1.14, 3.634), xytext=(1.14, 2.879),
                arrowprops=dict(arrowstyle="-|>", color=SLATE, lw=0.8))
    a1.text(1.20, 3.26, "$+$0.75 bits", fontsize=7.2, color=SLATE, ha="left",
            va="center")
    a1.set_xlim(-0.28, 3.95)
    a1.set_ylim(1.85, 5.85)
    a1.set_xticks(ks)
    a1.set_xticklabels(["0\nunigram", "1", "2", "3"], fontsize=7.8)
    a1.set_xlabel("Markov order $k$")
    a1.set_ylabel("held-out cross-entropy (bits/token)")
    a1.set_title("a first order buys a bit per token; the control pays for it",
                 color=INK)
    hgrid(a1, [2, 3, 4, 5])
    a1.text(0.0, -0.235,
            "Lower is better. Per species, an 80/20 split by bout, a "
            "$k$-order backoff model fitted on the train\nhalf, every held-out token "
            "scored. An unbiased estimator paying for parameters it cannot use is "
            "the\nclean form of the claim that the tokens are units. Production "
            "corpus: 34 696 bouts, 327 164 tokens.",
            transform=a1.transAxes, fontsize=6.7, color=MUTED, va="top",
            linespacing=1.42)

    a2.bar([0], [-0.091], 0.44, color=CLAY, edgecolor="none")
    a2.bar([1], [-0.912], 0.44, color=SLATE, edgecolor="none")
    a2.axhline(0, color=BODY, linewidth=0.8)
    a2.set_xlim(-0.65, 1.65)
    a2.set_ylim(-1.10, 0.28)
    a2.set_xticks([0, 1])
    a2.set_xticklabels(["real", "control"], fontsize=7.8)
    a2.set_ylabel("median gain, order 1 $\\rightarrow$ 2 (bits/token)")
    a2.set_title("magnitude: fails", color=CLAY)
    hgrid(a2, [-1.0, -0.5, 0.0])
    a2.text(0, -0.13, "$-$0.091", ha="center", va="top", fontsize=7.8, color=CLAY)
    a2.text(1, -0.95, "$-$0.912", ha="center", va="top", fontsize=7.8, color=SLATE)
    gate_line(a2, 0.05, "gate $\\geq +$0.05", side="right", pad=0.02)
    a2.text(0.0, -0.235,
            "The median species loses 0.091 bits per\ntoken going to a second "
            "order, at three\nindependent splits ($-$0.091 / $-$0.116 / $-$0.142).\n"
            "The corpus cannot estimate the contexts a\nsecond order asks for.",
            transform=a2.transAxes, fontsize=6.7, color=MUTED, va="top",
            linespacing=1.42)

    a3.bar([0], [25.3], 0.44, color=VIOLET, edgecolor="none")
    a3.bar([1], [4.1], 0.44, color=SLATE, edgecolor="none")
    a3.set_xlim(-0.65, 1.65)
    a3.set_ylim(0, 34)
    a3.set_xticks([0, 1])
    a3.set_xticklabels(["real", "control"], fontsize=7.8)
    a3.set_ylabel("species gaining at order 1 $\\rightarrow$ 2 (%)")
    a3.set_title("share: passes", color=VIOLET)
    hgrid(a3, [0, 10, 20, 30])
    a3.text(0, 26.3, "25.3", ha="center", va="bottom", fontsize=7.8, color=VIOLET)
    a3.text(1, 5.1, "4.1", ha="center", va="bottom", fontsize=7.8, color=SLATE)
    gate_line(a3, 24.1, "gate: control $+$ 20 points", side="right", pad=0.5,
              colour=VIOLET)
    a3.text(0.0, -0.235,
            "A six-fold rate over the shuffle, clearing the\n20-point margin. So: "
            "there is no second-order\nstructure this corpus can support, and a\n"
            "quarter of species hint at one. 217 of 2 421\nspecies can be asked "
            "at all.",
            transform=a3.transAxes, fontsize=6.7, color=MUTED, va="top",
            linespacing=1.42)

    fig.tight_layout(w_pad=2.4)
    return save(
        fig, "orders", width="full",
        shows="held-out cross-entropy against Markov order for the real corpus and "
              "its within-species shuffle, and the two halves of the order-2 gate",
        source="docs/23 §23.2.2, pipeline/analysis/w2_heldout_orders.py — production "
               "corpus, 34 696 bouts, 327 164 tokens, 2 421 species",
        caption="Held-out order scaling. A first-order transition model over the "
                "learned syllable-type inventory buys 0.98 bits per token on bouts it "
                "has not seen, while on a within-species shuffle of the same tokens, "
                "with bout lengths and marginals preserved, the same model "
                "\\emph{costs} 0.75 bits. The estimator is unbiased by construction, "
                "so a model can only win if the transitions are real. A second order "
                "is not supported: the median species loses 0.091 bits per token, "
                "which fails the magnitude criterion, while a quarter of species gain "
                "something, which passes the share criterion. Production scale.",
    )


def fig_retrieval_population():
    """FULL WIDTH. Type retrieval against the cluster budget, and against the query
    population. docs/22 §22.8, analysis/w5_field_retrieval.py — one fixed 100-species
    debug matrix, 214 154 points, 2 143 types, 160 279 field points.
    """
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(W_FULL, 2.85), sharey=True)

    allpts = [
        ("$k$-means,\nuncapped\n$k = 4 298$", 0.5775, SLATE),
        ("$k$-means at\nproduction's\nshed ratio\n$k = 1 264$", 0.4599, SLATE_W),
        ("$k$-means at\n$k = 1 024$", 0.4227, SLATE_W),
        ("label\nassignment\n$k = 4 298$", 0.6020, VIOLET),
    ]
    field = [
        ("$k$-means,\nas shipped\n$k = 4 298$", 0.7176, SLATE),
        ("label\nassignment\n$k = 4 298$", 0.7604, VIOLET),
        ("label assignment,\nno synthetic\nanchor\n$k = 2 155$", 0.7606, VIOLET),
        ("$k$-means,\nno synthetic\nanchor\n$k = 2 155$", 0.7156, SLATE_W),
    ]
    for ax, arms, title, sub in (
        (a1, allpts, "all 214 154 points", "the population the build reports"),
        (a2, field, "the 160 279 field points every arm holds",
         "the population the question is about"),
    ):
        xs = list(range(len(arms)))
        ax.bar(xs, [a[1] for a in arms], 0.50, color=[a[2] for a in arms],
               edgecolor="none")
        ax.set_xticks(xs)
        ax.set_xticklabels([a[0] for a in arms], fontsize=6.8, linespacing=1.35)
        ax.set_xlim(-0.62, len(arms) - 0.38)
        ax.set_ylim(0, 0.90)
        ax.set_title(title, color=INK)
        ax.text(0.0, 1.015, sub, transform=ax.transAxes, fontsize=6.8, color=MUTED,
                va="bottom")
        hgrid(ax, [0, 0.2, 0.4, 0.6, 0.8])
        for x, a in zip(xs, arms):
            ax.text(x, a[1] + 0.012, f"{a[1]:.4f}", ha="center", va="bottom",
                    fontsize=7.6, color=a[2] if a[2] is not SLATE_W else BODY)
    a1.set_ylabel("type retrieval: is the nearest centroid\nthe point's own type?")

    # the 0.602 ceiling, drawn across both panels
    for ax, side in ((a1, "left"), (a2, "left")):
        ax.axhline(0.6020, color=VIOLET, linewidth=0.8, linestyle=(0, (3.0, 2.2)),
                   zorder=1)
    a1.text(-0.55, 0.615,
            "0.602 - the embedding's own ceiling: every type granted its own "
            "cluster",
            fontsize=6.8, color=VIOLET, ha="left", va="bottom")
    a2.text(-0.55, 0.615, "the same 0.602 line", fontsize=6.8, color=VIOLET,
            ha="left", va="bottom")

    # the two arms both panels hold, and what the population change is worth
    a1.annotate("", xy=(0.34, 0.5775), xytext=(0.66, 0.6020),
                arrowprops=dict(arrowstyle="-", color=CLAY, lw=0.7))
    a1.text(0.5, 0.545, "gate asked $+$10 points,\nmeasured $+$2.5: fails",
            fontsize=6.8, color=CLAY, ha="center", va="top", linespacing=1.35)
    a2.text(0.5, 0.688, "$+$4.3 points", fontsize=6.8, color=VIOLET, ha="center",
            va="top")
    a2.annotate("", xy=(0.34, 0.7176), xytext=(0.66, 0.7604),
                arrowprops=dict(arrowstyle="-", color=VIOLET, lw=0.7))

    fig.text(
        0.0, -0.055,
        "One fixed matrix dumped from a 100-species debug build: 214 154 points, "
        "2 143 types, 160 279 of the points from field recordings; every arm "
        "scored through the shipped clustering, seeding and purity\nfunctions. "
        "Changing the query population moves the same arm by 14 to 16 points, which is "
        "larger than any difference between arms - and an arm that drops the "
        "synthetic copies drops the hard queries, so on all\npoints it flatters itself "
        "by 18. Purity and type coverage are identities under label assignment, not "
        "measurements; type retrieval is the statistic that survives because nothing "
        "forces it. Debug-scale.",
        fontsize=6.7, color=MUTED, va="top", linespacing=1.45,
    )
    fig.tight_layout(w_pad=2.0)
    return save(
        fig, "retrieval-population", width="full",
        shows="type retrieval for the four clustering arms of each table, scored on "
              "all points and on the field points every arm holds unchanged, with the "
              "0.602 all-types-own-cluster ceiling drawn across both",
        source="docs/22 §22.8, pipeline/analysis/w5_field_retrieval.py — one fixed "
               "100-species debug matrix",
        caption="Type retrieval against the cluster budget, and against the query "
                "population. The question is the one the browser asks of live audio: "
                "is the nearest centroid by cosine the point's own type? Left: scored "
                "over all points, label assignment beats the shipped $k$-means by 2.5 "
                "points against a pre-registered 10, and fails --- on a corpus that "
                "fits under the cluster cap, seeded $k$-means is nearly as good as "
                "knowing the answer. Right: scored on the field points every arm "
                "holds unchanged, which is the population the question is about. The "
                "query population changes the same arm's answer by more than any arm "
                "changes it. Debug-scale.",
    )


def fig_avex():
    """FULL WIDTH. The data road and its honest shrink. docs/17 §17.4, §17.6.1."""
    fig, (a1, a2, a3) = plt.subplots(
        1, 3, figsize=(W_FULL, 2.40), gridspec_kw={"width_ratios": [1, 1, 1.15]}
    )
    arms = ["A\nsingle\ndomain", "B\nnaive\nmerge", "C\nmerge $+$\ncontrastive"]
    cols = [SLATE_W, VIOLET, VIOLET_W]
    for ax, vals, chance, title, ymax, ticks in (
        (a1, [0.360, 0.504, 0.638], 1 / 12,
         "first test: 12 species, 3 held out", 0.78, [0, 0.2, 0.4, 0.6]),
        (a2, [0.058, 0.093, 0.110], 1 / 63,
         "re-test: 63 species, 16 held out", 0.145, [0, 0.04, 0.08, 0.12]),
    ):
        xs = [0, 1, 2]
        ax.bar(xs, vals, 0.50, color=cols, edgecolor="none")
        ax.set_xticks(xs)
        ax.set_xticklabels(arms, fontsize=7.0, linespacing=1.35)
        ax.set_xlim(-0.62, 2.62)
        ax.set_ylim(0, ymax)
        ax.set_title(title, color=INK)
        hgrid(ax, ticks)
        for x, v in zip(xs, vals):
            ax.text(x, v + ymax * 0.02, f"{v:.3f}", ha="center", va="bottom",
                    fontsize=7.6, color=BODY)
        ax.axhline(chance, color=SLATE, linewidth=0.8, linestyle=(0, (3.0, 2.2)))
        ax.text(2.58, chance + ymax * 0.015, f"chance {chance:.3f}", fontsize=6.8,
                color=SLATE, ha="right", va="bottom")
    a1.set_ylabel("cross-domain species retrieval")

    effects = [("B over A\nmore domains per species", 14.4, 3.6, VIOLET),
               ("C over B\na contrastive mechanism", 13.4, 1.7, CLAY)]
    ys = [1, 0]
    for yy, (name, first, retest, c) in zip(ys, effects):
        a3.plot([retest, first], [yy, yy], color=c, linewidth=1.3,
                solid_capstyle="round", zorder=2)
        a3.plot([first], [yy], "o", color="white", markeredgecolor=c,
                markeredgewidth=1.1, markersize=5.4, zorder=3)
        a3.plot([retest], [yy], "o", color=c, markersize=5.4,
                markeredgecolor="white", markeredgewidth=0.8, zorder=4)
        a3.text(first + 0.7, yy, f"$+${first:.1f}", ha="left", va="center",
                fontsize=7.4, color=c)
        a3.text(retest - 0.7, yy, f"$+${retest:.1f}", ha="right", va="center",
                fontsize=7.4, color=c)
    a3.set_yticks(ys)
    a3.set_yticklabels([e[0] for e in effects], fontsize=7.0, linespacing=1.35)
    a3.set_xlim(-1.5, 21.5)
    a3.set_ylim(-0.75, 1.65)
    a3.set_xticks([0, 5, 10, 15, 20])
    a3.set_xlabel("effect size (percentage points)")
    a3.set_title("every effect shrank; the ordering survived", color=INK)
    vgrid(a3)
    a3.axvline(10.0, color=CLAY, linewidth=0.8, linestyle=(0, (3.0, 2.2)), zorder=1)
    a3.text(10.4, 1.48, "the $+$10 gate\nC had to clear", fontsize=6.8, color=CLAY,
            ha="left", va="top", linespacing=1.35)
    a3.text(0.0, -0.30,
            "Hollow: the first test. Filled: the pre-registered re-test.\n"
            "The mechanism's boost was small-sample structure; the\ndata road's was "
            "not, and survives at a quarter of the size.",
            transform=a3.transAxes, fontsize=6.7, color=MUTED, va="top",
            linespacing=1.42)

    fig.text(0.0, -0.075,
             "Both panels are debug-scale and absolute levels are comparable only arm "
             "against arm inside each panel. The merge's own held-out realism AUC "
             "reads below the single-domain arm's in the re-test\n"
             "(0.976 against 0.995) where the first test gained 0.012, so every number "
             "from the first test should be treated as small-sample in both directions.",
             fontsize=6.7, color=MUTED, va="top", linespacing=1.45)
    fig.tight_layout(w_pad=2.2)
    return save(
        fig, "avex", width="full",
        shows="cross-domain species retrieval for three training arms at two scales, "
              "and the two effect sizes as measured first and on the pre-registered "
              "re-test",
        source="docs/17 §17.4 (12 species, 3 held out) and §17.6.1 (63 species, "
               "16 held out)",
        caption="The data road works and its effect size shrank honestly when "
                "re-tested. Merging two genuinely different recording domains bought "
                "$+14.4$ points of cross-domain species retrieval on 12 species and "
                "$+3.6$ on 63; a cross-domain contrastive mechanism on top reached "
                "$+13.4$ at the small scale and $+1.7$ against a $+10$ gate at the "
                "larger one, so the mechanism's boost was small-sample structure. "
                "What survives the bigger test is the ordering: more domains per "
                "species helps, and the mechanism adds approximately nothing on top "
                "of the data. Both panels are debug-scale.",
    )


def fig_syntax_depth():
    """FULL WIDTH. Why the heavier grammar wins, and where the data runs out.
    docs/18 P1 (30-species debug bake-off and the 2026-08-01 re-run at 104 species);
    the debug-100 bout count.
    """
    fig, (a1, a2) = plt.subplots(
        1, 2, figsize=(W_FULL, 2.45), gridspec_kw={"width_ratios": [1.45, 1]}
    )

    groups = ["seen transitions\n90 % of held-out tokens", "unseen tail\n10 %"]
    first = [-1.525, -9.25]
    hmm = [-1.624, -4.16]
    xs = [0, 1]
    bw = 0.30
    a1.bar([x - bw / 2 - 0.01 for x in xs], first, bw, color=VIOLET, edgecolor="none")
    a1.bar([x + bw / 2 + 0.01 for x in xs], hmm, bw, color=SLATE_W, edgecolor="none")
    a1.axhline(0, color=BODY, linewidth=0.8)
    for x, f, h in zip(xs, first, hmm):
        a1.text(x - bw / 2 - 0.01, f - 0.4, f"{f:.2f}", ha="center", va="top",
                fontsize=7.4, color=VIOLET)
        a1.text(x + bw / 2 + 0.01, h - 0.4, f"{h:.2f}", ha="center", va="top",
                fontsize=7.4, color=BODY)
    a1.text(-0.42, -6.4, "first order (shipped)", fontsize=7.4, color=VIOLET)
    a1.text(-0.42, -7.4, "hidden-state HMM", fontsize=7.4, color=BODY)
    a1.set_xticks(xs)
    a1.set_xticklabels(groups, fontsize=7.4, linespacing=1.35)
    a1.set_xlim(-0.62, 1.62)
    a1.set_ylim(-11.4, 1.4)
    a1.set_ylabel("held-out log-likelihood (nats/token)")
    a1.set_title("the heavier grammar wins only where the data runs out", color=INK)
    hgrid(a1, [-10, -8, -6, -4, -2, 0])
    a1.text(0.0, -0.235,
            "First order is the better model on the 90 % of held-out tokens whose "
            "transition was seen in\ntraining, and the HMM's entire advantage is the "
            "unseen tail. That is a property of smoothing\nshape, not of "
            "recovered hidden structure, so the smoothing was repaired instead: a "
            "Kneser-Ney\ncontinuation backoff gains $+$1.90 and $+$2.32 nats per token "
            "on unseen-context transitions.",
            transform=a1.transAxes, fontsize=6.7, color=MUTED, va="top",
            linespacing=1.42)

    a2.barh([0], [12], color=VIOLET, height=0.40, edgecolor="white", linewidth=1.0)
    a2.barh([0], [88], left=[12], color=SLATE_W, height=0.40, edgecolor="white",
            linewidth=1.0)
    a2.text(6, 0, "12", ha="center", va="center", color="white", fontsize=8.4)
    a2.text(56, 0, "88", ha="center", va="center", color=BODY, fontsize=8.4)
    a2.set_xlim(0, 100)
    a2.set_ylim(-0.95, 0.55)
    a2.set_yticks([])
    a2.set_xticks([0, 50, 100])
    a2.set_xlabel("species of the 100-species debug store")
    a2.set_title("and few species have the bouts to try", color=INK)
    a2.spines["left"].set_visible(False)
    a2.tick_params(axis="y", length=0)
    a2.text(0, -0.58,
            "Twelve species reach 20 bouts after run-collapse, which is\nthe syntax "
            "threshold. Counted before the depth harvest; the\nproduction re-count is "
            "217 of 2 421 species, and the harvest\ntook the bake-off's "
            "qualifying species from 30 to 104.",
            fontsize=6.7, color=MUTED, linespacing=1.42)

    fig.tight_layout(w_pad=2.4)
    return save(
        fig, "syntax-depth", width="full",
        shows="left: held-out likelihood split by whether the transition was seen in "
              "training, first-order against a hidden-state model; right: how few "
              "species of the debug store have the bouts to attempt song-level "
              "structure",
        source="docs/18 P1 and its 2026-08-01 re-run; the bout count is the "
               "100-species debug store",
        caption="Left: held-out likelihood split by whether the transition was seen "
                "in training. The heavier grammar's whole advantage lives where the "
                "data runs out, which is a property of smoothing shape rather than of "
                "recovered hidden structure. Right: species of the 100-species debug "
                "store with enough bouts to attempt song-level structure, counted "
                "before the depth harvest. Both panels are debug-scale.",
    )


def fig_song_funnel():
    """FULL WIDTH. The song funnel, in the three units it actually changes through.
    docs/22 §22.1, §22.2; docs/12 §12.2-12.3.
    """
    fig, (a1, a2, a3) = plt.subplots(
        1, 3, figsize=(W_FULL, 2.30), gridspec_kw={"width_ratios": [1, 1.05, 1.15]}
    )

    # stage 1 — syllable observations
    s1 = [("observations", 340079, SLATE_W), ("typed", 327164, VIOLET)]
    ys = [1, 0]
    a1.barh(ys, [s[1] for s in s1], height=0.46, color=[s[2] for s in s1],
            edgecolor="none")
    for yy, s in zip(ys, s1):
        a1.text(s[1] * 0.97, yy, thousands(s[1]), va="center", ha="right",
                fontsize=7.6, color="white" if s[2] is VIOLET else BODY)
    a1.set_yticks(ys)
    a1.set_yticklabels(["syllable observations", "typed (96.2 %)"], fontsize=7.4)
    a1.set_xlim(0, 3.9e5)
    a1.set_ylim(-0.62, 1.62)
    a1.set_xticks([0, 2e5])
    a1.set_xticklabels(["0", "200 000"])
    a1.set_title("syllables", color=INK)
    vgrid(a1)
    a1.text(0.0, -0.24,
            "The loss here is accounting, not machinery.",
            transform=a1.transAxes, fontsize=6.7, color=MUTED, va="top")

    # stage 2 — bouts
    s2 = [("bouts", 34696, SLATE_W), ("collapse to one token", 19738, CLAY_W),
          ("candidates, 3 tokens or more", 10550, VIOLET)]
    ys = [2, 1, 0]
    a2.barh(ys, [s[1] for s in s2], height=0.46, color=[s[2] for s in s2],
            edgecolor="none")
    for yy, s in zip(ys, s2):
        a2.text(s[1] * 0.97, yy, thousands(s[1]), va="center", ha="right",
                fontsize=7.6, color="white" if s[2] is VIOLET else BODY)
    a2.set_yticks(ys)
    a2.set_yticklabels(["bouts (a 1.0 s gap breaks one)", "collapse to one token\n"
                        "(56.9 %)", "candidates (30.4 %)"], fontsize=7.4,
                       linespacing=1.35)
    a2.set_xlim(0, 4.1e4)
    a2.set_ylim(-0.62, 2.62)
    a2.set_xticks([0, 2e4, 4e4])
    a2.set_xticklabels(["0", "20 000", "40 000"])
    a2.set_title("bouts", color=INK)
    vgrid(a2)
    a2.text(0.0, -0.24,
            "6 940 of the collapsing bouts are three syllables\nor more, a "
            "bird repeating one sound, which is a\nrepertoire fact and not a "
            "measurement error.",
            transform=a2.transAxes, fontsize=6.7, color=MUTED, va="top",
            linespacing=1.42)

    # stage 3 — species and song types
    s3 = [("species that can be asked", 366, SLATE_W),
          ("motifs only: species with a song", 48, SLATE),
          ("$+$ repeat classes", 98, VIOLET)]
    ys = [2, 1, 0]
    a3.barh(ys, [s[1] for s in s3], height=0.46, color=[s[2] for s in s3],
            edgecolor="none")
    for yy, s in zip(ys, s3):
        a3.text(s[1] + 7, yy, thousands(s[1]), va="center", fontsize=7.6,
                color=s[2] if s[2] is not SLATE_W else BODY)
    a3.set_yticks(ys)
    a3.set_yticklabels(["6 candidates, 2 distinct strings\n(15.1 % of species)",
                        "shipped: motifs only", "$+$ repeat classes: adopted"],
                       fontsize=7.4, linespacing=1.35)
    a3.set_xlim(0, 430)
    a3.set_ylim(-0.62, 2.62)
    a3.set_xticks([0, 100, 200, 300, 400])
    a3.set_title("species with a measured song", color=INK)
    vgrid(a3)
    a3.text(0.0, -0.24,
            "Repeat classes take song types from 96 to 356 (96\nmotifs, 260 repeats) "
            "and placed bouts from 1 052 to\n3 741, with the within-species "
            "shuffle control\nunchanged to the bout at 0.170 % against a "
            "0.2 % bar:\nshuffling destroys runs, so the control finds no repeat\n"
            "classes at all. Ninety-eight of 2 421 species is 4.0 %.",
            transform=a3.transAxes, fontsize=6.7, color=MUTED, va="top",
            linespacing=1.42)

    fig.tight_layout(w_pad=2.0)
    return save(
        fig, "song-funnel", width="full",
        shows="the song funnel stage by stage, in the three units it passes through: "
              "syllable observations, bouts, and species with a measured song",
        source="docs/22 §22.1, §22.2; docs/12 §12.2-§12.3 — production store",
        caption="The song funnel on the production store, drawn in the three units it "
                "actually changes through rather than on one axis. Of 340\\,079 "
                "syllable observations, 327\\,164 are typed and form 34\\,696 bouts, "
                "of which 56.9\\,\\% collapse to a single token and 30.4\\,\\% "
                "survive as candidates; 366 species have enough candidates to ask the "
                "question and 48 got a motif song type. Adding a repeat class --- one "
                "collapsed string heard at least six times, matched by equality --- "
                "takes that to 98 species with the permutation control unmoved to the "
                "bout.",
    )


# ================================================================================
# D. OUR METHODS AGAINST OTHER APPROACHES
# ================================================================================


def fig_external_spaces():
    """FULL WIDTH. Three spaces, two populations. docs/23 §23.6.1-§23.6.3,
    analysis/w6_birdnet_arms.json.

    This is the one figure in the set where hue carries model identity rather than a
    verdict. The verdicts are carried by the gate rules and the labels.
    """
    fig, (a1, a2, a3) = plt.subplots(1, 3, figsize=(W_FULL, 2.85))
    spaces = [("our critic\n32-d", VIOLET), ("Perch 2.0\n1 536-d", MOSS),
              ("BirdNET\n1 024-d", OCHRE)]
    xs = [0, 1, 2]

    panels = [
        (a1, [0.0891, 0.0744, 0.1107], 0.0891 * 0.70, 0.145,
         "recordist lift, T1 population",
         "1 567 recordings, 135 recordists, 1 341 species\n"
         "recordist coverage 0.907",
         [None, "$-$16.5 %", "$+$24 %"], True),
        (a2, [0.1684, 0.1155, 0.1755], 0.1684 * 0.70, 0.235,
         "recordist lift, T3 population",
         "958 species with two recordings each, 1 644\nrecordings, 760 "
         "recordists; recordist coverage 0.329",
         [None, "$-$31.4 %", "$+$4 %"], True),
        (a3, [0.0074, 0.0588, 0.0393], None, 0.082,
         "species lift, T3 population",
         "the same rows and the same null as the middle\npanel; species coverage "
         "0.834",
         [None, "8.0$\\times$ ours", "5.3$\\times$ ours"], False),
    ]
    for ax, vals, gate, ymax, title, cover, deltas, lower_better in panels:
        ax.bar(xs, vals, 0.50, color=[s[1] for s in spaces], edgecolor="none")
        ax.set_xticks(xs)
        ax.set_xticklabels([s[0] for s in spaces], fontsize=7.2, linespacing=1.35)
        ax.set_xlim(-0.62, 2.62)
        ax.set_ylim(0, ymax)
        ax.set_title(title, color=INK)
        hgrid(ax)
        for x, v, d in zip(xs, vals, deltas):
            ax.text(x, v + ymax * 0.018, f"{v:.4f}", ha="center", va="bottom",
                    fontsize=7.6, color=BODY)
            if d:
                ax.text(x, v + ymax * 0.085, d, ha="center", va="bottom",
                        fontsize=7.0, color=spaces[x][1])
        if gate is not None:
            ax.axhline(gate, color=CLAY, linewidth=0.8, linestyle=(0, (3.0, 2.2)),
                       zorder=1)
            ax.text(2.60, gate + ymax * 0.012,
                    "the T1 gate: $-$30 % of our recordist lift", fontsize=6.8,
                    color=CLAY, ha="right", va="bottom")
        ax.text(0.0, -0.245, cover, transform=ax.transAxes, fontsize=6.7,
                color=MUTED, va="top", linespacing=1.42)
    a1.set_ylabel("nearest-neighbour lift over a permutation null,\nper recording")

    a1.text(0.0, -0.42,
            "T1 fails: Perch measured\n$-$16.5 % against a $-$30 % bar, and "
            "is\nthe fourth independent closure of\nthis road.",
            transform=a1.transAxes, fontsize=6.7, color=CLAY, va="top",
            linespacing=1.42)
    a2.text(0.0, -0.42,
            "The verdict rests on a coverage\ntie-break: T1 passes here at $-$31.4 % "
            "and\nfails on its own population, whose\nestimate covers 0.907 of rows "
            "against\n0.329. The instrument built for the\nquestion wins.",
            transform=a2.transAxes, fontsize=6.7, color=MUTED, va="top",
            linespacing=1.42)
    a3.text(0.0, -0.42,
            "T3 passes, within its stated scope:\nan external space is the "
            "better\nper-recording species descriptor. It\ndoes not say that "
            "Perch beats our critic\nsyllable for syllable: that comparison\n"
            "has never been run.",
            transform=a3.transAxes, fontsize=6.7, color=MOSS, va="top",
            linespacing=1.42)

    fig.text(0.0, -0.30,
             "Read-only tests on a fixed store, one estimator, no training and no new "
             "data. The representation is per recording in every row, so "
             "same-recording leakage is impossible by construction. The finding that "
             "holds in both draws is the\none to carry: in Perch's space the recordist "
             "lift is still twice the species lift, in BirdNET's 4.5 times, in ours "
             "23 times. Every space tested is confounded in the same direction and "
             "they differ only in degree.",
             fontsize=6.7, color=MUTED, va="top", linespacing=1.45)
    fig.tight_layout(w_pad=2.4)
    return save(
        fig, "external-spaces", width="full",
        shows="recordist and species nearest-neighbour lift for our 32-d critic and "
              "two archive-scale external models, on the two populations, with the "
              "T1 gate and each estimate's coverage",
        source="docs/23 §23.6.1, §23.6.2, §23.6.3; "
               "pipeline/analysis/w6_birdnet_arms.json",
        caption="Three spaces, two populations. Recordist and species "
                "nearest-neighbour lift over a permutation null, per recording, for "
                "our 32-dimensional critic and two archive-scale external models. "
                "Perch 2.0 --- trained on the same archives at roughly a hundred times "
                "our scale and never asked to tell our resynthesis from a bird --- "
                "still carries five sixths of the recordist structure ours does, and "
                "BirdNET carries more than ours in both populations. If archive-scale "
                "training conferred recorder invariance the two largest models would "
                "both have it and they would agree; one is better than ours and one is "
                "worse, which locates the property in the archives. The species panel "
                "is the comparison we lose, and lose clearly. Hue carries model "
                "identity here, not a verdict.",
    )


# ================================================================================
# E. THE ACOUSTIC EXAMPLES — real audio against our own renderer
# ================================================================================

# Three fitted types, chosen once and pinned here so the figure is reproducible.
#
# Selection rule, applied to `data/learned-inventory.json` joined to the audio
# cache: of the 2 773 fitted types that have at least 8 member syllables in a
# cached recording and a fitted duration between 0.10 s and 0.45 s, these are taken
# from the top, the middle and the bottom of the resynthesis-cosine ordering, with
# the additional requirement that the syllable's energy lies above 1 kHz so that a
# 22.05 kHz cache can show it. The corpus median cosine is 0.6477 over 13 859
# types, so the middle row is a median type and not a chosen success.
#
# The cosine is the objective the fit was run under. docs/19 measured its
# correlation with audible distortion at about +0.1, so it does NOT rank audible
# fidelity, and the caption says so.
EXAMPLES = [
    ("monarcha_melanopsis", "L02", "the model reproduces this one"),
    ("arundinax_aedon", "L06", "a median type"),
    ("pellorneum_tickelli", "L02", "the model does not reproduce this one"),
]

STORE = "harvest-gan"


def _load_examples():
    """Join inventory -> typing -> syllables -> cached WAV for the pinned types."""
    wanted = {(s, t) for s, t, _ in EXAMPLES}

    inv = json.loads((ROOT / "data" / "learned-inventory.json").read_text())
    fitted: dict[tuple[str, str], dict] = {}
    for sp in inv["species"]:
        for syl in sp.get("syllables", []):
            key = (sp["id"], syl["id"])
            if key in wanted:
                fitted[key] = {"syllable": syl, "species": sp}
    missing = wanted - set(fitted)
    if missing:
        raise SystemExit(f"pinned types absent from the inventory: {sorted(missing)}")

    cache_dir = ROOT / "pipeline" / "out" / "audio-cache"
    cached = {p.stem for p in cache_dir.glob("*.wav")}

    typing = json.loads(
        (ROOT / "pipeline" / "out" / STORE / "typing.json").read_text()
    )["entries"]
    members: dict[tuple[str, str], list[tuple[str, int]]] = {k: [] for k in wanted}
    for e in typing:
        key = (e["speciesId"], e["typeId"])
        if key in wanted and e["recordingId"] in cached:
            members[key].append((e["recordingId"], e["order"]))

    index = {(k[0], rid, order): k for k, v in members.items() for rid, order in v}
    probes = [rid.encode() for rid in {rid for _, rid, _ in index}]
    measured: dict[tuple[str, str], list[dict]] = {k: [] for k in wanted}
    with (ROOT / "pipeline" / "out" / STORE / "syllables.jsonl").open("rb") as fh:
        for line in fh:
            if not any(p in line for p in probes):
                continue
            rec = json.loads(line)
            key = index.get((rec["species_id"], rec["recording_id"], rec["order"]))
            if key is not None:
                measured[key].append(rec)
    for k, rows in measured.items():
        rows.sort(key=lambda r: (r["recording_id"], r["order"]))
        if not rows:
            raise SystemExit(f"no cached member syllables found for {k}")
    return fitted, measured


def _contour_mean_hz(contour) -> float:
    return float(np.mean([p[1] for p in contour]))


def _representative(rows: list[dict], fit: dict) -> dict:
    """The member closest to the fitted type in log duration and log mean pitch.

    Deterministic: ties break on (recording id, order).
    """
    tf0 = _contour_mean_hz(fit["contour"])

    def cost(r):
        return (
            abs(math.log(r["dur"] / fit["dur"]))
            + abs(math.log(_contour_mean_hz(r["contour"]) / tf0)),
            r["recording_id"],
            r["order"],
        )

    return min(rows, key=cost)


def _spec_db(x: np.ndarray, sr: int, nperseg=256, hop=64):
    f, t, S = spectrogram(x, fs=sr, window="hann", nperseg=nperseg,
                          noverlap=nperseg - hop, mode="magnitude", detrend=False)
    peak = float(S.max()) if S.size else 1.0
    db = 20.0 * np.log10(np.maximum(S, 1e-9) / max(peak, 1e-9))
    return f, t, db


def _resample_contour(contour, n=9):
    ts = np.array([p[0] for p in contour], dtype=float)
    hz = np.array([p[1] for p in contour], dtype=float)
    return np.interp(np.linspace(0.0, 1.0, n), ts, hz)


def fig_spectral_examples(fitted, measured, calibration):
    """FULL WIDTH. Real recording against our resynthesis, for three fitted types."""
    import soundfile as sf

    pad = 0.020  # seconds of context either side, identical on both sides
    nrow = len(EXAMPLES)
    fig = plt.figure(figsize=(W_FULL, 5.85))
    gs = fig.add_gridspec(
        nrow, 3, left=0.060, right=0.940, top=0.930, bottom=0.200,
        hspace=1.15, wspace=0.30, width_ratios=[1.15, 1.15, 1.0],
    )
    axes = np.empty((nrow, 3), dtype=object)
    for r in range(nrow):
        for c in range(3):
            axes[r, c] = fig.add_subplot(gs[r, c])
    mesh = None
    fmax_khz = 10.0

    for row, (sp_id, ty_id, verdict) in enumerate(EXAMPLES):
        fit = fitted[(sp_id, ty_id)]["syllable"]
        sp = fitted[(sp_id, ty_id)]["species"]
        rows = measured[(sp_id, ty_id)]
        rep = _representative(rows, fit)
        cosine = fit["learned"]["resynthesisCosine"]

        wav, sr = sf.read(
            str(ROOT / "pipeline" / "out" / "audio-cache" / f"{rep['recording_id']}.wav"),
            dtype="float64", always_2d=False,
        )
        if wav.ndim > 1:
            wav = wav.mean(axis=1)
        a = int(round(max(0.0, rep["start"] - pad) * sr))
        b = int(round((rep["start"] + rep["dur"] + pad) * sr))
        real = peak_normalise(np.asarray(wav[a:b], dtype=np.float64).copy())

        # our own renderer, then to the cache's rate so both panels share one axis
        syn = render_syllable(fit, sample_rate=SAMPLE_RATE, calibration=calibration)
        syn = resample_poly(syn, sr, SAMPLE_RATE)
        npad = int(round(pad * sr))
        syn = peak_normalise(
            np.concatenate([np.zeros(npad), syn, np.zeros(npad)])
        )

        span = max(real.size, syn.size) / sr * 1000.0
        for col, (x, head) in enumerate(
            ((real, "the recording"), (syn, "our resynthesis"))
        ):
            ax = axes[row, col]
            f, t, db = _spec_db(x, sr)
            mesh = ax.pcolormesh(t * 1000.0, f / 1000.0, db, vmin=-70.0, vmax=0.0,
                                 cmap=SPEC_CMAP, shading="nearest", rasterized=True)
            ax.set_ylim(0, fmax_khz)
            ax.set_xlim(0, span)
            ax.set_yticks([0, 4, 8])
            ax.tick_params(colors=MUTED, labelsize=7.0)
            for s in ax.spines.values():
                s.set_visible(False)
            ax.set_title(head, fontsize=7.6, color=INK, pad=3.0)
            if col == 0:
                ax.set_ylabel("kHz", fontsize=7.4)
            if row == len(EXAMPLES) - 1:
                ax.set_xlabel("ms", fontsize=7.4)

        # the measured contours of every cached member, and the fitted one
        ax = axes[row, 2]
        grid = np.array([_resample_contour(r["contour"]) for r in rows]) / 1000.0
        tt = np.linspace(0.0, 1.0, grid.shape[1])
        for r in rows:
            ax.plot([p[0] for p in r["contour"]],
                    [p[1] / 1000.0 for p in r["contour"]],
                    color="#c9c5d1", linewidth=0.6, zorder=2)
        ax.plot([p[0] for p in rep["contour"]],
                [p[1] / 1000.0 for p in rep["contour"]],
                color=SLATE, linewidth=1.3, zorder=3)
        ax.plot([p[0] for p in fit["contour"]],
                [p[1] / 1000.0 for p in fit["contour"]],
                color=VIOLET, linewidth=1.7, zorder=4)
        iqr = float(np.median(np.percentile(grid, 75, axis=0)
                              - np.percentile(grid, 25, axis=0)))
        ax.set_xlim(0, 1)
        ax.set_ylim(0, fmax_khz)
        ax.set_yticks([0, 4, 8])
        ax.set_xticks([0, 0.5, 1.0])
        ax.set_title("measured $f_0$, all members", fontsize=7.6, color=INK, pad=3.0)
        ax.set_ylabel("kHz", fontsize=7.4)
        if row == len(EXAMPLES) - 1:
            ax.set_xlabel("normalised time", fontsize=7.4)
        hgrid(ax, [0, 4, 8])
        ax.text(0.03, 9.4, f"member spread {iqr:.2f} kHz", fontsize=6.4,
                color=MUTED, va="top")

        # the row's identity, on two lines above the left panel
        verdict_colour = VIOLET if cosine > 0.9 else (CLAY if cosine < 0 else INK)
        axes[row, 0].text(
            0.0, 1.58,
            f"{sp.get('common') or sp['scientific']} ({sp['scientific']}), type "
            f"{ty_id}: {verdict}",
            transform=axes[row, 0].transAxes, fontsize=7.8, color=verdict_colour,
            va="bottom", ha="left",
        )
        axes[row, 0].text(
            0.0, 1.30,
            f"resynthesis cosine {cosine:+.3f}   |   {len(rows)} member syllables "
            f"with cached audio   |   fitted duration {fit['dur'] * 1000:.0f} ms, "
            f"timbre class {fit['timbre']}",
            transform=axes[row, 0].transAxes, fontsize=6.8, color=MUTED,
            va="bottom", ha="left",
        )

    cax = fig.add_axes([0.958, 0.760, 0.009, 0.130])
    cb = fig.colorbar(mesh, cax=cax)
    cb.set_ticks([-70, -35, 0])
    cb.set_label("dB re panel peak", fontsize=6.4, color=MUTED, labelpad=1.5)
    cb.ax.tick_params(labelsize=6.2, colors=MUTED, length=1.8)
    cb.outline.set_visible(False)

    fig.text(0.004, 0.140,
             "Each spectrogram: 22.05 kHz cached audio, 256-sample Hann window, "
             "64-sample hop, peak-normalised, 70 dB range. Both sides of a\nrow carry "
             "identical settings, identical axes and one colour scale. The resynthesis "
             "is rendered by the repository's own renderer\nat 48 kHz and resampled to "
             "the cache's rate; 20 ms of context is kept on the recording and matched "
             "with silence on the\nresynthesis, so the flat band at each panel's edge "
             "is the field recording's own noise floor. Third panel, grey: the "
             "measured\npitch contour of every cached member of the type; slate: the "
             "member plotted to its left; violet: the contour the fit ships.\n"
             "The cosine is the objective the fit was run under; docs/19 measured its "
             "correlation with audible distortion at about $+$0.1, so\nit ranks the "
             "fit's own criterion and not audible fidelity. Production store, and the "
             "audio cache holds iNaturalist recordings only.",
             fontsize=6.5, color=MUTED, va="top", linespacing=1.5)

    return save(
        fig, "spectral-examples", width="full",
        shows="for three fitted types spanning the corpus's fit quality, the "
              "original recording's syllable, our resynthesis of the type on the same "
              "axes and colour scale, and the measured pitch contours of every cached "
              "member against the contour the fit ships",
        source="pipeline/out/harvest-gan/{typing.json,syllables.jsonl}, "
               "data/learned-inventory.json, pipeline/out/audio-cache/, rendered "
               "through birdy_pipeline.syrinx.render_syllable with "
               "app/static/birdy/syrinx-calibration.json",
        caption="What the physical model reproduces, and what it misses. Three fitted "
                "types, taken from the top, the middle and the bottom of the "
                "resynthesis-cosine ordering over the types whose members have cached "
                "audio; the corpus median is 0.648 over 13\\,859 types, so the middle "
                "row is a median type rather than a chosen success. Top: a clean "
                "descending whistle, which the oscillator and its tracking tract "
                "reproduce closely. Middle: the median case --- the pitch is right and "
                "the pulse train that carries the real syllable's timbre is replaced "
                "by a steady tone. Bottom: a failure, and the third panel says why: "
                "the type's member contours disagree by kilohertz, so the cluster "
                "median the fit starts from describes no member well. The cosine is "
                "the objective the fit optimised and is \\emph{not} a ranking of "
                "audible fidelity (Section~\\ref{sec:walls}).",
    )


def fig_gestures(fitted, calibration):
    """FULL WIDTH. The fitted gestures behind the same three types.

    This is what "interpretable parameters" means here: two contours, in physical
    units, that a reader can name. Pressure and tension are separate rows because
    they are separate units — never two y-scales on one axis.
    """
    fig, axes = plt.subplots(
        2, len(EXAMPLES), figsize=(W_FULL, 2.85), sharex=True,
        gridspec_kw={"hspace": 0.30, "wspace": 0.28},
    )
    for col, (sp_id, ty_id, _verdict) in enumerate(EXAMPLES):
        fit = fitted[(sp_id, ty_id)]["syllable"]
        sp = fitted[(sp_id, ty_id)]["species"]
        plan = render_plan(fit, SAMPLE_RATE)
        beta = beta_for(plan.f0, plan.ps, calibration, plan.gamma)
        lo, hi, bmin, bmax = clamp_incidence(fit, calibration, SAMPLE_RATE)
        tn = plan.t / max(plan.t[-1], 1e-9)

        ax = axes[0, col]
        ax.plot(tn, plan.ps, color=VIOLET, linewidth=1.4)
        ax.set_ylim(0, 1.5)
        ax.set_yticks([0, 0.5, 1.0, 1.5])
        ax.set_title(f"{sp.get('common') or sp['scientific']}, {ty_id}",
                     fontsize=7.6, color=INK)
        hgrid(ax, [0, 0.5, 1.0, 1.5])
        if col == 0:
            ax.set_ylabel("$p_s$: air-sac\npressure gesture", fontsize=7.4)
        ax.text(0.03, 1.40, f"{fit['dur'] * 1000:.0f} ms, attack "
                            f"{fit['attack'] * 1000:.0f} ms", fontsize=6.4,
                color=MUTED, va="top")

        ax = axes[1, col]
        ax.axhspan(BETA_MIN * 0.5, BETA_MIN, color=CLAY_W, zorder=0)
        ax.plot(tn, beta, color=VIOLET, linewidth=1.4, zorder=3)
        ax.axhline(BETA_MIN, color=CLAY, linewidth=0.7,
                   linestyle=(0, (3.0, 2.2)), zorder=2)
        ax.set_yscale("log")
        ax.set_ylim(BETA_MIN * 0.55, 20.0)
        ax.set_yticks([0.15, 1.0, 10.0])
        ax.set_yticklabels(["0.15", "1", "10"])
        ax.set_axisbelow(True)
        ax.grid(axis="y", color=GRID, linewidth=0.5)
        ax.spines["left"].set_visible(True)
        ax.set_xlabel("normalised time", fontsize=7.4)
        if col == 0:
            ax.set_ylabel("$\\beta$: labial\ntension (log)", fontsize=7.4)
            ax.text(0.03, BETA_MIN * 0.62, "the clamp floor, $\\beta = 0.15$",
                    fontsize=6.4, color=CLAY, va="bottom")
        bite = lo + hi
        ax.text(0.97, 15.0,
                ("no clamp while audible" if bite < 1e-9 else
                 f"clamped for {bite * 100:.0f} % of the audible span"),
                fontsize=6.4, color=MUTED if bite < 1e-9 else CLAY, ha="right",
                va="top")
    for ax in axes[0]:
        ax.set_xlim(0, 1)

    fig.text(0.0, -0.075,
             "The two gestures the oscillator is driven by, for the same three types "
             "as the acoustic examples, read straight out of the shipped fit through "
             "syrinx.render_plan and the measured $\\beta$ table. This is what "
             "interpretable\n"
             "parameters buys: every sound in the corpus is two named contours "
             "and thirteen searched gesture axes, not a latent code. Pressure and "
             "tension are separate panels because they are separate units. The clamp "
             "annotation is measured\nper type by `syrinx.clamp_incidence`, weighted "
             "by where the envelope is actually open; across the production learn it "
             "bites in 6 617 of 12 724 types.",
             fontsize=6.7, color=MUTED, va="top", linespacing=1.45)
    return save(
        fig, "gestures", width="full",
        shows="the fitted air-sac pressure and labial-tension contours behind the "
              "three acoustic examples, with the measured tension-clamp incidence for "
              "each",
        source="data/learned-inventory.json rendered through "
               "birdy_pipeline.syrinx.render_plan / beta_for / clamp_incidence with "
               "app/static/birdy/syrinx-calibration.json; clamp corpus total from "
               "cli.py report_reachability",
        caption="The fitted gestures behind the three examples. Every syllable in the "
                "corpus is two named physical contours --- air-sac pressure and labial "
                "tension --- rather than a latent code, and this is the whole of the "
                "interpretability claim. The dashed line is the tension clamp of the "
                "parameterisation; a contour that rides it is at a limit of the "
                "parameterisation rather than at a fitted value, which happens in "
                "6\\,617 of 12\\,724 types across the production learn.",
    )


# ================================================================================
# Manifest
# ================================================================================

MANIFEST_HEAD = """# Figure manifest

Generated by `docs/whitepaper/arxiv/figures.py`. Do not edit by hand; edit the
script and re-run:

```
cd pipeline && uv run python ../docs/whitepaper/arxiv/figures.py
```

Every file is vector PDF. Spectrogram meshes are rasterised inside an otherwise
vector figure, so axes and type stay sharp.

## Widths

| name | inches | use |
|---|---|---|
| single | 3.4 | one column |
| full | 7.0 | full width |

**Reconciliation note for `main.tex`.** The manuscript is a one-column `article`
(11 pt, A4, 2.6 cm margins), so `\\linewidth` is 6.22 in and a `full` figure
included at `width=\\linewidth` is scaled to 0.89. Font sizes here have headroom
for that. Two edits are needed on the manuscript side and are deliberately not
made by this script, which does not touch `main.tex`:

1. `\\graphicspath{{../figures/}}` points at the old PNG directory. It should be
   `\\graphicspath{{figures/}}`.
2. `\\includegraphics` names the `.png` extension explicitly. Dropping the
   extension lets LaTeX pick up the PDF.

File base names are unchanged from the old figure set wherever a figure survived,
so the diff is one line per figure.

## Colour semantics

| role | hex | meaning |
|---|---|---|
| violet | `#7a4fa3` | ours, adopted, the project's accent |
| clay | `#bc4b2f` | refuted, failed gate, the worse arm |
| slate | `#5b6070` | baseline or permutation control |
| moss | `#0b7d5f` | external space 1 (Perch 2.0) |
| ochre | `#a8871a` | external space 2 (BirdNET) |

`external-spaces.pdf` is the only figure where hue carries model identity rather
than a verdict; its gate lines carry the verdict instead. The categorical set
violet / moss / ochre / clay passes every all-pairs gate of the house data-viz
validator on a white surface (worst pair CVD dE 7.8, normal-vision dE 15.2, all
four above 3:1 contrast), and every series is also directly labelled.

## Figures

"""


def write_manifest():
    lines = [MANIFEST_HEAD]
    for row in MANIFEST:
        lines.append(f"### `{row['file']}`\n")
        lines.append(f"- **width** {row['width']}"
                     f" ({'3.4 in' if row['width'] == 'single' else '7.0 in'}),"
                     f" {int(row['bytes']) / 1024:.0f} kB\n")
        lines.append(f"- **shows** {row['shows']}\n")
        lines.append(f"- **source** {row['source']}\n")
        lines.append(f"- **caption**\n\n  > {row['caption']}\n")
        lines.append("\n")
    (OUT / "MANIFEST.md").write_text("".join(lines), encoding="utf-8")
    print(f"  MANIFEST.md ({len(MANIFEST)} figures)")


def main():
    print(f"writing to {OUT}")
    fig_architecture()
    fig_signal_chain()
    fig_claim_ladder()
    fig_spaces_bridge()
    fig_corpus()
    fig_ruler()
    fig_confound()
    fig_batch_exchange()
    fig_map_quality()
    fig_tonal_pin()
    fig_orders()
    fig_retrieval_population()
    fig_avex()
    fig_syntax_depth()
    fig_song_funnel()
    fig_external_spaces()

    calibration = Calibration.from_dict(
        json.loads((ROOT / "app" / "static" / "birdy"
                    / "syrinx-calibration.json").read_text())
    )
    fitted, measured = _load_examples()
    fig_spectral_examples(fitted, measured, calibration)
    fig_gestures(fitted, calibration)

    write_manifest()
    print(f"done: {len(MANIFEST)} PDFs")


if __name__ == "__main__":
    main()

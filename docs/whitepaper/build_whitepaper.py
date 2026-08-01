#!/usr/bin/env python3
"""Build the Birdy whitepaper: figures, typeset equations, DOCX.

Run:  cd pipeline && uv run python ../docs/whitepaper/build_whitepaper.py

Every number in the document comes from the repository's research notes
(docs/NN, HANDOFF.md, AGENTS.md). Each figure caption names its source. In-text
superscripts resolve to the numbered literature list; internal notes are cited
inline as "docs/19 §19.2" and are not numbered.

Debug-scale measurements say so in the caption, per the project's evidence
discipline (docs/19 §19.5, docs/17 §17.6). No claim goes beyond what the cited
source states. Comparison cells with no documented answer say "not documented".

Typography: A4, 15 cm measure, Cambria/Calibri (Caladea/Carlito on Linux —
metric clones, so the page is the same on both), automatic hyphenation,
booktabs-style rules instead of Word's grid. Figures are drawn at final size
(5.9 in = 15 cm) so nothing is rescaled.

Deterministic: no randomness anywhere. Every chart is plotted from literals.
"""

import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle
from PIL import Image

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Inches, Pt, RGBColor

HERE = os.path.dirname(os.path.abspath(__file__))
FIG = os.path.join(HERE, "figures")
DOCX_PATH = os.path.join(HERE, "birdy-whitepaper.docx")

# --------------------------------------------------------------------------
# Palette. Violet is the app's own accent (HANDOFF: "ink mode -> violet").
# Clay marks a refuted or failed-gate result, slate a baseline or control.
# The colour therefore carries the verdict, in the charts and in the tables.
# --------------------------------------------------------------------------

INK_HEX = "#241f33"
VIOLET = "#7a4fa3"
VIOLET_PALE = "#e7dff0"
CLAY = "#bc4b2f"
CLAY_PALE = "#f2ded7"
SLATE = "#6e7484"
SLATE_PALE = "#dcdee4"
RULE = "#c7c2cf"

INK = RGBColor(0x24, 0x1F, 0x33)
VIOLET_RGB = RGBColor(0x7A, 0x4F, 0xA3)
CLAY_RGB = RGBColor(0xBC, 0x4B, 0x2F)
GREY_RGB = RGBColor(0x5A, 0x5A, 0x66)
FAINT_RGB = RGBColor(0x8A, 0x86, 0x92)

SERIF = "Cambria"   # -> Caladea on Linux (metric clone)
SANS = "Calibri"    # -> Carlito on Linux (metric clone)

MEASURE_CM = 15.0   # text width; every figure is drawn to exactly this
FIGW = 5.9          # inches, = 15 cm

plt.rcParams.update(
    {
        "font.family": ["Carlito", "DejaVu Sans"],
        "font.size": 8.0,
        "mathtext.fontset": "cm",
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "axes.edgecolor": "#b8b4c0",
        "axes.linewidth": 0.7,
        "axes.grid": False,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "grid.color": "#e9e7ed",
        "grid.linewidth": 0.6,
        "xtick.color": "#5a5a66",
        "ytick.color": "#5a5a66",
        "xtick.major.size": 2.5,
        "ytick.major.size": 2.5,
        "xtick.major.width": 0.7,
        "ytick.major.width": 0.7,
        "text.color": INK_HEX,
        "axes.labelcolor": INK_HEX,
        "axes.titlecolor": INK_HEX,
        "axes.titlesize": 8.5,
        "axes.titleweight": "bold",
        "axes.titlelocation": "left",
        "axes.titlepad": 6.0,
        "legend.frameon": False,
        "legend.fontsize": 7.5,
        "figure.dpi": 300,
        "savefig.dpi": 300,
    }
)


# --------------------------------------------------------------------------
# Equations (matplotlib mathtext -> transparent PNG, 400 dpi)
# --------------------------------------------------------------------------

EQUATIONS = {
    # The syrinx oscillator, published normal form term for term — docs/08
    # §8.1, docs/21 §21.1 (Amador & Mindlin 2021 / Laje & Mindlin 2002 form).
    "syrinx": (
        r"\dot{x} = y, \qquad "
        r"\dot{y} = -\alpha\, g^{2} - \beta\, g^{2} x - g^{2} x^{3}"
        r" - g\, x^{2} y + g^{2} x^{2} - g\, x y"
    ),
    # gamma is a pure time-scale — docs/08 §8.1 (measured PHI).
    "gamma": r"f_{0} = g \cdot \Phi(\alpha, \beta), \qquad \Phi(0.1,\,1) = 0.17061",
    # Tracheal stopped-tube comb — docs/08 §8.1a.
    "comb": (
        r"f_{n} = (2n-1)\, f_{1}, \quad n = 1 \ldots 4,"
        r" \qquad f_{1} = \frac{c}{4L}"
    ),
    # Respiratory oscillator — docs/15 §1 (Fainstein, Goller & Mindlin 2025).
    "respiration": (
        r"\tau_{x}\, \dot{x} = -(1 + x^{2})\,x - p + F_{0}\, f(t), \qquad "
        r"\tau_{p}\, \dot{p} = -(1 + x^{2})\,x - \left(1 + \alpha(p)\right) p"
        r" + F_{0}\, f(t)"
    ),
    # NT-Xent — docs/09 §9.2b; temperature 0.2 in critic.py.
    "ntxent": (
        r"\ell_{i} = -\log \frac{\exp\left(\mathrm{sim}(z_i, z_i^{+}) / \tau\right)}"
        r"{\sum_{k \neq i} \exp\left(\mathrm{sim}(z_i, z_k) / \tau\right)},"
        r" \qquad \tau = 0.2"
    ),
    # RFF ridge bridge — spacemap.py, docs/11 §11.3.
    "rff": (
        r"\varphi(x) = \sqrt{\frac{2}{D}}\, \cos\left( x R + b \right),"
        r" \quad R \sim \mathcal{N}(0, \sigma^{-2} I),"
        r" \qquad \hat{z} = \varphi(x)\, W + c"
    ),
    # The fit objective — docs/08 §8.2, docs/19.
    "cosine": (
        r"\mathrm{score} = \cos\left( z_{\mathrm{syn}},\, z_{\mathrm{ref}} \right)"
        r" = \frac{z_{\mathrm{syn}} \cdot z_{\mathrm{ref}}"
        r"}{\left\| z_{\mathrm{syn}} \right\| \, \left\| z_{\mathrm{ref}} \right\|}"
    ),
    # kNN lift against a permutation null — geometry.py.
    "knnlift": r"\mathrm{lift}(G) = A(G) - \mathbb{E}_{\pi}\left[ A(\pi G) \right]",
}


def render_equations() -> dict:
    paths = {}
    eq_dir = os.path.join(FIG, "eq")
    os.makedirs(eq_dir, exist_ok=True)
    for name, tex in EQUATIONS.items():
        path = os.path.join(eq_dir, f"{name}.png")
        fig = plt.figure(figsize=(0.1, 0.1))
        fig.text(0, 0, f"${tex}$", fontsize=13, color=INK_HEX)
        fig.savefig(path, dpi=400, transparent=True, bbox_inches="tight",
                    pad_inches=0.03)
        plt.close(fig)
        paths[name] = path
    return paths


# --------------------------------------------------------------------------
# Figure helpers
# --------------------------------------------------------------------------


def _save(fig, name) -> str:
    path = os.path.join(FIG, name)
    fig.savefig(path, bbox_inches="tight", facecolor="white", pad_inches=0.02)
    plt.close(fig)
    return path


def _yrule(ax, values=None):
    """Faint horizontal reference lines only, behind the marks."""
    ax.set_axisbelow(True)
    ax.grid(axis="y", color="#eceaf0", linewidth=0.6)
    ax.spines["left"].set_visible(False)
    if values is not None:
        ax.set_yticks(values)


def _box(ax, x, y, w, h, text, fc="white", ec=VIOLET, fs=7.0, dashed=False,
         tc=INK_HEX, lw=0.9):
    ax.add_patch(
        FancyBboxPatch(
            (x, y), w, h,
            boxstyle="round,pad=0.05,rounding_size=0.10",
            linewidth=lw, edgecolor=ec, facecolor=fc,
            linestyle=(0, (3.5, 2.5)) if dashed else "-",
        )
    )
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center",
            fontsize=fs, color=tc, linespacing=1.35)


def _arrow(ax, x1, y1, x2, y2, dashed=False, both=False, color=None):
    ax.add_patch(
        FancyArrowPatch(
            (x1, y1), (x2, y2),
            arrowstyle="<|-|>" if both else "-|>",
            mutation_scale=9, linewidth=0.9,
            color=color or ("#a9a5b1" if dashed else "#75717d"),
            linestyle=(0, (3.5, 2.5)) if dashed else "-",
        )
    )


def _blank(ax, xlim, ylim):
    ax.set_xlim(*xlim)
    ax.set_ylim(*ylim)
    ax.axis("off")
    ax.grid(False)


# --------------------------------------------------------------------------
# Figure 1 — the claim ladder (the honesty rule as a picture)
# --------------------------------------------------------------------------


def fig_claim_ladder() -> str:
    """docs/08 §8.5, with the counts that populate each level."""
    rows = [
        ("experimental", VIOLET, "a bird was played this sound and responded",
         "great tit ABC–D; 256 sparrow playback tests"),
        ("documented", "#9470b8", "the function is in the peer-reviewed literature",
         "chickadee D-count, Siberian jay, nightingale order"),
        ("inferred", "#a884c6", "measured in the corpus, function not established",
         "48 species carry detected song types, heard ≥ 2×"),
        ("invented", "#b79bd0", "a designed mapping, always named as designed",
         "hand-set jitter, only where no measurement exists"),
        ("unlabelled", SLATE, "real acoustics, no documented function",
         "23 697 novel syllables, 841 honestly unlabelable"),
    ]
    fig, ax = plt.subplots(figsize=(FIGW, 2.62))
    _blank(ax, (0, 100), (-0.4, len(rows) + 0.5))
    ax.text(0, len(rows) + 0.12, "stronger evidence", fontsize=7.0,
            color=SLATE, style="italic")
    ax.annotate("", xy=(0.9, -0.28), xytext=(0.9, len(rows) - 0.05),
                arrowprops=dict(arrowstyle="-|>", color="#c3bfcb", lw=0.9))
    for i, (name, colour, requires, example) in enumerate(rows):
        y = len(rows) - 1 - i
        ax.add_patch(Rectangle((4, y - 0.02), 20.5, 0.62, facecolor=colour,
                               edgecolor="none"))
        ax.text(5.4, y + 0.29, name, fontsize=8.2, color="white",
                fontweight="bold", va="center")
        ax.text(26.5, y + 0.40, requires, fontsize=7.6, color=INK_HEX, va="center")
        ax.text(26.5, y + 0.13, example, fontsize=6.9, color=SLATE, va="center")
    ax.text(4, -0.42,
            "Every phrase the app speaks carries one of these five labels. "
            "Nothing renders without one.",
            fontsize=6.9, color=SLATE)
    return _save(fig, "claim-ladder.png")


# --------------------------------------------------------------------------
# Figure 2 — the synthesis signal chain
# --------------------------------------------------------------------------


def fig_signal_chain() -> str:
    """docs/08 §8.1/§8.1a, docs/15 §1/§5, docs/16 §16.7."""
    fig, ax = plt.subplots(figsize=(FIGW, 3.15))
    _blank(ax, (0, 100), (0, 50))

    y, h, w = 20.0, 13.0, 17.5
    xs = [20.0, 38.0, 56.0, 74.0]

    _box(ax, 0.5, y + 7.5, 17.5, 6.5,
         "$\\alpha(t)$  air-sac pressure\n≈ loudness", ec=SLATE, fs=6.4)
    _box(ax, 0.5, y - 1.0, 17.5, 6.5,
         "$\\beta(t)$  labial tension\n≈ pitch", ec=SLATE, fs=6.4)
    ax.text(9.25, y - 3.0, "+ 140 Hz noise on $\\beta$", fontsize=6.2,
            color=SLATE, ha="center")

    _box(ax, xs[0], y, w, h,
         "syrinx oscillator\neq. 1\nHopf / SNIC\n$\\gamma$ per syllable", fs=6.2)
    _box(ax, xs[1], y, w, h,
         "turbulence\nat the labia\n$\\propto$ air flow", fs=6.2)
    _box(ax, xs[2], y, w, h,
         "$f_0$-tracking\nresonance\ntract retuning", fs=6.2)
    _box(ax, xs[3], y, w, h,
         "tracheal comb\neq. 3\nstopped tube\n$f_1$ per species", fs=6.2)

    _arrow(ax, 18.2, y + 10.5, 20.6, y + 8.5)
    _arrow(ax, 18.2, y + 2.5, 20.6, y + 4.5)
    for i in range(3):
        _arrow(ax, xs[i] + w + 0.3, y + h / 2, xs[i + 1] - 0.4, y + h / 2)
    _arrow(ax, xs[3] + w + 0.3, y + h / 2, 95.0, y + h / 2)
    ax.text(95.8, y + h / 2, "sound", fontsize=7.2, ha="left", va="center",
            color=INK_HEX)

    # the fricative branch is the one extension that ships
    _box(ax, 38.0, 39.0, 38.0, 8.0,
         "fricative route — noise into the fitted formants\n"
         "ships per type  ·  bench 0.584 → 0.656  ·  13 wins / 0 losses",
         ec=VIOLET, fc=VIOLET_PALE, fs=6.2)
    _arrow(ax, 48.5, 38.8, 48.5, 33.4, color=VIOLET)

    # parked extensions carry their own refutation
    _box(ax, 0.5, 3.5, 46.0, 8.5,
         "respiration, eq. 4 — replaces the envelope\n"
         "hand-set default 0.343 → 0.336  ·  the fit won 445 types",
         dashed=True, ec=SLATE, fs=6.1, tc=SLATE)
    _box(ax, 51.5, 3.5, 46.0, 8.5,
         "second voice — coupled via tracheal pressure\n"
         "hand-set default 0.343 → 0.294  ·  the fit won 2 027 of 5 922",
         dashed=True, ec=SLATE, fs=6.1, tc=SLATE)
    _arrow(ax, 24.0, 12.2, 27.0, 19.6, dashed=True)
    _arrow(ax, 68.0, 12.2, 62.0, 19.6, dashed=True)
    ax.text(0.5, 0.4,
            "Dashed: implemented and parity-tested, off by default — the physics "
            "is published, and the hand-set defaults lost their bake-offs.",
            fontsize=6.2, color=SLATE)
    return _save(fig, "signal-chain.png")


# --------------------------------------------------------------------------
# Figure 3 — the tonal-regime pin
# --------------------------------------------------------------------------


def fig_tonal_pin() -> str:
    """docs/08 §8.1a as read by docs/21 §21.2: the fit parks at the tonal end."""
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(FIGW, 2.25),
                                 gridspec_kw={"width_ratios": [1.55, 1]})

    labels = ["SCI > 1.5", "SCI > 3"]
    ours = [1.4, 0.0]
    real = [15.6, 5.3]
    x = [0, 1]
    bw = 0.33
    a1.bar([i - bw / 2 for i in x], ours, bw, color=CLAY, label="resynthesis")
    a1.bar([i + bw / 2 for i in x], real, bw, color=VIOLET, label="real syllables")
    for i, (o, r) in enumerate(zip(ours, real)):
        a1.text(i - bw / 2, o + 0.4, f"{o:.1f} %", ha="center", fontsize=7.2,
                color=CLAY)
        a1.text(i + bw / 2, r + 0.4, f"{r:.1f} %", ha="center", fontsize=7.2,
                color=VIOLET)
    a1.set_xticks(x)
    a1.set_xticklabels(labels)
    a1.set_ylim(0, 21)
    a1.set_ylabel("share of syllables")
    a1.set_title("the spectrally rich tail is missing", loc="left")
    a1.legend(loc="upper right")
    _yrule(a1, [0, 5, 10, 15])

    a2.bar([0], [0.0005], 0.42, color=CLAY)
    a2.bar([1], [0.044], 0.42, color=VIOLET)
    a2.set_yscale("log")
    a2.set_ylim(1e-4, 3e-1)
    a2.set_xlim(-0.6, 1.6)
    a2.set_xticks([0, 1])
    a2.set_xticklabels(["resynthesis", "real"])
    a2.text(0, 0.0008, "0.0005", ha="center", fontsize=7.2, color=CLAY)
    a2.text(1, 0.068, "0.044", ha="center", fontsize=7.2, color=VIOLET)
    a2.set_ylabel("median spectral flatness")
    a2.set_title("three orders too pure", loc="left")
    a2.grid(axis="y", color="#eceaf0", linewidth=0.6)
    a2.set_axisbelow(True)
    a2.spines["left"].set_visible(False)

    fig.tight_layout(w_pad=2.4)
    return _save(fig, "tonal-pin.png")


# --------------------------------------------------------------------------
# Figure 4 — the corpus: breadth, then depth
# --------------------------------------------------------------------------


def fig_corpus() -> str:
    """docs/08 §8.1a, docs/09 §9.7-9.8, docs/14 §14.1, docs/16 §16.1,
    HANDOFF 2026-07-31 (P0)."""
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(FIGW, 2.35),
                                 gridspec_kw={"width_ratios": [1.5, 1]})

    stores = [
        ("original 22-species", 39976, 22),
        ("harvest-gan at 40 k", 39993, 13),
        ("+ xccoverbl", 39874, 121),
        ("+ iNatSounds 2024", 226264, 3811),
        ("+ P0 depth harvest", 340079, 3811),
    ]
    y = list(range(len(stores)))[::-1]
    a1.barh(y, [s[1] for s in stores], color=[SLATE_PALE] * 3 + [VIOLET_PALE, VIOLET],
            height=0.58, edgecolor="none")
    for yi, s in zip(y, stores):
        a1.text(s[1] * 1.12, yi, f"{s[1]:,}".replace(",", " "),
                va="center", fontsize=7.2, color=INK_HEX)
        a1.text(-0.02, yi, f"{s[2]:,}".replace(",", " ") + " sp.",
                va="center", ha="right", fontsize=6.6, color=SLATE,
                transform=a1.get_yaxis_transform())
    a1.set_xscale("log")
    a1.set_xlim(2.5e4, 1.3e6)
    a1.set_yticks(y)
    a1.set_yticklabels([s[0] for s in stores], fontsize=7.4)
    a1.set_xlabel("measured syllables (log scale)")
    a1.set_title("breadth", loc="left")
    a1.tick_params(axis="x", labelsize=7)
    a1.spines["left"].set_visible(False)
    a1.tick_params(axis="y", length=0)

    a2.barh([0], [71], color=VIOLET, height=0.44, edgecolor="none")
    a2.barh([0], [29], left=[71], color=SLATE_PALE, height=0.44, edgecolor="none")
    a2.text(35.5, 0, "71", ha="center", va="center", color="white",
            fontsize=9.5, fontweight="bold")
    a2.text(85.5, 0, "29", ha="center", va="center", color=SLATE, fontsize=8.5)
    a2.set_xlim(0, 100)
    a2.set_ylim(-0.75, 0.55)
    a2.set_yticks([])
    a2.set_xticks([0, 50, 100])
    a2.tick_params(axis="x", labelsize=7)
    a2.set_xlabel("species of the target 100")
    a2.set_title("depth, after P0", loc="left")
    a2.text(0, -0.46, "≥ 20 recordings each · median 29 · p10 = 5",
            fontsize=6.9, color=SLATE)
    a2.text(0, -0.66,
            "the 29 are what xeno-canto has, not what the harvest missed",
            fontsize=6.5, color=SLATE)
    a2.spines["left"].set_visible(False)

    fig.tight_layout(w_pad=2.0)
    return _save(fig, "corpus.png")


# --------------------------------------------------------------------------
# Figure 5 — the pipeline
# --------------------------------------------------------------------------


def fig_architecture() -> str:
    """docs/06 §6.1, docs/08 §8.3."""
    fig, ax = plt.subplots(figsize=(FIGW, 2.55))
    _blank(ax, (0, 100), (0, 40))

    ax.add_patch(FancyBboxPatch((0.6, 8.5), 76.0, 28.0,
                                boxstyle="round,pad=0.4,rounding_size=0.8",
                                linewidth=0.8, edgecolor="#d5d1db",
                                facecolor="#fbfafc"))
    ax.text(1.8, 34.2, "offline pipeline (Python) — no audio retained",
            fontsize=7.2, color=SLATE)
    ax.add_patch(FancyBboxPatch((78.6, 8.5), 20.8, 28.0,
                                boxstyle="round,pad=0.4,rounding_size=0.8",
                                linewidth=0.8, edgecolor="#d5d1db",
                                facecolor="#fbfafc"))
    ax.text(79.8, 34.2, "browser — no torch", fontsize=7.2, color=SLATE)

    y, h, w = 17.0, 12.0, 17.0
    xs = [2.0, 21.0, 40.0, 59.0, 80.0]
    specs = [
        ("harvest", "xeno-canto · iNat\ndecode → describe\n→ delete", "white", SLATE),
        ("store", "28-d descriptors\n+ 32×23 patches\naudio deleted", "white", SLATE),
        ("learn", "types in the 32-d\nembedding, then\ngesture inversion", "white", VIOLET),
        ("build", "galaxy assets\nJSON / f32\nno weights", VIOLET_PALE, VIOLET),
        ("app", "3-D galaxy\nsynth · mic\nsession gate", VIOLET_PALE, VIOLET),
    ]
    for i, (x, (name, body, fc, ec)) in enumerate(zip(xs, specs)):
        _box(ax, x, y, w, h, "", fc=fc, ec=ec)
        ax.text(x + w / 2, y + h - 2.6, name, ha="center", fontsize=8.0,
                fontweight="bold", color=INK_HEX)
        ax.text(x + w / 2, y + 4.0, body, ha="center", va="center",
                fontsize=6.6, color=INK_HEX, linespacing=1.4)
        ax.add_patch(plt.Circle((x + 1.9, y + h + 1.2), 1.55, facecolor=ec,
                                edgecolor="none"))
        ax.text(x + 1.9, y + h + 1.2, str(i + 1), ha="center", va="center",
                fontsize=6.8, color="white", fontweight="bold")
    for i in range(4):
        _arrow(ax, xs[i] + w + 0.3, y + h / 2, xs[i + 1] - 0.4, y + h / 2)

    _box(ax, 40.0, 9.6, 17.0, 5.6,
         "critic — 3 heads\nrealism · species · NT-Xent", fs=6.4)
    _arrow(ax, 48.5, 15.4, 48.5, 16.8, both=True)

    ax.add_patch(FancyBboxPatch((0.6, 1.6), 98.8, 5.0,
                                boxstyle="round,pad=0.3,rounding_size=0.6",
                                linewidth=0.8, edgecolor=RULE, facecolor="#f6f4f8"))
    ax.text(50.0, 4.1,
            "the claim ladder sits over everything station 5 shows:  experimental "
            "· documented · inferred · invented · unlabelled",
            ha="center", va="center", fontsize=6.8, color=INK_HEX)
    return _save(fig, "architecture.png")


# --------------------------------------------------------------------------
# Figure 6 — two feature spaces and the bridge
# --------------------------------------------------------------------------


def fig_spaces() -> str:
    """docs/08 §8.2, docs/11 §11.3, docs/20 §20.1."""
    fig, ax = plt.subplots(figsize=(FIGW, 2.05))
    _blank(ax, (0, 100), (0, 34))

    _box(ax, 0.8, 12.0, 34.0, 19.0, "", ec=SLATE)
    ax.text(17.8, 27.6, "28-d descriptor", ha="center", fontsize=8.0,
            fontweight="bold", color=INK_HEX)
    ax.text(17.8, 18.6,
            "13 MFCC means · 13 MFCC stds\nlog₂ spectral centroid · flatness\n\n"
            "computed sample-for-sample\nalike in Python and the browser",
            ha="center", va="center", fontsize=6.7, color=INK_HEX, linespacing=1.45)

    _box(ax, 65.2, 12.0, 34.0, 19.0, "", ec=VIOLET, fc=VIOLET_PALE)
    ax.text(82.2, 27.6, "32-d embedding", ha="center", fontsize=8.0,
            fontweight="bold", color=INK_HEX)
    ax.text(82.2, 18.6,
            "critic trunk, NT-Xent-trained\n\nthe galaxy's coordinate system\n"
            "clusters, novelty, relations",
            ha="center", va="center", fontsize=6.7, color=INK_HEX, linespacing=1.45)

    _arrow(ax, 35.6, 21.5, 64.4, 21.5, color=VIOLET)
    ax.text(50.0, 25.4, "RFF ridge, eq. 6", ha="center", fontsize=7.4,
            fontweight="bold", color=INK_HEX)
    ax.text(50.0, 22.6, "D = 2048 · σ = 4 · λ = 1", ha="center",
            fontsize=6.8, color=SLATE)
    ax.text(50.0, 16.6, "ships as plain numbers,\nno torch in the browser",
            ha="center", va="center", fontsize=6.6, color=SLATE, linespacing=1.4)

    ax.text(0.8, 7.4,
            "Ship gate: median held-out cosine ≥ 0.8. The debug build passes at "
            "0.962; the linear ridge it replaced broke at 0.7997.",
            fontsize=6.8, color=INK_HEX)
    ax.text(0.8, 3.6,
            "Knot-level agreement 0.61 raw · 0.91 tie-adjusted · 0.78 at species "
            "level — decomposed in figure 9.",
            fontsize=6.8, color=SLATE)
    return _save(fig, "spaces-bridge.png")


# --------------------------------------------------------------------------
# Figure 7 — the ruler problem
# --------------------------------------------------------------------------


def fig_ruler() -> str:
    """docs/19 §19.2/§19.4/§19.5."""
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(FIGW, 2.3),
                                 gridspec_kw={"width_ratios": [1.25, 1]})

    names = ["cosine\nvs MCD", "cosine\nvs STFT", "melTarget\nvs MCD"]
    pear = [0.106, 0.102, -0.305]
    spear = [0.100, 0.111, -0.420]
    x = [0, 1, 2]
    bw = 0.32
    cols = [CLAY, CLAY, VIOLET]
    a1.bar([i - bw / 2 for i in x], pear, bw, color=cols, alpha=0.55,
           edgecolor="none")
    a1.bar([i + bw / 2 for i in x], spear, bw, color=cols, edgecolor="none")
    a1.axhline(0, color="#5a5a66", linewidth=0.8)
    for lvl, sign in ((0.4, 1), (-0.4, -1)):
        a1.axhline(lvl, color=SLATE, linewidth=0.8, linestyle=(0, (3, 2.5)))
    a1.text(2.58, 0.44, "|r| = 0.4", fontsize=6.6, color=SLATE, ha="right")
    for i, (p, s) in enumerate(zip(pear, spear)):
        a1.text(i - bw / 2, p + (0.035 if p >= 0 else -0.075), f"{p:+.3f}",
                ha="center", fontsize=6.7, color=SLATE)
        a1.text(i + bw / 2, s + (0.035 if s >= 0 else -0.075), f"{s:+.3f}",
                ha="center", fontsize=6.9, color=INK_HEX, fontweight="bold")
    a1.set_xticks(x)
    a1.set_xticklabels(names, fontsize=7.0)
    a1.set_ylim(-0.72, 0.60)
    a1.set_ylabel("correlation with audible distortion")
    a1.set_title("the objective cannot hear", loc="left")
    a1.text(-0.42, -0.68, "pale = Pearson · solid = Spearman", fontsize=6.4,
            color=SLATE)
    _yrule(a1, [-0.4, -0.2, 0, 0.2, 0.4])

    a2.bar([0], [70], 0.42, color=SLATE_PALE, edgecolor="none")
    a2.bar([1], [31], 0.42, color=CLAY, edgecolor="none")
    a2.axhline(60, color=SLATE, linewidth=0.9, linestyle=(0, (3, 2.5)))
    a2.text(1.62, 61.5, "gate 60 %", fontsize=6.6, color=SLATE, ha="right")
    a2.text(0, 72, "70 %", ha="center", fontsize=7.4, color=SLATE)
    a2.text(1, 33, "31 %", ha="center", fontsize=7.4, color=CLAY,
            fontweight="bold")
    a2.set_xticks([0, 1])
    a2.set_xticklabels(["probe\nn = 10", "gate run\nn = 80"], fontsize=7.0)
    a2.set_xlim(-0.6, 1.7)
    a2.set_ylim(0, 88)
    a2.set_ylabel("share of types the mel target wins")
    a2.set_title("and the promising fix was small-sample", loc="left")
    _yrule(a2, [0, 20, 40, 60, 80])

    fig.tight_layout(w_pad=2.2)
    return _save(fig, "ruler.png")


# --------------------------------------------------------------------------
# Figure 8 — the map's agreement, and the sessions that break it
# --------------------------------------------------------------------------


def fig_map_quality() -> str:
    """docs/20 §20.1 and §20.3.2."""
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(FIGW, 2.55),
                                 gridspec_kw={"height_ratios": [1, 1.25]})

    segs = [
        ("boundary near-ties, true-space margin < 0.05", 76.4, VIOLET_PALE),
        ("mid-margin 0.05–0.1, mostly bad sessions", 18.5, SLATE_PALE),
        ("genuine map failure, unseen recordist", 2.6, CLAY),
        ("seen recordist, map cosine < 0.90", 1.7, "#d98a72"),
        ("residual", 0.8, "#eceaf0"),
    ]
    left = 0.0
    for name, share, colour in segs:
        a1.barh([0], [share], left=[left], height=0.5, color=colour,
                edgecolor="white", linewidth=0.8)
        if share > 6:
            a1.text(left + share / 2, 0, f"{share:.1f} %", ha="center",
                    va="center", fontsize=7.4,
                    color=INK_HEX if colour == VIOLET_PALE else SLATE)
        left += share
    a1.set_xlim(0, 100)
    a1.set_ylim(-1.05, 0.85)
    a1.set_yticks([])
    a1.set_xticks([])
    for s in a1.spines.values():
        s.set_visible(False)
    a1.set_title("what the 38.6 % knot-disagreement is made of", loc="left")
    a1.annotate("genuine map failure: 4.3 %", xy=(97.5, 0.27),
                xytext=(76.0, 0.62), fontsize=6.9, color=CLAY, ha="center",
                arrowprops=dict(arrowstyle="-", color=CLAY, lw=0.7))
    a1.text(0, -0.55,
            "tie-adjusted agreement 0.91  ·  species-level 0.78  ·  "
            "1 439 flips over 3 731 held-out syllables",
            fontsize=6.8, color=SLATE)

    labels = ["off-manifold\n5-NN distance", "mapped-norm\ndeviation",
              "the two combined"]
    aucs = [0.953, 0.922, 0.954]
    cols = [VIOLET, SLATE_PALE, SLATE_PALE]
    a2.bar(range(3), aucs, 0.45, color=cols, edgecolor="none")
    a2.axhline(0.9, color=SLATE, linewidth=0.9, linestyle=(0, (3, 2.5)))
    a2.text(-0.55, 0.903, "gate 0.90", fontsize=6.6, color=SLATE, ha="left")
    for i, v in enumerate(aucs):
        a2.text(i, v + 0.004, f"{v:.3f}", ha="center", fontsize=7.2,
                color=INK_HEX, fontweight="bold" if i == 0 else "normal")
    a2.set_xticks(range(3))
    a2.set_xticklabels(labels, fontsize=7.0)
    a2.set_xlim(-0.6, 2.7)
    a2.set_ylim(0.86, 0.985)
    a2.set_ylabel("AUC vs the bad-session label")
    a2.set_title("8 of 45 held-out sessions carry 22.9 % of that loss — and separate cleanly",
                 loc="left")
    _yrule(a2, [0.88, 0.92, 0.96])

    fig.tight_layout(h_pad=2.0)
    return _save(fig, "map-quality.png")


# --------------------------------------------------------------------------
# Figure 9 — the recorder confound and the loss road
# --------------------------------------------------------------------------


def fig_confound() -> str:
    """docs/14 §14.4, docs/17 §17.2/§17.3/§17.5."""
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(FIGW, 2.45),
                                 gridspec_kw={"width_ratios": [1, 1.45]})

    a1.bar([0], [0.488], 0.44, color=CLAY, edgecolor="none")
    a1.bar([1], [0.196], 0.44, color=VIOLET, edgecolor="none")
    a1.text(0, 0.502, "+0.488", ha="center", fontsize=7.6, color=CLAY,
            fontweight="bold")
    a1.text(1, 0.210, "+0.196", ha="center", fontsize=7.6, color=VIOLET)
    a1.set_xticks([0, 1])
    a1.set_xticklabels(["which\nrecordist", "which\nspecies"], fontsize=7.2)
    a1.set_xlim(-0.6, 1.6)
    a1.set_ylim(0, 0.58)
    a1.set_ylabel("kNN lift over a permutation null")
    a1.set_title("the problem", loc="left")
    _yrule(a1, [0, 0.2, 0.4])

    # every swept point: relative change in recordist lift vs species lift
    rec_head = [(-0.7, 3.0, "aug only"), (-14.7, -7.0, "w 0.1"),
                (-33.0, -28.9, "w 0.05"), (-61.4, -59.9, "w 0.3")]
    sp_head = [(1.1, 6.3, ""), (-1.4, 11.2, ""), (-3.2, 10.0, ""),
               (-6.1, 10.4, "w 0.1")]

    a2.add_patch(Rectangle((-70, -10), 40, 30, facecolor=VIOLET_PALE,
                           edgecolor=VIOLET, linewidth=0.8,
                           linestyle=(0, (3, 2.5)), zorder=0))
    a2.text(-50, 15.0, "what the gates asked for", fontsize=6.7, color=VIOLET,
            ha="center", style="italic")
    a2.text(-50, 11.0, "(empty)", fontsize=6.7, color=VIOLET, ha="center")
    a2.plot([-70, 20], [-70, 20], color=SLATE, linewidth=0.7,
            linestyle=(0, (2, 2)), zorder=1)
    a2.text(-33, -41, "one for one", fontsize=6.5, color=SLATE, rotation=41)
    a2.axhline(0, color="#c3bfcb", linewidth=0.7, zorder=1)
    a2.axvline(0, color="#c3bfcb", linewidth=0.7, zorder=1)

    a2.plot([p[0] for p in rec_head], [p[1] for p in rec_head], "o-",
            color=CLAY, markersize=4.2, linewidth=1.0, zorder=3,
            label="recordist-adversarial head")
    a2.plot([p[0] for p in sp_head], [p[1] for p in sp_head], "s-",
            color=VIOLET, markersize=4.0, linewidth=1.0, zorder=3,
            label="within-species head")
    for xx, yy, lbl in rec_head:
        if lbl:
            a2.annotate(lbl, (xx, yy), textcoords="offset points",
                        xytext=(6, -9) if lbl != "aug only" else (-4, -11),
                        fontsize=6.3, color=CLAY,
                        ha="left" if lbl != "aug only" else "right")
    a2.set_xlim(-72, 22)
    a2.set_ylim(-72, 22)
    a2.set_xlabel("change in recordist lift (%)")
    a2.set_ylabel("change in species lift (%)")
    a2.set_title("every loss that reaches the recorder takes the bird with it",
                 loc="left")
    a2.legend(loc="lower right", fontsize=6.7)
    a2.set_axisbelow(True)
    a2.grid(color="#f1eff3", linewidth=0.6)

    fig.tight_layout(w_pad=2.2)
    return _save(fig, "confound.png")


# --------------------------------------------------------------------------
# Figure 10 — the data road, and its honest shrink
# --------------------------------------------------------------------------


def fig_avex() -> str:
    """docs/17 §17.4 (12 species) and §17.6 (63 species)."""
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(FIGW, 2.15), sharey=False)
    arms = ["A\nsingle\ndomain", "B\nnaive\nmerge", "C\ncross-domain\npositives"]
    for ax, vals, chance, title, ymax in (
        (a1, [0.360, 0.504, 0.638], 0.083, "first test — 12 species, 3 held out", 0.76),
        (a2, [0.058, 0.093, 0.110], 0.016, "pre-registered re-test — 63 species, 16 held out", 0.142),
    ):
        ax.bar(range(3), vals, 0.5, color=[SLATE_PALE, VIOLET, VIOLET_PALE],
               edgecolor="none")
        ax.axhline(chance, color=SLATE, linewidth=0.8, linestyle=(0, (3, 2.5)))
        ax.text(2.72, chance + ymax * 0.02, f"chance {chance:.3f}", fontsize=6.5,
                color=SLATE, ha="right")
        for i, v in enumerate(vals):
            ax.text(i, v + ymax * 0.022, f"{v:.3f}", ha="center", fontsize=7.2,
                    color=INK_HEX)
        ax.set_xticks(range(3))
        ax.set_xticklabels(arms, fontsize=6.9)
        ax.set_xlim(-0.6, 2.8)
        ax.set_ylim(0, ymax)
        ax.set_title(title, loc="left", fontsize=7.8)
        _yrule(ax)
    a1.set_ylabel("cross-domain species retrieval")
    a1.text(-0.55, 0.700, "B over A:  +14.4 pts", fontsize=7.0, color=VIOLET,
            fontweight="bold")
    a2.text(-0.55, 0.1305, "B over A:  +3.6 pts", fontsize=7.0, color=VIOLET,
            fontweight="bold")
    a2.text(-0.55, 0.1215, "C over B:  +1.7 pts, against a +10 gate",
            fontsize=7.0, color=CLAY)
    fig.tight_layout(w_pad=2.2)
    return _save(fig, "avex.png")


# --------------------------------------------------------------------------
# Figure 11 — why syntax starves
# --------------------------------------------------------------------------


def fig_syntax() -> str:
    """docs/18 P1 and P2, plus the debug-100 bout count."""
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(FIGW, 2.3),
                                 gridspec_kw={"width_ratios": [1.4, 1]})

    groups = ["seen transitions\n(90 % of held-out)", "unseen tail\n(10 %)"]
    first = [-1.525, -9.25]
    hmm = [-1.624, -4.16]
    x = [0, 1]
    bw = 0.3
    a1.bar([i - bw / 2 for i in x], first, bw, color=VIOLET, edgecolor="none",
           label="first-order (shipped)")
    a1.bar([i + bw / 2 for i in x], hmm, bw, color=SLATE_PALE, edgecolor="none",
           label="hidden-state HMM")
    a1.axhline(0, color="#5a5a66", linewidth=0.8)
    for i, (f, h) in enumerate(zip(first, hmm)):
        a1.text(i - bw / 2, f - 0.55, f"{f:.2f}", ha="center", fontsize=6.9,
                color=VIOLET, fontweight="bold")
        a1.text(i + bw / 2, h - 0.55, f"{h:.2f}", ha="center", fontsize=6.9,
                color=SLATE)
    a1.set_xticks(x)
    a1.set_xticklabels(groups, fontsize=7.0)
    a1.set_ylim(-11.2, 1.2)
    a1.set_ylabel("held-out log-likelihood (nats/token)")
    a1.set_title("the heavier model wins only where the data runs out", loc="left")
    a1.legend(loc="lower left", fontsize=6.7)
    _yrule(a1, [-10, -8, -6, -4, -2, 0])

    a2.barh([0], [12], color=VIOLET, height=0.42, edgecolor="none")
    a2.barh([0], [88], left=[12], color=SLATE_PALE, height=0.42, edgecolor="none")
    a2.text(6, 0, "12", ha="center", va="center", color="white", fontsize=8.5,
            fontweight="bold")
    a2.text(56, 0, "88", ha="center", va="center", color=SLATE, fontsize=8.5)
    a2.set_xlim(0, 100)
    a2.set_ylim(-0.8, 0.5)
    a2.set_yticks([])
    a2.set_xticks([0, 50, 100])
    a2.tick_params(axis="x", labelsize=7)
    a2.set_xlabel("species of the debug-100 store")
    a2.set_title("and 12 species have the bouts to try", loc="left")
    a2.text(0, -0.50, "≥ 20 bouts after run-collapse — the syntax threshold",
            fontsize=6.8, color=SLATE)
    a2.text(0, -0.70, "counted before the P0 depth harvest; the re-count is owed",
            fontsize=6.5, color=SLATE)
    a2.spines["left"].set_visible(False)

    fig.tight_layout(w_pad=2.2)
    return _save(fig, "syntax-depth.png")


# --------------------------------------------------------------------------
# References — external literature only. Internal notes are cited inline
# as "docs/19 §19.2", because that is how they are addressed in the repo.
# --------------------------------------------------------------------------

REFERENCES = [
    ("rutz", "Rutz, C. et al. “Using machine learning to decode animal "
     "communication”. Science, 2023. DOI 10.1126/science.adg7314."),
    ("suzuki", "Suzuki, T. N., Wheatcroft, D. & Griesser, M. “Experimental "
     "evidence for compositional syntax in bird calls”. Nature Communications, "
     "2016 — the great tit ABC–D construction."),
    ("griesser", "Griesser, M. “Referential calls signal predator behavior in a "
     "group-living bird species”. Current Biology, 2008 — Siberian jay."),
    ("freeberg", "Freeberg, T. M. et al., 2003 — black-capped chickadee "
     "chick-a-dee call: four note types, strict A→B→C→D order, D-count "
     "scaling with threat."),
    ("hultsch", "Hultsch, H. & Todt, D. — nightingale song-type organisation: "
     "180–200 types per male, package organisation, countersinging rules."),
    ("okanoya", "Okanoya, K., 2004; Katahira, K. et al. — finite-state song "
     "syntax of the Bengalese finch."),
    ("gardner2001", "Gardner, T., Cecchi, G., Magnasco, M., Laje, R. & Mindlin, G. B. "
     "“Simple motor gestures for birdsongs”. Physical Review Letters 87:208101, "
     "2001 — two scalar gestures reproduce canary song."),
    ("laje2002", "Laje, R., Gardner, T. & Mindlin, G. B. “Neuromuscular control of "
     "vocalizations in birdsong: a model”. Physical Review E 65:051921, 2002; and "
     "Laje, R. & Mindlin, G. B. “Diversity within a birdsong”. Physical Review "
     "Letters 89:288102, 2002 — the normal form Birdy implements."),
    ("mindlinbook", "Mindlin, G. B. & Laje, R. The Physics of Birdsong. Springer, 2005."),
    ("fee1998", "Fee, M. S., Shraiman, B., Pesaran, B. & Mitra, P. P. “The role of "
     "nonlinear dynamics of the syrinx in the vocalizations of a songbird”. Nature "
     "395:67–71, 1998 — measured skewed, pulse-like labial waveforms."),
    ("laje2005", "Laje, R. & Mindlin, G. B. “Source–source and source–filter "
     "coupling in birdsong production”. Physical Review E 72:036218, 2005."),
    ("amador2021", "Amador, A. & Mindlin, G. B. “Low-dimensional dynamics of "
     "birdsong production and imitation”. Frontiers in Neuroscience 15:647978, 2021."),
    ("amador2013", "Amador, A., Perl, Y. S., Mindlin, G. B. & Margoliash, D. "
     "“Elemental gesture dynamics are encoded by song premotor cortical neurons”. "
     "Nature 495:59–64, 2013 — synthetic song from the low-dimensional model "
     "drives HVC neurons indistinguishably from real song."),
    ("sitt2008", "Sitt, J. D., Amador, A., Goller, F. & Mindlin, G. B. “Dynamical "
     "origin of spectrally rich vocalizations in birdsong”. Physical Review E "
     "78:011905, 2008 — the spectral content index is a function of tension alone."),
    ("amador2008", "Amador, A. & Mindlin, G. B. “Beyond harmonic sounds in a simple "
     "model for birdsong production”. Chaos 18:043123, 2008."),
    ("sitt2010", "Sitt, J. D. et al. “Physiologically driven avian vocal "
     "synthesizer”. Physical Review E 81:031927, 2010."),
    ("perl2011", "Perl, Y. S., Arneodo, E. M., Amador, A., Goller, F. & Mindlin, G. B. "
     "Physical Review E 84:051909, 2011 — χ²(γ) fit over 28 segments."),
    ("boari2015", "Boari, S., Perl, Y. S., Amador, A., Margoliash, D. & Mindlin, G. B. "
     "“Automatic reconstruction of physiological gestures used in a model of "
     "birdsong production”. Journal of Neurophysiology 114:2912, 2015."),
    ("arneodo2012", "Arneodo, E. M. et al. PLOS Computational Biology, 2012 — the "
     "low-dimensional syrinx model running as a real-time neural prosthesis."),
    ("bistel2024", "Bistel, A., Amador, A. & Mindlin, G. B. “Response of wild "
     "songbirds to songs synthesized with a low-dimensional model”. Physical Review E "
     "109:054410, 2024 — 256 playback tests, 26 wild rufous-collared sparrows, 15 "
     "sites, no significant difference between real and synthetic song."),
    ("fainstein2025", "Fainstein, D., Goller, F. & Mindlin, G. B. “Nonlinear "
     "biomechanical resonances in birdsong”. arXiv:2509.11019, 2025."),
    ("hartley1989", "Hartley, R. S. & Suthers, R. A. Journal of Comparative Physiology A "
     "165:15–26, 1989 — mini-breath and pulsatile respiratory regimes."),
    ("nowicki1987", "Nowicki, S. “Vocal tract resonances in oscine bird sound "
     "production: evidence from birdsongs in a helium atmosphere”. Nature 325:53, 1987."),
    ("beckers2003", "Beckers, G. J. L., Suthers, R. A. & ten Cate, C. “Pure-tone "
     "birdsong by resonance filtering of harmonic overtones”. PNAS, 2003."),
    ("nelson2005", "Nelson, B. S., Beckers, G. J. L. & Suthers, R. A. “Vocal tract "
     "filtering and sound radiation in a songbird”. Journal of Experimental Biology "
     "208:297–308, 2005 — the towhee tracheal measurement, and beak gape as a "
     "high-shelf, A = −5 + 32·log(B)."),
    ("riede2006", "Riede, T., Suthers, R. A., Fletcher, N. H. & Blevins, W. E. "
     "“Songbirds tune their vocal tract to the fundamental frequency of their "
     "song”. PNAS 103:5543–5548, 2006."),
    ("riede2009", "Riede, T. & Suthers, R. A. Journal of Comparative Physiology A "
     "195:183–192, 2009 — white-throated sparrow tracheal resonances."),
    ("suthers1990", "Suthers, R. A. “Contributions to birdsong from the left and "
     "right sides of the intact syrinx”. Nature 347:473–477, 1990."),
    ("goller1996", "Goller, F. & Suthers, R. A. Journal of Neurophysiology 75:867–876 "
     "and 76:287–300, 1996 — independent control of the two syringeal sides."),
    ("zollinger2008", "Zollinger, S. A., Riede, T. & Suthers, R. A. Journal of "
     "Experimental Biology 211:1978–1991, 2008 — two-voice complexity from a "
     "single side."),
    ("elemans2009", "Elemans, C. P. H. et al., 2009 — the two-mass membrane model "
     "applied to doves."),
    ("elemans2008", "Elemans, C. P. H. et al. PLOS ONE 3:e2581, 2008 — syringeal "
     "muscles modulate up to 250 Hz."),
    ("riedegoller", "Riede, T. & Goller, F. “Peripheral mechanisms for vocal "
     "production in birds”. Brain and Language 115:69–80, 2010 — modulation "
     "below 80 Hz is respiratory, 80–250 Hz syringeal."),
    ("tumer2007", "Tumer, E. C. & Brainard, M. S. Nature 450:1240–1244, 2007 — "
     "rendition-to-rendition fundamental-frequency CV of about 1 % in crystallised "
     "adult Bengalese finch song."),
    ("wood2013", "Wood, W. E. et al. PLOS ONE 8:e82327, 2013 — slow within-day drift "
     "of fundamental frequency and amplitude."),
    ("chen2013", "Chen, R. et al. PLOS ONE, 2013 — rendition-to-rendition f0 and "
     "amplitude near-uncorrelated, R² ≈ 0.03."),
    ("ohms2010", "Ohms, V. R. et al. PLOS ONE 5:e11923, 2010 — beak gape correlates "
     "with fundamental frequency in zebra finch song."),
    ("ohms2012", "Ohms, V. R. et al. Journal of Experimental Biology 215:85–92, 2012 "
     "— the monk parakeet's trachea shortens 9–44 % during calls."),
    ("podos2004", "Podos, J., Southall, J. A. & Rossi-Santos, M. R. Journal of "
     "Experimental Biology 207:607–619, 2004 — gape tracks the trill-rate / "
     "frequency trade-off in Darwin's finches."),
    ("sainburg2020", "Sainburg, T., Thielk, M. & Gentner, T. Q. “Finding, "
     "visualizing, and quantifying latent structure across diverse animal vocal "
     "repertoires”. PLOS Computational Biology, 2020."),
    ("goffinet2021", "Goffinet, J. et al. “Low-dimensional learned feature spaces "
     "quantify individual and group differences in vocal repertoires”. eLife, 2021."),
    ("birdsounds", "McDonald, K., Tan, M. & Mann, Y. Google Creative Lab "
     "“Bird Sounds” experiment, 2016, Apache 2.0 — a t-SNE map of thousands "
     "of bird recordings."),
    ("perch", "Google Perch / Perch 2.0. arXiv:2508.04665, 2025, Apache 2.0 — a "
     "14 597-species bioacoustic embedding model."),
    ("birdnet", "BirdNET. Cornell Lab of Ornithology, CC BY-NC-SA — non-commercial."),
    ("moummad", "Moummad, I. et al. Domain-invariant contrastive learning for "
     "bioacoustics. arXiv:2409.08589."),
    ("morocutti", "Morocutti, F. et al. Impulse-response augmentation and Freq-MixStyle "
     "for device-invariant audio classification. arXiv:2305.07499."),
    ("avex", "AVEX — corpus diversity over architecture for bioacoustic embeddings. "
     "arXiv:2508.11845."),
    ("jin2011", "Jin, D. Z. & Kozhevnikov, A. A., 2011 — repeat-count-dependent "
     "transition structure in Bengalese finch song."),
    ("lu2025", "Lu, K. et al., 2025 — partially observable Markov models beat HMMs "
     "on Bengalese finch song."),
    ("sharma2024", "Sharma, P. et al., 2024, Project CETI — sperm-whale codas "
     "factorised into a combinatorial 156-unit alphabet."),
]
REFNUM = {k: i + 1 for i, (k, _) in enumerate(REFERENCES)}


def C(*keys):
    """A superscript citation segment."""
    return ("[" + ",".join(str(REFNUM[k]) for k in keys) + "]", "sup")


# --------------------------------------------------------------------------
# DOCX assembly
# --------------------------------------------------------------------------


def T(text):
    return (text, "")


def B(text):
    return (text, "b")


def I(text):
    return (text, "i")


def P(doc, segs, style=None, align=None, space_after=7, indent=None,
      size=None, colour=None, space_before=None, keep=False):
    p = doc.add_paragraph(style=style)
    for text, s in segs:
        run = p.add_run(text)
        if s == "b":
            run.bold = True
        elif s == "i":
            run.italic = True
        elif s == "sup":
            run.font.superscript = True
        if size is not None:
            run.font.size = Pt(size)
        if colour is not None:
            run.font.color.rgb = colour
    if align is not None:
        p.alignment = align
    pf = p.paragraph_format
    pf.space_after = Pt(space_after)
    if space_before is not None:
        pf.space_before = Pt(space_before)
    if indent is not None:
        pf.left_indent = Cm(indent)
    if keep:
        pf.keep_with_next = True
    return p


def _pborder(p, side, sz=6, colour="7A4FA3", space=10):
    """A rule on one side of a paragraph. sz is in eighths of a point."""
    pPr = p._p.get_or_add_pPr()
    bdr = pPr.find(qn("w:pBdr"))
    if bdr is None:
        bdr = OxmlElement("w:pBdr")
        pPr.append(bdr)
    el = OxmlElement(f"w:{side}")
    el.set(qn("w:val"), "single")
    el.set(qn("w:sz"), str(sz))
    el.set(qn("w:space"), str(space))
    el.set(qn("w:color"), colour)
    bdr.append(el)
    return p


def lede(doc, text):
    """The section's opening statement: what it is, before what it measures.

    Replaces the old repeated "In plain terms." label — the typography says
    it instead, so the reader is not told the same thing eight times.
    """
    p = P(doc, [T(text)], space_after=12, space_before=2, indent=0.42,
          size=10.5, colour=RGBColor(0x3D, 0x33, 0x52))
    p.paragraph_format.line_spacing = 1.24
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    _pborder(p, "left", sz=16, colour="B9A3CE", space=12)
    return p


def H1(doc, number, text):
    h = doc.add_heading("", level=1)
    r1 = h.add_run(f"{number}   ")
    r1.font.color.rgb = VIOLET_RGB
    h.add_run(text)
    _pborder(h, "bottom", sz=4, colour="D8D2E0", space=6)
    return h


def H2(doc, text):
    h = doc.add_heading("", level=2)
    h.add_run(text)
    return h


def add_equation(doc, eq_paths, name, number):
    path = eq_paths[name]
    with Image.open(path) as im:
        w_px, h_px = im.size
    h_in = h_px / 400.0
    w_in = w_px / 400.0
    max_w_in = (MEASURE_CM - 1.6) / 2.54
    if w_in > max_w_in:
        h_in *= max_w_in / w_in
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run().add_picture(path, height=Inches(h_in))
    num = p.add_run(f"     ({number})")
    num.font.size = Pt(8.5)
    num.font.name = SANS
    num.font.color.rgb = FAINT_RGB
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(10)
    return p


def add_caption(doc, caption_segs, space_after=13):
    cap = doc.add_paragraph()
    cap.alignment = WD_ALIGN_PARAGRAPH.LEFT
    for text, s in caption_segs:
        run = cap.add_run(text)
        run.font.name = SANS
        run.font.size = Pt(8.0)
        run.font.color.rgb = GREY_RGB
        if s == "b":
            run.bold = True
            run.font.color.rgb = INK
        elif s == "i":
            run.italic = True
        elif s == "sup":
            run.font.superscript = True
    pf = cap.paragraph_format
    pf.space_after = Pt(space_after)
    pf.space_before = Pt(3)
    pf.line_spacing = 1.1
    return cap


def add_figure(doc, path, caption_segs, width_cm=MEASURE_CM):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    p.add_run().add_picture(path, width=Cm(width_cm))
    p.paragraph_format.space_before = Pt(8)
    p.paragraph_format.space_after = Pt(0)
    p.paragraph_format.keep_with_next = True
    return add_caption(doc, caption_segs)


# ---- booktabs-style tables ------------------------------------------------


def _tbl_no_borders(table):
    tblPr = table._tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "none")
        el.set(qn("w:sz"), "0")
        borders.append(el)
    tblPr.append(borders)
    layout = OxmlElement("w:tblLayout")
    layout.set(qn("w:type"), "fixed")
    tblPr.append(layout)
    margins = OxmlElement("w:tblCellMar")
    for edge, w in (("top", 60), ("bottom", 60), ("left", 85), ("right", 85)):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:w"), str(w))
        el.set(qn("w:type"), "dxa")
        margins.append(el)
    tblPr.append(margins)


def _cell_rule(cell, side, sz, colour):
    tcPr = cell._tc.get_or_add_tcPr()
    borders = tcPr.find(qn("w:tcBorders"))
    if borders is None:
        borders = OxmlElement("w:tcBorders")
        tcPr.append(borders)
    el = OxmlElement(f"w:{side}")
    el.set(qn("w:val"), "single")
    el.set(qn("w:sz"), str(sz))
    el.set(qn("w:space"), "0")
    el.set(qn("w:color"), colour)
    borders.append(el)


def _cell_shade(cell, fill):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:fill"), fill)
    tcPr.append(shd)


def _no_split(row):
    trPr = row._tr.get_or_add_trPr()
    el = OxmlElement("w:cantSplit")
    el.set(qn("w:val"), "true")
    trPr.append(el)


def _repeat_header(row):
    trPr = row._tr.get_or_add_trPr()
    el = OxmlElement("w:tblHeader")
    el.set(qn("w:val"), "true")
    trPr.append(el)


def add_table(doc, header, rows, widths, font_size=8.0, colour_col=None,
              shade_rows=()):
    """A table with rules only above and below the header and at the foot.

    colour_col: index of a column whose text is coloured by verdict — a cell
    starting with "fail" or "refuted" reads clay, "pass" or "ships" reads
    violet. The colour repeats the word, it never replaces it.
    """
    table = doc.add_table(rows=1 + len(rows), cols=len(header))
    table.alignment = WD_TABLE_ALIGNMENT.LEFT
    table.autofit = False
    _tbl_no_borders(table)

    for j, h in enumerate(header):
        cell = table.rows[0].cells[j]
        cell.text = ""
        para = cell.paragraphs[0]
        para.paragraph_format.space_after = Pt(1)
        para.paragraph_format.space_before = Pt(1)
        run = para.add_run(h)
        run.bold = True
        run.font.name = SANS
        run.font.size = Pt(font_size)
        run.font.color.rgb = INK
        _cell_rule(cell, "top", 12, "6E7484")
        _cell_rule(cell, "bottom", 6, "6E7484")
    _repeat_header(table.rows[0])

    for i, row in enumerate(rows):
        for j, val in enumerate(row):
            cell = table.rows[i + 1].cells[j]
            cell.text = ""
            para = cell.paragraphs[0]
            para.paragraph_format.space_after = Pt(1.5)
            para.paragraph_format.space_before = Pt(1.5)
            para.paragraph_format.line_spacing = 1.05
            run = para.add_run(str(val))
            run.font.name = SANS
            run.font.size = Pt(font_size)
            low = str(val).lower()
            if colour_col is not None and j == colour_col:
                run.bold = True
                if low.startswith(("fail", "refuted", "parked", "no ")):
                    run.font.color.rgb = CLAY_RGB
                elif low.startswith(("pass", "ships", "adopted", "holds")):
                    run.font.color.rgb = VIOLET_RGB
                else:
                    run.font.color.rgb = GREY_RGB
            if i in shade_rows:
                _cell_shade(cell, "F6F3F9")
            if i == len(rows) - 1:
                _cell_rule(cell, "bottom", 12, "6E7484")
            elif i in shade_rows or (i + 1) in shade_rows:
                _cell_rule(cell, "bottom", 2, "DCD8E2")

    for row in table.rows:
        _no_split(row)
    for j, w in enumerate(widths):
        for row in table.rows:
            row.cells[j].width = Cm(w)
    doc.add_paragraph().paragraph_format.space_after = Pt(1)
    return table


# ---- document furniture ---------------------------------------------------


def enable_hyphenation(doc):
    """Justified text without hyphenation is where the rivers come from."""
    settings = doc.settings.element
    for tag, val in (("w:autoHyphenation", "true"),
                     ("w:consecutiveHyphenLimit", "2"),
                     ("w:doNotHyphenateCaps", "true")):
        el = OxmlElement(tag)
        el.set(qn("w:val"), val)
        settings.append(el)
    zone = OxmlElement("w:hyphenationZone")
    zone.set(qn("w:val"), "284")
    settings.append(zone)


def style_document(doc):
    normal = doc.styles["Normal"]
    normal.font.name = SERIF
    normal.font.size = Pt(11)
    normal.font.color.rgb = INK
    normal.element.rPr.rFonts.set(qn("w:eastAsia"), SERIF)
    pf = normal.paragraph_format
    pf.space_after = Pt(7)
    pf.line_spacing = 1.26
    pf.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

    h1 = doc.styles["Heading 1"]
    h1.font.name = SANS
    h1.font.size = Pt(14.5)
    h1.font.bold = True
    h1.font.color.rgb = INK
    h1.paragraph_format.space_before = Pt(22)
    h1.paragraph_format.space_after = Pt(9)
    h1.paragraph_format.keep_with_next = True
    h1.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT

    h2 = doc.styles["Heading 2"]
    h2.font.name = SANS
    h2.font.size = Pt(10.5)
    h2.font.bold = True
    h2.font.color.rgb = VIOLET_RGB
    h2.paragraph_format.space_before = Pt(14)
    h2.paragraph_format.space_after = Pt(5)
    h2.paragraph_format.keep_with_next = True
    h2.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT

    for section in doc.sections:
        section.page_width = Cm(21.0)
        section.page_height = Cm(29.7)
        section.top_margin = Cm(2.5)
        section.bottom_margin = Cm(2.4)
        section.left_margin = Cm(3.0)
        section.right_margin = Cm(3.0)


def add_furniture(doc):
    section = doc.sections[0]
    section.different_first_page_header_footer = True

    p = section.header.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = p.add_run("Birdy — working draft · 2026-08-01")
    run.font.name = SANS
    run.font.size = Pt(8)
    run.font.color.rgb = FAINT_RGB
    _pborder(p, "bottom", sz=4, colour="DCD8E2", space=4)

    p = section.footer.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run()
    run.font.name = SANS
    run.font.size = Pt(8.5)
    run.font.color.rgb = FAINT_RGB
    fld_begin = OxmlElement("w:fldChar")
    fld_begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = "PAGE"
    fld_end = OxmlElement("w:fldChar")
    fld_end.set(qn("w:fldCharType"), "end")
    run._r.append(fld_begin)
    run._r.append(instr)
    run._r.append(fld_end)


def build_title_page(doc):
    for _ in range(3):
        doc.add_paragraph().paragraph_format.space_after = Pt(0)

    t = P(doc, [T("Birdy")], align=WD_ALIGN_PARAGRAPH.LEFT, space_after=2)
    t.runs[0].font.size = Pt(46)
    t.runs[0].font.bold = True
    t.runs[0].font.color.rgb = INK
    t.runs[0].font.name = SERIF

    rule = doc.add_paragraph()
    rule.paragraph_format.space_before = Pt(2)
    rule.paragraph_format.space_after = Pt(10)
    _pborder(rule, "bottom", sz=18, colour="7A4FA3", space=1)

    s = doc.add_paragraph()
    s.alignment = WD_ALIGN_PARAGRAPH.LEFT
    s.paragraph_format.space_after = Pt(6)
    s.paragraph_format.line_spacing = 1.22
    for i, line in enumerate(["A physical bird voice, a corpus with no audio in it,",
                              "and a label on every claim"]):
        run = s.add_run(line)
        run.font.size = Pt(14)
        run.font.name = SANS
        run.font.color.rgb = VIOLET_RGB
        if i == 0:
            run.add_break(WD_BREAK.LINE)

    d = P(doc, [T("Working draft · internal research note · 2026-08-01")],
          align=WD_ALIGN_PARAGRAPH.LEFT, space_after=26)
    d.runs[0].font.size = Pt(9.5)
    d.runs[0].font.name = SANS
    d.runs[0].font.color.rgb = FAINT_RGB

    P(doc, [
        B("Abstract.  "),
        T("Birdy is an instrument in three parts. It sings with a physical model "
          "of the bird syrinx, two equations driven by air-sac pressure and "
          "labial tension, fitted to field recordings by gesture inversion. It "
          "remembers 340 079 measured syllables and no audio: the harvest "
          "decodes each recording, describes it as numbers, and deletes the "
          "file, so nothing Birdy ships carries a licence. It shows the result "
          "as a three-dimensional map with one point per measured syllable. "
          "What Birdy claims about meaning is narrow and stated on the face of "
          "it: call type to documented behavioural function, with a confidence "
          "label on every phrase it speaks. Playback experiments are the only "
          "proof of meaning the field accepts, and Birdy has run none of its "
          "own, so everything past the literature is labelled as inference or "
          "as invention. This note reports the instrument and its evidence. The "
          "learned syllable embedding lifts species placement by 13.3 points. "
          "The parallel learn is bit-identical to the serial one and about "
          "twelve times faster. A session-quality gate separates pathological "
          "recordings at AUC 0.953. Against that: the number the pipeline "
          "optimises carries almost no information about audible distortion "
          "(r ≈ 0.1), the embedding organises by microphone before it "
          "organises by bird (+0.488 against +0.196), and no loss term yet "
          "found buys recorder invariance more cheaply than more data does. "
          "Section 9 is a ledger of every pre-registered gate and how it came "
          "out, wins and losses in one table. Refutations stay in the record. "
          "That is the method, not an apology."),
    ], space_after=14)

    kw = P(doc, [
        B("Keywords.  "),
        T("birdsong · syrinx model · gesture inversion · contrastive "
          "embedding · bioacoustics · confidence labels · negative results"),
    ], space_after=0)
    for run in kw.runs:
        run.font.size = Pt(9.5)
        run.font.color.rgb = GREY_RGB

    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)


def build_contents(doc):
    p = P(doc, [T("Contents")], space_after=8)
    p.runs[0].font.name = SANS
    p.runs[0].font.size = Pt(11)
    p.runs[0].font.bold = True

    entries = [
        ("1", "What Birdy is, and what it refuses to claim"),
        ("2", "The voice: a syrinx, and the audit of it"),
        ("3", "The corpus: decode, describe, delete"),
        ("4", "The critic, the two spaces, and the recorder in the way"),
        ("5", "The map and the live path"),
        ("6", "Structure above the syllable"),
        ("7", "The unknown bird"),
        ("8", "The ruler problem"),
        ("9", "The ledger"),
        ("10", "Where Birdy sits"),
        ("11", "What comes next"),
        ("12", "References"),
    ]
    for num, title in entries:
        e = doc.add_paragraph()
        e.paragraph_format.space_after = Pt(3)
        e.paragraph_format.left_indent = Cm(0.2)
        e.alignment = WD_ALIGN_PARAGRAPH.LEFT
        r = e.add_run(f"{num}".rjust(2) + "     ")
        r.font.name = SANS
        r.font.size = Pt(9.5)
        r.font.color.rgb = VIOLET_RGB
        r2 = e.add_run(title)
        r2.font.name = SANS
        r2.font.size = Pt(9.5)
    doc.add_paragraph().paragraph_format.space_after = Pt(6)


# --------------------------------------------------------------------------
# The document
# --------------------------------------------------------------------------


def build_docx(eq_paths, figs):
    doc = Document()
    style_document(doc)
    enable_hyphenation(doc)
    add_furniture(doc)
    build_title_page(doc)
    build_contents(doc)

    # ============ 1. What Birdy is ============
    H1(doc, "1", "What Birdy is, and what it refuses to claim")
    lede(
        doc,
        "A great tit does not improvise. It owns a small set of calls, and one "
        "of them is a sentence: three notes that mean scan for danger, then one "
        "note that means come here. In that order, other tits do both things. "
        "Played backwards, they do nothing. So birdsong is structure, and a "
        "machine can learn structure. What no machine can yet do is say what an "
        "unheard call means. The only proof of meaning the field accepts is a "
        "playback experiment — play the sound to a bird and watch what the bird "
        "does. Birdy is built on both halves of that. It learns the structure "
        "hard, and it labels the meaning honestly."
    )
    P(doc, [
        T("The field's own position has three parts"),
        C("rutz"),
        T(". Machine learning today can "),
        B("characterise"),
        T(" a repertoire: find the units and their structure. It can "),
        B("functionally decode"),
        T(": link a signal to a context and a behaviour. It "),
        B("cannot"),
        T(" translate into propositional human language, because that needs "
          "playback experiments, and those exist for a handful of systems. An "
          "ethological asymmetry sharpens the point. Bird "),
        I("song"),
        T(" has rich syntax and weak referential meaning. Bird "),
        I("calls"),
        T(" carry meaning and little syntax (docs/03 §3.1). The defensible "
          "product is therefore "),
        B("functional translation"),
        T(": call type to documented behavioural function, plus species, "
          "individual identity and urgency, each with a confidence label. "
          "Word-for-word translation is marketing. The app says so in its own "
          "interface."),
    ])
    P(doc, [
        T("The vocabularies behind the language set are real, and each one is "
          "somebody's fieldwork. The Japanese great tit composes ABC–D: ABC "
          "means scan for danger, D means approach, and the reversed order "
          "elicits nothing"),
        C("suzuki"),
        T(". The Siberian jay's alarm calls encode predator "),
        I("behaviour"),
        T(" rather than predator species"),
        C("griesser"),
        T(". The chickadee's chick-a-dee call has four note types, a strict "
          "A→B→C→D order, and a D-count that scales with threat"),
        C("freeberg"),
        T(". The nightingale delivers 180 to 200 song types in rule-governed "
          "order"),
        C("hultsch"),
        T(". The Bengalese finch sings a finite-state syntax"),
        C("okanoya"),
        T(". That literature-anchored set is what Birdy calls a documented "
          "function. Everything outside it is labelled as what it is."),
    ])
    P(doc, [
        B("Five labels, and nothing renders without one. "),
        T("The honesty rule (docs/08 §8.5) is a product requirement rather than "
          "a nicety, and it is the reason the rest of this note can be read at "
          "face value. Every phrase the app speaks carries its confidence: "),
        I("experimental"),
        T(" for playback-verified, "),
        I("documented"),
        T(" for the literature, "),
        I("inferred"),
        T(" for plausible and unestablished, and "),
        I("invented"),
        T(" for a designed mapping, always named as designed. Anything the "
          "system flags as new gets the fifth label, "),
        B("“unlabelled: real acoustics, no documented function”"),
        T(", because detecting that a sound is new is not knowing what it means."),
    ])
    add_figure(doc, figs["ladder"], [
        B("Figure 1 — The claim ladder. "),
        T("Five levels of evidence, and the label the interface prints for "
          "each. The counts are the current corpus. Source: docs/08 §8.5, "
          "docs/12, docs/16 §16.5."),
    ])
    P(doc, [
        B("Why a physical synthesiser. "),
        T("Two reasons carry the design, one scientific and one legal. "
          "Scientifically, a procedural model of the syrinx is a falsifiable "
          "theory of the bird, because its parameters — air-sac pressure, "
          "labial tension, tract geometry — are physiological claims that can "
          "be wrong. The model class has passed the strongest realism tests the "
          "field has. Synthetic song from it drives song premotor neurons "
          "indistinguishably from real song"),
        C("amador2013"),
        T(", and wild territorial sparrows respond to it as they do to a real "
          "rival"),
        C("bistel2024"),
        T(". Legally, it is the only clean voice available. Xeno-canto "
          "recordings carry per-file Creative Commons licences, largely "
          "non-commercial, so Birdy retains and ships "),
        B("no audio at all"),
        T(". Every sound the app makes is synthesised from fitted parameters, "
          "and every point in its map is a measurement rather than a file."),
    ])
    add_figure(doc, figs["arch"], [
        B("Figure 2 — The instrument, end to end. "),
        T("Stations 1 to 4 run offline in Python and are the subject of "
          "sections 3 and 4. Station 5 is the browser: static assets, no "
          "torch, no Python, described in section 5. Sources: docs/06 §6.1, "
          "docs/08 §8.3."),
    ])
    P(doc, [
        T("Table 1 is the legend to that figure. It names every technique, the "
          "place it runs, and the reason it is there. Rows marked parked are "
          "implemented and parity-tested but ship off by default, and section 2 "
          "explains what they cost."),
    ])
    add_table(
        doc,
        ["component", "technique", "where it runs", "why it is there"],
        [
            ["voice source", "Mindlin–Laje flapping oscillator, eq. 1",
             "AudioWorklet synth + Python fit",
             "physiological, bird-validated, real-time (docs/08 §8.1)"],
            ["time scale", "per-syllable γ, f₀ = g·Φ, eq. 2", "fit + synth",
             "Φ(0.1, 1) = 0.17061 is measured, not fitted (docs/08 §8.1)"],
            ["tract", "f₀-tracking resonance + stopped-tube comb, eq. 3",
             "synth",
             "pure tone is a filter effect; the comb ships in 10 of 22 species "
             "(docs/08 §8.1a)"],
            ["roughness", "140 Hz noise on β", "synth",
             "tension noise drives forebrain neurons, and an intermediate "
             "amount scores best (docs/08 §8.1a)"],
            ["fricatives", "turbulence routed to fitted formants",
             "synth, per type",
             "a chip note is shaped noise, not a tone with hiss (docs/16 §16.7)"],
            ["respiration", "air-sac oscillator, eq. 4", "parked, off by default",
             "the hand-set default is a wash; the per-species fit won 445 types "
             "(docs/15 §1)"],
            ["two voices", "sides coupled via tracheal pressure",
             "parked, off by default",
             "hand-set default regresses 0.343 → 0.294 (docs/15 §5)"],
            ["descriptor", "28-d: 13 MFCC means + 13 stds + centroid + flatness",
             "harvest, fit, browser",
             "the one representation Python and the browser can compute "
             "identically (docs/08 §8.2)"],
            ["spectral fingerprint", "32×23 log-mel patch, 736 numbers",
             "store, critic",
             "not invertible to audio, so the licensing property holds "
             "(docs/09 §9.3)"],
            ["critic", "3-head CNN: realism, species, contrastive", "pipeline",
             "it scores and types, and it never generates (docs/09 §9.2b)"],
            ["contrastive loss", "NT-Xent, τ = 0.2, eq. 5", "critic training",
             "same syllable close, different syllables apart (docs/09 §9.2b)"],
            ["map space", "the critic's 32-d embedding", "build, galaxy",
             "+13.3 points of species placement over the hand-weighted vector "
             "(docs/09 §9.8)"],
            ["browser bridge", "random Fourier features + ridge, eq. 6",
             "build fits it, browser applies it",
             "no torch in the browser; gated at cosine 0.8 (docs/11 §11.3)"],
            ["fit objective", "28-d descriptor cosine, eq. 7",
             "inversion, ship gates",
             "cluster-safe and audibly blind — section 8 (docs/08 §8.2, docs/19)"],
            ["session gate", "off-manifold 5-NN distance", "browser live path",
             "AUC 0.953, computable from the 28-d side alone (docs/20 §20.3.2)"],
            ["grammar", "first-order + Kneser–Ney backoff",
             "build, app sequences",
             "unseen tail +1.90 / +2.32 nats, seen side bit-identical (docs/18)"],
            ["song baseline", "bag-of-types", "build",
             "the bar any learned song encoder has to beat (docs/18 P2)"],
            ["novel-species hint", "Perch 2.0 top-3, ONNX, offline",
             "pipeline only",
             "metadata, never typing ground truth (docs/13)"],
        ],
        widths=[2.55, 4.35, 3.0, 5.1],
        font_size=7.6,
    )
    add_caption(doc, [
        B("Table 1 — Where the system uses what. "),
        T("Every technique, the place it runs, and the note that defines it."),
    ])

    # ============ 2. The voice ============
    H1(doc, "2", "The voice: a syrinx, and the audit of it")
    lede(
        doc,
        "Birds do not sing with a larynx. At the bottom of the windpipe sits "
        "the syrinx: soft membranes that vibrate in the airstream like a reed. "
        "The bird has two controls. Air-sac pressure sets how hard it blows, "
        "which is roughly loudness. Labial tension sets how tight the membranes "
        "are, which is roughly pitch. Two equations for that reed, driven by "
        "those two controls, are realistic enough to fool the auditory neurons "
        "of a listening bird. Birdy's voice is those equations plus the physics "
        "of the tube above them."
    )
    H2(doc, "2.1  The source")
    P(doc, [
        T("The source is the normal-form flapping oscillator of the Mindlin "
          "lineage"),
        C("gardner2001", "laje2002", "mindlinbook"),
        T(", integrated as two first-order equations (docs/08 §8.1):"),
    ])
    add_equation(doc, eq_paths, "syrinx", 1)
    P(doc, [
        T("Here "),
        I("α"),
        T(" is air-sac pressure and "),
        I("β"),
        T(" is labial tension, which sets the fundamental frequency. "),
        I("g"),
        T(" is a pure time-scale: rescaling time by "),
        I("g"),
        T(" leaves the equations unchanged. Each syllable gets its own "),
        I("g"),
        T(", chosen to place its median pitch in the well-behaved region of the "
          "model:"),
    ])
    add_equation(doc, eq_paths, "gamma", 2)
    P(doc, [
        T("Φ was measured once on a calibration sweep, so the value above is a "
          "measurement rather than a fitted parameter"),
        C("perl2011"),
        T(". The bifurcation that starts the oscillation decides the timbre. At "
          "high tension a Hopf bifurcation gives tonal, whistle-like notes. At "
          "low tension a saddle-node on a limit cycle gives pulse-like, "
          "harmonically dense ones, and the spectral content index is a "
          "function of tension alone"),
        C("sitt2008"),
        T(". The tonal-to-rich axis is therefore the model's own tension scale "
          "and not a filter setting. The integrator is deliberately plain: "
          "forward Euler at 16× oversampling at 48 kHz. RK4 agrees to within "
          "2 % of F0, so Euler is what ships."),
    ])
    H2(doc, "2.2  The tube above it")
    P(doc, [
        T("The vocal tract is not cosmetic. Pure-tone birdsong is a filter "
          "effect, in which the tract suppresses the harmonics the source "
          "produces, and heliox experiments prove it"),
        C("nowicki1987", "beckers2003"),
        T(". Songbirds also retune the oropharyngeal cavity actively, tracking "
          "the fundamental from 1.5 to 5 kHz inside a single syllable"),
        C("riede2006"),
        T(". So one resonance in Birdy follows the instantaneous f₀. A tracking "
          "resonance on its own would make every spectrum pitch-invariant, and "
          "two species at the same pitch would become the same instrument. The "
          "part that does not move is the trachea. It is a tube closed at the "
          "syrinx, and it resonates as a stopped quarter-wave pipe at the odd "
          "harmonics of one body-fixed frequency:"),
    ])
    add_equation(doc, eq_paths, "comb", 3)
    P(doc, [
        T("The measured agreement is close. Eastern towhee resonances sit at "
          "about 2.0 and 5.5 kHz against 1.88 and 5.67 kHz predicted for its "
          "45 mm trachea"),
        C("nelson2005"),
        T(", the cardinal shows the 1:3:5:7 pattern"),
        C("riede2006"),
        T(", and the white-throated sparrow sits at about 2.2 and 6.6 kHz"),
        C("riede2009"),
        T(". Birdy measures f₁ per species from the harvest itself, where "
          "pitch-dependent structure averages away and only body-fixed "
          "resonances survive. The comb ships only where the resynthesis scores "
          "better with it, which was 10 of 22 species on the original corpus "
          "(docs/08 §8.1a)."),
    ])
    H2(doc, "2.3  Texture, which is also physics")
    P(doc, [
        T("Turbulence is injected at the labia and scaled by air flow, so a "
          "silent bird does not hiss. Roughness perturbs "),
        I("β"),
        T(", the tension, rather than the output. The literature is specific "
          "here: matching the fundamental and the filters was not enough to "
          "drive selective forebrain neurons, noise on tension was required, "
          "and an intermediate amount scored best"),
        C("amador2021"),
        T(". The modulation sits at 140 Hz, inside the 80 to 250 Hz band that "
          "syringeal muscle can follow"),
        C("riedegoller", "elemans2008"),
        T(". Because the perturbation acts through the oscillator, f₀ and "
          "amplitude wobble arrive correlated, as they do in real song"),
        C("chen2013"),
        T(". All noise comes from a seeded xorshift32 stream, which makes “the "
          "same turbulence” a testable claim on both sides of the contract."),
    ])
    P(doc, [
        B("The fricative route, which is the one extension that ships. "),
        T("A real chip note is a broadband burst shaped by the tract, closer to "
          "a whispered vowel than to a tone with hiss on it. The evidence was "
          "two species parked at the noise ceiling and still failing: Algerian "
          "nuthatch types scored cosine 0.16 to 0.60 with the noise parameter "
          "already at 0.60 to 0.85. The fit was reporting a missing "),
        I("shape"),
        T(", not a missing amount. The route sends turbulence around the "
          "f₀-tracking band into the syllable's own fitted formant set, driven "
          "by the same pressure gesture as the tonal source. The bench median "
          "moved 0.584 to 0.656, end to end 13 wins and 0 losses, and it ships "
          "per type only where the resynthesis beats the tonal fit. Syllables "
          "without the flag render bit-identically (docs/16 §16.7)."),
    ])
    add_figure(doc, figs["chain"], [
        B("Figure 3 — The synthesis signal chain. "),
        T("Gesture contours drive the oscillator (eq. 1), then texture and the "
          "two tract stages shape the result. Sources: docs/08 §8.1 and §8.1a, "
          "docs/15 §1 and §5, docs/16 §16.7."),
    ])
    H2(doc, "2.4  Two extensions, and what they cost")
    P(doc, [
        T("Two structural extensions are implemented, parity-tested, and off by "
          "default. The respiratory oscillator"),
        C("fainstein2025", "hartley1989"),
        T(" replaces the hand-designed amplitude envelope with two-state "
          "air-sac dynamics (docs/15 §1):"),
    ])
    add_equation(doc, eq_paths, "respiration", 4)
    P(doc, [
        T("A Heaviside conductance asymmetry between inflow and outflow lets "
          "attack shape and cross-syllable memory emerge instead of being "
          "designed. The hand-set default lost its pre-registered bake-off: "
          "median cosine 0.343 to 0.336, with the losses concentrated in "
          "sub-50 ms notes whose onsets the physically correct 20 to 40 ms "
          "attack eats. The second extension couples the syrinx's two sides "
          "through the shared tracheal pressure"),
        C("laje2005", "suthers1990", "goller1996"),
        T(", and it is parked for the same reason, 0.343 to 0.294 with the "
          "hand-set default, although the two worst-fitting low-pitched species "
          "improved. The per-species fit pass is the version that wins: "
          "respiration took 445 of 12 680 scored types and the second voice "
          "took 2 027 of 5 922 screened, with the ship gate holding everywhere "
          "(docs/16 §16.4). The rule this taught, twice, now applies to every "
          "extension. Hand-set physics loses bake-offs, however correct the "
          "physics is."),
    ])
    H2(doc, "2.5  The audit: the model is right, and the fit is what fails")
    P(doc, [
        T("docs/21 audits the synthesiser against the canonical literature, "
          "term by term, and the verdict is worth stating plainly because it "
          "redirects the entire roadmap. The oscillator is the published normal "
          "form"),
        C("laje2002", "fee1998"),
        T(", with "),
        I("x"),
        T(" sign-flipped against the papers' convention and verified "
          "numerically before the mapping was fixed. It is validated against "
          "RK4, against the reference calibration table to 0.1 % on F0 and 2 % "
          "on peak amplitude, and against a two-sided parity harness that "
          "stands at 18 of 18 fixtures. The two-voice kernel's measured "
          "strong-coupling boundary falls exactly where its paper says the "
          "weak-coupling approximation dies"),
        C("laje2005"),
        T(". Nothing the project has measured implicates the oscillator."),
    ])
    P(doc, [
        T("Everything it has measured implicates three other places. The "),
        B("representation"),
        T(" of a syllable — one tension contour, one envelope, one static tract "
          "— cannot hold what a real note carries. The "),
        B("gesture sources"),
        T(" are designed rather than measured, which is what section 2.4 costs. "
          "And the "),
        B("objective"),
        T(" is unproven as a fidelity ranking, which is section 8. The most "
          "legible symptom is a parameterisation choice. The γ rule parks every "
          "syllable's median pitch at "),
        I("β"),
        T(" ≈ 1, the tonal end of the model rather than its middle, and the "
          "spectrally rich tail is simply absent from the output."),
    ])
    add_figure(doc, figs["pin"], [
        B("Figure 4 — The tonal-regime pin. "),
        T("Left: the share of syllables above two spectral-content thresholds, "
          "resynthesis against real. Right: median spectral flatness, log "
          "scale. The model contains the pulse-like regime that produces the "
          "missing tail, and the fit does not reach it. Source: docs/08 §8.1a "
          "as read by docs/21 §21.2."),
    ])
    P(doc, [
        T("A second symptom is blunter. The production learn's reachability "
          "report logged the tension clamp biting in "),
        B("6 617 of 12 724 types"),
        T(". Over half the fitted corpus has contour excursions that hit the "
          "tension floor or ceiling while audible, so their pitch rides the "
          "clamp instead of the dynamics. The fit is asking the equations for "
          "frequencies outside the range the calibration table measures. The "
          "honest fix is on the fit side, in per-syllable γ and wider sweeps, "
          "and not in new equations."),
    ])
    P(doc, [
        T("Table 2 is the useful form of this. What a listener calls noise or "
          "machine decomposes into six causes, each pinned to a number the "
          "project already owns. Two of the rows are worth reading together, "
          "because noise and machine are opposite failures of one cause family. "
          "The representation has one noise axis and one envelope. A fricative "
          "collapses to unshaped hiss, which is too random. A tonal note "
          "collapses to a metronomic sine, which is not random enough. The ear "
          "files both as artificial, because real syringes live between the "
          "regimes, and the model contains that middle"),
        C("sitt2008", "amador2008"),
        T(" while the fit cannot find its way there."),
    ])
    add_table(
        doc,
        ["what a listener hears", "the measured cause"],
        [
            ["hiss where a chip note should be",
             "Fricative fits parked at the noise ceiling and still failing — "
             "oropendola types at noise 0.85 scoring 0.12 to 0.77. The "
             "turbulence was shaped only by an f₀-tracking band, a filter tuned "
             "to a pitch a broadband burst does not have (docs/16 §16.7)."],
            ["flute purity, a whistle too clean to be an animal",
             "The tonal-regime pin of figure 4. Real labial motion at low "
             "tension is a skewed, pulse-like waveform with rich harmonics; the "
             "regime that produces it was unreachable until gammaScale and the "
             "0.002 calibration table (docs/08 §8.1a)."],
            ["a sine with an organ envelope",
             "Authored one-tone calls carried noise 0, rough 0, timbre pure, "
             "while the same bird's learned types measure noise 0.05 to 0.25 "
             "and rough up to 0.65. The re-fit shipped a measured texture to 14 "
             "of 15, median gain +0.148 (docs/16 §16.4)."],
            ["metronomic, the same note every time",
             "No physiological micro-variation. The oscillator is "
             "deterministic and the envelope fixed, and variation exists only "
             "per corpus-level variant. Real crystallised song has about 1 % "
             "rendition-to-rendition frequency variation, and Birdy's roughness "
             "implements that mechanism as one static fitted depth per type."],
            ["no loudness life, onsets arrive pre-shaped",
             "The tract is static per syllable, with formant coefficients "
             "computed once and nothing coupling pressure to filter. Real birds "
             "articulate per note, and beak gape acts as a high shelf on 4 to "
             "7.5 kHz. The multiplicative tract drive that would fix it exists "
             "only on the default-off respiration path (docs/15 §1)."],
            ["machine-fitted types sound worse than their cosine says",
             "The objective is the suspect. The cosine does not rank audible "
             "fit, so a type can climb the proxy into a spectrally wrong "
             "corner. Median resynthesis cosine is 0.648 across the current "
             "learn, and most sub-0.3 types are a different, unfixed gap "
             "(docs/19 §19.2, docs/16 §16.3)."],
        ],
        widths=[3.7, 11.3],
        font_size=7.8,
    )
    add_caption(doc, [
        B("Table 2 — The noise-and-machine taxonomy. "),
        T("Six symptoms, six measured causes, and not one of them in the "
          "oscillator. Source: docs/21 §21.2."),
    ])

    # ============ 3. The corpus ============
    H1(doc, "3", "The corpus: decode, describe, delete")
    lede(
        doc,
        "The harvest downloads a recording, decodes it, measures every syllable "
        "in it, and deletes the file. What survives is two sets of numbers per "
        "syllable. This is load-bearing rather than tidy: xeno-canto recordings "
        "carry per-file Creative Commons licences, largely non-commercial, so a "
        "corpus that keeps no audio is the only corpus this project is allowed "
        "to ship. One exception exists and is owner-sanctioned — a local "
        "training cache, gitignored, deleted at the end of the phase, and never "
        "read by the app."
    )
    P(doc, [
        T("The first measurement is a 28-dimensional descriptor: 13 MFCC means, "
          "13 MFCC standard deviations, mean log₂ spectral centroid, and mean "
          "spectral flatness. It is computed under an exact frame-level "
          "contract, 48 kHz mono with 1024/512 Hann frames, which the browser "
          "re-implements sample for sample (docs/08 §8.2). The second is a "
          "fixed 32×23 log-mel patch: 736 numbers, log magnitude only, no "
          "phase, resampled onto the syllable's own duration. A patch cannot be "
          "turned back into recognisable audio, so the licensing property holds "
          "while a spectral fingerprint survives (docs/09 §9.3)."),
    ])
    P(doc, [
        B("The stores, because every number in this note names one. "),
        T("No measurement here is quoted without the corpus it came from. Table "
          "3 lists them in order, and figure 5 shows what each ingest bought."),
    ])
    add_table(
        doc,
        ["store or phase", "syllables", "species", "what it added"],
        [
            ["out/harvest, original", "39 976", "22",
             "the reference corpus of docs/08 §8.1a"],
            ["out/harvest-gan, first", "9 041", "25",
             "the learned-typing bake-off store (docs/09 §9.7)"],
            ["out/harvest-gan at 40 k", "39 993", "25, 13 after a fixed trim bug",
             "the +13.3-point replication (docs/09 §9.8)"],
            ["+ xccoverbl ingest", "39 874", "121",
             "the first multi-source fetch (docs/14 §14.1)"],
            ["+ iNatSounds 2024", "226 264", "3 811",
             "6 453 recordings in one pass, zero failures (docs/16 §16.1)"],
            ["+ P0 depth harvest", "340 079", "3 811",
             "+139 440 syllables, 7 992 → 10 184 recordings (HANDOFF "
             "2026-07-31)"],
            ["current learn", "340 079 embedded", "2 421 fitted, 13 859 types",
             "median resynthesis cosine 0.648, 23 minutes"],
        ],
        widths=[4.3, 2.6, 3.5, 4.6],
        font_size=7.8,
        shade_rows=(5, 6),
    )
    add_caption(doc, [
        B("Table 3 — The measurement stores. "),
        T("Each row is a fixed corpus. The shaded rows are the current one."),
    ])
    P(doc, [
        B("Breadth came first, and depth had to be bought separately. "),
        T("The iNatSounds ingest multiplied the species count by 31 and did "
          "nothing for depth per species, which is what nearly every open "
          "problem in this note actually needs. The P0 depth harvest was the "
          "correction: 100 species chosen for documented syntax cases, "
          "repertoire depth and existing playback anchors, up to 30 recordings "
          "each, run in four batches of 25 with every species exiting clean. It "
          "added 139 440 syllables and took the target 100 to a median of 29 "
          "recordings per species, with 71 of them above the 20-recording "
          "threshold. The tenth percentile is 5, and that is not a harvest "
          "failure — xeno-canto has no more for those birds. The store grew "
          "28.65 MB per species, all of it measurements."),
    ])
    add_figure(doc, figs["corpus"], [
        B("Figure 5 — Breadth, then depth. "),
        T("Left: measured syllables per store, log scale, with the species "
          "count at each row. Right: recordings per species on the P0 target "
          "100. Sources: docs/08 §8.1a, docs/09 §9.7 and §9.8, docs/14 §14.1, "
          "docs/16 §16.1, HANDOFF 2026-07-31."),
    ])
    P(doc, [
        B("What the learn does with it. "),
        T("Syllable identity was once decided by seven hand-weighted numbers "
          "with guessed weights. It is now KMeans clustering in the critic's "
          "32-d embedding, with the cluster count chosen by silhouette. Each "
          "type is then fitted by gesture inversion, a coordinate descent over "
          "about 16 axes of the synthesiser's parameter vector in three passes, "
          "scored against the reference observation by the descriptor cosine:"),
    ])
    add_equation(doc, eq_paths, "cosine", 7)
    P(doc, [
        I("z"),
        T(" is the standardised 28-d descriptor in the harvest population "
          "frame. Section 8 is largely about what is wrong with this number. It "
          "remains the optimiser because its failure is bounded and "
          "cluster-safe. The learn itself is parallel and streaming, with "
          "per-species fits in a fork pool after one GPU embedding pass and "
          "checkpoints every 100 species, and it is verified bit-identical to "
          "the serial fit (docs/16 §16.3). Rhythm is measured rather than "
          "invented: 26 897 per-transition gaps come out of the same pass, and "
          "no invented rhythm is left in the app."),
    ])

    # ============ 4. The critic and the two spaces ============
    H1(doc, "4", "The critic, the two spaces, and the recorder in the way")
    lede(
        doc,
        "One learned component sits in the pipeline, and it never makes a "
        "sound. The critic is a small convolutional network over the log-mel "
        "patch. It decides which syllables are the same syllable, it flags the "
        "ones it has never heard, and its internal representation is the "
        "coordinate system of the map. It also organises that map by "
        "microphone before it organises it by bird, which is the largest "
        "unsolved problem in this note and is stated here rather than in a "
        "footnote."
    )
    H2(doc, "4.1  A critic that scores, never sings")
    P(doc, [
        T("The network is four convolutional layers with spectral "
          "normalisation, about 1 to 3 million parameters, trained with three "
          "heads on a shared trunk (docs/09 §9.2b). A "),
        B("realism"),
        T(" logit separates real patches from renders of the current fit. A "),
        B("species"),
        T(" classifier reads the harvest labels. A "),
        B("contrastive"),
        T(" head trains with an NT-Xent loss, so two augmented views of one "
          "syllable embed close and different syllables embed apart:"),
    ])
    add_equation(doc, eq_paths, "ntxent", 5)
    P(doc, [
        T("Augmentations are time stretches, gain changes and added noise, "
          "never pitch shifts, which are genuinely type-diagnostic. Whole "
          "species are held out of training, so realism and novelty are "
          "measured on birds the network has never seen. The current critic "
          "trained on 2 686 species with 895 held out entirely. It scores "
          "realism AUC 1.000 on held-out species and species accuracy 0.730 "
          "over 2 686 classes against chance of 0.0004. Its novelty ROC is "
          "0.846, flagging 32.2 % of unheard species' syllables at a chosen 5 % "
          "false-positive rate (docs/16 §16.2). The 32-d embedding is the "
          "deliverable. The realism logit is a refuted objective, and section 8 "
          "records how it failed."),
    ])
    H2(doc, "4.2  What the embedding bought")
    P(doc, [
        T("Typing syllables in the critic's embedding instead of the "
          "hand-weighted vector moved species placement from 26.6 % to 32.9 % "
          "on the 9 k store against chance of 4.0 %. On the 40 k store it moved "
          "placement from 38.4 % to 51.7 %, a gain of 13.3 points, against "
          "chance of 7.7 %. The guardrail cosine held at 0.807 to 0.796 and F0 "
          "error improved from 3.3 % to 2.2 %. Nothing regressed, on two "
          "independent stores (docs/09 §9.7 and §9.8). The same retrain epochs "
          "lifted novelty detection through 0.596, 0.786 and 0.846, with the "
          "true-positive rate at 5 % false positives going from 7.4 % to "
          "32.2 %. Those three ROC numbers are reported per epoch on purpose, "
          "rather than as the best one."),
    ])
    P(doc, [
        T("The learn that consumes it is fast and exactly reproducible. "
          "Parallel per-species fitting is verified bit-identical to the serial "
          "fit, and the 3 800-species learn went from about three hours to "
          "about fifteen minutes on sixteen workers. Checkpointing every 100 "
          "species arrived after two crash losses taught the lesson. The "
          "current learn on the deepened store fitted 2 421 species into 13 859 "
          "types in 23 minutes, and every fitted species carries a recovered "
          "common name."),
    ])
    H2(doc, "4.3  Two feature spaces and a bridge")
    P(doc, [
        T("Two feature spaces coexist because of one constraint. The "
          "hand-written 28-d descriptor is what the browser can compute live. "
          "The critic's 32-d embedding is what the map is clustered in. No "
          "torch ships to the browser, so a bridge maps the first space into "
          "the second: random Fourier features approximating an RBF kernel, "
          "then a closed-form ridge regression, fitted on descriptor-embedding "
          "pairs from the store with the knobs chosen on held-out recordings "
          "(docs/11 §11.3):"),
    ])
    add_equation(doc, eq_paths, "rff", 6)
    P(doc, [
        T("The bridge ships as plain numbers, D = 2048 features with σ = 4 and "
          "λ = 1 on the reference fit, and it is gated. A median mapped-versus-"
          "true cosine below 0.8 on held-out recordings ships "),
        I("accepted: false"),
        T(" and the browser stays on the 28-d path. The debug build passes at "
          "0.962. A linear ridge was the original and more honest choice, and "
          "it broke at 0.7997, just under the gate, once the embedding grew "
          "finer. That refutation is recorded in place rather than quietly "
          "replaced."),
    ])
    add_figure(doc, figs["spaces"], [
        B("Figure 6 — Two feature spaces and the bridge. "),
        T("The browser computes only the 28-d descriptor, the map lives in the "
          "critic's 32-d embedding, and the ridge of eq. 6 maps one into the "
          "other behind a ship gate. Sources: docs/08 §8.2, docs/11 §11.3, "
          "docs/20 §20.1."),
    ])
    H2(doc, "4.4  The recorder in the way")
    P(doc, [
        T("The geometry battery scores how much a grouping organises the "
          "embedding, as the same-label rate among a point's nearest neighbours "
          "minus a permutation null:"),
    ])
    add_equation(doc, eq_paths, "knnlift", 8)
    P(doc, [
        T("On the production embedding the strongest relation is not the bird. "
          "It is "),
        I("which recordist made the recording"),
        T(": kNN lift +0.488, against species at +0.196 (docs/14 §14.4). Every "
          "consumer of the embedding inherits that. The typing, the novelty "
          "detector, the map and the relations are all built on a space whose "
          "dominant axis is a microphone. The literature is unambiguous that "
          "invariance is a training-time problem"),
        C("moummad", "morocutti", "avex"),
        T(", so Birdy attacked it there, three times, on pre-registered gates "
          "(docs/17). All three attacks on the loss failed, and they failed "
          "informatively."),
    ])
    P(doc, [
        B("Augmentation is free and does nothing. "),
        T("Channel-EQ simulation and Freq-MixStyle on log-mel patches are "
          "perfectly species-safe, and they move recordist lift by −0.7 % "
          "relative, which is nothing. "),
        B("The adversarial head works and costs exactly what it buys. "),
        T("A recordist-adversarial head does move the target, and the trade is "
          "almost perfectly linear in log weight. At w = 0.05 it takes 33 % off "
          "recordist lift and 14.7 points off species accuracy. At w = 0.3 the "
          "embedding is destroyed, with species accuracy at 0.199 and realism "
          "AUC at 0.862. No swept weight buys the required 30 % while holding "
          "species inside the gates. Recorder invariance costs species "
          "information at roughly one to one (docs/17 §17.3)."),
    ])
    P(doc, [
        B("The species-safe version cannot reach the confound at all. "),
        T("Masking the adversarial softmax to recordings of the patch's own "
          "species fences species information out by construction, and it does "
          "exactly that: species lift stays flat to +10 % at every weight. But "
          "it buys only −6 % against a −30 % gate. The reason is the useful "
          "part. The recordist signal is carried "),
        I("between"),
        T(" species, because each species' recordings come from different "
          "people, and that is precisely where a species-factored head is "
          "forbidden to look (docs/17 §17.5)."),
    ])
    add_figure(doc, figs["confound"], [
        B("Figure 7 — The confound, and why the loss road is closed. "),
        T("Left: what the embedding actually organises by. Right: every swept "
          "point from both adversarial heads, as relative change in recordist "
          "lift against relative change in species lift. The shaded region is "
          "what the pre-registered gates asked for, and no arm reaches it. "
          "37-species debug store, debug-scale. Sources: docs/14 §14.4, "
          "docs/17 §17.3 and §17.5."),
    ])
    P(doc, [
        B("Data helps, and the honest re-test shrank the help. "),
        T("The AVEX direction"),
        C("avex"),
        T(" held where the losses did not: merging two recording domains per "
          "species beat every loss term tried. The first test used 12 species "
          "with a 3-species holdout, and the pre-registered bigger re-test used "
          "63 both-domain species with 16 held out. The re-test shrank every "
          "delta. The naive merge's +14.4 points became +3.6. The cross-domain "
          "contrastive mechanism's +13.4-point boost became +1.7 against a +10 "
          "gate, and the AUC drop that had counted against it reversed. What "
          "survives at both scales is the ordering, and the ordering is what "
          "matters: more domains per species helps, the mechanism adds about "
          "nothing on top, and no loss term buys invariance more cheaply than "
          "data does (docs/17 §17.4 and §17.6). The same lesson arrives twice "
          "in this note, from two directions. Small samples flatter whichever "
          "arm you hoped for."),
    ])
    add_figure(doc, figs["avex"], [
        B("Figure 8 — The data road, and its honest shrink. "),
        T("Cross-domain species retrieval for three training arms, at two "
          "scales. Both are debug-scale, and the absolute levels are only "
          "comparable arm against arm inside each panel. Sources: docs/17 "
          "§17.4 and §17.6."),
    ])

    # ============ 5. The map and the live path ============
    H1(doc, "5", "The map and the live path")
    lede(
        doc,
        "The map is a precomputed three-dimensional point cloud with one point "
        "per measured syllable. It is a measurement rather than an "
        "illustration, which is a distinction the project pays for: hand-set "
        "jitter survives only where no measurement exists, and where it "
        "survives it is labelled invented. The app that reads it is a static "
        "site. It loads JSON and float arrays, synthesises in an AudioWorklet, "
        "analyses the microphone, and never calls a Python process."
    )
    P(doc, [
        T("The browser runs the same oscillator as the pipeline and the same "
          "feature extractor on the microphone. The two renderers are verified "
          "sample for sample against each other at 18 of 18 parity fixtures, "
          "with the worst divergence at float32 rounding. Live audio is "
          "standardised, bridged into the map's space by eq. 6, and turned into "
          "cluster activations by a softmax over centroid cosines with about "
          "120 ms of smoothing (docs/08 §8.2)."),
    ])
    P(doc, [
        B("The map's honesty number is 0.61, and that number is a metric "
          "problem. "),
        T("Raw knot-level agreement between the bridged position and the true "
          "one is 0.61 on held-out recordings, which reads like a failing map. "
          "Decomposing the 38.6 % disagreement over 3 731 held-out syllables "
          "says otherwise. 76.4 % of it is boundary near-ties, with 74 % of all "
          "rows sitting within a margin of 0.05 and 41 % of flips landing on "
          "the runner-up knot. Tie-adjusted agreement is 0.91. Genuine "
          "big-margin map failure is about 4 % of rows, and no better map class "
          "can fix a near-tie, because at a knot boundary the question is "
          "ill-posed. The honest single-label claim is species-level agreement, "
          "which is 0.78, and that is the claim the interface makes (docs/20 "
          "§20.1)."),
    ])
    P(doc, [
        B("Eight recordings carry a quarter of the damage. "),
        T("Of 45 held-out sessions on the debug build, 8 carry 22.9 % of the "
          "map's flip loss, and all 8 are xeno-canto. They separate cleanly. An "
          "off-manifold 5-NN distance — computable from the 28-d side alone, "
          "which is all the browser will ever have — reaches AUC 0.953 against "
          "the bad-session label, and a shipped cloud of 256 random anchors "
          "weighing 28 kB holds AUC at or above 0.92. The pre-registered "
          "two-signal combination adds nothing at 0.954, so it does not ship. "
          "The lever gate failed its raw bar at +3.5 points against +5, so the "
          "pre-registered fallback fired and the signal ships as an "),
        B("honesty gate"),
        T(" instead of a correction: “this session is off everything the galaxy "
          "knows, and positions are guesses.” On the shipped operating point it "
          "flags 8 of 45 sessions, catches 5 of the 8 bad ones including the "
          "three worst loss-carriers, and produces 3 clean false flags, all "
          "within 0.02 of the bad line (docs/20 §20.3.2)."),
    ])
    add_figure(doc, figs["map"], [
        B("Figure 9 — The map, and the sessions that break it. "),
        T("Top: the 38.6 % knot disagreement decomposed, 1 439 flips over "
          "3 731 held-out syllables. Bottom: AUC against the bad-session label "
          "for each candidate signal, with the pre-registered adoption gate. "
          "End-to-end debug build, debug-scale. Source: docs/20 §20.1 and "
          "§20.3.2."),
    ])
    P(doc, [
        B("Removing the bad sessions from the fit makes things worse. "),
        T("The obvious move is to drop the worst-quintile off-manifold sessions "
          "before fitting. It costs 0.006 and 0.015 of evaluation cosine on the "
          "two debug stores, against an allowance of 0.005, so it failed its "
          "gate. The reading is more useful than the fail: the weird sessions "
          "are manifold coverage, and pruning them hurts the next unseen weird "
          "session. Gating is a live-path action only (docs/20 §20.3.1)."),
    ])

    # ============ 6. Structure above the syllable ============
    H1(doc, "6", "Structure above the syllable")
    lede(
        doc,
        "A syllable is not a sentence. Above the syllable sit transitions, "
        "bouts, song types and dialects, and this is where a project about "
        "birdsong either becomes interesting or admits it is a sound library. "
        "Birdy measures what it can at this level and reports that most of it "
        "is currently starved by corpus depth rather than by missing machinery. "
        "The machinery has been built and pre-registered anyway, so the re-test "
        "after the depth harvest is a re-run rather than a project."
    )
    P(doc, [
        T("Birdsong is not first-order. Repeat-count adaptation and partially "
          "observable structure are both established"),
        C("jin2011", "lu2025"),
        T(". Birdy ran the pre-registered bake-off anyway: the shipped "
          "first-order transitions against Jin–Kozhevnikov repeat-count "
          "structure and against a hidden-state HMM, scored on held-out bout "
          "likelihood. The repeat-count model lost decisively at −0.348 "
          "nats per token, winning 0 of 30 species. The HMM won the stated "
          "rule at +0.422 nats and 29 of 30 species. Then the decomposition "
          "reversed the adoption. On the 90 % of held-out transitions that were "
          "seen in training, first-order is the better model, −1.525 against "
          "−1.624. The HMM's entire advantage sits in the 10 % unseen tail, "
          "−9.25 against −4.16. That is a property of smoothing "),
        I("shape"),
        T(", not of recovered hidden structure, and adopting a heavier model "
          "for a smoothing artifact is the wrong lesson. First-order stays "
          "(docs/18 P1)."),
    ])
    P(doc, [
        T("The finding was worth more than the bake-off. It named the real "
          "weakness as unseen-context transitions, at −9.25 nats per token, and "
          "that has a cheap fix. A Kneser–Ney continuation backoff gained +1.90 "
          "and +2.32 nats per token on unseen-context transitions across the "
          "two debug stores, while the seen side stayed bit-identical with loss "
          "of exactly 0.0000. The honest scope belongs next to it: 80 % of the "
          "unseen tail is seen-context, so the gain over the full tail is +0.37 "
          "and +0.65."),
    ])
    add_figure(doc, figs["syntax"], [
        B("Figure 10 — Why the heavier grammar was refused, and why syntax "
          "starves. "),
        T("Left: held-out likelihood split by whether the transition was seen "
          "in training. Right: species of the debug-100 store with enough bouts "
          "to attempt song-level structure. Both debug-scale. Source: docs/18 "
          "P1 and P2."),
    ])
    P(doc, [
        B("Song types fall out of the data, with a control under them. "),
        T("Clustering run-collapsed sequences of type ids by normalised edit "
          "distance found 50 song types across 13 of 35 species, placing 693 of "
          "2 419 candidate bouts. A global-permutation control yields 0.2 % at "
          "the shipped constants, which is one spurious type, so the recurrence "
          "floor is measured rather than assumed. The nightingale, the famous "
          "improviser, yields zero types over 275 candidate bouts, and that "
          "agreement with a century of field notes is the most reassuring "
          "negative in the project (docs/12). Forty-eight species carry "
          "detected song types today, and the app plays each type heard at "
          "least twice as a song, with repeats sampled from the bird's own "
          "measured self-transition rates and gaps from the measured transition "
          "table."),
    ])
    P(doc, [
        B("The song-level kernel failed both its gates, and the reason is one "
          "number. "),
        T("A weighted edit distance over sequences of type and gap loses "
          "species lift to plain bag-of-types, +0.877 against +0.924 on the "
          "37-species store and +0.050 against +0.081 on debug-100. It also "
          "fails the recordist gate at +0.264. Within-species song structure "
          "does exist, and all 18 deep species separate their own recordings, "
          "but it lives entirely in the token marginals. Order and rhythm add "
          "nothing measurable at current depth. The one number is that only 12 "
          "of the debug-100 species have 20 or more bouts after run-collapse. "
          "The bar any learned song encoder must beat is now bag-of-types, and "
          "the depth harvest is what makes the attempt worth running (docs/18 "
          "P2)."),
    ])

    # ============ 7. The unknown bird ============
    H1(doc, "7", "The unknown bird")
    lede(
        doc,
        "What happens when a bird the system has never heard starts to sing? "
        "Not a guess, and not silence. The arrival is measured and compared "
        "against everything known. If it fits nothing, it is allowed to be new. "
        "It waits with similar arrivals until enough of them agree to found a "
        "new knot in the map. An external model may suggest which species it "
        "resembles, and that suggestion is metadata, never identity."
    )
    P(doc, [
        T("The arrival pipeline is live end to end. Each new observation is "
          "embedded and scored against a calibrated novelty threshold, which is "
          "a chosen false-positive rate rather than a discovered boundary. "
          "Known-looking syllables inherit the nearest type. In a "
          "relabel-recovery test, 97.4 % of relabelled syllables inherited a "
          "known type and 65.2 % inherited the correct species' type. The "
          "misassignments go to similar-sounding types of other species, which "
          "is the detector behaving as designed: it prices acoustic "
          "neighbourhood, not taxonomy. Novel syllables are not force-assigned. "
          "Below quorum they stay unassigned. At quorum, which is 8 or more "
          "coherent pending points inside a 0.70 cosine radius above a 0.75 "
          "cohesion floor, they found a new knot labelled "),
        I("unheard syllable"),
        T(", at confidence "),
        B("“unlabelled: real acoustics, no documented function”"),
        T(" (docs/10 §10.3 and §10.4, docs/16 §16.5)."),
    ])
    P(doc, [
        T("A Perch 2.0 pass"),
        C("perch"),
        T(" labels the novel-flagged syllables from the training cache. It runs "
          "as ONNX, offline, at about 48 ms per window, and its label reads "),
        I("closest documented species, Perch 2.0 inference, unverified"),
        T(". It is metadata only. Nothing in the learn path may read it. The "
          "store holds 23 697 novel syllables, and 841 of them are honestly "
          "unlabelable because their xeno-canto audio was deleted by design, "
          "which the pipeline states rather than guesses around. Structure "
          "above the syllable inherits the same label all the way up (docs/18 "
          "P6)."),
    ])
    P(doc, [
        B("Thresholds do not transfer, and that was found the hard way. "),
        T("A novelty threshold calibrated for 5 % false positives on the 9 k "
          "store flagged 29.8 % of the 47 k store. Recalibration is cheap and "
          "is now automatic, and the ROC is reported per corpus epoch rather "
          "than as the best one ever measured. Anything more confident than "
          "this pipeline is numerology, and the interface keeps saying so."),
    ])

    # ============ 8. The ruler problem ============
    H1(doc, "8", "The ruler problem")
    lede(
        doc,
        "One number judges every fit decision in the pipeline: the inversion's "
        "gesture search, the respiration and two-voice ship gates, the "
        "fricative routing, the extension bake-offs. That number is the cosine "
        "between the resynthesis's 28-d descriptor and the real audio's. In "
        "2026 the project finally asked the question none of those gates could "
        "ask. Is a cosine gain an audible gain? It is not. This section is the "
        "answer and its consequences, and it is the reason section 11 is "
        "ordered the way it is."
    )
    P(doc, [
        T("The bench (docs/19 §19.1) is the instrument. For a fitted type, "
          "render it, then take the "),
        I("medoid"),
        T(" member's cached audio, which is a typical rendition rather than a "
          "lucky one. Resample the longer clip to the shorter, because time "
          "inside a syllable is relative. Shift the render's per-band log-mel "
          "mean onto the original, because channel is the measured dominant "
          "nuisance. Then score two independent spectral distances: "),
        B("mel-cepstral distortion"),
        T(" over 25 coefficients in Kubichek dB, band-limited per pair to the "
          "file's own Nyquist, and "),
        B("multi-resolution STFT error"),
        T(" at 512, 1024 and 2048. The self-test is the part that earns trust. "
          "Identity scores 0.000 dB. A half-low-passed render costs +77.9 dB "
          "MCD and +7.0 dB STFT while the cosine drops only 0.015."),
    ])
    P(doc, [
        B("The finding. "),
        T("Over 200 fitted types on the debug-100 store, the cosine's "
          "correlation with audible distortion sits at about 0.1, with "
          "p-values that cannot reject zero and point estimates that lean the "
          "wrong way. This is not a bench artifact. The recomputed cosine "
          "reproduces the stored one at Pearson 0.921, so the bench measured "
          "the number the learn actually uses. MCD and STFT agree with each "
          "other at 0.925, so they measure something coherent, and the cosine "
          "does not measure it. There is even a plausible mechanism for the "
          "wrong-way lean. High-cosine types are clean whistles whose renders "
          "concentrate energy in one band while the field audio carries "
          "broadband noise everywhere else, so the spectral distance is large. "
          "Noisy buzzes score a low cosine and have broadband energy on both "
          "sides, so their distance is small."),
    ])
    P(doc, [
        T("The obvious fix was tried and did not survive its own sample size. "
          "A mel-path target — a time-resolved exp(−LSD) similarity to the "
          "type's measured mel trajectory — is the better "),
        I("measurement"),
        T(" by a wide margin, at Spearman −0.420 against MCD where the cosine "
          "reads +0.100, signs correct. It is the worse "),
        I("optimiser"),
        T(". At blend weight 1.0 the cosine guardrail collapses by 0.377. A "
          "10-type probe won 7 of 10 on MCD, and the pre-registered 80-type "
          "gate run took that to a 31 % win share against a 60 % bar, with a "
          "median ΔMCD of exactly 0.0 dB and one type losing 0.120 cosine. The "
          "honest reading is better than the bare fail: the objective change "
          "mostly does nothing, because the inversion already lands where the "
          "blend would send it. It occasionally helps enormously, with a mean "
          "of +2.07 dB pulled by a handful of types at +13.8 dB. And it "
          "sometimes wanders. An objective that is a wash on the median with an "
          "unguarded tail is not a default (docs/19 §19.4 and §19.5)."),
    ])
    add_figure(doc, figs["ruler"], [
        B("Figure 11 — The ruler problem, in two panels. "),
        T("Left: correlation with audible distortion for the incumbent "
          "objective and its replacement, n = 200 types. Right: the "
          "replacement's win share at the exploratory scale and at the "
          "pre-registered gate scale. Debug-scale, debug-100 store against the "
          "iNat cache. Source: docs/19 §19.2, §19.4 and §19.5."),
    ])
    P(doc, [
        B("The learned alternative failed earlier and harder. "),
        T("A realism-trained critic is an excellent classifier, at AUC 0.990 to "
          "1.000 on entirely held-out species. Used as the fit objective it is "
          "monotonically harmful in its weight. At w = 1 the cosine collapses "
          "from 0.762 to 0.335 and placement drops to 17.3 %. The refutation "
          "replicated on the 40 k store, where placement went from 38.4 % to "
          "31.9 % at w = 0.5. Separating two distributions perfectly is not the "
          "same as having a gradient that points at the nearer one, and the "
          "retained cosine guardrail is what made the gaming visible at all "
          "(docs/09 §9.7 and §9.8)."),
    ])
    P(doc, [
        B("A structurally better tract tells the same story from a third "
          "angle. "),
        T("A fixed waveguide with 32 times the spectral freedom of the tracking "
          "band improved all three metrics at once on five species, and it was "
          "a regression across 22, at 23.1 % against 22.2 % placement. It was "
          "later shown to have been rejected by badly defined types rather than "
          "by the objective. It now wins on the gan store under learned typing "
          "at 37.0 % and pays for it in cosine, so it stays promising and "
          "unconfirmed (docs/08 §8.1c, docs/09 §9.7)."),
    ])
    P(doc, [
        B("The oldest open problem is species identity, and four explanations "
          "for it are already dead. "),
        T("On the original 22-species store a resynthesis lands nearest its own "
          "species 23.1 % of the time against chance of 4.5 %. The envelopes "
          "are not collapsed: the synthesiser expresses 103 % of the real "
          "between-species spread and 106 % of the spectral detail, varied "
          "along different axes. A spectral tilt error does exist, and "
          "correcting it exactly drops placement to 20.2 %. The harmonic "
          "structure is not missing, because real syllables resolve to a mean "
          "of 2.2 partials. And a time-resolved objective improves its own "
          "metric by 36 % while placement falls from 61.7 % to 43.2 %, which "
          "means the two objectives conflict. The ceiling is the descriptor and "
          "the filter chain's capacity rather than the search (docs/08 §8.1a)."),
    ])
    P(doc, [
        T("The state of the metrology, verbatim from docs/19 §19.5: "),
        I("“measure spectrally, optimise descriptor-ly”"),
        T(". Every fit gate from here reads the bench. The inversion keeps "
          "climbing the cosine, because its failure is at least bounded and "
          "cluster-safe. An objective that is both remains unfound, and that "
          "sentence is the most important one in this note."),
    ])

    # ============ 9. The ledger ============
    H1(doc, "9", "The ledger")
    lede(
        doc,
        "One table, both directions. Every pre-registered gate this project has "
        "run, what it asked for before the run, what it measured, and what "
        "shipped. A gate written down in advance is the only kind whose result "
        "means anything, and a refutation that stays on the record is the only "
        "kind that stops somebody trying it again. Read the failures first. "
        "They are why the successes above can be taken at face value."
    )
    add_table(
        doc,
        ["what was tried", "the gate, set in advance", "what it measured",
         "verdict"],
        [
            ["Typing in the critic's 32-d embedding",
             "placement up, cosine guardrail held",
             "38.4 % → 51.7 %, cosine 0.807 → 0.796", "ships"],
            ["Parallel and streaming learn", "bit-identical to serial",
             "bit-identical, ~3 h → ~15 min", "ships"],
            ["Fricative route, noise through fitted formants",
             "resynthesis beats the tonal fit, per type",
             "bench 0.584 → 0.656, 13 wins / 0 losses", "ships per type"],
            ["Tracheal comb per species", "comb improves the resynthesis",
             "won 10 of 22 species", "ships where it wins"],
            ["Measured texture on authored one-tone calls",
             "gain against the same bird's learned types",
             "14 of 15, median +0.148", "ships"],
            ["Respiratory oscillator, hand-set default",
             "beat the envelope on median cosine", "0.343 → 0.336",
             "fails, parked"],
            ["Respiratory oscillator, per-species fit",
             "win the type, gate held everywhere",
             "won 445 of 12 680 scored types", "ships per species"],
            ["Two-voice coupling, hand-set default", "beat the single voice",
             "0.343 → 0.294", "fails, parked"],
            ["Two-voice coupling, per-species fit", "win the type",
             "won 2 027 of 5 922 screened", "ships per species"],
            ["RFF ridge browser bridge", "median held-out cosine ≥ 0.8",
             "0.962 on the debug build", "ships"],
            ["Linear ridge bridge, the incumbent", "the same 0.8 gate",
             "0.7997", "refuted, replaced"],
            ["Realism logit as the fit objective",
             "placement and cosine hold",
             "cosine 0.762 → 0.335, placement 17.3 %; replicated at 40 k",
             "refuted twice"],
            ["Mel-path objective at w = 0.5",
             "≥ 60 % MCD wins, ΔMCD > +1 dB, cosine drop ≤ 0.02 / max 0.05",
             "31 % wins, 0.0 dB, max drop 0.120", "fails, not adopted"],
            ["Mel-path as a measurement", "|r| ≥ 0.4 against MCD",
             "Spearman −0.420, Pearson −0.305", "adopted as the bench target"],
            ["Channel-EQ + Freq-MixStyle augmentation",
             "−30 % recordist lift, species held", "−0.7 % recordist",
             "fails"],
            ["Recordist-adversarial head", "the same",
             "−33 % recordist for −14.7 pts species accuracy", "fails"],
            ["Within-species adversarial head",
             "the same, species-safe by construction",
             "species flat, recordist −6 %", "fails"],
            ["Naive two-domain merge", "cross-domain retrieval up",
             "+14.4 pts at 12 species, +3.6 at 63",
             "no adoption, direction holds"],
            ["Cross-domain contrastive positives", "+10 pts over the merge",
             "+13.4 at 12 species, +1.7 at 63", "fails on re-test"],
            ["Jin–Kozhevnikov repeat-count grammar",
             "beat first-order on held-out bouts",
             "−0.348 nats/token, 0 of 30 species", "refuted"],
            ["Hidden-state HMM grammar", "the same",
             "+0.422 nats overall, all of it in the 10 % unseen tail",
             "refuted on decomposition"],
            ["Kneser–Ney unseen-transition backoff",
             "gain on unseen contexts, no loss on seen",
             "+1.90 / +2.32 nats, seen side exactly 0.0000", "ships"],
            ["Song-level edit-distance kernel",
             "beat bag-of-types on species lift",
             "+0.877 vs +0.924, and recordist lift +0.264",
             "fails both gates"],
            ["Song-type detection against a permutation null",
             "recurrence above the null",
             "0.2 % at the shipped constants, one spurious type", "ships"],
            ["Session gate: off-manifold 5-NN", "AUC ≥ 0.90",
             "0.953, and ≥ 0.92 from 256 shipped anchors", "ships"],
            ["Session gate: map-flip lever", "+5 points of agreement",
             "+3.5 points raw", "fails, ships as an honesty gate"],
            ["Session gate: prune bad sessions from the fit",
             "evaluation cosine cost ≤ 0.005", "−0.006 and −0.015", "refuted"],
            ["Learned inverse for synthesis parameters",
             "2× faster at equal cosine",
             "0.737 vs 0.734, and 0.2 s either way", "fails its ship rule"],
        ],
        widths=[4.3, 3.7, 4.3, 2.7],
        font_size=7.4,
        colour_col=3,
    )
    add_caption(doc, [
        B("Table 4 — The ledger. "),
        T("Twenty-eight pre-registered gates. Twelve ended in something "
          "shipping, and sixteen ended in a written-down refusal. Two of the "
          "refusals still produced an asset: the map-flip lever became an "
          "honesty gate, and the mel target became the bench instead of the "
          "objective. Sources: docs/08 to docs/21 as cited in the body."),
    ])
    P(doc, [
        T("The shape of that table is the argument. A project that reports only "
          "the twelve is indistinguishable, from the outside, from a project "
          "that ran twelve experiments and got lucky. The sixteen are what make "
          "the twelve legible. Three of them cost real work and are worth "
          "naming as the expensive lessons: hand-set physics loses bake-offs, "
          "small samples flatter the arm you hoped for, and an objective can be "
          "excellent at telling two distributions apart while being useless at "
          "pointing toward the nearer one."),
    ])

    # ============ 10. Where Birdy sits ============
    H1(doc, "10", "Where Birdy sits")
    lede(
        doc,
        "Birdy sits among bioacoustic tools that classify, embed, map or "
        "generate. None of them is a voice. Table 5 puts the approaches beside "
        "each other on the properties this project has to care about. A cell "
        "says “not documented” where the project's own references do not answer "
        "the question, and the table claims nothing past its sources."
    )
    add_table(
        doc,
        ["approach", "what it is", "sings", "interpretable parameters",
         "ships in a static app", "labels its claims"],
        [
            ["BirdNET", "species classifier on spectrograms", "no", "no",
             "no — CC BY-NC-SA, non-commercial", "not documented"],
            ["Perch 2.0", "14 597-species embedding model", "no", "no",
             "no — 409 MB ONNX, pipeline only", "no"],
            ["Google Bird Sounds", "t-SNE map of thousands of recordings",
             "no", "no", "yes — Apache 2.0 web experiment", "no"],
            ["Sainburg et al.", "VAE latent space across species", "no",
             "latent, not physiological", "not documented", "no"],
            ["Goffinet et al.",
             "learned low-d features for individual and group differences",
             "no", "no", "not documented", "no"],
            ["generative audio models", "waveform generators", "yes", "no",
             "no — training-data licences unclear", "no"],
            ["Birdy",
             "physical syrinx + a corpus with no audio", "yes",
             "yes — pressure, tension, tract geometry",
             "yes — no audio retained, no weights shipped",
             "yes — five levels"],
        ],
        widths=[2.5, 3.6, 1.2, 2.7, 3.2, 1.8],
        font_size=7.4,
        shade_rows=(6,),
    )
    add_caption(doc, [
        B("Table 5 — Approaches beside each other. "),
        T("Sources for the external rows are references [42] to [45] and the "
          "project's docs/13. “Not documented” means the references do not "
          "answer the cell."),
    ])
    P(doc, [
        B("What Birdy takes, and what it declines. "),
        T("The map's prior art is open and was taken freely. A t-SNE map of "
          "bird recordings, a VAE latent space and learned low-dimensional "
          "feature spaces together established that vocal repertoires have "
          "navigable geometry"),
        C("birdsounds", "sainburg2020", "goffinet2021"),
        T(". Perch 2.0 gives novel syllables a second opinion, as metadata and "
          "never as identity"),
        C("perch"),
        T(". BirdNET's non-commercial licence excludes it from the app"),
        C("birdnet"),
        T(". A generative audio model would trade interpretability, the claim "
          "ladder and the playback-tested realism evidence for sample quality "
          "the field cannot yet measure. On the documented cells of table 5, no "
          "listed approach combines Birdy's particular triple: a bird-validated "
          "physical voice, a corpus that keeps no audio, and a label on every "
          "claim."),
    ])

    # ============ 11. What comes next ============
    H1(doc, "11", "What comes next")
    lede(
        doc,
        "In order, each with the number that would prove it. The depth harvest "
        "that blocked most of this list is done, so the next steps are re-runs "
        "of pre-registered comparisons rather than new projects. Under all of "
        "them sits the metrology problem, which is named and open."
    )
    P(doc, [
        B("Done: the depth harvest. "),
        T("100 species, up to 30 recordings each, +139 440 syllables, median 29 "
          "recordings per species and 71 of 100 above the syntax threshold. "
          "That one action unblocked the grammar re-test, the song-level space "
          "and the widening of the spectral bench, and nothing else on this "
          "list has that reach."),
    ])
    P(doc, [
        B("Next: the grammar bake-off, again. "),
        T("First-order against Jin–Kozhevnikov against a partially observable "
          "Markov model, on the deepened store, on the terms already written "
          "down. Thin data is exactly where higher-order models starve, and the "
          "repeat-count model's 0 of 30 says so. The bake-off is a re-run, and "
          "its result is pre-committed. "),
        B("Then the song-level embedding. "),
        T("Bouts as points. The parameter-free kernel baseline already failed, "
          "so the bar any learned encoder must beat is bag-of-types at +0.924, "
          "with the recordist-lift gate upstream of it (docs/18 P2)."),
    ])
    P(doc, [
        B("Then structure, and only then anything resembling meaning. "),
        T("A CETI-style factorisation"),
        C("sharma2024"),
        T(" would decompose each deep species' songs into independent axes — "
          "rhythm, tempo, ornamentation — toward per-species combinatorial "
          "alphabets, which is the strongest honest claim available without "
          "playback of Birdy's own. Dialect and individual maps follow: "
          "same-species variants placed geographically, individuals separated "
          "where 10 to 16 bouts each exist, which the literature has shown to "
          "be sufficient (docs/18 P3 and P4)."),
    ])
    P(doc, [
        B("Two synthesis extensions, ranked and pre-registered. "),
        T("The audit of section 2.5 ranks the extension roadmap by realism per "
          "unit of interpretability, and the top two are already specified. "
          "First, the per-species respiratory pressure fit, forced by each "
          "type's measured gesture rather than a median envelope. Its gate is "
          "the bench: an MCD win share of 60 % or better, a median ΔMCD better "
          "than 1 dB, a median cosine drop no worse than 0.02 and a maximum no "
          "worse than 0.05, on the debug-100 store with the audio cache. That "
          "is the same set of gates that killed the mel-weight objective, "
          "applied deliberately. Second, measured physiological jitter and "
          "tremor per type: two scalars extending the existing roughness "
          "mechanism into a two-band measured gesture, against the roughly 1 % "
          "rendition-to-rendition frequency variation the literature reports"),
        C("tumer2007", "wood2013"),
        T(". Its gate is a KS distance halved against the unmodulated render "
          "with no type regressing more than 1 dB of MCD, on the 100 deepest "
          "species of the depth harvest, which is the first corpus with enough "
          "renditions to measure the target at all (docs/21 §21.3)."),
    ])
    P(doc, [
        B("What will not be done, and why it is a decision rather than a gap. "),
        T("No neural audio generation. No DDSP decoder, no RAVE, no diffusion "
          "vocoder, no neural timbre transfer. Three reasons, in increasing "
          "order of weight. They are not parametrically controllable and not "
          "interpretable. They ship weights the browser contract forbids. And "
          "they cannot carry the claim ladder, because every claim in the "
          "interface needs a confidence label grounded in a mechanism a user "
          "can inspect, and a neural generator's mechanism is a weight matrix. "
          "The project's own evidence discipline makes the same argument from "
          "the other side: hand-set "),
        I("physical"),
        T(" extensions, with five interpretable parameters and the "
          "literature's own equations, still had to lose two bake-offs in "
          "public before earning a fit pass. A generator that cannot state its "
          "loss in physical terms could never be judged that way. Learned "
          "components analyse and score. They never generate audio (docs/21 "
          "§21.4)."),
    ])
    P(doc, [
        B("The open problem, named. "),
        T("Under the roadmap sits metrology. The project optimises one number, "
          "the descriptor cosine, which is cluster-safe and audibly blind. It "
          "measures with another, MCD and STFT, which are audibly faithful and "
          "hostile to an optimiser. It has refuted the learned third, the "
          "realism logit. Every future fit gate reads the bench, and every "
          "future objective candidate is pre-registered against it. Structure "
          "first, and meaning only from playback. That ordering is the "
          "roadmap's spine, and it does not move."),
    ])

    # ============ 12. References ============
    H1(doc, "12", "References")
    P(doc, [
        T("External literature, numbered in list order, resolving the "
          "superscripts in the body. Internal research notes are cited inline "
          "as “docs/19 §19.2”, which is how they are addressed in the "
          "repository. They live in the "),
        I("docs/"),
        T(" directory, and docs/08 is the normative contract both halves of the "
          "codebase implement."),
    ], space_after=10)
    for i, (_, text) in enumerate(REFERENCES):
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(3.5)
        p.paragraph_format.left_indent = Cm(0.85)
        p.paragraph_format.first_line_indent = Cm(-0.85)
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        r1 = p.add_run(f"[{i + 1}]  ")
        r1.font.size = Pt(8.5)
        r1.font.name = SANS
        r1.font.color.rgb = VIOLET_RGB
        r2 = p.add_run(text)
        r2.font.size = Pt(8.5)

    doc.save(DOCX_PATH)
    return DOCX_PATH


def main():
    os.makedirs(FIG, exist_ok=True)
    eq_paths = render_equations()
    figs = {
        "ladder": fig_claim_ladder(),
        "arch": fig_architecture(),
        "chain": fig_signal_chain(),
        "pin": fig_tonal_pin(),
        "corpus": fig_corpus(),
        "spaces": fig_spaces(),
        "confound": fig_confound(),
        "avex": fig_avex(),
        "map": fig_map_quality(),
        "syntax": fig_syntax(),
        "ruler": fig_ruler(),
    }
    out = build_docx(eq_paths, figs)
    print(f"equations: {len(eq_paths)} in {os.path.join(FIG, 'eq')}")
    print(f"figures:   {len(figs)} in {FIG}")
    print(f"docx:      {out}")


if __name__ == "__main__":
    main()

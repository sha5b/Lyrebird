#!/usr/bin/env python3
"""Build the Birdy whitepaper: charts, typeset equations, DOCX.

Run:  cd pipeline && uv run python ../docs/whitepaper/build_whitepaper.py

Every number in the document is sourced from the repo's research notes
(docs/NN, HANDOFF.md, AGENTS.md) — the citation for each figure is in its
caption, and in-text superscripts resolve to the numbered References section.
Debug-scale measurements are labelled as such in the captions, per the
project's evidence discipline (docs/19 §19.5, docs/17 §17.6). No claim in
this document goes beyond what the cited sources state; comparison cells
with no documented answer say "not documented".

Deterministic: no randomness anywhere (charts are plotted from literals).
"""

import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
from PIL import Image

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Inches, Pt, RGBColor

HERE = os.path.dirname(os.path.abspath(__file__))
FIG = os.path.join(HERE, "figures")
DOCX_PATH = os.path.join(HERE, "birdy-whitepaper.docx")

ACCENT = "#7a4fa3"
GREY = "#888888"
INK = RGBColor(0x24, 0x1F, 0x33)
ACCENT_RGB = RGBColor(0x7A, 0x4F, 0xA3)

plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.size": 9,
        "mathtext.fontset": "cm",
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "axes.edgecolor": "#bbbbbb",
        "axes.linewidth": 0.8,
        "axes.grid": True,
        "grid.color": "#e4e4e4",
        "grid.linewidth": 0.7,
        "xtick.color": "#555555",
        "ytick.color": "#555555",
        "text.color": "#241f33",
        "axes.labelcolor": "#241f33",
        "figure.dpi": 200,
        "savefig.dpi": 200,
    }
)


# --------------------------------------------------------------------------
# Equations (matplotlib mathtext -> transparent PNG, 300 dpi)
# --------------------------------------------------------------------------

EQUATIONS = {
    # The syrinx oscillator — docs/08 §8.1 (Amador & Mindlin 2021 form).
    "syrinx": (
        r"\dot{x} = y, \qquad "
        r"\dot{y} = -\alpha\, g^{2} - \beta\, g^{2} x - g^{2} x^{3}"
        r" - g\, x^{2} y + g^{2} x^{2} - g\, x y"
    ),
    # gamma is a pure time-scale — docs/08 §8.1 (measured PHI).
    "gamma": r"f_{0} = g \cdot \Phi(\alpha, \beta), \qquad \Phi(0.1,\,1) = 0.17061",
    # Tracheal stopped-tube comb — docs/08 §8.1a.
    "comb": r"f_{n} = (2n-1)\, f_{1}, \quad n = 1 \ldots 4,"
    r" \qquad f_{1} = \frac{c}{4L}",
    # Respiratory oscillator — docs/15 §1 (Fainstein, Goller & Mindlin 2025, eqs 1-2).
    "respiration": (
        r"\tau_{x}\, \dot{x} = -(1 + x^{2})\,x - p + F_{0}\, f(t), \qquad "
        r"\tau_{p}\, \dot{p} = -(1 + x^{2})\,x - \left(1 + \alpha(p)\right) p + F_{0}\, f(t)"
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
    # The fit objective — docs/08 §8.2, docs/09 §9.2.
    "cosine": (
        r"\mathrm{score} = \cos\left( z_{\mathrm{syn}},\, z_{\mathrm{ref}} \right)"
        r" = \frac{z_{\mathrm{syn}} \cdot z_{\mathrm{ref}}"
        r"}{\left\| z_{\mathrm{syn}} \right\| \, \left\| z_{\mathrm{ref}} \right\|}"
    ),
    # kNN lift against a permutation null — geometry.py.
    "knnlift": (
        r"\mathrm{lift}(G) = A(G) - \mathbb{E}_{\pi}\left[ A(\pi G) \right]"
    ),
}


def render_equations() -> dict:
    paths = {}
    eq_dir = os.path.join(FIG, "eq")
    os.makedirs(eq_dir, exist_ok=True)
    for name, tex in EQUATIONS.items():
        path = os.path.join(eq_dir, f"{name}.png")
        fig = plt.figure(figsize=(0.1, 0.1))
        fig.text(0, 0, f"${tex}$", fontsize=13, color="#241f33")
        fig.savefig(path, dpi=300, transparent=True, bbox_inches="tight", pad_inches=0.03)
        plt.close(fig)
        paths[name] = path
    return paths


# --------------------------------------------------------------------------
# Charts (all numbers literal, from the docs cited in each caption)
# --------------------------------------------------------------------------


def _save(fig, name) -> str:
    path = os.path.join(FIG, name)
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def _box(ax, x, y, w, h, text, fc="white", ec=ACCENT, fs=7.6, dashed=False):
    ax.add_patch(
        FancyBboxPatch(
            (x, y), w, h,
            boxstyle="round,pad=0.06,rounding_size=0.09",
            linewidth=1.0, edgecolor=ec, facecolor=fc,
            linestyle=(0, (4, 3)) if dashed else "-",
        )
    )
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs, color="#241f33")


def _arrow(ax, x1, y1, x2, y2, dashed=False, both=False):
    ax.add_patch(
        FancyArrowPatch(
            (x1, y1), (x2, y2),
            arrowstyle="<|-|>" if both else "-|>",
            mutation_scale=11, linewidth=1.0,
            color="#999999" if dashed else "#666666",
            linestyle=(0, (4, 3)) if dashed else "-",
        )
    )


def chart_bench() -> str:
    """docs/19 §19.2 + §19.4: the cosine does not track audible distortion; the mel target does."""
    labels = ["cosine vs MCD", "cosine vs STFT error", "melTarget vs MCD"]
    pearson = [0.106, 0.102, -0.305]
    spearman = [0.100, 0.111, -0.420]
    x = range(len(labels))
    w = 0.34
    fig, ax = plt.subplots(figsize=(6.3, 2.7))
    ax.bar([i - w / 2 for i in x], pearson, w, color=ACCENT, label="Pearson")
    ax.bar([i + w / 2 for i in x], spearman, w, color=GREY, label="Spearman")
    ax.axhline(0, color="#555555", linewidth=0.8)
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels)
    ax.set_ylabel("correlation")
    ax.set_ylim(-0.55, 0.3)
    ax.legend(frameon=False, loc="upper left", ncols=2)
    for i, (p, s) in enumerate(zip(pearson, spearman)):
        ax.text(i - w / 2, p + (0.03 if p >= 0 else -0.05), f"{p:+.3f}", ha="center", fontsize=7.5)
        ax.text(i + w / 2, s + (0.03 if s >= 0 else -0.05), f"{s:+.3f}", ha="center", fontsize=7.5)
    return _save(fig, "bench-cosine-vs-distortion.png")


def chart_adversarial() -> str:
    """docs/17 §17.3 (recordist head) and §17.5 (recording-within-species head)."""
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(6.6, 2.6), sharey=True)
    # §17.3: w 0.05 / 0.1 / 0.3 (aug-only point at "aug"); baseline at "base".
    x1 = ["base", "aug", "0.05", "0.1", "0.3"]
    rec1 = [0.285, 0.283, 0.191, 0.243, 0.110]
    sp1 = [0.429, 0.442, 0.305, 0.399, 0.172]
    a1.plot(x1, rec1, "o-", color=ACCENT, label="recordist lift")
    a1.plot(x1, sp1, "s--", color=GREY, label="species lift")
    a1.axhline(0.7 * 0.285, color=ACCENT, linewidth=0.8, linestyle=":", alpha=0.7)
    a1.set_title("recordist-adversarial head (docs/17 §17.3)", fontsize=8.5)
    a1.set_xlabel("adversarial weight w")
    a1.set_ylabel("kNN lift")
    a1.legend(frameon=False, fontsize=7.5, loc="lower left")
    a1.tick_params(axis="x", labelsize=8)
    # §17.5: ws 0.01..0.1
    x2 = ["base", "0.01", "0.03", "0.05", "0.1"]
    rec2 = [0.277, 0.280, 0.273, 0.268, 0.260]
    sp2 = [0.412, 0.438, 0.458, 0.453, 0.455]
    a2.plot(x2, rec2, "o-", color=ACCENT, label="recordist lift")
    a2.plot(x2, sp2, "s--", color=GREY, label="species lift")
    a2.axhline(0.7 * 0.277, color=ACCENT, linewidth=0.8, linestyle=":", alpha=0.7)
    a2.set_title("recording-within-species head (§17.5)", fontsize=8.5)
    a2.set_xlabel("adversarial weight w")
    a2.tick_params(axis="x", labelsize=8)
    fig.tight_layout()
    return _save(fig, "adversarial-sweeps.png")


def chart_avex() -> str:
    """docs/17 §17.4 (12 species) and §17.6 (63 species) cross-domain retrieval."""
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(6.6, 2.6))
    arms = ["A\nsingle\ndomain", "B\nnaive\nmerge", "C\nx-domain\npositives"]
    v1 = [0.360, 0.504, 0.638]
    v2 = [0.058, 0.093, 0.110]
    a1.bar(range(3), v1, color=[GREY, ACCENT, ACCENT], width=0.6)
    a1.axhline(0.083, color="#555555", linewidth=0.9, linestyle="--")
    a1.set_xlim(-0.6, 3.4)
    a1.text(2.55, 0.095, "chance 0.083", fontsize=7.5, color="#555555", ha="left")
    for i, v in enumerate(v1):
        a1.text(i, v + 0.015, f"{v:.3f}", ha="center", fontsize=8)
    a1.set_xticks(range(3))
    a1.set_xticklabels(arms, fontsize=7.5)
    a1.set_ylim(0, 0.72)
    a1.set_title("first test — 12 species (§17.4)", fontsize=8.5)
    a1.set_ylabel("cross-domain species retrieval")
    a2.bar(range(3), v2, color=[GREY, ACCENT, ACCENT], width=0.6)
    a2.axhline(0.016, color="#555555", linewidth=0.9, linestyle="--")
    a2.set_xlim(-0.6, 3.4)
    a2.text(2.55, 0.022, "chance 0.016", fontsize=7.5, color="#555555", ha="left")
    for i, v in enumerate(v2):
        a2.text(i, v + 0.004, f"{v:.3f}", ha="center", fontsize=8)
    a2.set_xticks(range(3))
    a2.set_xticklabels(arms, fontsize=7.5)
    a2.set_ylim(0, 0.135)
    a2.set_title("bigger re-test — 63 species (§17.6)", fontsize=8.5)
    fig.tight_layout()
    return _save(fig, "avex-arms.png")


def chart_spacemap() -> str:
    """docs/20 §20.1: decomposition of the 38.6 % centroid-agreement loss."""
    causes = [
        "boundary near-ties\n(true-space margin < 0.05)",
        "mid-margin (0.05–0.1),\nmostly bad sessions",
        "big-margin genuine map failure\n(unseen recordist)",
        "big-margin, seen recordist,\nmap cosine < 0.90",
        "residual unlucky geometry",
    ]
    shares = [76.4, 18.5, 2.6, 1.7, 0.8]
    colors = [GREY, GREY, ACCENT, ACCENT, GREY]
    fig, ax = plt.subplots(figsize=(6.3, 2.6))
    y = range(len(causes))[::-1]
    ax.barh(list(y), shares, color=colors, height=0.62)
    for yi, s in zip(y, shares):
        ax.text(s + 1.2, yi, f"{s:.1f} %", va="center", fontsize=8)
    ax.set_yticks(list(y))
    ax.set_yticklabels(causes, fontsize=8)
    ax.set_xlabel("share of the agreement loss (%)")
    ax.set_xlim(0, 88)
    return _save(fig, "spacemap-loss.png")


def chart_session_gate() -> str:
    """docs/20 §20.3.2: per-signal AUC against the bad-session label."""
    labels = ["off-manifold\n5-NN distance", "mapped-norm\ndeviation", "two-signal\ncombination"]
    aucs = [0.953, 0.922, 0.954]
    fig, ax = plt.subplots(figsize=(5.2, 2.5))
    ax.bar(range(3), aucs, color=[ACCENT, GREY, ACCENT], width=0.55)
    ax.axhline(0.9, color="#555555", linewidth=0.9, linestyle="--")
    ax.text(2.4, 0.905, "adoption gate AUC 0.9", fontsize=7.5, color="#555555", ha="right")
    for i, v in enumerate(aucs):
        ax.text(i, v + 0.004, f"{v:.3f}", ha="center", fontsize=8)
    ax.set_xticks(range(3))
    ax.set_xticklabels(labels, fontsize=8)
    ax.set_ylim(0.85, 0.99)
    ax.set_ylabel("AUC")
    return _save(fig, "session-gate-auc.png")


def chart_depth() -> str:
    """docs/18 P1/debug-100 note: only 12 of 100 species have >= 20 bouts."""
    fig, ax = plt.subplots(figsize=(6.0, 1.5))
    ax.barh([0], [12], color=ACCENT, height=0.5, label="≥ 20 bouts (12)")
    ax.barh([0], [88], left=[12], color="#d8d8d8", height=0.5, label="< 20 bouts (88)")
    ax.set_xlim(0, 100)
    ax.set_yticks([])
    ax.set_xlabel("species of the debug-100 store")
    ax.text(6, 0, "12", ha="center", va="center", color="white", fontsize=10, fontweight="bold")
    ax.text(56, 0, "88", ha="center", va="center", color="#555555", fontsize=10)
    ax.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.55), ncols=2, fontsize=8)
    return _save(fig, "corpus-depth.png")


def chart_wins() -> str:
    """Headline measured gains; each row maps before -> 0 and after -> 1 visually.
    Numbers: docs/09 §9.8, docs/16 §16.2/§16.3/§16.7, docs/18."""
    rows = [
        ("species placement, 40 k store\n(chance 7.7 %)", "38.4 %", "51.7 %", "+13.3 pts"),
        ("novelty ROC,\nthree corpus epochs", "0.596", "0.846", "+0.250"),
        ("fricative bench,\nmedian cosine", "0.584", "0.656", "+0.072"),
        ("grammar backoff, unseen\ntransitions (2 stores)", "0", "+1.90 / +2.32", "nats/token"),
        ("learn wall time,\n3 800 species", "≈ 3 h", "≈ 15 min", "12× faster"),
    ]
    fig, ax = plt.subplots(figsize=(6.8, 2.9))
    labels = []
    for i, (label, before, after, delta) in enumerate(rows):
        y = len(rows) - 1 - i
        labels.append(label)
        ax.annotate(
            "", xy=(0.62, y), xytext=(0.30, y),
            arrowprops=dict(arrowstyle="-|>", color=ACCENT, lw=1.4),
        )
        ax.plot(0.30, y, "o", color=GREY, ms=6)
        ax.plot(0.62, y, "o", color=ACCENT, ms=7)
        ax.text(0.30, y + 0.30, before, ha="center", fontsize=7.6, color="#555555")
        ax.text(0.62, y + 0.30, after, ha="center", fontsize=7.8,
                color=ACCENT, fontweight="bold")
        ax.text(0.70, y, delta, va="center", fontsize=7.6, color="#241f33")
    ax.set_yticks(list(range(len(rows))))
    ax.set_yticklabels(labels[::-1], fontsize=8)
    ax.set_xlim(0.2, 1.0)
    ax.set_ylim(-0.6, len(rows) - 0.1)
    ax.set_xticks([])
    for s in ("top", "right", "bottom"):
        ax.spines[s].set_visible(False)
    ax.grid(False)
    fig.tight_layout()
    return _save(fig, "measured-wins.png")


def chart_corpus_growth() -> str:
    """The measurement stores behind this note (docs/08, 09, 14, 16)."""
    stores = [
        ("original 22-species", 39976, 22),
        ("harvest-gan, first", 9041, 25),
        ("harvest-gan at 40 k", 39993, 13),
        ("+ xccoverbl ingest", 39874, 121),
        ("+ iNatSounds 2024", 226264, 3811),
    ]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(6.9, 2.4))
    names = [s[0] for s in stores]
    y = list(range(len(stores)))[::-1]
    a1.barh(y, [s[1] for s in stores], color=ACCENT, height=0.6)
    a1.set_xscale("log")
    a1.set_xlim(5e3, 9e5)
    for yi, s in zip(y, stores):
        a1.text(s[1] * 1.3, yi, f"{s[1]:,}".replace(",", " "), va="center", fontsize=7.5)
    a1.set_yticks(y)
    a1.set_yticklabels(names, fontsize=8)
    a1.set_xlabel("syllables (log scale)", fontsize=8.5)
    a2.barh(y, [s[2] for s in stores], color=GREY, height=0.6)
    a2.set_xscale("log")
    a2.set_xlim(8, 3e4)
    for yi, s in zip(y, stores):
        a2.text(s[2] * 1.25, yi, f"{s[2]:,}".replace(",", " "), va="center", fontsize=7.5)
    a2.set_yticks(y)
    a2.set_yticklabels([])
    a2.set_xlabel("species (log scale)", fontsize=8.5)
    fig.tight_layout()
    return _save(fig, "corpus-growth.png")


def diagram_signal_chain() -> str:
    """The synthesis signal chain with the two parked extensions (docs/08 §8.1, docs/15)."""
    fig, ax = plt.subplots(figsize=(7.2, 3.3))
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 5.4)
    ax.axis("off")
    ax.grid(False)

    y, h = 2.7, 1.25
    # gesture contours
    _box(ax, 0.3, y + 0.95, 1.9, 0.85, "α(t)  air-sac pressure\n≈ loudness", ec=GREY, fs=7.2)
    _box(ax, 0.3, y - 0.55, 1.9, 0.85, "β(t)  syringeal tension\n≈ pitch", ec=GREY, fs=7.2)
    # main chain
    _box(ax, 2.8, y, 1.75, h, "syrinx oscillator (1)\nHopf / SNIC timbre\nγ per syllable (2)", fs=7.2)
    _box(ax, 5.0, y, 1.55, h, "turbulence at\nthe labia\n∝ air flow", fs=7.2)
    _box(ax, 7.0, y, 1.6, h, "f0-tracking\nresonance\n(tract retuning)", fs=7.2)
    _box(ax, 9.05, y, 1.65, h, "tracheal comb (3)\nstopped tube,\nf1 per species", fs=7.2)
    _arrow(ax, 2.2, y + 1.35, 2.85, y + 0.95)
    _arrow(ax, 2.2, y - 0.1, 2.85, y + 0.3)
    _arrow(ax, 4.55, y + h / 2, 5.0, y + h / 2)
    _arrow(ax, 6.55, y + h / 2, 7.0, y + h / 2)
    _arrow(ax, 8.6, y + h / 2, 9.05, y + h / 2)
    _arrow(ax, 10.7, y + h / 2, 11.5, y + h / 2)
    ax.text(11.5, y + h / 2 + 0.35, "sound", fontsize=7.6, ha="center", color="#241f33")
    ax.text(1.25, y - 0.95, "+ 140 Hz noise on β (roughness)", fontsize=7.0,
            color="#555555", ha="center")
    # parked extensions
    _box(ax, 0.3, 0.35, 3.1, 0.9, "respiration (4) — parked:\nreplaces the envelope",
         dashed=True, ec=GREY, fs=7.0)
    _box(ax, 3.9, 0.35, 3.1, 0.9, "second voice — parked:\ncoupled via tracheal pressure",
         dashed=True, ec=GREY, fs=7.0)
    _arrow(ax, 1.85, 1.25, 1.6, 2.15, dashed=True)
    _arrow(ax, 5.45, 1.25, 4.3, 2.7, dashed=True)
    ax.text(9.2, 0.8, "dashed = implemented and parity-tested,\noff by default (ship gates: docs/15 §1, §5)",
            fontsize=7.0, color="#777777", ha="center")
    fig.tight_layout()
    return _save(fig, "signal-chain.png")


def diagram_spaces() -> str:
    """The two feature spaces and the RFF bridge (docs/11 §11.3, docs/20 §20.1)."""
    fig, ax = plt.subplots(figsize=(6.9, 2.8))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 4.7)
    ax.axis("off")
    ax.grid(False)

    _box(ax, 0.3, 1.7, 3.6, 2.3,
         "28-d descriptor\n13 MFCC means · 13 MFCC stds\nlog₂ spectral centroid · flatness\n\n"
         "computed identically in\nPython and the browser", ec=GREY, fs=7.4)
    _box(ax, 6.1, 1.7, 3.6, 2.3,
         "32-d embedding\ncritic trunk, NT-Xent-trained\n\n"
         "the galaxy's coordinate system\nno torch ships to the browser", fs=7.4)
    _arrow(ax, 3.9, 2.85, 6.1, 2.85)
    ax.text(5.0, 3.25, "RFF (D = 2048, σ = 4)\n+ ridge (λ = 1)", ha="center", fontsize=7.4)
    ax.text(5.0, 1.15, "ship gate: median held-out cosine ≥ 0.8 — the debug build passes at 0.962",
            ha="center", fontsize=7.2, color="#555555")
    ax.text(5.0, 0.6, "knot agreement: 0.61 raw · 0.91 tie-adjusted · 0.78 species-level (docs/20)",
            ha="center", fontsize=7.2, color="#555555")
    fig.tight_layout()
    return _save(fig, "spaces-bridge.png")


def diagram_architecture() -> str:
    """Five stations, one direction: harvest -> store -> learn -> build -> browser."""
    fig, ax = plt.subplots(figsize=(7.3, 3.6))
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 6.1)
    ax.axis("off")
    ax.grid(False)

    # containers
    ax.add_patch(FancyBboxPatch((0.15, 1.6), 9.0, 4.3, boxstyle="round,pad=0.08",
                                linewidth=1.1, edgecolor="#c9c9c9", facecolor="#fafafa"))
    ax.text(4.65, 5.68, "offline pipeline (Python) — no audio retained",
            ha="center", fontsize=8.4, color="#555555")
    ax.add_patch(FancyBboxPatch((9.35, 1.6), 2.5, 4.3, boxstyle="round,pad=0.08",
                                linewidth=1.1, edgecolor="#c9c9c9", facecolor="#fafafa"))
    ax.text(10.6, 5.68, "browser (no torch)", ha="center", fontsize=8.4, color="#555555")

    y, h, w = 3.35, 1.55, 1.95
    xs = [0.45, 2.75, 5.05, 7.35, 9.65]
    _box(ax, xs[0], y, w, h, "harvest\nxeno-canto · iNatSounds\ndecode → describe\n→ delete", ec=GREY, fs=7.2)
    _box(ax, xs[1], y, w, h, "store\n28-d descriptors\n+ 32×23 mel patches\n(audio deleted)", ec=GREY, fs=7.2)
    _box(ax, xs[2], y, w, h, "learn\nKMeans types +\ngesture inversion\n(bit-identical ∥)", fs=7.2)
    _box(ax, xs[3], y, w, h, "build\ngalaxy assets\nJSON / f32\nno torch weights", fc="#f2ecf7", fs=7.2)
    _box(ax, xs[4], y, w, h, "app\n3-D galaxy · synth\nmic analysis", fc="#f2ecf7", fs=7.2)
    for i, x in enumerate(xs):
        ax.add_patch(plt.Circle((x + w / 2, y + h + 0.42), 0.21, facecolor=ACCENT, edgecolor="none"))
        ax.text(x + w / 2, y + h + 0.42, str(i + 1), ha="center", va="center",
                fontsize=8, color="white", fontweight="bold")
    for i in range(4):
        _arrow(ax, xs[i] + w + 0.04, y + h / 2, xs[i + 1] - 0.04, y + h / 2)
    # the critic feeds the learn and the build
    _box(ax, 5.05, 1.9, 1.95, 1.0, "critic (3-head CNN)\nrealism · species · NT-Xent (5)", fs=6.8)
    _arrow(ax, 6.02, 2.9, 6.02, 3.35, both=True)

    # honesty band
    ax.add_patch(FancyBboxPatch((0.45, 0.2), 11.15, 0.85, boxstyle="round,pad=0.06",
                                linewidth=1.0, edgecolor=GREY, facecolor="#f5f5f5"))
    ax.text(6.0, 0.62,
            "honesty layer over everything the app shows:  experimental · documented · inferred · "
            "invented · “unlabelled: real acoustics, no documented function”",
            ha="center", va="center", fontsize=7.2, color="#241f33")
    fig.tight_layout()
    return _save(fig, "architecture.png")


# --------------------------------------------------------------------------
# References (numbered; in-text superscripts resolve here)
# --------------------------------------------------------------------------

REFERENCES = [
    ("rutz", "Rutz, C. et al., “Using machine learning to decode animal communication”, Science 2023. DOI 10.1126/science.adg7314."),
    ("suzuki", "Suzuki, T.N., Wheatcroft, D. & Griesser, M., “Experimental evidence for compositional syntax in bird calls”, Nature Communications 2016 (great tit ABC–D)."),
    ("griesser", "Griesser, M., “Referential calls signal predator behavior in a group-living bird species”, Current Biology 2008 (Siberian jay)."),
    ("freeberg", "Freeberg, T.M. et al. 2003 — black-capped chickadee chick-a-dee call: four note types, strict A→B→C→D ordering, D-count scaling with threat."),
    ("hultsch", "Hultsch, H. & Todt, D. — nightingale song-type organisation (~180–200 types per male, package organisation, countersinging rules); as reviewed in Birdy research notes docs/01 §1.1 and docs/03 §3.2."),
    ("okanoya", "Okanoya, K. 2004; Katahira, K. et al. — finite-state song syntax of the Bengalese finch."),
    ("mindlinbook", "Mindlin, G.B. & Laje, R., The Physics of Birdsong, Springer 2005."),
    ("laje2005", "Laje, R. & Mindlin, G.B., “Source–source and source–filter coupling in birdsong production”, Physical Review E 72:036218 (2005)."),
    ("amador2021", "Amador, A. & Mindlin, G.B., “Low-dimensional dynamics of birdsong production and imitation”, Frontiers in Neuroscience 15:647978 (2021)."),
    ("amador2013", "Amador, A., Perl, Y.S., Mindlin, G.B. & Margoliash, D., “Elemental gesture dynamics are encoded by song premotor cortical neurons”, Nature 2013 — synthetic song from the low-dimensional model drives HVC neurons indistinguishably from real song."),
    ("sitt2008", "Sitt, J.D., Amador, A., Goller, F. & Mindlin, G.B., “Dynamical origin of spectrally rich vocalizations in birdsong”, Physical Review E 78:011905 (2008)."),
    ("sitt2010", "Sitt, J.D. et al., “Physiologically driven avian vocal synthesizer”, Physical Review E 81:031927 (2010)."),
    ("perl2011", "Perl, Y.S., Arneodo, E.M., Amador, A., Goller, F. & Mindlin, G.B., Physical Review E 84:051909 (2011) — χ²(γ) fit over 28 segments → γ = 24 000."),
    ("boari2015", "Boari, S., Perl, Y.S., Amador, A., Margoliash, D. & Mindlin, G.B., “Automatic reconstruction of physiological gestures used in a model of birdsong production”, Journal of Neurophysiology 114:2912 (2015)."),
    ("bistel2024", "Bistel, A., Amador, A. & Mindlin, G.B., “Response of wild songbirds to songs synthesized with a low-dimensional model”, Physical Review E 109:054410 (2024) — 256 playback tests, 26 wild rufous-collared sparrows, 15 sites: no significant difference between responses to real and synthetic song."),
    ("fainstein2025", "Fainstein, D., Goller, F. & Mindlin, G.B., “Nonlinear biomechanical resonances in birdsong”, arXiv:2509.11019 (2025)."),
    ("nowicki1987", "Nowicki, S., “Vocal tract resonances in oscine bird sound production: evidence from birdsongs in a helium atmosphere”, Nature 325:53 (1987)."),
    ("beckers2003", "Beckers, G.J.L., Suthers, R.A. & ten Cate, C., “Pure-tone birdsong by resonance filtering of harmonic overtones”, PNAS 2003."),
    ("nelson2005", "Nelson, B.S., Beckers, G.J.L. & Suthers, R.A., “Vocal tract filtering and sound radiation in a songbird”, Journal of Experimental Biology 208:297 (2005)."),
    ("riede2006", "Riede, T., Suthers, R.A., Fletcher, N.H. & Blevins, W.E., “Songbirds tune their vocal tract to the fundamental frequency of their song”, PNAS 103:5543 (2006)."),
    ("arneodo2012", "Arneodo, E.M. et al., PLOS Computational Biology 2012 — the low-dimensional syrinx model running as a real-time neural prosthesis."),
    ("sainburg2020", "Sainburg, T., Thielk, M. & Gentner, T.Q., “Finding, visualizing, and quantifying latent structure across diverse animal vocal repertoires”, PLOS Computational Biology 2020."),
    ("goffinet2021", "Goffinet, J. et al., “Low-dimensional learned feature spaces quantify individual and group differences in vocal repertoires”, eLife 2021."),
    ("birdsounds", "McDonald, K., Tan, M. & Mann, Y., Google Creative Lab “Bird Sounds” experiment, 2016 (Apache 2.0) — t-SNE map of thousands of bird recordings."),
    ("perch", "Google Perch / Perch 2.0, arXiv:2508.04665 (2025), Apache 2.0 — 14 597-species bioacoustic embedding model."),
    ("birdnet", "BirdNET, Cornell Lab of Ornithology (CC BY-NC-SA, non-commercial)."),
    ("moummad", "Moummad, I. et al., domain-invariant contrastive learning for bioacoustics, arXiv:2409.08589."),
    ("morocutti", "Morocutti, F. et al., impulse-response augmentation + Freq-MixStyle for device-invariant audio classification, arXiv:2305.07499."),
    ("avex", "AVEX — corpus diversity over architecture for bioacoustic embeddings, arXiv:2508.11845."),
    ("jin2011", "Jin, D.Z. & Kozhevnikov, A.A. 2011 — repeat-count-dependent transition structure in Bengalese finch song."),
    ("lu2025", "Lu, K. et al. 2025 — partially observable Markov models beat HMMs on Bengalese finch song; as cited in Birdy research notes docs/18."),
    ("sharma2024", "Sharma, P. et al. 2024 (Project CETI) — sperm-whale codas factorized into a combinatorial 156-unit alphabet; as cited in Birdy research notes docs/18 P3."),
    ("chen2013", "Chen, R. et al., PLOS ONE 2013 — rendition-to-rendition f0 and amplitude near-uncorrelated (R² ≈ 0.03)."),
    ("riedegoller", "Riede, T. & Goller, F., “Peripheral mechanisms for vocal production in birds” — modulation below 80 Hz is respiratory, 80–250 Hz syringeal."),
    # Internal research notes
    ("d02", "Birdy research notes, docs/02-procedural-voice-engine.md."),
    ("d03", "Birdy research notes, docs/03-decoding-science.md."),
    ("d06", "Birdy research notes, docs/06-architecture.md."),
    ("d08", "Birdy research notes, docs/08-implementation.md (normative contract)."),
    ("d09", "Birdy research notes, docs/09-learned-objective-plan.md."),
    ("d10", "Birdy research notes, docs/10-real-data-galaxy.md."),
    ("d11", "Birdy research notes, docs/11-critic-47k-map-coverage.md."),
    ("d12", "Birdy research notes, docs/12-song-level-types.md."),
    ("d13", "Birdy research notes, docs/13-sources-and-complexification.md."),
    ("d14", "Birdy research notes, docs/14-xccoverbl-ingest.md."),
    ("d15", "Birdy research notes, docs/15-synth-extensions-math.md."),
    ("d16", "Birdy research notes, docs/16-inat-critic-naturalness.md."),
    ("d17", "Birdy research notes, docs/17-source-invariance.md."),
    ("d18", "Birdy research notes, docs/18-syntax-roadmap.md."),
    ("d19", "Birdy research notes, docs/19-spectral-bench.md."),
    ("d20", "Birdy research notes, docs/20-spacemap-agreement.md."),
    ("handoff", "Birdy session handoff, HANDOFF.md (2026-07-30 and 2026-07-31 entries)."),
    ("agents", "Birdy repository conventions, AGENTS.md."),
]
REFNUM = {k: i + 1 for i, (k, _) in enumerate(REFERENCES)}


def C(*keys):
    """A superscript citation segment."""
    return ("[" + ",".join(str(REFNUM[k]) for k in keys) + "]", "sup")


# --------------------------------------------------------------------------
# DOCX assembly helpers
# --------------------------------------------------------------------------

CONTENT_WIDTH_CM = 21.0 - 2 * 2.2  # A4 minus margins


def P(doc, segs, style=None, align=None, space_after=6, indent=None):
    """Add a paragraph from (text, style) segments; style in '', 'b', 'i', 'sup'."""
    p = doc.add_paragraph(style=style)
    for text, s in segs:
        run = p.add_run(text)
        if s == "b":
            run.bold = True
        elif s == "i":
            run.italic = True
        elif s == "sup":
            run.font.superscript = True
    if align is not None:
        p.alignment = align
    p.paragraph_format.space_after = Pt(space_after)
    if indent is not None:
        p.paragraph_format.left_indent = Cm(indent)
    return p


def T(text):
    return (text, "")


def B(text):
    return (text, "b")


def I(text):
    return (text, "i")


def H1(doc, text):
    return doc.add_heading(text, level=1)


def H2(doc, text):
    return doc.add_heading(text, level=2)


def plain_terms(doc, text):
    p = P(doc, [B("In plain terms. "), T(text)], space_after=8)
    for run in p.runs:
        run.font.color.rgb = RGBColor(0x44, 0x3A, 0x5E)
    return p


def add_equation(doc, eq_paths, name, number):
    path = eq_paths[name]
    with Image.open(path) as im:
        w_px, h_px = im.size
    h_in = h_px / 300.0
    w_in = w_px / 300.0
    max_w_in = (CONTENT_WIDTH_CM - 2.0) / 2.54
    if w_in > max_w_in:
        h_in *= max_w_in / w_in
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run().add_picture(path, height=Inches(h_in))
    num = p.add_run(f"    ({number})")
    num.font.size = Pt(9)
    num.font.color.rgb = RGBColor(0x66, 0x66, 0x66)
    p.paragraph_format.space_after = Pt(8)
    return p


def add_caption(doc, caption_segs):
    cap = doc.add_paragraph()
    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for text, s in caption_segs:
        run = cap.add_run(text)
        run.font.size = Pt(8.5)
        run.font.color.rgb = RGBColor(0x55, 0x55, 0x55)
        if s == "b":
            run.bold = True
        elif s == "i":
            run.italic = True
        elif s == "sup":
            run.font.superscript = True
    cap.paragraph_format.space_after = Pt(10)
    return cap


def add_figure(doc, path, caption_segs, width_cm=15.6):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run().add_picture(path, width=Cm(width_cm))
    p.paragraph_format.space_after = Pt(2)
    return add_caption(doc, caption_segs)


def add_page_number_footer(doc):
    footer = doc.sections[0].footer
    p = footer.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run("Birdy whitepaper — working draft · p. ")
    run.font.size = Pt(8)
    run.font.color.rgb = RGBColor(0x88, 0x88, 0x88)
    fld_begin = OxmlElement("w:fldChar")
    fld_begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = "PAGE"
    fld_end = OxmlElement("w:fldChar")
    fld_end.set(qn("w:fldCharType"), "end")
    run2 = p.add_run()
    run2.font.size = Pt(8)
    run2.font.color.rgb = RGBColor(0x88, 0x88, 0x88)
    run2._r.append(fld_begin)
    run2._r.append(instr)
    run2._r.append(fld_end)


def add_header(doc):
    header = doc.sections[0].header
    p = header.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = p.add_run("Birdy — A Physical Voice for Understanding Birdsong")
    run.font.size = Pt(8)
    run.font.color.rgb = RGBColor(0x88, 0x88, 0x88)


def style_document(doc):
    normal = doc.styles["Normal"]
    normal.font.name = "Cambria"
    normal.font.size = Pt(10.5)
    normal.element.rPr.rFonts.set(qn("w:eastAsia"), "Cambria")
    normal.paragraph_format.space_after = Pt(6)
    normal.paragraph_format.line_spacing = 1.15
    normal.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    for level, size in (("Heading 1", 15), ("Heading 2", 12)):
        st = doc.styles[level]
        st.font.name = "Cambria"
        st.font.size = Pt(size)
        st.font.bold = True
        st.font.color.rgb = INK
        st.paragraph_format.space_before = Pt(16 if level == "Heading 1" else 10)
        st.paragraph_format.space_after = Pt(6)
        st.paragraph_format.keep_with_next = True
    for section in doc.sections:
        section.top_margin = Cm(2.2)
        section.bottom_margin = Cm(2.2)
        section.left_margin = Cm(2.2)
        section.right_margin = Cm(2.2)


def add_table(doc, header, rows, widths=None, font_size=9):
    table = doc.add_table(rows=1 + len(rows), cols=len(header))
    table.style = "Light Grid Accent 1"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    for j, h in enumerate(header):
        cell = table.rows[0].cells[j]
        cell.text = ""
        run = cell.paragraphs[0].add_run(h)
        run.bold = True
        run.font.size = Pt(font_size)
    for i, row in enumerate(rows):
        for j, val in enumerate(row):
            cell = table.rows[i + 1].cells[j]
            cell.text = ""
            run = cell.paragraphs[0].add_run(str(val))
            run.font.size = Pt(font_size)
    if widths:
        for j, w in enumerate(widths):
            for row in table.rows:
                row.cells[j].width = Cm(w)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)
    return table


# --------------------------------------------------------------------------
# The document
# --------------------------------------------------------------------------


def build_docx(eq_paths, figs):
    doc = Document()
    style_document(doc)
    add_page_number_footer(doc)
    add_header(doc)

    # ---- Cover ----
    for _ in range(4):
        doc.add_paragraph()
    title = P(
        doc,
        [T("Birdy — A Physical Voice for Understanding Birdsong")],
        align=WD_ALIGN_PARAGRAPH.CENTER,
    )
    title.runs[0].font.size = Pt(26)
    title.runs[0].font.bold = True
    title.runs[0].font.color.rgb = INK
    sub = P(
        doc,
        [T("Working draft — internal research note · 2026-08-01")],
        align=WD_ALIGN_PARAGRAPH.CENTER,
    )
    sub.runs[0].font.size = Pt(11)
    sub.runs[0].font.color.rgb = ACCENT_RGB
    doc.add_paragraph()
    P(
        doc,
        [
            B("Abstract. "),
            T(
                "Birdy is a research programme and an interactive installation. It treats birdsong "
                "as learnable structure. Its voice is a physical model of the avian syrinx, fitted "
                "to field recordings by gesture inversion. Its memory is a measurement-only "
                "corpus: the harvest decodes each recording, describes it as numbers, and deletes "
                "the audio. Its map is a 3-D galaxy with one point per measured syllable. Its "
                "claim to translation is narrow on purpose. The system does functional decoding: "
                "call type to documented behavioural function, with confidence labels. Playback "
                "experiments are the only proof of meaning the field accepts, so the app labels "
                "everything else as what it is. This note describes the instrument, the design "
                "choices and their reasons, the pipeline, and the evidence. It reports what works: "
                "a learned syllable embedding that lifts species placement by up to +13.3 points, "
                "a bit-identical parallel learn, a measured fricative synthesis path, and a "
                "session-quality gate at AUC 0.953. It reports at equal length what does not "
                "work: the fit objective does not track audible distortion, recorder invariance "
                "does not come from loss engineering, and the corpus is too shallow for song "
                "grammar. Negative results stay in the record. That is the method, not an "
                "apology."
            ),
        ],
    )
    doc.add_paragraph()
    kw = P(
        doc,
        [
            B("Keywords. "),
            T("birdsong, syrinx model, gesture inversion, contrastive embedding, bioacoustics, "
              "confidence labels"),
        ],
    )
    for run in kw.runs:
        run.font.size = Pt(9.5)
        run.font.color.rgb = RGBColor(0x55, 0x55, 0x55)
    doc.add_paragraph()
    P(doc, [B("Contents")], space_after=2)
    for line in [
        "1  The premise: what translating birdsong can honestly mean",
        "2  Design choices and why",
        "3  Comparison with other approaches",
        "4  The pipeline, end to end",
        "5  Results: what works (measured)",
        "6  Limitations: what does not work (measured)",
        "7  The unknown-bird pipeline",
        "8  Roadmap",
        "9  References",
    ]:
        P(doc, [T(line)], space_after=2, indent=0.6)
    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)

    # ================= 1. The premise =================
    H1(doc, "1. The premise: what translating birdsong can honestly mean")
    plain_terms(
        doc,
        "A great tit does not improvise. It owns a small set of calls. One of them is a sentence: "
        "three notes that mean “scan for danger”, then one note that means “come here”. Played in "
        "that order, other tits do both. Played backwards, they do nothing. Birdsong is structure "
        "that a machine can learn. But a machine cannot yet say what an unheard call means. The "
        "only accepted proof of meaning is a playback experiment: play the sound to a bird and "
        "watch what the bird does. Birdy builds on both halves of that fact. It learns the "
        "structure aggressively, and it labels the meaning honestly."
    )
    P(doc, [
        T("The field's own position has three parts"),
        C("rutz"),
        T(". Machine learning today can "),
        B("characterize"),
        T(" repertoires: find the units and their structure. It can "),
        B("functionally decode"),
        T(": link signals to context and behaviour. It "),
        B("cannot"),
        T(" translate into propositional human language. That requires playback experiments, and "
          "those exist for only a handful of systems. An ethological asymmetry sharpens the "
          "point. Bird "),
        I("song"),
        T(" has rich syntax but weak or no referential meaning. Bird "),
        I("calls"),
        T(" carry meaning but little syntax (docs/03 §3.1)"),
        C("d03"),
        T(". The defensible product is therefore "),
        B("functional translation"),
        T(": call type to documented behavioural function, species, individual identity, urgency, "
          "each with a confidence label. Word-for-word translation is marketing, and the app says "
          "so in its own interface."),
    ])
    P(doc, [
        T("The studied vocabularies behind the language set are real. The Japanese great tit "
          "composes ABC–D: ABC means “scan for danger”, D means “approach”, and the reversed "
          "order elicits nothing"),
        C("suzuki"),
        T(". The Siberian jay's alarm calls encode predator "),
        I("behaviour"),
        T(" rather than predator species"),
        C("griesser"),
        T(". The chickadee's chick-a-dee call has four note types, a strict A→B→C→D order, and a "
          "D-count that scales with threat"),
        C("freeberg"),
        T(". The nightingale delivers 180–200 song types in rule-governed order"),
        C("hultsch"),
        T(". The Bengalese finch sings a finite-state syntax"),
        C("okanoya"),
        T(". This literature-anchored set is what Birdy calls a documented function. Everything "
          "else is labelled as what it is."),
    ])
    P(doc, [
        B("Why a physical synthesiser. "),
        T("Two reasons anchor the design, one scientific and one legal. Scientifically, a "
          "procedural model of the syrinx is a falsifiable theory of the bird. Its parameters — "
          "air-sac pressure, syringeal tension, tract geometry — are physiological claims. The "
          "model class has passed the strongest realism tests available. Synthetic song from it "
          "drives song premotor neurons indistinguishably from real song"),
        C("amador2013"),
        T(", and wild territorial sparrows respond to it as they do to a real rival"),
        C("bistel2024"),
        T(". Legally, it is the app's only clean voice. xeno-canto recordings carry per-file "
          "Creative Commons licences, largely non-commercial, so Birdy retains and ships "),
        B("no audio at all"),
        T(". The harvest decodes each recording, describes it as numbers, and deletes it "
          "(docs/09 §9.4, AGENTS.md)"),
        C("d09", "agents"),
        T(". Every sound the app makes is synthesized from fitted parameters. Every point in its "
          "galaxy is a measurement, not a file."),
    ])

    # ================= 2. Design choices and why =================
    H1(doc, "2. Design choices and why")
    plain_terms(
        doc,
        "Five choices carry the system: a physical voice, a corpus without audio, a network that "
        "scores but never sings, two feature spaces with a bridge between them, and a label on "
        "every claim. Each choice has a stated reason. Each has a measured consequence later in "
        "this note. Table 1 maps every technique to the place where it runs."
    )
    H2(doc, "2.1 A physical syrinx as the voice")
    P(doc, [
        T("Birds do not sing with a larynx. At the bottom of the windpipe sits the syrinx: soft "
          "membranes that vibrate in the airstream like a reed. The bird has two control knobs. "
          "Air-sac pressure sets how hard it blows, roughly loudness. Syringeal tension sets how "
          "tight the membranes are, roughly pitch. A two-equation model of that reed, driven by "
          "those two knobs, is realistic enough to fool the auditory neurons of a listening bird. "
          "Birdy's voice is that model, plus the physics of the tube above it. The source is the "
          "low-dimensional Mindlin–Laje flapping oscillator"),
        C("mindlinbook", "amador2021"),
        T(", integrated as two first-order equations (docs/08 §8.1)"),
        C("d08"),
        T(":"),
    ])
    add_equation(doc, eq_paths, "syrinx", 1)
    P(doc, [
        T("Here "),
        I("α"),
        T(" is the air-sac pressure and "),
        I("β"),
        T(" the syringeal tension that sets the fundamental frequency. "),
        I("g"),
        T(" is a pure time-scale: rescaling time by "),
        I("g"),
        T(" leaves the equations unchanged. Each syllable gets its own "),
        I("g"),
        T(", chosen to place its median pitch in the well-behaved region of the model:"),
    ])
    add_equation(doc, eq_paths, "gamma", 2)
    P(doc, [
        T("Φ was measured once on a calibration sweep; the value above is measured, not fitted"),
        C("perl2011"),
        T(". The bifurcation that births the oscillation decides the timbre. At high tension a "
          "Hopf bifurcation produces tonal, whistle-like notes. At low tension a saddle-node on a "
          "limit cycle produces pulse-like, harmonically dense sounds"),
        C("sitt2008"),
        T(". The spectral content index is a function of tension alone, so the model's γ-scale — "
          "not its filters — is the tonal-to-rich axis (docs/08 §8.1a). The integrator is "
          "deliberately plain: forward Euler at 16× oversampling at 48 kHz. RK4 agrees to within "
          "2 % of F0, so Euler is what ships (docs/08 §8.1)."),
    ])
    P(doc, [
        T("The vocal tract is not cosmetic. Pure-tone birdsong is a filter effect: the tract "
          "suppresses harmonics, proven by heliox experiments"),
        C("nowicki1987", "beckers2003"),
        T(". Songbirds also retune the oropharyngeal cavity actively, tracking the fundamental "
          "from 1.5 to 5 kHz within a single syllable"),
        C("riede2006"),
        T(". So one resonance follows the instantaneous f0. A tracking resonance alone would make "
          "every spectrum pitch-invariant: two species at the same pitch would become the same "
          "instrument. The part that does not move is the trachea. It is a tube closed at the "
          "syrinx, and it resonates as a stopped quarter-wave pipe at the odd harmonics of one "
          "body-fixed frequency:"),
    ])
    add_equation(doc, eq_paths, "comb", 3)
    P(doc, [
        T("The measured agreement is close: eastern towhee resonances at ~2.0 and ~5.5 kHz "
          "against 1.88 and 5.67 kHz predicted for its 45 mm trachea"),
        C("nelson2005"),
        T(". Birdy measures f₁ per species from the harvest itself. Pitch-dependent structure "
          "averages away, so only body-fixed resonances survive. The comb ships only where the "
          "resynthesis scores better with it: 10 of 22 species earned one on the original corpus "
          "(docs/08 §8.1a)."),
    ])
    add_figure(doc, figs["chain"], [
        B("Figure 1 — The synthesis signal chain. "),
        T("Gesture contours drive the oscillator (eq. 1); texture and the two tract stages shape "
          "the result. The dashed blocks are implemented and parity-tested but off by default, "
          "because their hand-set defaults lost the pre-registered bake-offs. Sources: docs/08 "
          "§8.1, docs/15 §1, §5"),
        C("d08", "d15"),
    ])
    P(doc, [
        B("Texture is physics too. "),
        T("Turbulence is added at the labia and scaled by air flow, so a silent bird does not "
          "hiss. Roughness perturbs "),
        I("β"),
        T(", the tension, not the output. The literature is specific here: matching the "
          "fundamental and the filters was not enough to drive selective forebrain neurons, noise "
          "on tension was required, and an intermediate amount scored best"),
        C("amador2021"),
        T(". The modulation sits at 140 Hz, inside the 80–250 Hz band that syringeal muscle can "
          "follow"),
        C("riedegoller"),
        T(". The perturbation acts through the oscillator, so f0 and amplitude wobble arrive "
          "correlated, as they do in real song (rendition-to-rendition R² ≈ 0.03)"),
        C("chen2013"),
        T(". All noise is a seeded xorshift32 stream, so “the same turbulence” is a testable "
          "claim on both sides of the contract (docs/08 §8.1a)."),
    ])
    P(doc, [
        B("Extensions, measured and mostly parked. "),
        T("Two structural extensions are implemented and parity-tested, but off by default. The "
          "respiratory oscillator"),
        C("fainstein2025"),
        T(" replaces the hand-designed envelope with two-state air-sac dynamics (docs/15 §1)"),
        C("d15"),
        T(":"),
    ])
    add_equation(doc, eq_paths, "respiration", 4)
    P(doc, [
        T("A Heaviside conductance asymmetry between inflow and outflow lets attack shape and "
          "cross-syllable memory emerge instead of being designed. The hand-set default is a "
          "wash on the pre-registered bake-off: median cosine 0.343 → 0.336, placement 17/81 → "
          "20/81. It stays off until the per-species fit wins. The two-voice extension couples "
          "the syrinx's two sides through the shared tracheal pressure"),
        C("laje2005"),
        T(", and it is parked for the same reason: 0.343 → 0.294 with the hand-set default. Both "
          "refutations stay in the record, per the project's rule that a negative result is a "
          "deliverable."),
    ])
    P(doc, [
        B("Why this voice at all. "),
        T("The validation lineage is strong. The model class fools HVC auditory neurons"),
        C("amador2013"),
        T(" and runs as a real-time neural prosthesis"),
        C("arneodo2012"),
        T(". The decisive test is playback: in 256 tests across 26 wild rufous-collared sparrows "
          "at 15 sites, territorial responses to synthetic song did not differ significantly "
          "from responses to real song, and heterospecific song evoked none"),
        C("bistel2024"),
        T(". Automatic gesture inversion from real audio is likewise published"),
        C("boari2015"),
        T(". A generative audio model would trade all of this for raw sample quality the field "
          "itself admits it cannot measure (docs/09 §9.6). The synthesiser stays physical; "
          "learned components analyse and score, they never generate."),
    ])
    H2(doc, "2.2 A measurement-only corpus")
    P(doc, [
        T("No audio is ever retained or shipped. The decode → describe → delete loop is "
          "load-bearing for licensing. One owner-sanctioned exception exists: a local training "
          "cache under "),
        I("pipeline/out/audio-cache/"),
        T(", gitignored and deleted at phase end, which never feeds the app (AGENTS.md)"),
        C("agents"),
        T(". What a syllable leaves behind is two measurements. The first is a 28-dimensional "
          "descriptor: 13 MFCC means, 13 MFCC standard deviations, mean log₂ spectral centroid, "
          "and mean spectral flatness. It is computed under an exact frame-level contract — "
          "48 kHz mono, 1024/512 Hann frames — that the browser re-implements sample for sample "
          "(docs/08 §8.2)"),
        C("d08"),
        T(". The second is a fixed 32×23 log-mel patch: 736 numbers, log-magnitude only, no "
          "phase, resampled onto the syllable's own duration. A patch cannot be turned back into "
          "recognisable audio, so the licensing property holds while a spectral fingerprint "
          "survives (docs/09 §9.3, docs/17 §17)"),
        C("d09", "d17"),
        T("."),
    ])
    H2(doc, "2.3 A critic that scores, never sings")
    P(doc, [
        T("The critic is a small convolutional network over the log-mel patch: 4 conv layers, "
          "spectral normalisation, about 1–3 M parameters. It trains with three heads on a "
          "shared trunk (docs/09 §9.2b). A "),
        B("realism"),
        T(" logit separates real patches from renders of the current fit. A "),
        B("species"),
        T(" classifier reads the harvest labels. A "),
        B("contrastive"),
        T(" head trains with an NT-Xent loss: two augmented views of the same syllable embed "
          "close, different syllables embed apart:"),
    ])
    add_equation(doc, eq_paths, "ntxent", 5)
    P(doc, [
        T("Augmentations are time stretches, gain changes, and added noise — never pitch shifts, "
          "which are genuinely type-diagnostic. Whole species are held out of training, so "
          "realism and novelty are measured on birds the network never saw. The current critic "
          "trained on 2 686 species, with 895 held out entirely. It scores realism AUC 1.000 on "
          "held-out species and species accuracy 0.730 over 2 686 classes (chance 0.0004). Its "
          "novelty ROC is 0.846, flagging 32.2 % of unheard species' syllables at a chosen 5 % "
          "false-positive rate (docs/16 §16.2)"),
        C("d16"),
        T(". The 32-d embedding is the deliverable. The realism logit, as section 6 records, is "
          "a refuted objective. The rule behind this choice: learned components analyse and "
          "score, they never generate. A generator would need its own honesty story; a scorer "
          "inherits the physical synth's story for free."),
    ])
    H2(doc, "2.4 Two feature spaces and a bridge")
    P(doc, [
        T("Two feature spaces coexist. The hand-written 28-d descriptor is what the browser can "
          "compute live. The critic's 32-d embedding is what the galaxy is clustered in. No "
          "torch ships to the browser, so a bridge maps the first space into the second: random "
          "Fourier features approximating an RBF kernel, then a closed-form ridge regression, "
          "fitted on (descriptor, embedding) pairs of the store with knobs chosen on held-out "
          "recordings (docs/11 §11.3)"),
        C("d11"),
        T(":"),
    ])
    add_equation(doc, eq_paths, "rff", 6)
    P(doc, [
        T("The bridge ships as plain numbers: D = 2048 features, σ = 4, λ = 1 on the reference "
          "fit. The map is gated: a median mapped-vs-true cosine below 0.8 on held-out "
          "recordings ships "),
        I("accepted: false"),
        T(", and the browser stays on the 28-d path. On the debug build the gate passes at "
          "0.962. The honest knot-level agreement is 0.61 raw, 0.91 tie-adjusted, and 0.78 at "
          "species level — section 6 decomposes why the raw number undersells the map (docs/20)"),
        C("d20"),
        T(". A linear ridge was the original honest choice. It broke at 0.7997, below the gate, "
          "when the embedding grew finer. The refutation is recorded in place (docs/11 §11.3)."),
    ])
    add_figure(doc, figs["spaces"], [
        B("Figure 2 — Two feature spaces and the bridge. "),
        T("The browser computes only the 28-d descriptor; the galaxy lives in the critic's 32-d "
          "embedding; the RFF ridge bridge (eq. 6) maps one into the other behind a ship gate. "
          "Sources: docs/11 §11.3, docs/20 §20.1"),
        C("d11", "d20"),
    ])
    H2(doc, "2.5 The honesty layer")
    P(doc, [
        T("The browser runs the same syrinx model in an AudioWorklet and the same feature "
          "extractor on the mic. The two renderers are verified sample for sample against each "
          "other: 18/18 parity fixtures, worst divergence at float32 rounding (docs/08 §8.1a, "
          "HANDOFF)"),
        C("d08", "handoff"),
        T(". Live audio is standardised, bridged into the galaxy's space, and turned into "
          "cluster activations by a softmax over centroid cosines with ~120 ms smoothing "
          "(docs/08 §8.2). The honesty rule (docs/08 §8.5) is a product requirement, not a "
          "nicety. Every rendered phrase carries its confidence: "),
        I("experimental"),
        T(" (playback-verified), "),
        I("documented"),
        T(" (in the literature), "),
        I("inferred"),
        T(" (plausible, not established), "),
        I("invented"),
        T(" (a designed mapping, always labelled as such). Anything the system flags as new is "),
        B("“unlabelled: real acoustics, no documented function”"),
        T(", because detecting that a sound is new is not knowing what it means"),
        C("d08"),
        T("."),
    ])
    add_table(
        doc,
        ["component", "technique", "where it runs", "source", "why it is there"],
        [
            ["voice source", "Mindlin–Laje flapping oscillator (eq. 1)", "AudioWorklet synth + Python fit", "docs/08 §8.1", "physiological, bird-validated, real-time"],
            ["time scale", "per-syllable γ, f0 = g·Φ (eq. 2)", "fit + synth", "docs/08 §8.1", "measured Φ(0.1, 1) = 0.17061, not fitted"],
            ["tract", "f0-tracking resonance + stopped-tube comb (eq. 3)", "synth", "docs/08 §8.1a", "pure tone is a filter effect; comb ships only where it wins (10/22)"],
            ["roughness", "140 Hz noise on β", "synth", "docs/08 §8.1a", "tension noise drives forebrain neurons; intermediate amount best"],
            ["fricatives", "turbulence routed to fitted formants", "synth, per type", "docs/16 §16.7", "chip notes are shaped noise; ships where it beats the tonal fit"],
            ["respiration", "air-sac oscillator (eq. 4)", "parked (off by default)", "docs/15 §1", "hand-set default is a wash; waits for the per-species fit"],
            ["two voices", "pair coupled via tracheal pressure", "parked (off by default)", "docs/15 §5", "hand-set default regresses (0.343 → 0.294)"],
            ["descriptor", "28-d: 13 MFCC means + 13 stds + centroid + flatness", "harvest, fit, browser", "docs/08 §8.2", "computable identically in Python and the browser"],
            ["spectral fingerprint", "32×23 log-mel patch", "store, critic", "docs/09 §9.3", "not invertible to audio; the licensing property holds"],
            ["critic", "3-head CNN: realism, species, contrastive", "pipeline", "docs/09 §9.2b", "scores and types; never generates"],
            ["contrastive loss", "NT-Xent, τ = 0.2 (eq. 5)", "critic training", "docs/09 §9.2b", "same syllable close, different syllables apart"],
            ["galaxy space", "critic 32-d embedding", "build, galaxy", "docs/09 §9.7", "+13.3 pts placement over the hand-weighted vector"],
            ["browser bridge", "RFF + ridge (eq. 6)", "build fits it, browser applies it", "docs/11 §11.3", "no torch in the browser; gated at 0.8"],
            ["fit objective", "descriptor cosine (eq. 7)", "inversion, ship gates", "docs/08 §8.2, docs/19", "cluster-safe; audibly blind (section 6)"],
            ["session gate", "off-manifold 5-NN distance", "browser live path", "docs/20 §20.3.2", "AUC 0.953; computable from the 28-d side alone"],
            ["grammar", "first-order + Kneser–Ney backoff", "build, app sequences", "docs/18", "unseen tail +1.90 / +2.32 nats; seen side bit-identical"],
            ["song baseline", "bag-of-types", "build", "docs/18 P2", "the bar any learned song encoder must beat"],
            ["novel-species hint", "Perch 2.0 top-3 (ONNX, offline)", "pipeline only", "docs/13", "metadata, never typing ground truth"],
        ],
        widths=[2.3, 4.1, 3.1, 2.4, 4.7],
        font_size=7.5,
    )
    add_caption(doc, [
        B("Table 1 — Where the system uses what. "),
        T("Every technique, the place it runs, the note that defines it, and the reason it is "
          "there. Parked rows are implemented and parity-tested but ship off by default."),
    ])

    # ================= 3. Comparison with other approaches =================
    H1(doc, "3. Comparison with other approaches")
    plain_terms(
        doc,
        "Birdy sits in a landscape of bioacoustic tools. Some classify, some embed, some map, "
        "some generate. None of them is a voice. Table 2 puts the approaches side by side on "
        "the properties this project cares about. A cell says “not documented” where the "
        "project's own references do not answer the question. The comparison claims nothing "
        "beyond the cited sources."
    )
    add_table(
        doc,
        ["approach", "what it is", "generates sound", "interpretable", "offline in browser", "licence-clean", "confidence labels", "bird-validated"],
        [
            ["BirdNET [26]", "species classifier on spectrograms", "no", "no", "not documented", "no — CC BY-NC-SA, non-commercial", "not documented", "not documented"],
            ["Perch 2.0 [25]", "14 597-species embedding model", "no", "no", "no — 409 MB ONNX; runs offline in the pipeline only", "yes — Apache 2.0", "no", "not documented"],
            ["Google Bird Sounds [24]", "t-SNE map of thousands of recordings", "no", "no", "yes — web experiment", "yes — Apache 2.0", "no", "no"],
            ["Sainburg et al. [22]", "VAE latent space across species", "no", "latent, not physiological", "not documented", "not documented", "no", "not documented"],
            ["Goffinet et al. [23]", "learned low-d features for individual and group differences", "no", "no", "not documented", "not documented", "no", "not documented"],
            ["generative audio models [38]", "waveform generators", "yes", "no", "no", "training-data licences unclear", "no", "no"],
            ["Birdy (this work)", "physical syrinx + measurement-only corpus", "yes", "yes — physiological parameters", "yes", "yes — no audio retained", "yes — four levels", "yes — playback-tested [10, 15]"],
        ],
        widths=[2.5, 3.3, 1.6, 2.0, 2.4, 2.2, 1.6, 1.9],
        font_size=7.5,
    )
    add_caption(doc, [
        B("Table 2 — Approaches side by side. "),
        T("Bracketed numbers resolve to the References section. “Not documented” means the "
          "project's references do not answer the cell; the table claims nothing beyond its "
          "sources."),
    ])
    P(doc, [
        B("What Birdy takes, and what it declines. "),
        T("The galaxy's prior art is open source: the t-SNE bird map, the VAE latent space, and "
          "the learned feature spaces showed that vocal repertoires have navigable geometry"),
        C("birdsounds", "sainburg2020", "goffinet2021"),
        T(". Perch 2.0 gives novel syllables a second opinion — as metadata, never as identity"),
        C("perch"),
        T(". BirdNET's non-commercial licence excludes it from the app"),
        C("birdnet"),
        T(". A generative audio model would trade interpretability, the honesty labels, and the "
          "bird-validated realism evidence for sample quality the field cannot yet measure "
          "(docs/09 §9.6)"),
        C("d09"),
        T(". On the documented cells of Table 2, no listed approach combines Birdy's specific "
          "triple: a bird-validated physical voice, a corpus that keeps no audio, and a "
          "confidence label on every claim."),
    ])

    # ================= 4. The pipeline, end to end =================
    H1(doc, "4. The pipeline, end to end")
    plain_terms(
        doc,
        "The pipeline is a conveyor belt with five stations. Recordings come in, are measured, "
        "and are destroyed. Only numbers survive. A clustering step decides which sounds are "
        "the same sound: a syllable type. A fitting step searches the synthesiser's knobs until "
        "the render of each type matches the measurements as closely as possible. The critic's "
        "internal representation becomes the coordinate system of a 3-D map: the galaxy. The "
        "browser replays all of it with no server and no neural network, and it labels every "
        "claim it makes."
    )
    add_figure(doc, figs["arch"], [
        B("Figure 3 — Architecture. "),
        T("Stations 1–4 run offline in Python; the harvest keeps only descriptors and log-mel "
          "patches. Station 5 is the browser: static assets only, no torch, no Python. The "
          "honesty band labels every claim the app shows. Sources: docs/06 §6.1, docs/08 §8.3"),
        C("d06", "d08"),
    ])
    H2(doc, "4.1 Harvest: decode → describe → delete")
    P(doc, [
        T("The harvest downloads a recording, decodes it, measures every syllable, and deletes "
          "the file. What stays is the descriptor and the patch of section 2.2. The largest "
          "ingest to date is iNatSounds 2024, in one pass: 6 453 recordings, 2 513 minutes, "
          "226 264 syllables, 3 811 species, zero failures (docs/16 §16.1)"),
        C("d16"),
        T("."),
    ])
    H2(doc, "4.2 Learn: types and gestures")
    P(doc, [
        T("Syllable identity was once decided by seven hand-weighted numbers with guessed "
          "weights. It is now KMeans clustering in the critic's 32-d embedding, with the "
          "cluster count chosen by silhouette (docs/09 §9.2b, §9.7). Each type is then fitted "
          "by gesture inversion: a coordinate descent over ~16 axes of the synthesiser's "
          "parameter vector, in three passes. The score against the reference observation is "
          "the descriptor cosine, the number every fit gate in the project reads:"),
    ])
    add_equation(doc, eq_paths, "cosine", 7)
    P(doc, [
        T("z is the standardised 28-d descriptor in the harvest population frame. Section 6 is "
          "largely about what is wrong with this objective. It remains the optimiser because "
          "its failure is bounded and cluster-safe (docs/19 §19.5). The learn is parallel and "
          "streaming: per-species fits in a fork pool after one GPU embedding pass, "
          "checkpointed every 100 species. It is verified bit-identical to the serial fit "
          "(docs/16 §16.3)"),
        C("d16"),
        T(". Rhythm is measured, not invented: 26 897 per-transition gaps extracted with the "
          "grammar (docs/18)"),
        C("d18"),
        T("."),
    ])
    H2(doc, "4.3 Build: the galaxy as static assets")
    P(doc, [
        T("The build renders every fitted type, places every measured syllable, and writes "
          "static assets: JSON and f32, no torch weights. The galaxy is a precomputed 3-D "
          "point cloud with one point per measured syllable, plus renders of measured "
          "realisations. Hand-set jitter survives only where no measurements exist, and it is "
          "labelled “invented” (docs/10 §10.1)"),
        C("d10"),
        T("."),
    ])
    H2(doc, "4.4 The app: replay with no server")
    P(doc, [
        T("The app is a static site. It loads the assets, synthesises in an AudioWorklet, and "
          "analyses the mic. It never calls a Python process. The session gate of section 5 "
          "watches the live path: an off-manifold 5-NN distance, computable from the 28-d side "
          "alone, flags sessions that sit off everything the galaxy knows (docs/20 §20.3.2)"),
        C("d20"),
        T("."),
    ])
    P(doc, [
        B("Corpus growth, for scale. "),
        T("The measurement stores behind this note:"),
    ])
    add_table(
        doc,
        ["store / phase", "syllables", "species", "source"],
        [
            ["out/harvest (original)", "39 976", "22", "docs/08 §8.1a"],
            ["out/harvest-gan, first", "9 041", "25", "docs/09 §9.7"],
            ["out/harvest-gan at 40 k", "39 993", "25 (13 after a fixed trim bug)", "docs/09 §9.8"],
            ["+ xccoverbl ingest", "39 874", "121", "docs/14 §14.1"],
            ["+ iNatSounds 2024", "226 264", "3 811", "docs/16 §16.1"],
            ["200 k learn (parallel)", "187 078 typed", "2 423 fitted, 12 724 types", "docs/16 §16.3"],
        ],
        widths=[5.2, 3.0, 4.6, 3.8],
    )
    add_caption(doc, [
        B("Table 3 — The measurement stores. "),
        T("Each row is a fixed corpus; every number in this note names the store it was "
          "measured on."),
    ])
    add_figure(doc, figs["growth"], [
        B("Figure 4 — Corpus growth. "),
        T("Syllables and species per store, log scales. The iNatSounds 2024 ingest multiplied "
          "the species count by 31; depth per species did not grow with it — section 6.3. "
          "Sources: docs/08 §8.1a, docs/09 §9.7–9.8, docs/14 §14.1, docs/16 §16.1"),
        C("d08", "d09", "d14", "d16"),
    ])

    # ================= 5. Results: what works =================
    H1(doc, "5. Results: what works (measured)")
    plain_terms(
        doc,
        "The good news, with receipts. Every claim below is a number the project measured on a "
        "fixed corpus. Most were pre-registered: the target was written down before the run. "
        "Where a number comes from the smaller debug corpus, the caption or the text says so."
    )
    add_figure(doc, figs["wins"], [
        B("Figure 5 — Headline measured gains. "),
        T("Each row shows before and after, with units per row. Sources: docs/09 §9.8, docs/10 "
          "§10.3, docs/16 §16.2–16.3, §16.7, docs/18"),
        C("d09", "d10", "d16", "d18"),
    ])
    P(doc, [
        B("The learned embedding is a clean win, twice. "),
        T("Typing syllables in the critic's 32-d embedding instead of the hand-weighted vector "
          "moved species placement from 26.6 % to 32.9 % on the 9 k store (chance 4.0 %). On "
          "the 40 k store it moved placement from 38.4 % to 51.7 % — a +13.3-point gain — "
          "against 7.7 % chance (13 species after the trim bug). The guardrail cosine held: "
          "0.807 → 0.796. F0 error improved from 3.3 % to 2.2 %. Nothing regressed, on two "
          "independent stores (docs/09 §9.7, §9.8)"),
        C("d09"),
        T(". The same retrain epochs lifted novelty detection from ROC 0.596 to 0.846, and "
          "true-positive rate at 5 % FPR from 7.4 % to 32.2 %, across three corpus epochs "
          "(docs/10 §10.3, docs/11 §11.2, docs/16 §16.2)"),
        C("d10", "d11", "d16"),
        T("."),
    ])
    P(doc, [
        B("The learn is fast and exactly reproducible. "),
        T("Parallel per-species fitting is verified bit-identical to the serial fit. The "
          "3 800-species learn went from a ~3 h serial pace to ~15 min on 16 workers. "
          "Checkpointing every 100 species came after two crash losses taught the lesson. The "
          "200 k learn fitted 2 423 species into 12 724 types over 187 078 typed observations. "
          "All 2 423 fitted species carry recovered common names (docs/16 §16.3)"),
        C("d16"),
        T("."),
    ])
    P(doc, [
        B("The fricative path closed the biggest acoustic gap. "),
        T("Real chip notes are broadband bursts shaped by the tract: whispered vowels, not "
          "tones with hiss. The evidence was two species parked at the noise ceiling and still "
          "failing: Algerian nuthatch types scored cosine 0.16–0.60 with noise at 0.60–0.85. "
          "The fix routes turbulence around the f0-tracking band into the syllable's own fitted "
          "formant set, driven by the same pressure gesture as the tonal source. The bench "
          "median moved 0.584 → 0.656. End to end: 13 wins, 0 losses. The path ships per type "
          "only where the resynthesis beats the tonal fit. Syllables without the flag render "
          "bit-identically (docs/16 §16.7; HANDOFF 2026-07-30)"),
        C("d16", "handoff"),
        T("."),
    ])
    P(doc, [
        B("The naturalness fit pass won where hand-set physics washed. "),
        T("A per-species coordinate search over the respiratory and two-voice parameter sets "
          "scored 12 680 types. Respiration won 445. Two-voice won 2 027 of 5 922 screened. "
          "The median cosine moved 0.650 → 0.6623, and the ship gate held everywhere (docs/16 "
          "§16.4). The documented one-tone re-fit shipped measured noise and rough texture on "
          "14 of 15 authored calls, median gain +0.148 on the debug store of 37 species. The "
          "one holdout stayed pure: the gate doing its job. One caveat carries over from "
          "section 6: these gates read the cosine, and the bench has since shown that the "
          "cosine does not rank audible fit (docs/19 §19.3)"),
        C("d16", "d19"),
        T("."),
    ])
    P(doc, [
        B("Grammar repair, on pre-registered terms. "),
        T("The first-order model's one measured weakness was unseen-context transitions at "
          "−9.25 nats/token. A Kneser–Ney continuation backoff gained +1.90 and +2.32 "
          "nats/token on unseen-context transitions on the two debug stores. The seen side "
          "stayed bit-identical, with loss exactly 0.0000. The honest scope: 80 % of the "
          "unseen tail is seen-context, so the full-tail gain is +0.37 and +0.65 (docs/18)"),
        C("d18"),
        T("."),
    ])
    P(doc, [
        B("The session gate separates pathological recordings at AUC 0.953. "),
        T("Eight of 45 held-out recording sessions on the debug build carry 22.9 % of the "
          "galaxy map's flip loss, all xeno-canto. An off-manifold 5-NN distance — computable "
          "from the 28-d side alone, all the browser will ever have — separates them at AUC "
          "0.953 (norm-deviation 0.922; the pre-registered two-signal combination adds nothing "
          "at 0.954; gate 0.9). A shipped cloud of 256 random anchors (28 kB) holds AUC ≥ "
          "0.92. The lever gate failed its raw bar (+3.5 points vs +5), so the pre-registered "
          "fallback fired: it ships as an "),
        B("honesty gate"),
        T(" — “this session is off everything the galaxy knows” — catching 5 of the 8 bad "
          "sessions including the three worst loss-carriers, with 3 clean false-flags all "
          "within 0.02 of the bad line (docs/20 §20.3.2)"),
        C("d20"),
        T("."),
    ])
    add_figure(doc, figs["gate"], [
        B("Figure 6 — Session-gate signal AUCs. "),
        T("AUC against the bad-session label (8 of 45 held-out sessions), end-to-end debug "
          "build (harvest-b100, 3 731 eval rows); the dashed line is the pre-registered "
          "adoption gate. Debug-scale measurement. Source: docs/20 §20.3.2"),
        C("d20"),
    ])
    P(doc, [
        B("Song types fall out, with an honest control. "),
        T("Clustering run-collapsed type-id sequences by normalised edit distance found 50 "
          "song types over 13 of 35 species, placing 693 of 2 419 candidate bouts. A "
          "global-permutation control yields 0.2 % — one spurious type — at the shipped "
          "constants. The nightingale, the famous improviser, yields zero types over 275 "
          "candidate bouts: the noise category agrees with a century of field notes (docs/12)"),
        C("d12"),
        T(". Rhythm is measured everywhere the app plays sequences: 26 897 per-transition "
          "gaps (docs/18). And the two-renderer contract holds at 18/18 parity fixtures — the "
          "same syllable is the same samples in Python and in the browser (HANDOFF "
          "2026-07-30)"),
        C("d18", "handoff"),
        T("."),
    ])

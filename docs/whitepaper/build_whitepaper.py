#!/usr/bin/env python3
"""Build the Birdy whitepaper: charts, typeset equations, DOCX.

Run:  cd pipeline && uv run python ../docs/whitepaper/build_whitepaper.py

Every number in the document is sourced from the repo's research notes
(docs/NN, HANDOFF.md, AGENTS.md) — the citation for each figure is in its
caption, and in-text superscripts resolve to the numbered References section.
Debug-scale measurements are labelled as such in the captions, per the
project's evidence discipline (docs/19 §19.5, docs/17 §17.6).

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
    # The fit objective — docs/08 §8.2, docs/09 §9.2.
    "cosine": (
        r"\mathrm{score} = \cos\left( z_{\mathrm{syn}},\, z_{\mathrm{ref}} \right)"
        r" = \frac{z_{\mathrm{syn}} \cdot z_{\mathrm{ref}}"
        r"}{\left\| z_{\mathrm{syn}} \right\| \, \left\| z_{\mathrm{ref}} \right\|}"
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


def diagram_architecture() -> str:
    """Boxes-and-arrows: offline pipeline -> static assets -> browser app."""
    fig, ax = plt.subplots(figsize=(6.8, 4.0))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 6)
    ax.axis("off")
    ax.grid(False)

    def box(x, y, w, h, text, fc="white", ec=ACCENT, fs=7.6, tc="#241f33"):
        ax.add_patch(
            FancyBboxPatch(
                (x, y), w, h,
                boxstyle="round,pad=0.06,rounding_size=0.09",
                linewidth=1.0, edgecolor=ec, facecolor=fc,
            )
        )
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs, color=tc)

    def arrow(x1, y1, x2, y2, color="#666666"):
        ax.add_patch(
            FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=11,
                            linewidth=1.0, color=color)
        )

    # containers
    ax.add_patch(FancyBboxPatch((0.15, 0.55), 4.9, 4.9, boxstyle="round,pad=0.08",
                                linewidth=1.1, edgecolor="#c9c9c9", facecolor="#fafafa"))
    ax.text(2.6, 5.25, "offline pipeline (Python) — no audio retained", ha="center",
            fontsize=8.6, color="#555555")
    ax.add_patch(FancyBboxPatch((5.35, 0.55), 4.5, 4.9, boxstyle="round,pad=0.08",
                                linewidth=1.1, edgecolor="#c9c9c9", facecolor="#fafafa"))
    ax.text(7.6, 5.25, "browser app (SvelteKit) — no torch, no Python", ha="center",
            fontsize=8.6, color="#555555")

    box(0.45, 4.25, 1.9, 0.72, "field recordings\nxeno-canto · iNatSounds", ec=GREY)
    box(2.85, 4.25, 1.9, 0.72, "harvest\ndecode → describe\n→ delete", ec=GREY)
    box(1.65, 3.05, 1.9, 0.72, "store\n28-d descriptors\n+ log-mel patches", ec=GREY)
    box(0.45, 1.75, 1.9, 0.72, "critic (3-head CNN)\nrealism · species ·\ncontrastive")
    box(2.85, 1.75, 1.9, 0.72, "learn\ntype clustering +\ngesture inversion")
    box(1.65, 0.75, 1.9, 0.62, "build → galaxy assets\n(JSON / f32, no weights)", fc="#f2ecf7")

    box(5.75, 4.0, 3.65, 0.85, "Threlte 3D galaxy\none point per measured syllable,\nknots labelled with confidence")
    box(5.75, 2.75, 1.7, 0.8, "mic → 28-d\nfeatures →\nRFF map (32-d)")
    box(7.7, 2.75, 1.7, 0.8, "AudioWorklet\nsyrinx synth\n(bit-identical)")
    box(5.75, 0.75, 3.65, 0.8, "honesty layer, over everything above:\ndocumented · inferred · invented ·\n“unlabelled: real acoustics, no documented function”",
        fs=7.0)

    arrow(2.35, 4.6, 2.85, 4.6)
    arrow(3.8, 4.25, 2.9, 3.77)
    arrow(1.9, 3.05, 1.55, 2.47)
    arrow(3.35, 3.05, 3.65, 2.47)
    arrow(2.35, 2.1, 2.85, 2.1)   # critic <-> learn (fit renders scored)
    arrow(1.4, 1.75, 2.2, 1.37)   # critic embed -> build
    arrow(3.8, 1.75, 3.0, 1.37)   # learn -> build
    arrow(3.55, 1.2, 5.9, 4.0)    # assets -> galaxy
    arrow(3.55, 0.95, 8.2, 2.75)  # assets -> synth
    arrow(6.6, 3.55, 6.9, 4.0)    # mic features -> galaxy activation
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


def add_figure(doc, path, caption_segs, width_cm=15.6):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run().add_picture(path, width=Cm(width_cm))
    p.paragraph_format.space_after = Pt(2)
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


def style_document(doc):
    normal = doc.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(10.5)
    normal.element.rPr.rFonts.set(qn("w:eastAsia"), "Calibri")
    normal.paragraph_format.space_after = Pt(6)
    normal.paragraph_format.line_spacing = 1.12
    for level, size in (("Heading 1", 16), ("Heading 2", 12.5)):
        st = doc.styles[level]
        st.font.name = "Calibri"
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


def add_table(doc, header, rows, widths=None):
    table = doc.add_table(rows=1 + len(rows), cols=len(header))
    table.style = "Light Grid Accent 1"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    for j, h in enumerate(header):
        cell = table.rows[0].cells[j]
        cell.text = ""
        run = cell.paragraphs[0].add_run(h)
        run.bold = True
        run.font.size = Pt(9)
    for i, row in enumerate(rows):
        for j, val in enumerate(row):
            cell = table.rows[i + 1].cells[j]
            cell.text = ""
            run = cell.paragraphs[0].add_run(str(val))
            run.font.size = Pt(9)
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
        [T("Working draft — internal research note · 2026-07-31")],
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
                "Birdy is a research programme and interactive installation that treats birdsong as "
                "learnable structure rather than noise — and says so with measured confidence rather "
                "than marketing. Its voice is a physical model of the avian syrinx, fitted to field "
                "recordings by gesture inversion; its memory is a measurement-only corpus in which no "
                "audio is ever retained; its map is a navigable 3-D galaxy of every syllable the "
                "corpus holds; its claim to translation is deliberately narrow: functional decoding — "
                "call type to documented behavioural function, with confidence labels — because "
                "playback experiments are the only proof of meaning the field accepts. This note "
                "describes the instrument, the pipeline, and the evidence. It reports what works "
                "(a learned syllable embedding that lifts species placement by up to +13.3 points, a "
                "bit-identical parallel learn, a measured fricative synthesis path, a session-quality "
                "honesty gate at AUC 0.953) and — at equal length — what does not (the fit objective "
                "does not track audible distortion, recorder invariance cannot be bought with loss "
                "engineering, song structure is starved by corpus depth). Negative results are "
                "recorded here, not deleted; that is the project's method, not its apology."
            ),
        ],
    )
    doc.add_paragraph()
    P(doc, [B("Contents"), T("  (section numbers; a manual list)")], space_after=2)
    for line in [
        "1  The premise: what translating birdsong can honestly mean",
        "2  The instrument: a physical syrinx",
        "3  The pipeline: from field recordings to a galaxy",
        "4  What works (measured)",
        "5  What does not work (measured)",
        "6  The unknown-bird pipeline",
        "7  Roadmap",
        "8  References",
    ]:
        P(doc, [T(line)], space_after=2, indent=0.6)
    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)

    # ================= 1. The premise =================
    H1(doc, "1. The premise: what translating birdsong can honestly mean")
    plain_terms(
        doc,
        "A great tit does not improvise. It has a small set of calls, and one of them is a sentence: "
        "three notes meaning “scan for danger” followed by one meaning “come here” — played in that "
        "order, other tits do both; played backwards, they do nothing. Birdsong, in other words, is "
        "structure a machine can learn. What a machine cannot yet do is tell you what an unheard call "
        "means, because the only accepted proof of meaning is playing the sound back to a bird and "
        "watching what the bird does. Birdy is built around both halves of that sentence: it learns "
        "the structure aggressively, and it labels the meaning honestly."
    )
    P(doc, [
        T("The field's own position is three-part"),
        C("rutz"),
        T(": machine learning today can "),
        B("characterize"),
        T(" repertoires (find the units and their structure), it can "),
        B("functionally decode"),
        T(" (link signals to context and behaviour), and it "),
        B("cannot"),
        T(" translate into propositional human language — that requires playback experiments, which "
          "exist for only a handful of systems. A central ethological asymmetry sharpens the point: "
          "bird "),
        I("song"),
        T(" has rich syntax but weak or no referential meaning, while bird "),
        I("calls"),
        T(" carry meaning but little syntax (docs/03 §3.1)"),
        C("d03"),
        T(". The scientifically defensible product is therefore "),
        B("functional translation"),
        T(" — call type → documented behavioural function, species, individual identity, urgency — "
          "with confidence labels attached. Word-for-word translation is marketing, and the app says "
          "so in its own interface."),
    ])
    P(doc, [
        T("The studied vocabularies that anchor the language set are real: the Japanese great tit's "
          "ABC–D compositionality (ABC = “scan for danger”, D = “approach”; the reversed order elicits "
          "nothing)"),
        C("suzuki"),
        T(", the Siberian jay's alarm calls encoding predator "),
        I("behaviour"),
        T(" rather than predator species"),
        C("griesser"),
        T(", the chickadee's four-note chick-a-dee with D-count scaling with threat"),
        C("freeberg"),
        T(", the nightingale's 180–200 song types delivered in rule-governed order"),
        C("hultsch"),
        T(", and the Bengalese finch's finite-state song syntax"),
        C("okanoya"),
        T(". This curated, literature-anchored set is what Birdy calls a documented function; "
          "everything else is labelled as what it is."),
    ])
    P(doc, [
        B("Why a physical synthesiser. "),
        T("Two reasons, one scientific and one legal. Scientifically, a procedural model of the "
          "syrinx is a falsifiable theory of the bird: its parameters (air-sac pressure, syringeal "
          "tension, tract geometry) are physiological claims, and the model class has passed the "
          "strongest realism tests available — synthetic song from it drives song premotor neurons "
          "indistinguishably from real song"),
        C("amador2013"),
        T(", and wild territorial sparrows respond to it as they do to a real rival"),
        C("bistel2024"),
        T(". Legally, it is the app's only clean voice: xeno-canto recordings carry per-file Creative "
          "Commons licences, largely non-commercial, so Birdy retains and ships "),
        B("no audio at all"),
        T(" — the harvest decodes each recording, describes it as numbers, and deletes it "
          "(docs/09 §9.4, AGENTS.md)"),
        C("d09", "agents"),
        T(". Every sound the app makes is synthesized from fitted parameters; every point in its "
          "galaxy is a measurement, not a file."),
    ])

    # ================= 2. The instrument =================
    H1(doc, "2. The instrument: a physical syrinx")
    plain_terms(
        doc,
        "Birds do not sing with a larynx. At the bottom of the windpipe sits the syrinx — soft "
        "membranes that vibrate in the airstream like a reed, with effectively two control knobs: "
        "how hard the bird blows (air-sac pressure, roughly loudness) and how tight the membranes "
        "are (tension, roughly pitch). A two-equation model of that reed, driven by those two "
        "knobs, is realistic enough to fool the auditory neurons of a listening bird. Birdy's voice "
        "is that model, plus the physics of the tube above it."
    )
    P(doc, [
        T("The source is the low-dimensional Mindlin–Laje “flapping” oscillator"),
        C("mindlinbook", "amador2021"),
        T(", integrated as a pair of first-order equations (docs/08 §8.1)"),
        C("d08"),
        T(":"),
    ])
    add_equation(doc, eq_paths, "syrinx", 1)
    P(doc, [
        T("Here "),
        I("α"),
        T(" is the air-sac pressure, "),
        I("β"),
        T(" the syringeal tension that sets the fundamental frequency, and "),
        I("g"),
        T(" a pure time-scale — rescaling time by "),
        I("g"),
        T(" leaves the equations unchanged, so each syllable gets its own, chosen to place its median "
          "pitch in the well-behaved region of the model:"),
    ])
    add_equation(doc, eq_paths, "gamma", 2)
    P(doc, [
        T("with Φ measured once on a calibration sweep (the value above is measured, not fitted)"),
        C("perl2011"),
        T(". Which bifurcation births the oscillation decides the timbre: at high tension a Hopf "
          "produces tonal, whistle-like notes; at low tension a saddle-node-on-a-limit-cycle produces "
          "pulse-like, harmonically dense sounds"),
        C("sitt2008"),
        T(". The spectral content index is a function of tension alone, which is why the model's "
          "γ-scale — not its filters — is the tonal-to-rich axis (docs/08 §8.1a). The integrator is "
          "deliberately plain: forward Euler at 16× oversampling at 48 kHz; RK4 agrees to within 2 % "
          "of F0, so Euler is what ships (docs/08 §8.1)."),
    ])
    P(doc, [
        T("The vocal tract is not cosmetic. Pure-tone birdsong is a filter effect — the tract "
          "suppresses harmonics, proven by heliox experiments"),
        C("nowicki1987", "beckers2003"),
        T(" — and songbirds actively retune their oropharyngeal cavity to track the fundamental from "
          "1.5 to 5 kHz within a single syllable"),
        C("riede2006"),
        T(". So one resonance follows the instantaneous f0. But a tracking resonance alone makes "
          "every spectrum pitch-invariant — two species at the same pitch become the same instrument. "
          "The part that does not move is the trachea, a tube closed at the syrinx, resonating as a "
          "stopped quarter-wave pipe at the odd harmonics of one body-fixed frequency:"),
    ])
    add_equation(doc, eq_paths, "comb", 3)
    P(doc, [
        T("Measured agreement: eastern towhee resonances at ~2.0 and ~5.5 kHz against 1.88 and "
          "5.67 kHz predicted for its 45 mm trachea"),
        C("nelson2005"),
        T(". Birdy measures f₁ per species from the harvest itself (pitch-dependent structure "
          "averages away; only body-fixed resonances survive), and ships the comb only where the "
          "resynthesis scores better with it — 10 of 22 species earned one on the original corpus "
          "(docs/08 §8.1a)."),
    ])
    P(doc, [
        B("Texture is physics too. "),
        T("Turbulence is added at the labia, scaled by air flow so a silent bird does not hiss; "
          "roughness perturbs "),
        I("β"),
        T(" (tension), not the output — the literature is specific that matching the fundamental and "
          "the filters was not enough to drive selective forebrain neurons, that noise on tension was "
          "required, and that an intermediate amount scored best"),
        C("amador2021"),
        T(". The modulation sits at 140 Hz, inside the 80–250 Hz band syringeal muscle can follow"),
        C("riedegoller"),
        T(", and because the perturbation acts through the oscillator, f0 and amplitude wobble arrive "
          "correlated — as they do in real song (rendition-to-rendition R² ≈ 0.03)"),
        C("chen2013"),
        T(". All noise is a seeded xorshift32 stream so that “the same turbulence” is a testable "
          "claim on both sides of the contract (docs/08 §8.1a)."),
    ])
    P(doc, [
        B("Extensions, measured and mostly parked. "),
        T("Two structural extensions are implemented and parity-tested but off by default. The "
          "respiratory oscillator"),
        C("fainstein2025"),
        T(" replaces the hand-designed envelope with two-state air-sac dynamics (docs/15 §1)"),
        C("d15"),
        T(":"),
    ])
    add_equation(doc, eq_paths, "respiration", 4)
    P(doc, [
        T("with a Heaviside conductance asymmetry between inflow and outflow — attack shape and "
          "cross-syllable memory emerge instead of being designed. Its hand-set default is a wash on "
          "the pre-registered bake-off (median cosine 0.343 → 0.336, placement 17/81 → 20/81), so it "
          "stays off until the per-species fit wins; the two-voice coupling of the syrinx's two sides "
          "through the shared tracheal pressure"),
        C("laje2005"),
        T(" is parked for the same reason (0.343 → 0.294 with the hand-set default). Both are "
          "recorded in place, per the project's rule that a negative result is a deliverable."),
    ])
    P(doc, [
        B("Why this architecture at all. "),
        T("The validation lineage is unusually strong: the model class fools HVC auditory neurons"),
        C("amador2013"),
        T(", runs as a real-time neural prosthesis"),
        C("arneodo2012"),
        T(", and — the decisive test — in 256 playback tests across 26 wild rufous-collared sparrows "
          "at 15 sites, territorial responses to synthetic song did not differ significantly from "
          "responses to real song, while heterospecific song evoked none"),
        C("bistel2024"),
        T(". Automatic gesture inversion from real audio is likewise published"),
        C("boari2015"),
        T(". A generative audio model would trade all of this — interpretability, the honesty "
          "labels, the galaxy's geometry, and the only bird-validated realism evidence — for raw "
          "sample quality the field itself admits it cannot measure (docs/09 §9.6). The synthesiser "
          "stays physical; learned components analyse and score, they never generate."),
    ])

    # ================= 3. The pipeline =================
    H1(doc, "3. The pipeline: from field recordings to a galaxy")
    plain_terms(
        doc,
        "The pipeline is a conveyor belt with five stations. Recordings come in, are measured, and "
        "are destroyed — only numbers survive. A clustering step decides which sounds are “the same "
        "sound” (a syllable type). A fitting step searches the synthesiser's knobs until its render "
        "of each type is as close as it can get to the measurements. A small neural network — the "
        "critic — learns what a syllable is, and its internal representation becomes the coordinate "
        "system of a 3-D map: the galaxy. The browser replays all of it with no server and no "
        "neural network, and labels every claim it makes."
    )
    add_figure(doc, figs["arch"], [
        B("Figure 1. "),
        T("Architecture. Offline (left): harvest keeps only descriptors and log-mel patches; the "
          "critic and the learn pass turn them into types, fitted gestures, and galaxy assets. "
          "Online (right): static assets only — the browser synthesises, analyses the mic, and "
          "labels every claim. Sources: docs/06 §6.1, docs/08 §8.3"),
        C("d06", "d08"),
    ])
    H2(doc, "3.1 Harvest: decode → describe → delete")
    P(doc, [
        T("No audio is ever retained or shipped; the decode → describe → delete loop is load-bearing "
          "for licensing, and the one owner-sanctioned exception (a local training cache under "),
        I("pipeline/out/audio-cache/"),
        T(", gitignored, deleted at phase end) never feeds the app (AGENTS.md)"),
        C("agents"),
        T(". What a syllable leaves behind is two measurements. First, a 28-dimensional descriptor: "
          "13 MFCC means, 13 MFCC standard deviations, mean log₂ spectral centroid, mean spectral "
          "flatness, computed under an exact frame-level contract (48 kHz mono, 1024/512 Hann "
          "frames) that the browser re-implements sample-for-sample (docs/08 §8.2)"),
        C("d08"),
        T(". Second, a fixed 32×23 log-mel patch — 736 numbers, log-magnitude only, no phase — "
          "resampled onto the syllable's own duration. A patch cannot be turned back into "
          "recognisable audio, so the licensing property holds while a spectral fingerprint survives "
          "(docs/09 §9.3, docs/17 §17)"),
        C("d09", "d17"),
        T(". The largest ingest to date: iNatSounds 2024, one pass — 6 453 recordings, 2 513 minutes, "
          "226 264 syllables, 3 811 species, zero failures (docs/16 §16.1)"),
        C("d16"),
        T("."),
    ])
    H2(doc, "3.2 Learn: types and gestures")
    P(doc, [
        T("Syllable identity used to be decided by seven hand-weighted numbers with guessed weights; "
          "it is now KMeans clustering in the critic's 32-dimensional learned embedding, with the "
          "cluster count chosen by silhouette (docs/09 §9.2b, §9.7). Each type is then fitted by "
          "gesture inversion: coordinate descent over ~16 axes of the synthesiser's parameter "
          "vector, three passes, scored against the reference observation by the descriptor cosine — "
          "the number every fit gate in the project reads:"),
    ])
    add_equation(doc, eq_paths, "cosine", 5)
    P(doc, [
        T("where z is the standardised 28-d descriptor in the harvest population frame. §5 of this "
          "note is largely about what is wrong with this objective; it remains the optimiser "
          "because its failure is bounded and cluster-safe (docs/19 §19.5). The learn is parallel "
          "and streaming — per-species fits in a fork pool after one GPU embedding pass, "
          "checkpointed every 100 species — and verified bit-identical to the serial fit (docs/16 "
          "§16.3)"),
        C("d16"),
        T(". Rhythm is measured, not invented: 26 897 per-transition gaps were extracted with the "
          "grammar (docs/18)"),
        C("d18"),
        T("."),
    ])
    H2(doc, "3.3 The critic: a network that scores, never sings")
    P(doc, [
        T("The critic is a small convolutional network (4 conv layers, spectral normalisation, "
          "~1–3 M parameters) over the log-mel patch, trained with three heads on a shared trunk "
          "(docs/09 §9.2b): a "),
        B("realism"),
        T(" logit (real patch vs a render of the current fit), a "),
        B("species"),
        T(" classifier (the harvest labels every syllable), and a "),
        B("contrastive"),
        T(" head with an NT-Xent loss — two augmented views of the same syllable embed close, "
          "different syllables apart:"),
    ])
    add_equation(doc, eq_paths, "ntxent", 6)
    P(doc, [
        T("Augmentations are time stretches, gain changes, added noise — never pitch shifts, which "
          "are genuinely type-diagnostic. Whole species are held out of training, so realism and "
          "novelty are measured on birds the network never saw. The current critic trained on 2 686 "
          "species (895 held out entirely): realism AUC 1.000 on held-out species, species accuracy "
          "0.730 over 2 686 classes (chance 0.0004), novelty ROC 0.846 with 32.2 % of unheard "
          "species' syllables flagged at a chosen 5 % false-positive rate (docs/16 §16.2)"),
        C("d16"),
        T(". The 32-d embedding is the deliverable; the realism logit, as §5 records, is a "
          "refuted objective."),
    ])
    H2(doc, "3.4 The galaxy: two spaces and a bridge")
    P(doc, [
        T("The galaxy is a static, precomputed 3-D point cloud — one point per measured syllable, "
          "plus renders of measured realisations; hand-set jitter survives only where no "
          "measurements exist, and is labelled “invented” (docs/10 §10.1)"),
        C("d10"),
        T(". Prior art is open source"),
        C("birdsounds", "sainburg2020", "goffinet2021"),
        T(". Two feature spaces coexist: the hand-written 28-d descriptor (what the browser can "
          "compute live) and the critic's 32-d embedding (what the galaxy is clustered in). Since "
          "no torch ships to the browser, a bridge maps the former into the latter: random Fourier "
          "features approximating an RBF kernel, then a closed-form ridge regression, fitted on "
          "(descriptor, embedding) pairs of the store with knobs chosen on held-out recordings "
          "(docs/11 §11.3)"),
        C("d11"),
        T(":"),
    ])
    add_equation(doc, eq_paths, "rff", 7)
    P(doc, [
        T("shipped as plain numbers (D = 2048 features, σ = 4, λ = 1 on the reference fit). The map "
          "is gated: median mapped-vs-true cosine on held-out recordings below 0.8 ships "),
        I("accepted: false"),
        T(" and the browser stays on the 28-d path. On the debug build the gate passes at 0.962; "
          "the honest knot-level agreement is 0.61 raw, 0.91 tie-adjusted, 0.78 at species level — "
          "§5 decomposes why the raw number undersells the map (docs/20)"),
        C("d20"),
        T(". A linear ridge was the original “honest choice”; it broke (0.7997, below gate) when the "
          "embedding grew finer, and the refutation is recorded in place (docs/11 §11.3)."),
    ])
    H2(doc, "3.5 The app: realtime synthesis and the honesty rule")
    P(doc, [
        T("The browser runs the same syrinx model in an AudioWorklet and the same feature extractor "
          "on the mic; the two renderers are verified sample-for-sample against each other "
          "(18/18 parity fixtures, worst divergence at float32 rounding) (docs/08 §8.1a, HANDOFF)"),
        C("d08", "handoff"),
        T(". Live audio is standardised, bridged into the galaxy's space, and turned into cluster "
          "activations by a softmax over centroid cosines with ~120 ms smoothing (docs/08 §8.2). "
          "The honesty rule (docs/08 §8.5) is a product requirement, not a nicety: every rendered "
          "phrase carries its confidence — "),
        I("experimental"),
        T(" (playback-verified), "),
        I("documented"),
        T(" (in the literature), "),
        I("inferred"),
        T(" (plausible, not established), "),
        I("invented"),
        T(" (a designed mapping, always labelled as such) — and anything the system flags as new is "),
        B("“unlabelled: real acoustics, no documented function”"),
        T(", because detecting that a sound is new is not knowing what it means"),
        C("d08"),
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

    # ================= 4. What works =================
    H1(doc, "4. What works (measured)")
    plain_terms(
        doc,
        "The good news, with receipts. Every claim below is a number the project measured on a fixed "
        "corpus, most of them pre-registered — the target was written down before the run. Where a "
        "number comes from the smaller debug corpus rather than the full one, the caption or the "
        "text says so."
    )
    P(doc, [
        B("The learned embedding is a clean win, twice. "),
        T("Typing syllables in the critic's 32-d embedding instead of the hand-weighted vector moved "
          "species placement 26.6 % → 32.9 % on the 9 k store (chance 4.0 %) and 38.4 % → 51.7 % — "
          "a +13.3-point gain — on the 40 k store (13 species after the trim bug, chance 7.7 %), "
          "with the guardrail cosine essentially held (0.807 → 0.796) and F0 error improving "
          "3.3 % → 2.2 %. Nothing regressed, on two independent stores (docs/09 §9.7, §9.8)"),
        C("d09"),
        T(". The same retrain epochs lifted novelty detection from ROC 0.596 to 0.846 and "
          "true-positive rate at 5 % FPR from 7.4 % to 32.2 % across three corpus epochs "
          "(docs/10 §10.3, docs/11 §11.2, docs/16 §16.2)"),
        C("d10", "d11", "d16"),
        T("."),
    ])
    P(doc, [
        B("The learn is fast and exactly reproducible. "),
        T("Parallel per-species fitting is verified bit-identical to the serial fit; the "
          "3 800-species learn went from a ~3 h serial pace to ~15 min on 16 workers, checkpointed "
          "every 100 species after two crash losses taught the lesson. The 200 k learn fitted 2 423 "
          "species into 12 724 types over 187 078 typed observations; all 2 423 fitted species carry "
          "recovered common names (docs/16 §16.3)"),
        C("d16"),
        T("."),
    ])
    P(doc, [
        B("The fricative path closed the biggest acoustic gap. "),
        T("Real chip notes are broadband bursts shaped by the tract — whispered vowels, not tones "
          "with hiss. The evidence was two species parked at the noise ceiling and still failing "
          "(Algerian nuthatch types at cos 0.16–0.60 with noise 0.60–0.85). The fix routes "
          "turbulence around the f0-tracking band into the syllable's own fitted formant set, driven "
          "by the same pressure gesture as the tonal source: bench median 0.584 → 0.656, end-to-end "
          "13 wins / 0 losses, shipping per type only where the resynthesis beats the tonal fit, "
          "with syllables without the flag rendering bit-identically (docs/16 §16.7; HANDOFF "
          "2026-07-30)"),
        C("d16", "handoff"),
        T("."),
    ])
    P(doc, [
        B("The naturalness fit pass won where hand-set physics washed. "),
        T("The per-species coordinate search over the respiratory and two-voice parameter sets "
          "scored 12 680 types: respiration won 445, two-voice won 2 027 of 5 922 screened, median "
          "cosine 0.650 → 0.6623, ship gate held everywhere (docs/16 §16.4). The documented one-tone "
          "re-fit shipped measured noise/rough texture on 14 of 15 authored calls (median gain "
          "+0.148, debug store, 37 species; the one holdout stayed pure — the gate doing its job). "
          "Caveat carried from §5: these gates read the cosine, which the bench has since shown not "
          "to rank audible fit (docs/19 §19.3)"),
        C("d16", "d19"),
        T("."),
    ])
    P(doc, [
        B("Grammar repair, on pre-registered terms. "),
        T("The first-order model's one measured weakness — unseen-context transitions at −9.25 "
          "nats/token — gained a Kneser–Ney continuation backoff: +1.90 and +2.32 nats/token on "
          "unseen-context transitions on the two debug stores, with the seen side bit-identical "
          "(loss exactly 0.0000). Honest scope: 80 % of the unseen tail is seen-context, so the "
          "full-tail gain is +0.37 / +0.65 (docs/18)"),
        C("d18"),
        T("."),
    ])
    P(doc, [
        B("The session gate separates pathological recordings at AUC 0.953. "),
        T("Eight of 45 held-out recording sessions on the debug build carry 22.9 % of the galaxy "
          "map's flip loss, all xeno-canto. An off-manifold 5-NN distance — computable from the "
          "28-d side alone, all the browser will ever have — separates them at AUC 0.953 "
          "(norm-deviation 0.922; the pre-registered two-signal combination adds nothing at 0.954; "
          "gate 0.9). A shipped cloud of 256 random anchors (28 kB) holds AUC ≥ 0.92. The lever "
          "gate failed its raw bar (+3.5 points vs +5), so the pre-registered fallback fired: it "
          "ships as an "),
        B("honesty gate"),
        T(" — “this session is off everything the galaxy knows” — catching 5 of the 8 bad sessions "
          "including the three worst loss-carriers, with 3 clean false-flags all within 0.02 of the "
          "bad line (docs/20 §20.3.2)"),
        C("d20"),
        T("."),
    ])
    add_figure(doc, figs["gate"], [
        B("Figure 2. "),
        T("Session-gate signal AUCs against the bad-session label (8 of 45 held-out sessions), "
          "end-to-end debug build (harvest-b100, 3 731 eval rows); the dashed line is the "
          "pre-registered adoption gate. Debug-scale measurement. Source: docs/20 §20.3.2"),
        C("d20"),
    ])
    P(doc, [
        B("Song types fall out, with an honest control. "),
        T("Clustering run-collapsed type-id sequences by normalised edit distance found 50 song "
          "types over 13 of 35 species, placing 693 of 2 419 candidate bouts, against a "
          "global-permutation control that yields 0.2 % (one spurious type) at the shipped "
          "constants. The nightingale — the famous improviser — yields zero types over 275 "
          "candidate bouts: the noise category agreeing with a century of field notes (docs/12)"),
        C("d12"),
        T(". Rhythm is measured everywhere the app plays sequences: 26 897 per-transition gaps "
          "(docs/18). And the two-renderer contract holds at 18/18 parity fixtures — the same "
          "syllable is the same samples in Python and in the browser (HANDOFF 2026-07-30)"),
        C("d18", "handoff"),
        T("."),
    ])

    # ================= 5. What does not work =================
    H1(doc, "5. What does not work (measured)")
    plain_terms(
        doc,
        "This chapter is the spine of the paper, and it is as long as the good news on purpose. "
        "Birdy's rule is that a measurement which contradicts the plan is the deliverable: every "
        "failure below has a number, a fixed corpus, and a written-down verdict, and stays in the "
        "record so nobody tries it again. Three big things do not work yet: the number we optimise "
        "is not the number we hear; the embedding organises by microphone before it organises by "
        "bird; and the corpus is too shallow for song grammar to show up in it."
    )
    H2(doc, "5.1 The objective does not measure the audible")
    P(doc, [
        T("Every fit decision in the pipeline — the inversion's gesture search, the respiration and "
          "two-voice ship gates, the fricative routing — is judged by the 28-d descriptor cosine. "
          "The spectral bench asked the obvious question nobody had: is a cosine gain an audible "
          "gain? Rendering 200 fitted types against their medoid members' cached audio and scoring "
          "two independent spectral distances (mel-cepstral distortion, multi-resolution STFT "
          "error), the answer is no: the correlations sit at ≈ 0.1 with p-values that cannot reject "
          "zero, and the point estimates lean the wrong way (docs/19 §19.2)"),
        C("d19"),
        T(". It is not a bench artifact: the recomputed cosine matches the stored one (0.921), and "
          "the two distances agree with each other (0.925) — they measure something coherent; the "
          "cosine just does not measure it."),
    ])
    add_figure(doc, figs["bench"], [
        B("Figure 3. "),
        T("The incumbent objective carries no information about spectral distance to the original "
          "audio; the mel-path target does (signs correct: higher similarity ↔ lower distortion). "
          "n = 200 types, debug-100 store against the iNat cache. Source: docs/19 §19.2, §19.4"),
        C("d19"),
    ])
    P(doc, [
        T("The mel-path target — time-resolved, exp(−LSD) similarity to the type's measured mel "
          "trajectory — is the better "),
        I("measurement"),
        T(" (Spearman −0.420 vs MCD where the cosine reads +0.100). It is the worse "),
        I("optimiser"),
        T(": at blend weight 1.0 the cosine guardrail collapses by 0.377, and the n = 10 probe's "
          "7/3 MCD win did not survive n = 80 — 31 % win share against a 60 % gate, median ΔMCD "
          "exactly 0.0 dB, one type losing 0.12 cosine (docs/19 §19.4, §19.5). The honest state, "
          "verbatim: "),
        I("“measure spectrally, optimise descriptor-ly”"),
        T(" — gates are read on the bench, the inversion keeps climbing the cosine, and an "
          "objective that is both remains unfound."),
    ])
    P(doc, [
        T("The learned alternative failed the same way, earlier and harder. A realism-trained critic "
          "— itself excellent, AUC 0.990–1.000 on entirely held-out species — used as the fit "
          "objective is monotonically harmful in its weight: at w = 1 the cosine collapses "
          "0.762 → 0.335 and placement drops to 17.3 %, and the refutation replicated at 40 k "
          "(38.4 % → 31.9 % at w = 0.5). Separating two distributions perfectly is not the same as "
          "having a gradient that points at the nearer one; the retained cosine guardrail is what "
          "made the gaming visible (docs/09 §9.7, §9.8)"),
        C("d09"),
        T(". A structurally better tract — a fixed waveguide with 32× the spectral freedom of the "
          "tracking band — improved all three metrics at once on five species and was a regression "
          "over 22 (23.1 % → 22.2 % placement), later shown to have been rejected by badly defined "
          "types rather than by the objective; it now wins on the gan store under learned typing "
          "(37.0 %) and pays for it in cosine, so it stays promising and unconfirmed (docs/08 "
          "§8.1c, docs/09 §9.7)"),
        C("d08", "d09"),
        T("."),
    ])
    P(doc, [
        B("The original wound, still open: species identity. "),
        T("On the original 22-species store, a resynthesis lands nearest its own species only "
          "23.1 % of the time against 4.5 % chance. Four hypotheses were tested and refuted in "
          "place (docs/08 §8.1a): the envelopes are not collapsed (we express 103 % of the real "
          "between-species spread and 106 % of the spectral detail — varied along different axes); "
          "there is a spectral tilt error but correcting it exactly drops placement to 20.2 %; the "
          "harmonic structure is not missing (real syllables resolve to a mean of 2.2 partials); "
          "and a time-resolved objective improves its own metric 36 % while placement falls "
          "61.7 % → 43.2 % — the two objectives conflict. The ceiling is the descriptor and the "
          "filter chain's capacity, not the search."),
    ])
    H2(doc, "5.2 The embedding organises by recorder before bird")
    P(doc, [
        T("The geometry battery scores how much a grouping organises the embedding, as the same-label "
          "rate among a point's nearest neighbours minus a permutation null:"),
    ])
    add_equation(doc, eq_paths, "knnlift", 8)
    P(doc, [
        T("On the production embedding the strongest relation is "),
        I("source"),
        T(" — which recorder, not which bird: recordist kNN lift +0.488 against species' +0.196 "
          "(docs/14 §14.4)"),
        C("d14"),
        T(". Every consumer of the embedding inherits that confound. The literature is unambiguous "
          "that invariance is a training-time problem"),
        C("moummad", "morocutti", "avex"),
        T(", and Birdy swept it three times on pre-registered gates (docs/17)"),
        C("d17"),
        T(":"),
    ])
    P(doc, [
        B("Loss engineering trades 1:1 with species. "),
        T("Channel-EQ simulation and Freq-MixStyle augmentation are perfectly species-safe and move "
          "recordist lift not at all (−0.7 % relative). The recordist-adversarial head does move "
          "it — and the trade is almost perfectly linear in log weight: −33 % recordist at w 0.05 "
          "costs species accuracy −14.7 points; w 0.3 destroys the embedding (species accuracy "
          "0.199, realism AUC 0.862). No swept weight buys the required −30 % recordist while "
          "holding species within the gates: "),
        I("you can purchase recorder invariance with species information at roughly 1:1"),
        T(" (docs/17 §17.3)."),
    ])
    add_figure(doc, figs["adv"], [
        B("Figure 4. "),
        T("Adversarial sweeps on the 37-species debug store (debug-scale). Left: the recordist head "
          "trades recordist lift for species lift ~1:1. Right: the recording-within-species head "
          "never touches species — and barely reaches the recordist (−6 % at w 0.1 against the "
          "−30 % gate, dotted). Sources: docs/17 §17.3, §17.5"),
        C("d17"),
    ])
    P(doc, [
        B("The species-safe factorization cannot reach the confound. "),
        T("Masking the adversarial softmax to recordings of the patch's own species fences species "
          "information out by construction — and it works: species lift is flat to +10 % at every "
          "weight. But the target buys only −6 % against the −30 % gate, because the recordist "
          "signal is carried "),
        I("between"),
        T(" species (each species' recordings come from different people), where a species-factored "
          "head is forbidden to look (docs/17 §17.5)."),
    ])
    P(doc, [
        B("Data helps — and the honest re-test shrank it. "),
        T("The AVEX direction"),
        C("avex"),
        T(" held: merging two recording domains per species beat every loss. But the first test was "
          "12 species with a 3-species holdout, and the pre-registered bigger re-test (63 "
          "both-domain species, 16 held out) shrank every delta: the naive merge's +14.4 points "
          "became +3.6, and the cross-domain contrastive mechanism's +13.4-point boost became +1.7 "
          "against a +10 gate — small-sample structure, the same lesson as the mel-weight probe. "
          "What survives at both scales is the ordering: more domains per species helps, the "
          "mechanism adds ≈ nothing on top, and no loss term buys invariance cheaper than data "
          "(docs/17 §17.4, §17.6)."),
    ])
    add_figure(doc, figs["avex"], [
        B("Figure 5. "),
        T("Cross-domain species retrieval, three arms, two tests (both debug-scale; absolute levels "
          "are only comparable arm-vs-arm within each panel). The naive merge (B) beats "
          "single-domain (A) in both; the contrastive mechanism (C) looked decisive at 12 species "
          "and added +1.7 points at 63. Sources: docs/17 §17.4, §17.6"),
        C("d17"),
    ])
    H2(doc, "5.3 Song structure starves at current depth")
    P(doc, [
        T("Birdsong is not first-order — repeat-count adaptation and partially observable structure "
          "are established"),
        C("jin2011", "lu2025"),
        T(" — and Birdy ran the pre-registered bake-off anyway: current first-order transitions vs "
          "Jin–Kozhevnikov repeat-count vs hidden-state HMM, on held-out bout likelihood. M2 loses "
          "decisively (−0.348 nats/token, 0/30 species). M3 wins the rule (+0.422, 29/30) — and "
          "the decomposition reverses the adoption: on the 90 % of held-out transitions seen in "
          "training, first-order is the best model (−1.525 vs M3's −1.624), and M3's entire "
          "advantage sits in the 10 % unseen tail (−9.25 vs −4.16) — a property of smoothing "
          "*shape*, not recovered hidden structure. Adopting a heavier model for a smoothing "
          "artifact is the wrong lesson; first-order stays (docs/18 P1)"),
        C("d18"),
        T("."),
    ])
    P(doc, [
        T("The song-level kernel failed both its gates: a weighted edit-distance over (type, gap) "
          "sequences loses species lift to plain bag-of-types (+0.877 vs +0.924 on the 37-species "
          "store; +0.050 vs +0.081 on debug-100) and fails the recordist gate (+0.264). "
          "Within-species song structure exists — all 18 deep species separate their recordings — "
          "but it lives entirely in the token marginals: "),
        B("order and rhythm add nothing measurable at current depth"),
        T(". The reason is one number: only 12 of the debug-100 species have ≥ 20 bouts. The bar "
          "for any learned song encoder is now bag-of-types, after the depth harvest (docs/18 "
          "P2)"),
        C("d18"),
        T("."),
    ])
    add_figure(doc, figs["depth"], [
        B("Figure 6. "),
        T("Why syntax starves: species of the debug-100 store with enough bouts for song-level "
          "structure (≥ 20 bouts after run-collapse). Debug-scale. Source: docs/18 (debug-100 "
          "cycle note)"),
        C("d18"),
    ])
    H2(doc, "5.4 Smaller refutations, kept on the record")
    P(doc, [
        B("The galaxy map's 0.61 is a metric problem, not a map problem. "),
        T("Decomposing the centroid-agreement loss over 3 731 held-out syllables: 76.4 % of it is "
          "boundary near-ties (74 % of all rows sit within margin 0.05; tie-adjusted agreement is "
          "0.91, and 41 % of flips land on the runner-up knot), and genuine big-margin map failure "
          "is ~2 % of rows. No better map class can fix near-ties; the honest single-label claim is "
          "species-level agreement, 0.78 (docs/20 §20.1)"),
        C("d20"),
        T("."),
    ])
    add_figure(doc, figs["spacemap"], [
        B("Figure 7. "),
        T("Decomposition of the 38.6 % knot-agreement loss (1 439 flips over 3 731 held-out "
          "syllables, debug build). Most of the “error” is the question being ill-posed at knot "
          "boundaries; genuine map failure is the two small violet bars. Source: docs/20 §20.1"),
        C("d20"),
    ])
    P(doc, [
        B("Pruning bad sessions from the fit fails. "),
        T("Dropping the worst-quintile off-manifold sessions costs −0.006 / −0.015 eval cosine on "
          "the two debug stores against a ≤ 0.005 allowance: the weird sessions "),
        I("are"),
        T(" manifold coverage, and pruning them hurts the next unseen weird session. Gating is a "
          "live-path action only (docs/20 §20.3.1). "),
        B("The learned inverse failed its ship rule. "),
        T("An encoder predicting synthesis parameters from mel patches — trained on 150 k free "
          "rendered pairs — matched the coordinate descent on cosine (0.737 vs 0.734) but the "
          "pre-registered 2× speedup never existed on the hardware (0.2 s either way); it stays "
          "experimental, documented in place (docs/10 §10.5). "),
        B("Novelty thresholds do not transfer across harvest epochs. "),
        T("A threshold calibrated for 5 % false positives on the 9 k store flagged 29.8 % of the "
          "47 k store; recalibration is cheap and now automatic, and the honest ROCs are reported "
          "per epoch (0.596 → 0.786 → 0.846) rather than the best one (docs/10 §10.3, docs/14 "
          "§14.3, docs/16 §16.2)"),
        C("d10", "d14", "d16"),
        T("."),
    ])

    # ================= 6. The unknown-bird pipeline =================
    H1(doc, "6. The unknown-bird pipeline")
    plain_terms(
        doc,
        "What happens when a bird the system has never heard starts to sing? Not a guess, and not "
        "silence. The arrival is measured, compared against everything known, and — if it fits "
        "nothing — it is allowed to be new: it gathers with similar arrivals until enough of them "
        "agree to found a new knot in the galaxy, labelled exactly as honestly as the situation "
        "deserves: real acoustics, no documented function. An external model may suggest which "
        "species it resembles, but that suggestion is metadata, never identity."
    )
    P(doc, [
        T("The arrival pipeline is live end to end (docs/10 §10.3, §10.4; docs/16 §16.5)"),
        C("d10", "d16"),
        T(". At ingest, each new observation is embedded and scored against the calibrated novelty "
          "threshold — a chosen false-positive rate, not a discovered one. Known-looking syllables "
          "inherit the nearest type (in a relabel-recovery test, 97.4 % of relabelled syllables "
          "inherited a known type, 65.2 % the correct species' type; misassignments go to "
          "similar-sounding types of other species — the detector prices acoustic neighbourhood, "
          "not taxonomy, and the wren counterexample proves it). Novel syllables are not "
          "force-assigned: below quorum they stay unassigned; at quorum (≥ 8 coherent pending "
          "points, 0.70 cosine radius, 0.75 cohesion floor) they found a new knot labelled "),
        I("“unheard syllable”"),
        T(", confidence "),
        B("unlabelled: real acoustics, no documented function"),
        T("."),
    ])
    P(doc, [
        T("A Perch 2.0 pass"),
        C("perch"),
        T(" (ONNX, offline, ~48 ms/window) labels the novel-flagged syllables from the training "
          "cache as "),
        I("“closest documented species (Perch 2.0 inference, unverified)”"),
        T(" — metadata only, never typing ground truth; nothing in the learn path may read it. "
          "23 697 novel syllables were identified in the store; 841 are honestly unlabelable "
          "because their xeno-canto audio was deleted by design, and the pipeline says so rather "
          "than guessing. Structure above the syllable — sequence statistics, candidate song types "
          "for undocumented birds — inherits the same label all the way up (docs/18 P6)"),
        C("d18"),
        T(". Anything more confident than this pipeline is numerology, and the interface keeps "
          "saying so."),
    ])

    # ================= 7. Roadmap =================
    H1(doc, "7. Roadmap")
    plain_terms(
        doc,
        "The next steps, in order, each with the number that would prove it. First: listen longer "
        "to fewer birds, because nearly every open problem — grammar, dialects, the bench — is "
        "starved by shallow coverage rather than missing machinery. Then re-run the bake-offs that "
        "depth was blocking. The metrology problem underneath everything stays open and named."
    )
    P(doc, [
        B("P0 — Depth harvest (in progress at this writing). "),
        T("100 species × up to 30 recordings each, chosen for documented syntax cases, repertoire "
          "depth, and existing playback anchors, harvested in 25-species batches with the log read "
          "between batches (docs/18 P0; HANDOFF 2026-07-31)"),
        C("d18", "handoff"),
        T(". This one action unblocks the grammar re-test, the song-level space, and the widening "
          "of the spectral bench — nothing else on the roadmap does that."),
    ])
    P(doc, [
        B("P1 — Re-bake-off after depth. "),
        T("The first-order/Jin–Kozhevnikov/POMM comparison re-run once the unseen-transition tail "
        "shrinks; thin data is exactly where higher-order models starve, and M2's 0/30 says so. "),
        B("P2 — Song-level embedding. "),
        T("Bouts as points; the parameter-free kernel baseline already failed, so the bar any "
          "learned encoder must beat is bag-of-types (+0.924), with the recordist lift gate "
          "upstream (docs/18). "),
        B("P3 — CETI-style factorization"),
        C("sharma2024"),
        T(": decompose each deep species' songs into independent axes — rhythm, tempo, "
          "ornamentation — toward per-species combinatorial alphabets, the strongest honest claim "
          "available without playback. "),
        B("P4 — Dialect and individual maps. "),
        T("With depth: same-species variants placed geographically, individuals separated where "
          "10–16 bouts each exist — literature-proven sufficient (docs/18 P3–P4)"),
        C("d18"),
        T("."),
    ])
    P(doc, [
        B("The open problem, named. "),
        T("Underneath the roadmap sits metrology: the project optimises one number (the descriptor "
          "cosine, cluster-safe and audibly blind), measures with another (MCD/STFT, audibly "
          "faithful, optimiser-hostile), and has refuted the learned third (the realism logit). "),
        I("“An objective that is both remains unfound.”"),
        T(" Every future fit gate reads the bench; every future objective candidate is "
          "pre-registered against it (docs/19 §19.5)"),
        C("d19"),
        T(". Structure first, meaning only from playback — that ordering is the roadmap's spine, "
          "and it does not move."),
    ])

    # ================= 8. References =================
    H1(doc, "8. References")
    P(doc, [
        T("External literature and internal research notes, numbered in list order; in-text "
          "superscripts resolve here. Internal notes live in the repository's docs/ directory."),
    ])
    for i, (_, text) in enumerate(REFERENCES):
        p = P(doc, [B(f"[{i + 1}] "), T(text)], space_after=3)
        for run in p.runs:
            run.font.size = Pt(9)

    doc.save(DOCX_PATH)
    return DOCX_PATH


def main():
    os.makedirs(FIG, exist_ok=True)
    eq_paths = render_equations()
    figs = {
        "arch": diagram_architecture(),
        "bench": chart_bench(),
        "adv": chart_adversarial(),
        "avex": chart_avex(),
        "spacemap": chart_spacemap(),
        "gate": chart_session_gate(),
        "depth": chart_depth(),
    }
    out = build_docx(eq_paths, figs)
    print(f"equations: {len(eq_paths)} in {os.path.join(FIG, 'eq')}")
    print(f"charts:    {len(figs)} in {FIG}")
    print(f"docx:      {out}")


if __name__ == "__main__":
    main()

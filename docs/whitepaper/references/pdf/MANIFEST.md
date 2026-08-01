# PDF manifest

Fetched 2026-08-01. **65 PDFs, 148 MB.** Filenames are `<key>.pdf`, keys matching
[../REFERENCES.md](../REFERENCES.md) and [../references.bib](../references.bib).

## Fetching rules that were applied

Only sources that are legitimately free to fetch were used:

- arXiv (`arxiv.org/pdf/...`)
- PubMed Central and Europe PMC, for articles deposited there
- gold open-access publishers: PLOS, Frontiers, eLife, Nature Communications, Scientific Data,
  Royal Society (CC BY articles), PeerJ
- publisher "bronze" open access, where the publisher itself serves the PDF without a
  subscription
- author copies on institutional servers — chiefly the Mindlin lab's own reprint server at
  `lsd.df.uba.ar` and `lsd.df.uba.ar/wp-content/uploads/`, the UNSW music-acoustics
  publications page, the Dooling lab at UMD, and HAL
- NeurIPS proceedings, PMLR, JOSS

**No paywall was bypassed.** No proxy, no shadow library, no institutional credential, no
attempt to defeat an access control. Where a work is subscription-only, nothing was downloaded
and the DOI link is recorded instead.

Every file was checked after download: MIME type must be `application/pdf` and size must
exceed 15 kB. Anything that came back as an HTML interstitial was deleted rather than kept.

---

## Downloaded (65)

### Mindlin-lab author copies (12)

| key | source |
|---|---|
| `gardner2001` | lsd.df.uba.ar/papers/simplemotorgestures.pdf |
| `laje2002a` | lsd.df.uba.ar/papers/PRE65-2002-neuromuscular.pdf |
| `laje2002b` | lsd.df.uba.ar/papers/diversity.pdf |
| `laje2005` | lsd.df.uba.ar/papers/PhysRevE.72.036218.pdf |
| `sitt2008` | lsd.df.uba.ar/papers/PRE2008-Sitt-zffinch.pdf |
| `amador2008` | lsd.df.uba.ar/papers/Chaos_18_043123.pdf |
| `sitt2010` | lsd.df.uba.ar/papers/electronic_jaco.pdf |
| `perl2011` | lsd.df.uba.ar/papers/PhysRevE.84.051909.pdf |
| `uribarri2020` | lsd.df.uba.ar/papers/PhysRevLett.124.098101.pdf |
| `doppler2020` | lsd.df.uba.ar/wp-content/uploads/2021/02/con_juan_benteveo.pdf |
| `bistel2024` | lsd.df.uba.ar/wp-content/uploads/2024/07/wild.pdf |
| `amador2023` | lsd.df.uba.ar/wp-content/uploads/2023/11/Amador-Mindlin-2023-jeb227975.pdf |

These are the versions of record posted by the authors. APS journals (Phys. Rev. E, PRL) and
*Chaos* are subscription venues; the author copies are what makes this set readable.

### Gold or bronze open access at the publisher (15)

`arneodo2012`, `sainburg2020`, `elemans2008`, `wood2013`, `ohms2010`, `katahira2011`,
`jin2011` (PLOS) · `amador2021`, `jackel2022` (Frontiers) · `goffinet2021` (eLife) ·
`suzuki2016`, `elie2018`, `sharma2024` (Nature Communications) · `nbm2026` (Scientific Data) ·
`kazemi2023` (Royal Society, CC BY via PMC).

### PubMed Central / Europe PMC (11)

`beckers2003` (PMC165882) · `riede2006` (PMC1459391) · `brinklov2013` (PMC3664765) ·
`elemans2010` (PMC3487382) · `boari2015` (PMC4737419) · `elemans2008dove` (PMC2607454) ·
`bostwick2009` (PMC2842718) · `lu2025` (PMC11866996) · `rhinehart2020` (PMC7381559).

### arXiv (19)

`fainstein2025` (v2), `perch2`, `aves2022`, `birdmae2025`, `avex2025`, `naturelm2024`, `birdset2024`, `moummad2024`,
`morocutti2023`, `denton2021`, `inatsounds2024`, `finchgpt2025`, `umap2018`, `simclr2020`, and `nbm2026` (Scientific Data version).

Added 2026-08-01 for the arXiv manuscript's own citations: `beans2022` (2210.12300),
`cilibrasi2005` (cs/0312044), `li2004` (cs/0111054), `cranmer2020` (1911.01429),
`zhou2021mixstyle` (2104.02008). For `cilibrasi2005` and `li2004` the IEEE versions of record
are paywalled, so what is held is the author preprint — noted because the page numbers in the
bib entry are the IEEE ones.

### Author / institutional copies and proceedings (8)

| key | source |
|---|---|
| `fletcher1988` | UNSW music acoustics publications |
| `fletcher1999` | UNSW music acoustics publications |
| `tu2011` | Dooling lab, University of Maryland |
| `lostanlen2024` | VIHAR 2024 proceedings, `vihar-2024.vihar.org` — **see note below** |
| `rff2007` | NeurIPS 2007 proceedings (papers.nips.cc) |
| `umapsoft2018` | Journal of Open Source Software |
| `hdbscansoft2017` | Journal of Open Source Software |
| `ganin2016` | Journal of Machine Learning Research (`jmlr.org/papers/volume17/15-239/15-239.pdf`) — JMLR is fully open access and assigns no DOI |

**Note on `lostanlen2024.pdf`:** this file is the **entire VIHAR 2024 proceedings** (19 MB),
not the single extended abstract. The HAL single-paper copy
(<https://hal.science/hal-04660514/document>) is open access but sits behind an automated
bot check that a scripted fetch cannot clear. Fetch it manually, or extract the relevant pages
from the proceedings.

---

## Not downloaded (42)

Recorded here with the DOI link. Nothing was attempted beyond a normal request to the
publisher's own page.

Most of these are **subscription only**. Six are not, and are marked as such in the status
column: `laje2008` has an author copy whose URL contains spaces that a scripted fetch could not
handle, and `amador2013`, `garcia2017`, `riede2009` and `riedegoller2010` are free author
manuscripts on PMC whose PDF-render endpoint returned a server error, as is `korsunsky2019`.
All six are worth fetching by hand — `amador2013` in particular, since it turns out to be the primary source for
the noise-on-tension claim (CITATION-FINDINGS #4).

| key | citation | link | status |
|---|---|---|---|
| `mindlin2005` | Mindlin & Laje, *The Physics of Birdsong*, Springer 2005 | <https://doi.org/10.1007/3-540-28249-1> | book, paywalled, not downloaded. Controlled-lending scan at archive.org only |
| `laje2008` | Phys. Rev. E 77:011912 | <https://doi.org/10.1103/PhysRevE.77.011912> | author copy exists at lsd.df.uba.ar but the URL contains spaces and did not resolve in scripted form; fetch manually |
| `amador2013` | Nature 495:59–64 | <https://doi.org/10.1038/nature11967> | paywalled at publisher; free author manuscript at <https://pmc.ncbi.nlm.nih.gov/articles/PMC3878432/> — the PDF render endpoint returned an error, fetch manually |
| `garcia2017` | Curr. Biol. 27:2677–2683 | <https://doi.org/10.1016/j.cub.2017.07.059> | free at <https://pmc.ncbi.nlm.nih.gov/articles/PMC5599221/>; PDF render endpoint errored, fetch manually |
| `riede2009` | J. Comp. Physiol. A 195:183–192 | <https://doi.org/10.1007/s00359-008-0397-0> | free at <https://pmc.ncbi.nlm.nih.gov/articles/PMC2826496/>; PDF render endpoint errored, fetch manually |
| `riedegoller2010` | Brain and Language 115:69–80 | <https://doi.org/10.1016/j.bandl.2009.11.003> | free at <https://pmc.ncbi.nlm.nih.gov/articles/PMC2896990/>; PDF render endpoint errored, fetch manually |
| `fee1998` | Nature 395:67–71 | <https://doi.org/10.1038/25725> | paywalled, not downloaded. Pre-dates NIH deposit mandates; no free copy found |
| `nowicki1987` | Nature 325:53–55 | <https://doi.org/10.1038/325053a0> | paywalled, not downloaded |
| `suthers1990` | Nature 347:473–477 | <https://doi.org/10.1038/347473a0> | paywalled, not downloaded |
| `beckers2004` | Curr. Biol. 14:1592–1597 | <https://doi.org/10.1016/j.cub.2004.08.057> | paywalled, not downloaded |
| `fletcher2006` | JASA 119:1005–1011 | <https://doi.org/10.1121/1.2159434> | paywalled, not downloaded |
| `goller1996a` | J. Neurophysiol. 75:867–876 | <https://doi.org/10.1152/jn.1996.75.2.867> | paywalled, not downloaded |
| `goller1996b` | J. Neurophysiol. 76:287–300 | <https://doi.org/10.1152/jn.1996.76.1.287> | paywalled, not downloaded |
| `hartley1989` | J. Comp. Physiol. A 165:15–26 | <https://doi.org/10.1007/BF00613795> | paywalled, not downloaded |
| `larsen1999` | Proc. R. Soc. B 266:1609–1615 | <https://doi.org/10.1098/rspb.1999.0822> | green OA in principle (PMC1690181) but no retrievable full text; not downloaded |
| `podos2004` | J. Exp. Biol. 207:607–619 | <https://doi.org/10.1242/jeb.00770> | paywalled, not downloaded |
| `podos2001` | Nature 409:185–188 | <https://doi.org/10.1038/35051570> | paywalled, not downloaded |
| `riede2004` | J. Exp. Biol. 207:4025–4036 | <https://doi.org/10.1242/jeb.01256> | paywalled, not downloaded |
| `warren1996` | The Auk 113:41–58 | <https://doi.org/10.2307/4088934> | paywalled, not downloaded |
| `suthers1985` | J. Comp. Physiol. A 156:243–266 | <https://doi.org/10.1007/BF00610867> | paywalled, not downloaded |
| `suthers1994` | J. Comp. Physiol. A 175:457–466 | <https://doi.org/10.1007/BF00199253> | paywalled, not downloaded |
| `ishizaka1972` | Bell Syst. Tech. J. 51:1233–1268 | <https://doi.org/10.1002/j.1538-7305.1972.tb02651.x> | paywalled, not downloaded |
| `tumer2007` | Nature 450:1240–1244 | <https://doi.org/10.1038/nature06390> | paywalled, not downloaded. **Note:** the unverifiable "~1 % f₀ CV" figure (CITATION-FINDINGS #17) needs this full text |
| `rutz2023` | Science 381:152–155 | <https://doi.org/10.1126/science.adg7314> | paywalled, not downloaded |
| `griesser2008` | Curr. Biol. 18:69–73 | <https://doi.org/10.1016/j.cub.2007.11.069> | paywalled, not downloaded |
| `freeberg2003` | JASA 113:2127–2136 | <https://doi.org/10.1121/1.1559175> | paywalled, not downloaded |
| `hailman1985` | Semiotica 56:191–224 | <https://doi.org/10.1515/semi.1985.56.3-4.191> | paywalled, not downloaded |
| `templeton2005` | Science 308:1934–1937 | <https://doi.org/10.1126/science.1108841> | paywalled, not downloaded |
| `hultsch1989` | J. Comp. Physiol. A 165:197–203 | <https://doi.org/10.1007/BF00619194> | paywalled, not downloaded |
| `hultsch1981` | Behav. Ecol. Sociobiol. 8:183–188 | <https://doi.org/10.1007/BF00299828> | paywalled, not downloaded |
| `okanoya2004` | Ann. N.Y. Acad. Sci. 1016:724–735 | <https://doi.org/10.1196/annals.1298.026> | paywalled, not downloaded |
| `nemeth2006` | JASA 119:620–626 | <https://doi.org/10.1121/1.2139072> | paywalled, not downloaded |
| `dabelsteen1993` | JASA 93:2206–2220 | <https://doi.org/10.1121/1.406682> | green (submitted version in a repository); publisher version paywalled, not downloaded |
| `birdnet2021` | Ecol. Inform. 61:101236 | <https://doi.org/10.1016/j.ecoinf.2021.101236> | hybrid; no confirmed free PDF located |
| `patelgrosz2023` | Linguist. Philos. 46:627–692 | <https://doi.org/10.1007/s10988-022-09377-8> | hybrid; author copy at <https://hal.science/hal-04573423> (bot-checked, fetch manually) |
| `hdbscan2013` | PAKDD 2013, LNCS 7819:160–172 | <https://doi.org/10.1007/978-3-642-37456-2_14> | Springer, paywalled, not downloaded. The extended journal version (ACM TKDD, <https://doi.org/10.1145/2733381>) is also paywalled |
| `berwick2011` | Trends Cogn. Sci. 15:113–121 | <https://doi.org/10.1016/j.tics.2011.01.002> | paywalled, not downloaded |
| `dalziell2012` | Animal Behaviour 83:1401–1410 | <https://doi.org/10.1016/j.anbehav.2012.03.009> | paywalled, not downloaded (Unpaywall: closed). Abstract verified via the ANU repository record <https://openresearch-repository.anu.edu.au/handle/1885/64477> |
| `kneser1995` | ICASSP-95, vol. 1, 181–184 | <https://doi.org/10.1109/ICASSP.1995.479394> | IEEE, paywalled, not downloaded |
| `kubichek1993` | PACRIM-93, vol. 1, 125–128 | <https://doi.org/10.1109/PACRIM.1993.407206> | IEEE, paywalled, not downloaded |
| `prince2007` | ICCV 2007, 1–8 | <https://doi.org/10.1109/ICCV.2007.4409052> | IEEE, paywalled, not downloaded |
| `korsunsky2019` | Nature Methods 16:1289–1296 | <https://doi.org/10.1038/s41592-019-0619-0> | **not paywalled** — free author manuscript at <https://pmc.ncbi.nlm.nih.gov/articles/PMC6884693/>; the PDF render endpoint returned a server error. Fetch by hand |

## Not downloaded — open access, but the publisher blocks automated fetch (9)

These are all free to read. Every attempt returned HTTP 403 from an anti-bot layer
(Cloudflare or equivalent), not a paywall. Open the link in a browser to get the PDF.

| key | link |
|---|---|
| `nelson2005` | <https://journals.biologists.com/jeb/article/208/2/297/15809/> |
| `zollinger2008` | <https://journals.biologists.com/jeb/article/211/12/1978/17631> |
| `ohms2012` | <https://journals.biologists.com/jeb/article/215/1/85/10797> |
| `ballintijn1998` | <https://journals.biologists.com/jeb/article-abstract/201/10/1637/7672> |
| `clark2015` | <https://journals.biologists.com/jeb/article/218/21/3520/14411/> |
| `slabbekoorn2002` | <https://academic.oup.com/condor/article/104/3/564/5563226> |
| `a2o2021` | <https://besjournals.onlinelibrary.wiley.com/doi/10.1111/2041-210X.13660> |
| `chronister2021` | <https://esajournals.onlinelibrary.wiley.com/doi/10.1002/ecy.3329> |
| `nips4bplus2019` | <https://peerj.com/articles/cs-223/> |

Note that `ohms2012` and `nelson2005` between them carry most of the vocal-tract numbers the
project's `syrinx.py` constants rest on. They were both read during verification through the
publisher's HTML full text; only the PDF fetch was blocked.

## Not applicable (4)

`ddsp2020` and `rave2021` are on arXiv and could be fetched, but the project cites them only as
approaches it deliberately rejects (`docs/21` §21.4) — no claim depends on their content.
`farnell2010` is a book. The corpus and software URLs listed at the end of REFERENCES.md §7
are resources, not documents.

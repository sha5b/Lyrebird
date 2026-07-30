"""Audio sources beyond xeno-canto: one registry, six adapters, zero retained audio.

xeno-canto is the bottleneck of the harvest: v3 requires a personal key, rate-limits
per account, and paces a pass at `--pause` seconds a request. The open-dataset world
carries a great deal of bird audio that costs no key at all — the xccoverbl
xeno-canto mirror (264 flacs over 88 UK species, with a metadata csv), warblr and
ff1010bird (bird/no-bird control sets), BirdCLEF's competition archives, BirdSet's
~520 000-recording xeno-canto repackaging, the XCDC dawn-chorus set, iNatSounds'
230 000-observation iNaturalist dump. This module puts them behind one interface so
`birdy-pipeline sources list` can say, honestly, which of them this machine can use
right now.

Two rules bind every adapter, and they are the same rules `harvest.py` lives by:

- **No audio is ever retained.** Staged downloads land in a `TemporaryDirectory`, are
  decoded, described and folded into the store by the very same `ingest_file` the
  xeno-canto path uses, and the directory — audio included — is gone when the fetch
  returns. What survives is descriptors, syllable observations and a CREDITS.md row.
- **An unfilled key is a skip, never an error.** `available()` reports
  `(False, "reason")` and the CLI logs `skip <source>: <reason>` and exits 0. A source
  that needs a package (`kaggle`, `huggingface_hub`) imports it lazily inside the
  adapter, mirroring `critic.py`'s torch pattern, so a machine that only harvests from
  Zenodo never has to install them.

Access mechanics below were verified against the live services on 2026-07-29; where a
source turned out to be shaped differently than expected, the docstring says what it
actually is rather than what it was hoped to be.
"""

from __future__ import annotations

import csv
import io
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

from . import harvest
from .harvest import HarvestReport, HarvestStore, ingest_file, log, species_id_for

USER_AGENT = harvest.USER_AGENT
DOWNLOAD_TIMEOUT = harvest.DOWNLOAD_TIMEOUT

#: Members of a staged download we will feed to the decoder. Everything else a record
#: or archive carries (csvs, readmes, torrent files) is metadata, not audio.
AUDIO_SUFFIXES = {".wav", ".flac", ".mp3", ".ogg", ".opus", ".m4a", ".aif", ".aiff"}


def _get_json(url: str, timeout: int = 60, headers: dict[str, str] | None = None) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return json.loads(res.read().decode("utf-8"))


def _download(url: str, dest: Path, timeout: int = DOWNLOAD_TIMEOUT,
              headers: dict[str, str] | None = None) -> Path:
    """Stream one URL to disk. The file lands in a staging dir whose lifetime the caller owns."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as res, dest.open("wb") as fh:
        shutil.copyfileobj(res, fh, length=1 << 16)
    return dest


def _remote_size(url: str, timeout: int = 60) -> int:
    """Total length of an HTTP resource, from a one-byte ranged GET.

    A HEAD is not enough: some servers (the Internet Archive's download nodes among
    them) answer a ranged GET happily while giving a HEAD nothing trustworthy, and it
    is the ranged GET that has to work for `RemoteZip` anyway.
    """
    req = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Range": "bytes=0-0"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as res:
        content_range = res.headers.get("Content-Range", "")
        if "/" in content_range and content_range.rsplit("/", 1)[1].isdigit():
            return int(content_range.rsplit("/", 1)[1])
        length = res.headers.get("Content-Length")
        if length:
            return int(length)
    raise RuntimeError(f"{url}: server gave neither Content-Range nor Content-Length")


class _RangeFile(io.RawIOBase):
    """A seekable read-only file object over an HTTP resource, fetched in ranged blocks.

    This exists for one reason: the useful open archives are enormous single zips —
    warblrb10k is 4.9 GB, ff1010bird 5.7 GB — and a zip's directory sits at its *end*,
    so any per-file access means ranged reads. `zipfile` drives this like a normal
    seekable file; each `read` that crosses the cached window costs one HTTP request.
    """

    def __init__(self, url: str, size: int, block: int = 1 << 20):
        self.url = url
        self.size = int(size)
        self.block = int(block)
        self.pos = 0
        self._cache_start = -1
        self._cache = b""

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self.pos

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        if whence == io.SEEK_CUR:
            offset = self.pos + offset
        elif whence == io.SEEK_END:
            offset = self.size + offset
        self.pos = max(0, min(int(offset), self.size))
        return self.pos

    def read(self, n: int = -1) -> bytes:
        if n is None or n < 0:
            n = self.size - self.pos
        n = min(int(n), self.size - self.pos)
        out = bytearray()
        while len(out) < n:
            at = self.pos + len(out)
            if not (self._cache_start <= at < self._cache_start + len(self._cache)):
                self._cache_start = at
                end = min(at + self.block, self.size) - 1
                req = urllib.request.Request(
                    self.url,
                    headers={"User-Agent": USER_AGENT, "Range": f"bytes={at}-{end}"},
                )
                with urllib.request.urlopen(req, timeout=DOWNLOAD_TIMEOUT) as res:
                    self._cache = res.read()
            lo = at - self._cache_start
            take = min(len(self._cache) - lo, n - len(out))
            out += self._cache[lo : lo + take]
        self.pos += len(out)
        return bytes(out)


class RemoteZip:
    """Random access into a multi-GB zip over HTTP range requests.

    Fetching the central directory of warblrb10k (8001 entries, ZIP64) costs one
    628 KB request against the 4.9 GB whole; extracting one member costs a couple of
    requests the size of that member. That is the difference between "2 warblr clips"
    and "download 4.9 GB to read 2 MB", and it is why this class exists. Verified
    against archive.org's download nodes on 2026-07-29 (`Accept-Ranges: bytes`).
    """

    def __init__(self, url: str):
        self.url = url
        self.size = _remote_size(url)
        self._zip = zipfile.ZipFile(_RangeFile(url, self.size))

    def names(self) -> list[str]:
        return self._zip.namelist()

    def extract(self, member: str, dest_dir: Path) -> Path:
        dest = Path(dest_dir) / Path(member).name
        with self._zip.open(member) as src, dest.open("wb") as fh:
            shutil.copyfileobj(src, fh, length=1 << 16)
        return dest


def _ingest_staged(
    store: HarvestStore,
    path: Path,
    species_id: str,
    recording_id: str,
    info: dict[str, Any],
    max_seconds: float | None,
    report: HarvestReport,
) -> bool:
    """One staged file through the exact loop `harvest_xeno_canto` runs: ingest, note, let go.

    The caller's `TemporaryDirectory` deletes the audio; this just makes the per-file
    bookkeeping identical to the xeno-canto path's, so a store cannot tell which
    service a descriptor arrived from.
    """
    if store.has(recording_id):
        report.skipped += 1
        return False
    before = report.retained
    try:
        ingest_file(store, path, species_id, recording_id, max_seconds, report)
    except Exception as exc:
        report.failed += 1
        log(f"  skip {recording_id}: {exc}")
        return False
    store.note_recording(recording_id, info)
    report.recordings += 1
    log(f"  {recording_id[:40]:40} +{report.retained - before:4d} kept  store={len(store)}")
    return True


class Source:
    """Registry entry: a name, an honest availability check, and a fetch loop."""

    name = "?"
    summary = "?"

    def available(self) -> tuple[bool, str]:
        raise NotImplementedError

    def fetch(
        self,
        store: HarvestStore,
        species: str | None = None,
        limit: int = 5,
        max_seconds: float | None = harvest.DEFAULT_MAX_SECONDS,
        item: str | None = None,
    ) -> HarvestReport:
        raise NotImplementedError


# --- zenodo -----------------------------------------------------------------------


class ZenodoSource(Source):
    """Zenodo's REST records API — keyless; `ZENODO_TOKEN` only raises the rate limits.

    Checked against the live API on 2026-07-29: **warblr and freefield1010 are not on
    Zenodo** (a full-text search returns only derived evaluation sets, e.g. record
    1298604 for DCASE 2018). They live on the Internet Archive — see `ArchiveSource`.
    What Zenodo does carry:

    - **XCDC** (record 15420487, doi:10.5281/zenodo.15420487): 576 xeno-canto
      dawn-chorus soundscapes, each ≥3 min with ≥10 species, CC-BY-NC-ND-4.0, as ONE
      23.6 GB tar.gz plus a 403 KB recordings csv. Multi-species by construction, so
      nothing here may be filed under one species: points land as `unlabelled` and the
      species list rides along in the recording info. Fetched by streaming the tar
      from byte 0 — sequential, so `--limit` members cost their own size, not the
      archive's.
    - **BirdVox-full-night** (record 1205569): six ~1 GB continuous night flacs whose
      annotations are flight-call detections, *not* species labels. Listed here so the
      record is straight; there is no honest species-typed fetch to offer from it.

    Any other record id can be passed via `item`; the adapter then downloads the
    record's smallest audio files up to `--limit`, labelled by `--species` or
    `unlabelled`.
    """

    name = "zenodo"
    summary = "XCDC dawn-chorus soundscapes (record 15420487) + any open Zenodo record"
    API = "https://zenodo.org/api/records"
    XCDC_RECORD = "15420487"

    def available(self) -> tuple[bool, str]:
        return True, "no key needed; ZENODO_TOKEN (optional) only raises rate limits"

    def _headers(self) -> dict[str, str]:
        token = os.environ.get("ZENODO_TOKEN", "").strip()
        return {"Authorization": f"Bearer {token}"} if token else {}

    def _record(self, record_id: str) -> dict[str, Any]:
        return _get_json(f"{self.API}/{record_id}", headers=self._headers())

    def fetch(self, store, species=None, limit=5,
              max_seconds=harvest.DEFAULT_MAX_SECONDS, item=None) -> HarvestReport:
        record_id = item or self.XCDC_RECORD
        report = HarvestReport()
        record = self._record(record_id)
        title = record.get("metadata", {}).get("title", "")
        licence = (record.get("metadata", {}).get("license") or {}).get("id", "")
        log(f"zenodo record {record_id}: {title} ({licence or 'no licence listed'})")
        files = record.get("files", [])
        with tempfile.TemporaryDirectory() as tmp:
            staging = Path(tmp)
            if record_id == self.XCDC_RECORD:
                return self._fetch_xcdc(
                    store, files, staging, limit, max_seconds, licence, report
                )
            audio = sorted(
                (f for f in files if Path(f.get("key", "")).suffix.lower() in AUDIO_SUFFIXES),
                key=lambda f: int(f.get("size") or 0),
            )
            if not audio:
                log(f"  record {record_id} carries no audio files; nothing to fetch")
                return report
            sid = species_id_for(species) if species else "unlabelled"
            for f in audio[: max(0, limit)]:
                key = f["key"]
                rid = f"zenodo{record_id}-{Path(key).stem}"
                info = {
                    "speciesId": sid,
                    "scientific": species or "",
                    "recordist": "",
                    "licence": licence,
                    "url": f"https://doi.org/{record.get('doi', record_id)}",
                    "type": f"zenodo:{title[:60]}",
                }
                try:
                    staged = _download(f["links"]["self"], staging / Path(key).name,
                                       headers=self._headers())
                except Exception as exc:
                    report.failed += 1
                    log(f"  skip {key}: {exc}")
                    continue
                _ingest_staged(store, staged, sid, rid, info, max_seconds, report)
        return report

    def _fetch_xcdc(self, store, files, staging, limit, max_seconds, licence, report):
        csv_file = next((f for f in files if f.get("key", "").endswith(".csv")), None)
        tar_file = next((f for f in files if f.get("key", "").endswith(".tar.gz")), None)
        if not csv_file or not tar_file:
            log("  XCDC record does not have the expected csv + tar.gz layout")
            return report
        meta_path = _download(csv_file["links"]["self"], staging / csv_file["key"],
                              headers=self._headers())
        rows = {r["audio_id"]: r for r in csv.DictReader(meta_path.open())}
        log(f"  streaming {tar_file['key']} ({int(tar_file['size']) / 1e9:.1f} GB) "
            f"from byte 0 until {limit} recording(s) are ingested")
        req = urllib.request.Request(
            tar_file["links"]["self"],
            headers={"User-Agent": USER_AGENT, **self._headers()},
        )
        with urllib.request.urlopen(req, timeout=DOWNLOAD_TIMEOUT) as res:
            stream = tarfile.open(fileobj=res, mode="r|gz")
            taken = 0
            for member in stream:
                if taken >= limit:
                    break
                if not member.isfile() or Path(member.name).suffix.lower() not in AUDIO_SUFFIXES:
                    continue
                stem = Path(member.name).stem
                audio_id = stem[2:] if stem.startswith("XC") else stem
                rid = f"XC{audio_id}"
                row = rows.get(audio_id, {})
                info = {
                    "speciesId": "unlabelled",
                    "scientific": row.get("main_scientific", ""),
                    "english": row.get("main_common", ""),
                    "recordist": row.get("recordist", ""),
                    "licence": licence,
                    "url": row.get("url", ""),
                    "type": "dawn-chorus soundscape",
                    "also": [row.get("all_scientific", "")],
                    "date": row.get("date", ""),
                }
                staged = staging / Path(member.name).name
                src = stream.extractfile(member)
                with staged.open("wb") as fh:
                    shutil.copyfileobj(src, fh, length=1 << 16)
                if _ingest_staged(store, staged, "unlabelled", rid, info,
                                  max_seconds, report):
                    taken += 1
                staged.unlink(missing_ok=True)
        return report


# --- internet archive -------------------------------------------------------------

IA_META = "https://archive.org/metadata/{}"
IA_DL = "https://archive.org/download/{}/{}"
#: The DCASE Bird Audio Detection challenge's label csvs, on figshare — the same URLs
#: the maintained `soundata` loader resolves. NOT inside the IA zips (their zips are
#: wavs and nothing else, checked 2026-07-29). Both are `itemid,datasetid,hasbird`.
WARBLR_LABELS_CSV = "https://ndownloader.figshare.com/files/10853306"
FF1010_LABELS_CSV = "https://ndownloader.figshare.com/files/10853303"


class ArchiveSource(Source):
    """archive.org — keyless. Home of the sets everyone assumes are on Zenodo.

    Verified against the live metadata API on 2026-07-29:

    - **`xccoverbl_2014`** (default): a xeno-canto mirror — 264 flacs balanced over 88
      UK species, with `xcmeta.csv` carrying each recording's xeno-canto id, species,
      recordist and CC licence. Files download individually, so a probe costs a few
      MB. Recording ids are the original XC ids, so the store deduplicates this
      against a real xeno-canto harvest for free.
    - **`warblrb10k_public`**: the warblr set (8 000 ten-second UK smartphone clips,
      CC-BY-4.0) as ONE 4.9 GB zip, read through `RemoteZip` — directory and members
      over range requests, never the whole archive. **Not species-labelled.** The
      "8 000 species-labelled clips" description circulates widely (this module's
      first draft repeated it); the only public labels are the challenge's binary
      `hasbird` csv (6 045 bird / 1 955 no-bird), so warblr is a control set and is
      filed as one.
    - **`ff1010bird`**: freefield1010 annotated for bird presence/absence — the other
      control set (1 935 bird / 5 755 no-bird), same treatment.
    """

    name = "internet-archive"
    summary = "xccoverbl (XC mirror, 88 UK species) + warblr/ff1010bird controls"

    ITEMS = ("xccoverbl_2014", "warblrb10k_public", "ff1010bird")

    def available(self) -> tuple[bool, str]:
        return True, "no key needed"

    def fetch(self, store, species=None, limit=5,
              max_seconds=harvest.DEFAULT_MAX_SECONDS, item=None) -> HarvestReport:
        item = item or "xccoverbl_2014"
        if item == "xccoverbl_2014":
            return self._fetch_xccoverbl(store, species, limit, max_seconds)
        if item == "warblrb10k_public":
            return self._fetch_warblr(store, species, limit, max_seconds)
        if item == "ff1010bird":
            return self._fetch_ff1010(store, limit, max_seconds)
        raise RuntimeError(f"unknown archive.org item {item!r}; known: {', '.join(self.ITEMS)}")

    def _item_files(self, item: str) -> list[dict[str, Any]]:
        return _get_json(IA_META.format(item)).get("files", [])

    def _fetch_xccoverbl(self, store, species, limit, max_seconds) -> HarvestReport:
        report = HarvestReport()
        item = "xccoverbl_2014"
        with tempfile.TemporaryDirectory() as tmp:
            staging = Path(tmp)
            meta = _download(IA_DL.format(item, "xcmeta.csv"), staging / "xcmeta.csv")
            rows = list(csv.DictReader(meta.open(), delimiter="\t"))
            wanted = species_id_for(species) if species else ""
            if wanted:
                rows = [r for r in rows if species_id_for(f"{r['gen']} {r['sp']}") == wanted]
                if not rows:
                    log(f"  no {species!r} in xccoverbl's 88 species")
                    return report
            log(f"  xccoverbl_2014: {len(rows)} candidate recordings"
                + (f" for {species!r}" if wanted else " (88 species; taking the first)"))
            for row in rows[: max(0, limit)]:
                rid = f"XC{row['id']}"
                sid = species_id_for(f"{row['gen']} {row['sp']}") or "unlabelled"
                info = {
                    "speciesId": sid,
                    "scientific": f"{row['gen']} {row['sp']}".strip(),
                    "english": row.get("en", ""),
                    "recordist": row.get("rec", ""),
                    "licence": row.get("lic", ""),
                    "country": row.get("cnt", ""),
                    "type": row.get("type", ""),
                    "url": f"https://archive.org/details/{item}",
                }
                try:
                    staged = _download(IA_DL.format(item, f"xc{row['id']}.flac"),
                                       staging / f"xc{row['id']}.flac")
                except Exception as exc:
                    report.failed += 1
                    log(f"  skip {rid}: {exc}")
                    continue
                _ingest_staged(store, staged, sid, rid, info, max_seconds, report)
        return report

    def _fetch_control_zip(self, store, item, zip_name, meta_url, limit, max_seconds,
                           species) -> HarvestReport:
        """warblrb10k / ff1010bird: one giant zip of UUID wavs + a tiny label csv.

        The csvs are NOT in the zips (checked 2026-07-29: warblrb10k's zip is 8000
        wavs and nothing else) — they are the DCASE challenge's files on figshare, the
        same URLs the maintained `soundata` loader uses. Both csvs are
        `itemid,datasetid,hasbird`, so both sets are bird/no-bird CONTROLS and are
        filed under their own set name, never under a species.
        """
        report = HarvestReport()
        if species:
            log(f"  {item} has no species labels (hasbird 0/1 only); "
                "ignoring --species")
        rz = RemoteZip(IA_DL.format(item, zip_name))
        log(f"  {item}: zip is {rz.size / 1e9:.2f} GB; reading its directory over "
            "range requests, then only the members taken")
        with tempfile.TemporaryDirectory() as tmp:
            staging = Path(tmp)
            meta = _download(meta_url, staging / "labels.csv")
            hasbird = {
                (r.get("itemid") or "").strip(): (r.get("hasbird") or "").strip()
                for r in csv.DictReader(meta.open())
            }
            log(f"  labels: {len(hasbird)} rows "
                f"({sum(1 for v in hasbird.values() if v == '1')} bird / "
                f"{sum(1 for v in hasbird.values() if v == '0')} no-bird)")
            taken = 0
            for member in rz.names():
                if taken >= limit:
                    break
                if not member.lower().endswith(".wav"):
                    continue
                item_id = Path(member).stem
                rid = f"{item}-{item_id}"
                info = {
                    "speciesId": item,
                    "recordist": "",
                    "licence": f"CC-BY-4.0 ({item})",
                    "url": f"https://archive.org/details/{item}",
                    "type": f"control, hasbird={hasbird.get(item_id, '?')}",
                }
                try:
                    staged = rz.extract(member, staging)
                except Exception as exc:
                    report.failed += 1
                    log(f"  skip {rid}: {exc}")
                    continue
                if _ingest_staged(store, staged, item, rid, info, max_seconds, report):
                    taken += 1
                staged.unlink(missing_ok=True)
        return report

    def _fetch_warblr(self, store, species, limit, max_seconds) -> HarvestReport:
        return self._fetch_control_zip(
            store, "warblrb10k_public", "warblrb10k_public_wav.zip",
            WARBLR_LABELS_CSV, limit, max_seconds, species,
        )

    def _fetch_ff1010(self, store, limit, max_seconds) -> HarvestReport:
        return self._fetch_control_zip(
            store, "ff1010bird", "ff1010bird_wav.zip",
            FF1010_LABELS_CSV, limit, max_seconds, None,
        )


# --- kaggle -----------------------------------------------------------------------


class KaggleSource(Source):
    """BirdCLEF competition archives, via the `kaggle` package's CLI.

    Slugs `birdclef-2021` … `birdclef-2025` all resolve (checked 2026-07-29). The
    archives are tens of GB, so nothing here downloads one: the file list comes first
    (`kaggle competitions files`), `--species` (an eBird folder code such as
    `hawthr`, or a prefix of it) selects the `train_audio/<code>/` rows, and only
    those files are downloaded, one at a time, into staging.

    Competition archives come with competition rules, not a plain CC licence — the
    adapter records the competition page as the licence field, and BirdCLEF's terms
    apply to anything built from the descriptors.

    Both requirements are soft: no `kaggle` package → skip; no credentials
    (`KAGGLE_USERNAME` + `KAGGLE_KEY`, or `~/.kaggle/kaggle.json`) → skip.
    """

    name = "kaggle"
    summary = "BirdCLEF 2021-2025 train_audio, per-species folders only"

    SLUGS = [f"birdclef-{year}" for year in range(2021, 2026)]

    def available(self) -> tuple[bool, str]:
        if not shutil.which("kaggle"):
            return False, ("the `kaggle` package is not installed "
                           "(uv sync --extra sources)")
        if not (
            (os.environ.get("KAGGLE_USERNAME") and os.environ.get("KAGGLE_KEY"))
            or (Path.home() / ".kaggle" / "kaggle.json").exists()
        ):
            return False, ("no credentials: set KAGGLE_USERNAME + KAGGLE_KEY, or "
                           "create ~/.kaggle/kaggle.json from https://www.kaggle.com/settings")
        return True, ""

    def fetch(self, store, species=None, limit=5,
              max_seconds=harvest.DEFAULT_MAX_SECONDS, item=None) -> HarvestReport:
        slug = item or "birdclef-2024"
        report = HarvestReport()
        listing = subprocess.run(
            ["kaggle", "competitions", "files", slug, "--csv"],
            capture_output=True, text=True, timeout=300,
        )
        if listing.returncode != 0:
            log(f"  kaggle competitions files {slug} failed: "
                f"{listing.stderr.strip()[:200]}")
            return report
        rows = list(csv.DictReader(listing.stdout.splitlines()))
        names = [r.get("name", "") for r in rows]
        audio = [n for n in names
                 if n.startswith("train_audio/") and Path(n).suffix.lower() in AUDIO_SUFFIXES]
        if species:
            wanted = species.lower().strip()
            audio = [n for n in audio if n.split("/")[1].lower().startswith(wanted)]
        if not audio:
            log(f"  no train_audio files matching {species!r} in {slug}")
            return report
        log(f"  {slug}: {len(audio)} matching files under train_audio; taking {limit}")
        with tempfile.TemporaryDirectory() as tmp:
            staging = Path(tmp)
            for name in audio[: max(0, limit)]:
                folder = name.split("/")[1]
                rid = f"{slug}-{Path(name).stem}"
                info = {
                    "speciesId": folder.lower(),
                    "recordist": "",
                    "licence": f"BirdCLEF competition terms (https://www.kaggle.com/c/{slug})",
                    "url": f"https://www.kaggle.com/c/{slug}/data",
                    "type": "birdclef train_audio, eBird-code folder",
                }
                dl = subprocess.run(
                    ["kaggle", "competitions", "download", "-c", slug,
                     "-f", name, "-p", str(staging), "--quiet"],
                    capture_output=True, text=True, timeout=600,
                )
                staged = staging / Path(name).name
                if dl.returncode != 0 or not staged.exists():
                    report.failed += 1
                    log(f"  skip {name}: {dl.stderr.strip()[:160]}")
                    continue
                _ingest_staged(store, staged, folder.lower(), rid, info,
                               max_seconds, report)
                staged.unlink(missing_ok=True)
        return report


# --- hugging face -----------------------------------------------------------------


class HuggingFaceSource(Source):
    """BirdSet (`DBD-research-group/BirdSet`), via `huggingface_hub`.

    Verified against the hub API on 2026-07-29: the dataset is **not gated** (no
    `HF_TOKEN` needed; a token is still used when present), and its audio is NOT in
    parquet shards — it is tar.gz shards under the `data` branch: XCL at ~5.4 GB
    apiece, XCM at ~525 MB. The XCL metadata parquet alone is 100 MB. Inside a shard,
    member paths carry the species: `data/xeno-canto/<region>/<species_id>/XCnnn.ogg`.

    **Per-species partial download is not practical.** tar.gz has no directory, so
    finding one species means streaming the archive until its members appear, and the
    mapping of member to eBird code lives in a parquet the pipeline has no reader for
    (pandas/pyarrow are not dependencies). The honest subset implemented here: stream
    the first XCM shard from byte 0, keep members whose path matches `--species` (or
    the first members at all), stop at `--limit`. What that costs in transfer is said
    in the log rather than hidden.
    """

    name = "huggingface"
    summary = "BirdSet XCM/XCL (xeno-canto repackaged); streaming, not per-species"
    REPO = "DBD-research-group/BirdSet"

    def available(self) -> tuple[bool, str]:
        try:
            import huggingface_hub  # noqa: F401
        except ImportError:
            return False, ("the `huggingface_hub` package is not installed "
                           "(uv sync --extra sources)")
        return True, "no token needed (BirdSet is not gated); HF_TOKEN honoured if set"

    def fetch(self, store, species=None, limit=5,
              max_seconds=harvest.DEFAULT_MAX_SECONDS, item=None) -> HarvestReport:
        from huggingface_hub import HfApi  # lazy: the extra is optional

        config = (item or "XCM").upper()
        token = os.environ.get("HF_TOKEN") or None
        api = HfApi(token=token)
        shard = next(
            (e for e in api.list_repo_files(self.REPO, repo_type="dataset", revision="data")
             if e.startswith(f"{config}/{config}_shard_")),
            None,
        )
        report = HarvestReport()
        if shard is None:
            log(f"  no {config} shards in {self.REPO}@data")
            return report
        url = f"https://huggingface.co/datasets/{self.REPO}/resolve/data/{shard}"
        headers = {"User-Agent": USER_AGENT}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        wanted = species_id_for(species) if species else ""
        log(f"  streaming {shard} (shards are ~0.5-5.4 GB tar.gz; stopping after "
            f"{limit} member(s)" + (f" matching {wanted!r}" if wanted else "") + ")")
        req = urllib.request.Request(url, headers=headers)
        taken = 0
        transferred = 0
        with tempfile.TemporaryDirectory() as tmp:
            staging = Path(tmp)
            with urllib.request.urlopen(req, timeout=DOWNLOAD_TIMEOUT) as res:
                stream = tarfile.open(fileobj=res, mode="r|gz")
                for member in stream:
                    if taken >= limit:
                        break
                    if not member.isfile() or Path(member.name).suffix.lower() not in AUDIO_SUFFIXES:
                        continue
                    parts = Path(member.name).parts
                    sid = parts[-2].lower() if len(parts) >= 2 else "unlabelled"
                    if wanted and sid != wanted:
                        continue
                    rid = Path(member.name).stem
                    if not rid.startswith("XC"):
                        rid = f"birdset-{rid}"
                    info = {
                        "speciesId": sid,
                        "recordist": "",
                        "licence": "mixed xeno-canto licences via BirdSet "
                                   "(https://huggingface.co/datasets/DBD-research-group/BirdSet)",
                        "url": f"https://huggingface.co/datasets/{self.REPO}",
                        "type": f"birdset {config} shard member",
                    }
                    staged = staging / Path(member.name).name
                    src = stream.extractfile(member)
                    with staged.open("wb") as fh:
                        shutil.copyfileobj(src, fh, length=1 << 16)
                    transferred += member.size
                    if _ingest_staged(store, staged, sid, rid, info, max_seconds, report):
                        taken += 1
                    staged.unlink(missing_ok=True)
        log(f"  transferred ~{transferred / 1e6:.0f} MB of member data for {taken} recording(s)")
        return report


# --- inat-sounds ------------------------------------------------------------------


class InatSoundsSource(Source):
    """iNatSounds 2024 (visipedia/inat_sounds), via the AWS Open Data S3 bucket — keyless.

    Verified against the live bucket on 2026-07-30: 230k WAVs (22.05 kHz, one species
    per file) as train/val/test tar.gz archives (81/25/27 GB) plus COCO-style
    annotation JSONs with per-file CC licence, rights holder and location
    (https://github.com/visipedia/inat_sounds/tree/main/2024). Terms: non-commercial
    research/education, recordings are never redistributed — which is exactly what the
    decode → describe → delete loop guarantees anyway.

    Shape of the access: a tar.gz has no directory, so a fetch is one sequential stream
    — the 14 MB annotation JSON first (it maps every member path to species, licence
    and rights holder), then the archive, keeping wanted members as they pass. A
    `--limit` near the archive's start costs little; a species whose members sit at
    the end costs the whole 81 GB stream, and the log says what was transferred so the
    cost is never hidden. Only the train split is fetched: val/test are the dataset's
    benchmark splits, worth more as future *evaluation* ground truth than as harvest.

    Two filters, both stated rather than assumed. **Aves only** — the archive also
    holds insects, amphibians, mammals and reptiles, and a bird project's store is not
    where they belong (a "not-a-bird" control stratum would file them as one, like
    warblr). **No NoDerivatives licences** — ids 2 and 5 (CC-BY-NC-ND, CC-BY-ND):
    decoding a recording into descriptors is arguably a derivative, so the 531 ND
    files of 111 029 Aves are skipped; every ingested recording's exact licence lands
    in the store's CREDITS.md via `note_recording`.
    """

    name = "inat-sounds"
    summary = "iNatSounds 2024 (AWS Open Data): 111k Aves recordings, 3 846 species, keyless"

    BASE = "https://ml-inat-competition-datasets.s3.amazonaws.com/sounds/2024"
    #: Licence ids the ingest accepts (see class docstring): BY, BY-NC, BY-NC-SA, CC0,
    #: BY-SA — everything except the two NoDerivatives variants.
    LICENCES_OK = {0, 1, 3, 4, 6}

    def available(self) -> tuple[bool, str]:
        return True, "no key needed (AWS Open Data); ~131 GB of archives, streamed"

    def _wanted(self, staging: Path, species: str | None) -> dict[str, dict[str, Any]]:
        """Member path → ingest info, for every Aves recording with an acceptable licence."""
        archive = _download(f"{self.BASE}/train.json.tar.gz", staging / "train.json.tar.gz")
        with tarfile.open(archive) as tar:
            member = tar.extractfile("train.json")
            meta = json.loads(member.read().decode("utf-8"))
        categories = {c["id"]: c for c in meta["categories"]}
        licences = {lic["id"]: lic for lic in meta["licenses"]}
        category_of = {a["audio_id"]: a["category_id"] for a in meta["annotations"]}
        wanted_species = species_id_for(species) if species else ""
        out: dict[str, dict[str, Any]] = {}
        for audio in meta["audio"]:
            cat = categories.get(category_of.get(audio["id"]))
            if not cat or cat["supercategory"] != "Aves":
                continue
            lic = licences[audio["license"]]
            if audio["license"] not in self.LICENCES_OK:
                continue
            sid = species_id_for(cat["name"]) or "unlabelled"
            if wanted_species and sid != wanted_species:
                continue
            out[audio["file_name"]] = {
                "speciesId": sid,
                "scientific": cat["name"],
                "english": cat.get("common_name", ""),
                "recordist": audio.get("rights_holder", ""),
                "licence": f"{lic['name']} ({lic['url']})",
                "country": "",
                "type": "inatsounds train",
                "url": "https://github.com/visipedia/inat_sounds/tree/main/2024",
                "_audio_id": audio["id"],
            }
        return out

    def fetch(self, store, species=None, limit=5,
              max_seconds=harvest.DEFAULT_MAX_SECONDS, item=None,
              per_species: int | None = None,
              keep_audio: Path | None = None) -> HarvestReport:
        report = HarvestReport()
        if keep_audio is not None:
            keep_audio.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as tmp:
            staging = Path(tmp)
            wanted = self._wanted(staging, species)
            if not wanted:
                log("  no acceptable Aves recordings"
                    + (f" for {species!r}" if species else "")
                    + " in iNatSounds train")
                return report
            # Members stream in taxonomic order (the tar is laid out by category
            # directory), so a bare `--limit 5000` would be "the first ~50 species
            # alphabetically", not a sample. A per-species cap turns the same stream
            # into a balanced take: every species passes its first `per_species`
            # members, and the archive order stops mattering to what is kept.
            budget: dict[str, int] = {}
            if per_species is not None:
                for info in wanted.values():
                    budget[info["speciesId"]] = int(per_species)
            log(f"  iNatSounds train: {len(wanted)} acceptable Aves recordings"
                + (f" for {species!r}" if species else "")
                + (f", at most {per_species} per species" if per_species is not None else "")
                + f"; streaming the 81 GB archive until {limit} ingested"
                + (f"; audio cached to {keep_audio}" if keep_audio else ""))
            req = urllib.request.Request(
                f"{self.BASE}/train.tar.gz", headers={"User-Agent": USER_AGENT})
            taken = 0
            transferred = 0
            with urllib.request.urlopen(req, timeout=DOWNLOAD_TIMEOUT) as res:
                stream = tarfile.open(fileobj=res, mode="r|gz")
                for member in stream:
                    if taken >= limit:
                        break
                    if not member.isfile():
                        continue
                    info = wanted.get(member.name)
                    if info is None or not budget.get(info["speciesId"], True):
                        continue
                    audio_id = info["_audio_id"]
                    staged = staging / Path(member.name).name
                    src = stream.extractfile(member)
                    with staged.open("wb") as fh:
                        shutil.copyfileobj(src, fh, length=1 << 16)
                    transferred += member.size
                    info = {k: v for k, v in info.items() if not k.startswith("_")}
                    ok = _ingest_staged(store, staged, info["speciesId"],
                                        f"INAT{audio_id}", info, max_seconds, report)
                    if ok:
                        taken += 1
                        if per_species is not None:
                            budget[info["speciesId"]] -= 1
                    if keep_audio is not None and (ok or store.has(f"INAT{audio_id}")):
                        # The owner's explicit exception to the delete loop (AGENTS.md):
                        # cached audio stays local, feeds harvest_directory on re-runs,
                        # never ships, and is deleted when the training phase ends.
                        # shutil.move, not Path.replace: staging is tmpfs, the cache is
                        # not, and os.replace cannot cross filesystems.
                        shutil.move(str(staged),
                                    str(keep_audio / f"INAT{audio_id}{staged.suffix}"))
                    staged.unlink(missing_ok=True)
        log(f"  transferred ~{transferred / 1e6:.0f} MB of member data for "
            f"{taken} recording(s)")
        return report


# --- gbif sound archives ------------------------------------------------------------


class GbifSource(Source):
    """GBIF-hosted sound archives, via the keyless occurrence-search API.

    Verified against the live API on 2026-07-30: `occurrence/search` with
    `dataset_key` + `media_type=Sound` needs no account (unlike GBIF's DwC-A download,
    which does), paginates 300 records a page, and each record carries the media URL,
    its per-file licence, the recordist and the country.

    **But measured the same day: both wired archives' media hosts are dead.** GBIF
    indexes metadata, not audio — and the institutions' servers no longer answer:
    tierstimmenarchiv.de's relaunch redirects every old mp3 URL (and even its own
    details page's `download_short.mp3` link) to the museum homepage, and Borror's
    `osuc.osu.edu` no longer resolves. The search API therefore returns 65k records
    whose audio cannot be fetched from either archive today; the Tierstimmenarchiv
    answer count is 16 385, Borror's 48 465. The GBIF download API (credentials in
    `.env`) does not route around this — a DwC-A carries the same dead identifiers,
    GBIF never proxies the bytes. The adapter stays because it is the right shape for
    any GBIF dataset whose host is alive, and these two may recover; the consecutive-
    failure bail-out below is what a dead host costs a fetch: twenty tries, a logged
    reason, exit.
    """

    name = "gbif"
    summary = ("GBIF sound archives — measured 2026-07-30: search keyless, but "
               "Tierstimmenarchiv + Borror media hosts are dead")

    #: Named dataset keys for `--item`; any other GBIF dataset key works as-is.
    DATASETS = {
        "tierstimmenarchiv": "b7ec1bf8-819b-11e2-bad2-00145eb45e9a",
        "borror": "f11db245-3f9f-4fc6-a0cc-12b4124d081b",
    }

    def available(self) -> tuple[bool, str]:
        return True, "no key needed (occurrence-search API, unlike the DwC-A download)"

    def fetch(self, store, species=None, limit=5,
              max_seconds=harvest.DEFAULT_MAX_SECONDS, item=None) -> HarvestReport:
        dataset = self.DATASETS.get(item or "tierstimmenarchiv", item)
        report = HarvestReport()
        params = f"dataset_key={dataset}&media_type=Sound&limit=300"
        if species:
            params += f"&scientific_name={urllib.parse.quote(species)}"
        with tempfile.TemporaryDirectory() as tmp:
            staging = Path(tmp)
            taken = 0
            consecutive_failures = 0
            offset = 0
            while taken < limit:
                page = _get_json(
                    f"https://api.gbif.org/v1/occurrence/search?{params}&offset={offset}")
                results = page.get("results", [])
                if not results:
                    break
                for rec in results:
                    if taken >= limit:
                        break
                    media = [m for m in rec.get("media", [])
                             if m.get("type") == "Sound" and m.get("identifier")]
                    if not media:
                        continue
                    m = media[0]
                    sid = species_id_for(rec.get("scientificName", "")) or "unlabelled"
                    rid = f"GBIF-{rec.get('key')}"
                    info = {
                        "speciesId": sid,
                        "scientific": rec.get("scientificName", ""),
                        "english": rec.get("vernacularName", "") or "",
                        "recordist": rec.get("recordedBy", ""),
                        "licence": m.get("license") or rec.get("license", ""),
                        "country": rec.get("country", ""),
                        "type": f"gbif {item or 'tierstimmenarchiv'} excerpt",
                        "url": m.get("references") or m["identifier"],
                    }
                    try:
                        staged = _download(m["identifier"], staging / f"{rid}.mp3")
                    except Exception as exc:
                        report.failed += 1
                        consecutive_failures += 1
                        log(f"  skip {rid}: {exc}")
                        continue
                    consecutive_failures = 0
                    if _ingest_staged(store, staged, sid, rid, info, max_seconds, report):
                        taken += 1
                    staged.unlink(missing_ok=True)
                # A dead media host fails every download in turn (measured: both wired
                # archives, 2026-07-30). Without this bail the fetch grinds tens of
                # thousands of 404s against a server that has nothing to give.
                if consecutive_failures >= 20:
                    log(f"  aborting: {consecutive_failures} consecutive downloads "
                        "failed — the archive's media host is not answering (see the "
                        "GbifSource docstring)")
                    break
                offset += len(results)
                if page.get("endOfRecords"):
                    break
        return report


# --- xeno-canto (listing only) ------------------------------------------------------


class XenoCantoListing(Source):
    """Not an adapter — the availability row that completes the picture.

    xeno-canto already has its own command (`birdy-pipeline harvest`); it appears in
    `sources list` so the table answers "what can this machine fetch from, right now"
    in one place.
    """

    name = "xeno-canto"
    summary = "the main harvest path: birdy-pipeline harvest"

    def available(self) -> tuple[bool, str]:
        if os.environ.get("XC_API_KEY"):
            return True, ""
        return False, "XC_API_KEY is not set (https://xeno-canto.org/account)"

    def fetch(self, store, species=None, limit=5,
              max_seconds=harvest.DEFAULT_MAX_SECONDS, item=None) -> HarvestReport:
        log("xeno-canto is harvested by its own command: "
            "uv run birdy-pipeline harvest [--species ...]")
        return HarvestReport()


SOURCES: dict[str, Source] = {
    s.name: s
    for s in (ZenodoSource(), ArchiveSource(), KaggleSource(),
              HuggingFaceSource(), InatSoundsSource(), GbifSource(),
              XenoCantoListing())
}


def availability_table() -> list[tuple[str, bool, str, str]]:
    """(name, available, reason-if-not, what-it-unlocks) for `sources list`."""
    table = []
    for name, src in SOURCES.items():
        ok, reason = src.available()
        table.append((name, ok, reason, src.summary))
    return table

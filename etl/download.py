"""Download DOL/USCIS source files listed in etl/manifest.json."""

from __future__ import annotations

import argparse
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

MANIFEST_PATH = Path(__file__).parent / "manifest.json"
USER_AGENT = "h1b-service-etl/0.1 (+https://github.com/ixsx2/h1b-service)"


def load_manifest(path: Path | None = None) -> dict:
    p = path or MANIFEST_PATH
    return json.loads(p.read_text(encoding="utf-8"))


def _download(url: str, dest: Path, timeout: int = 300) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        dest.write_bytes(resp.read())


def _scrape_dol_lca_url(fiscal_year: int, quarter: str) -> str | None:
    """Best-effort scrape of the DOL performance page for an LCA xlsx link."""
    page_url = "https://www.dol.gov/agencies/eta/foreign-labor/performance"
    req = urllib.request.Request(page_url, headers={"User-Agent": USER_AGENT})
    try:
        html = urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "replace")
    except urllib.error.URLError:
        return None
    pattern = rf'href="([^"]*LCA_Disclosure_Data_FY{fiscal_year}_{quarter}\.xlsx)"'
    match = re.search(pattern, html, re.IGNORECASE)
    if not match:
        return None
    href = match.group(1)
    if href.startswith("http"):
        return href
    return urllib.parse.urljoin(page_url, href)


def download_manifest(
    output_dir: Path,
    manifest_path: Path | None = None,
    scrape_fallback: bool = True,
) -> list[Path]:
    manifest = load_manifest(manifest_path)
    downloaded: list[Path] = []
    errors: list[str] = []

    for entry in manifest.get("dol", []):
        filename = entry["filename"]
        dest = output_dir / filename
        url = entry.get("url") or ""
        if not url and scrape_fallback:
            url = _scrape_dol_lca_url(entry["fiscal_year"], entry["quarter"]) or ""
        if not url:
            errors.append(f"No URL for DOL {filename}")
            continue
        try:
            _download(url, dest)
            downloaded.append(dest)
            print(f"Downloaded {dest.name}")
        except urllib.error.URLError as exc:
            errors.append(f"DOL {filename}: {exc}")

    for entry in manifest.get("uscis", []):
        url = entry.get("url") or ""
        if not url:
            errors.append(f"No URL for USCIS {entry.get('filename', 'file')}")
            continue
        filename = entry.get("filename") or Path(urllib.parse.urlparse(url).path).name
        dest = output_dir / filename
        try:
            _download(url, dest)
            downloaded.append(dest)
            print(f"Downloaded {dest.name}")
        except urllib.error.URLError as exc:
            errors.append(f"USCIS {filename}: {exc}")

    if errors:
        msg = "\n".join(errors)
        raise RuntimeError(f"Download failures:\n{msg}")
    return downloaded


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Download DOL/USCIS files from manifest.json")
    parser.add_argument("--output", type=Path, default=Path("data/sources"))
    parser.add_argument("--manifest", type=Path, default=MANIFEST_PATH)
    parser.add_argument("--no-scrape", action="store_true")
    args = parser.parse_args(argv)

    paths = download_manifest(
        args.output,
        manifest_path=args.manifest,
        scrape_fallback=not args.no_scrape,
    )
    print(f"Downloaded {len(paths)} file(s) to {args.output}")


if __name__ == "__main__":
    main()

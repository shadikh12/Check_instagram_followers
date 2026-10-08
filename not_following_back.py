#!/usr/bin/env python3
"""
Instagram "who doesn't follow me back" checker.

Takes the HTML files from Instagram's "Download your information" export
(followers_1.html, following.html, ...) and lists the accounts you follow
that don't follow you back.

Usage:
    python not_following_back.py                      (searches this folder, subfolders and zips)
    python not_following_back.py "C:\\path\\to\\instagram-export.zip"
    python not_following_back.py --followers followers_1.html --following following.html
    python not_following_back.py --followers followers_1.html followers_2.html --following following.html -o result.txt
    python not_following_back.py --followers followers_1.html --following following.html --fans

How to get the files:
    Instagram > Settings > Accounts Center > Your information and permissions >
    Download your information > choose "Followers and following", format = HTML,
    Date range = "All time" (the default "Last year" leaves out older followers).
    Put the downloaded zip (or the unzipped folder) next to this script and run it -
    the files are found automatically, no need to unzip.

Only uses the Python standard library.
"""

import argparse
import re
import sys
import zipfile
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

# Instagram usernames: letters, digits, periods, underscores, max 30 chars.
USERNAME_RE = re.compile(r"^[A-Za-z0-9._]{1,30}$")

# Path segments that are Instagram pages, not usernames.
RESERVED_PATHS = {
    "accounts", "explore", "p", "reel", "reels", "stories", "direct",
    "about", "developer", "legal", "privacy", "help", "web", "",
}


class _ProfileLinkParser(HTMLParser):
    """Collects (href, link text) for every <a> tag in the document."""

    def __init__(self):
        super().__init__()
        self.links = []
        self._href = None
        self._text = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self._href = dict(attrs).get("href") or ""
            self._text = []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._href is not None:
            self.links.append((self._href, "".join(self._text).strip()))
            self._href = None


def _username_from_link(href, text):
    """Return the username for an Instagram profile link, or None."""
    parsed = urlparse(href)
    if "instagram.com" not in parsed.netloc.lower():
        return None

    parts = [p for p in parsed.path.split("/") if p]
    # Newer exports use https://www.instagram.com/_u/<username>
    if parts and parts[0] == "_u":
        parts = parts[1:]

    if parts and parts[0].lower() not in RESERVED_PATHS and USERNAME_RE.match(parts[0]):
        return parts[0].lower()

    # Fall back to the visible link text
    if USERNAME_RE.match(text):
        return text.lower()
    return None


def _read_source(source):
    """Read an HTML file. `source` is a path, or (zip_path, member) for a file inside a zip."""
    if isinstance(source, tuple):
        zip_path, member = source
        with zipfile.ZipFile(zip_path) as zf:
            return zf.read(member).decode("utf-8", errors="replace")
    file = Path(source)
    if not file.is_file():
        sys.exit(f"Error: file not found: {file}")
    return file.read_text(encoding="utf-8", errors="replace")


def _describe(source):
    return f"{source[0]} -> {source[1]}" if isinstance(source, tuple) else str(source)


_DATE_RANGE_RE = re.compile(
    r'requested from <time datetime="(\d{4}-\d{2}-\d{2})[^"]*">.*?'
    r'to <time datetime="(\d{4}-\d{2}-\d{2})', re.S)


def _warn_if_date_limited(html, source):
    """Instagram's export defaults to "Last year", which drops older followers and
    makes them look like they don't follow you back."""
    m = _DATE_RANGE_RE.search(html)
    if not m:
        return
    start, end = (date.fromisoformat(d) for d in m.groups())
    if (end - start).days <= 400:
        print(
            f"WARNING: {_describe(source)} only covers {start} to {end}.\n"
            "  Anyone who followed (or was followed) before that is missing, so results\n"
            "  will be wrong. Re-download the export with Date range = 'All time'.\n",
            file=sys.stderr,
        )


def load_usernames(sources):
    """Read one or more Instagram export HTML files and return a set of usernames."""
    usernames = set()
    for source in sources:
        html = _read_source(source)
        _warn_if_date_limited(html, source)
        parser = _ProfileLinkParser()
        parser.feed(html)

        found = {u for href, text in parser.links if (u := _username_from_link(href, text))}
        if not found:
            print(f"Warning: no usernames found in {_describe(source)}", file=sys.stderr)
        usernames |= found
    return usernames


def _is_followers(name):
    return re.fullmatch(r"followers(_\d+)?\.html", name) is not None


def find_export_files(location):
    """Find Instagram's followers/following HTML files in a folder (and its subfolders,
    including any .zip files there) or directly in a .zip file."""
    root = Path(location)
    zips = [root] if root.suffix.lower() == ".zip" else sorted(root.rglob("*.zip"))
    followers, following = [], []

    if root.is_dir():
        for p in sorted(root.rglob("*.html")):
            if _is_followers(p.name):
                followers.append(str(p))
            elif p.name == "following.html":
                following.append(str(p))

    # Only look inside zips if the unzipped files weren't found
    if not (followers and following):
        for zip_path in zips:
            if not zipfile.is_zipfile(zip_path):
                continue
            with zipfile.ZipFile(zip_path) as zf:
                for member in sorted(zf.namelist()):
                    name = member.rsplit("/", 1)[-1]
                    if _is_followers(name):
                        followers.append((str(zip_path), member))
                    elif name == "following.html":
                        following.append((str(zip_path), member))
    return followers, following


def main():
    ap = argparse.ArgumentParser(
        description="Find Instagram accounts you follow that don't follow you back."
    )
    ap.add_argument("folder", nargs="?", default=".",
                    help="Instagram export folder or .zip file (subfolders and zips are "
                         "searched); defaults to the current folder")
    ap.add_argument("--followers", nargs="+", metavar="HTML",
                    help="followers HTML file(s), e.g. followers_1.html followers_2.html")
    ap.add_argument("--following", nargs="+", metavar="HTML",
                    help="following HTML file(s), e.g. following.html")
    ap.add_argument("--fans", action="store_true",
                    help="also list people who follow you that you don't follow back")
    ap.add_argument("-o", "--output", metavar="FILE",
                    help="also save the results to a text file")
    args = ap.parse_args()

    if not args.followers or not args.following:
        found_followers, found_following = find_export_files(args.folder)
        args.followers = args.followers or found_followers
        args.following = args.following or found_following
        if not args.followers or not args.following:
            sys.exit(
                f"Error: couldn't find followers_*.html and following.html in "
                f"'{Path(args.folder).resolve()}'.\n"
                "Put your Instagram export (zip or folder) next to this script, or pass "
                "its path, e.g.:  python not_following_back.py \"C:\\path\\to\\export\""
            )
        print("Using files:")
        for f in [*args.followers, *args.following]:
            print(f"  {_describe(f)}")
        print()

    followers = load_usernames(args.followers)
    following = load_usernames(args.following)

    not_following_back = sorted(following - followers)
    fans = sorted(followers - following)

    lines = [
        f"Followers: {len(followers)}",
        f"Following: {len(following)}",
        "",
        f"Not following you back ({len(not_following_back)}):",
        *[f"  {u}  -  https://www.instagram.com/{u}/" for u in not_following_back],
    ]
    if args.fans:
        lines += [
            "",
            f"You don't follow back ({len(fans)}):",
            *[f"  {u}  -  https://www.instagram.com/{u}/" for u in fans],
        ]

    report = "\n".join(lines)
    print(report)

    if args.output:
        Path(args.output).write_text(report + "\n", encoding="utf-8")
        print(f"\nSaved to {args.output}")


if __name__ == "__main__":
    main()

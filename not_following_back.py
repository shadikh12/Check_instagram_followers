#!/usr/bin/env python3
"""
Instagram "who doesn't follow me back" checker.

Takes the HTML files from Instagram's "Download your information" export
(followers_1.html, following.html, ...) and lists the accounts you follow
that don't follow you back.

Usage:
    python not_following_back.py --followers followers_1.html --following following.html
    python not_following_back.py --followers followers_1.html followers_2.html --following following.html -o result.txt
    python not_following_back.py --followers followers_1.html --following following.html --fans

How to get the files:
    Instagram > Settings > Accounts Center > Your information and permissions >
    Download your information > choose "Followers and following", format = HTML.
    The files are in the zip under connections/followers_and_following/.

Only uses the Python standard library.
"""

import argparse
import re
import sys
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


def load_usernames(paths):
    """Read one or more Instagram export HTML files and return a set of usernames."""
    usernames = set()
    for path in paths:
        file = Path(path)
        if not file.is_file():
            sys.exit(f"Error: file not found: {file}")

        parser = _ProfileLinkParser()
        parser.feed(file.read_text(encoding="utf-8", errors="replace"))

        found = {u for href, text in parser.links if (u := _username_from_link(href, text))}
        if not found:
            print(f"Warning: no usernames found in {file}", file=sys.stderr)
        usernames |= found
    return usernames


def main():
    ap = argparse.ArgumentParser(
        description="Find Instagram accounts you follow that don't follow you back."
    )
    ap.add_argument("--followers", nargs="+", required=True, metavar="HTML",
                    help="followers HTML file(s), e.g. followers_1.html followers_2.html")
    ap.add_argument("--following", nargs="+", required=True, metavar="HTML",
                    help="following HTML file(s), e.g. following.html")
    ap.add_argument("--fans", action="store_true",
                    help="also list people who follow you that you don't follow back")
    ap.add_argument("-o", "--output", metavar="FILE",
                    help="also save the results to a text file")
    args = ap.parse_args()

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

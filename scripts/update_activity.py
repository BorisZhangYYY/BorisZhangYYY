#!/usr/bin/env python3
"""Refresh open Issues, PRs and merged upstream contributions in the profile README.

Requires only Python's standard library and GITHUB_TOKEN from GitHub Actions.
"""

import html
import json
import os
from pathlib import Path
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

USERNAME = "BorisZhangYYY"
README = Path(__file__).resolve().parents[1] / "README.md"
API_URL = "https://api.github.com/search/issues"
PER_PAGE = 100
MAX_MERGED_PRS = 15

# Keep these hand-written descriptions for notable merged upstream contributions.
CURATED_MERGED = {
    "https://github.com/Achuan-2/siyuan-plugin-copilot/pull/148": (
        "Added SiYuan `forwardProxy` support to improve access across AI providers."
    ),
    "https://github.com/siyuan-note/bazaar/pull/2344": (
        "Published [ZhiLiu (知流)](https://github.com/BorisZhangYYY/noosphere-siyuan) "
        "to the SiYuan community marketplace."
    ),
}



def fetch_items(kind: str, state: str) -> list[dict]:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_TOKEN is required for GitHub API requests")

    result = []
    page = 1
    while True:
        params = urlencode(
            {
                "q": f"author:{USERNAME} is:{kind} {state} archived:false"
                + (f" -user:{USERNAME}" if state == "is:merged" else ""),
                "sort": "updated",
                "order": "desc",
                "per_page": PER_PAGE,
                "page": page,
            }
        )
        request = Request(
            f"{API_URL}?{params}",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "BorisZhangYYY-profile-updater",
            },
        )
        try:
            with urlopen(request, timeout=30) as response:
                data = json.load(response)
        except HTTPError as exc:
            raise RuntimeError(f"GitHub API returned HTTP {exc.code} for {kind}") from exc
        except URLError as exc:
            raise RuntimeError(f"GitHub API request failed for {kind}: {exc.reason}") from exc

        total = int(data.get("total_count", 0))
        if total > 1000:
            raise RuntimeError(f"GitHub Search API can only return 1000 {kind} items; refusing an incomplete update")
        items = data["items"]
        result.extend(items)
        if len(items) < PER_PAGE or len(result) >= total:
            break
        page += 1

    return sorted(result, key=lambda item: item.get("updated_at", ""), reverse=True)


def escaped_title(raw: str) -> str:
    """Ensure issue titles don't change Markdown formatting or inject HTML."""
    flat = re.sub(r"\s+", " ", raw).strip()
    safe = html.escape(flat, quote=False)
    return re.sub(r"([\\\[\]`*_])", r"\\\1", safe)


def render(items: list[dict], kind: str) -> str:
    if not items:
        return f"_No open {kind} at the moment._"

    lines = []
    for item in items:
        repository_url = item["repository_url"]
        repository = repository_url.split("/repos/", 1)[1]
        url = item["html_url"]
        number = int(item["number"])
        title = escaped_title(item["title"])
        lines.append(f"- **[{repository} #{number}]({url})** — {title}")
    return "\n".join(lines)


def render_merged(items: list[dict]) -> str:
    if not items:
        return "_No merged upstream PRs yet._"

    lines = []
    for item in items[:MAX_MERGED_PRS]:
        repository = item["repository_url"].split("/repos/", 1)[1]
        url = item["html_url"]
        number = int(item["number"])
        description = CURATED_MERGED.get(url, escaped_title(item["title"]))
        lines.append(f"- **[{repository} #{number}]({url})** — {description}")

    if len(items) > MAX_MERGED_PRS:
        lines.append(
            f"\n[Browse all merged upstream PRs]"
            f"(https://github.com/pulls?q=is%3Apr+is%3Amerged+author%3A{USERNAME}+-user%3A{USERNAME})"
        )
    return "\n".join(lines)


def replace_section(text: str, name: str, body: str) -> str:
    start = f"<!-- ACTIVITY:{name}:START -->"
    end = f"<!-- ACTIVITY:{name}:END -->"
    if text.count(start) != 1 or text.count(end) != 1:
        raise RuntimeError(f"Expected exactly one pair of {name} markers in README.md")
    before, remainder = text.split(start, 1)
    _, after = remainder.split(end, 1)
    return f"{before}{start}\n{body}\n{end}{after}"


def main() -> None:
    original = README.read_text(encoding="utf-8")
    # Fetch all datasets before writing; fail closed on API errors.
    issues = fetch_items("issue", "is:open")
    prs = fetch_items("pr", "is:open")
    merged_upstream_prs = fetch_items("pr", "is:merged")

    updated = replace_section(original, "ISSUES", render(issues, "issues"))
    updated = replace_section(updated, "PRS", render(prs, "PRs"))
    updated = replace_section(updated, "MERGED", render_merged(merged_upstream_prs))
    if updated != original:
        README.write_text(updated, encoding="utf-8")
    print(
        f"Open Issues: {len(issues)} | Open PRs: {len(prs)} | "
        f"Merged upstream PRs: {len(merged_upstream_prs)} | "
        f"README changed: {updated != original}"
    )


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, KeyError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

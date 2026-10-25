#!/usr/bin/env python3
"""Replace the GitHub placeholder everywhere (manifest, card, docs, workflows).

Usage:  python scripts/set_github_user.py <github-user> [repo-name]
   or:  edit REPO, then  python scripts/set_github_user.py
It rewrites `your-github-user/tisseo-ha` (and `@your-github-user`) in tracked text files,
and records the new value in REPO. `--check` lists files that still contain the
placeholder and exits 1 if there are any (use it before publishing).
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
PLACEHOLDER = "your-github-user"
SKIP_DIRS = {".git", ".cache", "__pycache__", ".pytest_cache", "node_modules"}
EXTS = {".py", ".json", ".js", ".md", ".yaml", ".yml", ".txt", ""}


def read_repo():
    vals = {}
    for line in (ROOT / "REPO").read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            vals[k.strip()] = v.strip()
    return vals.get("github_user", PLACEHOLDER), vals.get("repo_name", "tisseo-ha")


def files():
    for p in ROOT.rglob("*"):
        if p.is_file() and not (SKIP_DIRS & set(p.relative_to(ROOT).parts)) and p.suffix in EXTS \
                and p.name not in ("set_github_user.py", "REPO", "LICENSE", "HACS_CHECKLIST.md"):
            yield p


def main(argv):
    if "--check" in argv:
        left = [p.relative_to(ROOT) for p in files()
                if PLACEHOLDER in p.read_text(encoding="utf-8", errors="ignore")]
        print(f"{len(left)} file(s) still contain {PLACEHOLDER!r}:")
        for c in left:
            print("  ", c)
        sys.exit(1 if left else 0)
    check = False
    args = [a for a in argv if not a.startswith("--")]
    cur_user, cur_repo = read_repo()
    user = args[0] if args else cur_user
    repo = args[1] if len(args) > 1 else cur_repo
    if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})", user):
        sys.exit(f"invalid GitHub user: {user!r}")
    if user == PLACEHOLDER and not check:
        sys.exit("give your GitHub user name (argument or REPO file)")
    changed = []
    for p in files():
        try:
            s = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        n = s.replace(f"{PLACEHOLDER}/tisseo-ha", f"{user}/{repo}").replace(f"@{PLACEHOLDER}", f"@{user}") \
             .replace(PLACEHOLDER, user)
        if n != s:
            changed.append(p.relative_to(ROOT))
            if not check:
                p.write_text(n, encoding="utf-8")
    if not check:
        (ROOT / "REPO").write_text((ROOT / "REPO").read_text().replace(f"github_user={cur_user}", f"github_user={user}")
                                   .replace(f"repo_name={cur_repo}", f"repo_name={repo}"))
    print(("would change" if check else "changed"), len(changed), "file(s):")
    for c in changed:
        print("  ", c)


if __name__ == "__main__":
    main(sys.argv[1:])

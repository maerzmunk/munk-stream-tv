#!/usr/bin/env python3
"""Munk Stream robot: bring the newest Nuvio release into this repository.

Usage: python munk/nuvio_update.py mobile|tv

Instead of a git merge (which would drag Nuvio's own CI workflow files into
this repo), it applies the diff between the Nuvio release we are based on
(munk/NUVIO_BASE) and the newest Nuvio release, with a 3-way merge per file.
Then it re-applies the Munk Stream name to all strings and bumps the version.

Writes to $GITHUB_OUTPUT:
  updated=true|false, nuvio_tag, version, conflicts
Exit code 2 means conflicts that a human (Claude) must fix.
"""
import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

KIND = sys.argv[1]
UPSTREAM = {"mobile": "NuvioMedia/NuvioMobile", "tv": "NuvioMedia/NuvioTV"}[KIND]
ROOT = Path(__file__).resolve().parent.parent
BASE_FILE = ROOT / "munk" / "NUVIO_BASE"
EXCLUDE = [".github", "README.md", "munk"]
if KIND == "mobile":
    EXCLUDE.append("iosApp/Configuration/Version.xcconfig")
IMAGE_EXT = {".png", ".webp", ".jpg", ".jpeg"}
STRINGS_RE = re.compile(r"/values[^/]*/strings?[^/]*\.xml$")
OUT = os.environ.get("GITHUB_OUTPUT")


def out(key, value):
    print(f"{key}={value}")
    if OUT:
        with open(OUT, "a", encoding="utf-8") as f:
            f.write(f"{key}={value}\n")


def git(*args, check=True):
    r = subprocess.run(["git", *args], cwd=ROOT, text=True, capture_output=True)
    if check and r.returncode != 0:
        sys.exit(f"git {' '.join(args)} failed:\n{r.stdout}\n{r.stderr}")
    return r


def semver(tag):
    m = re.match(r"v?(\d+)\.(\d+)\.(\d+)", tag or "")
    return tuple(int(x) for x in m.groups()) if m else None


def latest_upstream_tag():
    req = urllib.request.Request(
        f"https://api.github.com/repos/{UPSTREAM}/releases/latest",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "munk-stream-robot"},
    )
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)["tag_name"]


def rebrand_strings():
    """Same rule used for the first rebrand: visible 'Nuvio' -> 'Munk Stream'."""
    files = [p for p in ROOT.rglob("values*/*.xml") if re.search(r"^strings?[^/]*\.xml$", p.name)]
    files = [p for p in files if "/build/" not in p.as_posix()]
    changed = 0
    for p in files:
        s = p.read_text(encoding="utf-8")
        lines = s.splitlines(keepends=True)
        for i, line in enumerate(lines):
            if 'name="settings_licenses_attributions_nuvio_title"' in line:
                continue  # credit line stays "Nuvio"
            line = re.sub(r"\bNuvio ?TV\b", "Munk Stream", line)
            lines[i] = re.sub(r"\bNuvio(?![A-Za-z]|\.[a-z])", "Munk Stream", line)
        t = "".join(lines)
        if t != s:
            p.write_text(t, encoding="utf-8", newline="")
            changed += 1
    print(f"rebranded {changed} string files")


def bump_patch(v):
    a, b, c = semver(v)
    return f"{a}.{b}.{c + 1}"


def bump_versions(new_tag):
    if KIND == "mobile":
        cfg = ROOT / "iosApp/Configuration/Version.xcconfig"
        s = cfg.read_text(encoding="utf-8")
        ours_name = re.search(r"MARKETING_VERSION\s*=\s*(\S+)", s).group(1)
        ours_code = int(re.search(r"CURRENT_PROJECT_VERSION\s*=\s*(\d+)", s).group(1))
        theirs = git("show", f"{new_tag}:iosApp/Configuration/Version.xcconfig").stdout
        m = re.search(r"CURRENT_PROJECT_VERSION\s*=\s*(\d+)", theirs)
        theirs_code = int(m.group(1)) if m else 0
        version = bump_patch(ours_name)
        code = max(ours_code, theirs_code) + 1
        s = re.sub(r"(MARKETING_VERSION\s*=\s*)\S+", rf"\g<1>{version}", s)
        s = re.sub(r"(CURRENT_PROJECT_VERSION\s*=\s*)\d+", rf"\g<1>{code}", s)
        cfg.write_text(s, encoding="utf-8", newline="")
    else:
        vf = ROOT / "munk/VERSION"
        version = bump_patch(vf.read_text(encoding="utf-8").strip())
        vf.write_text(version + "\n", encoding="utf-8")
    return version


def main():
    base = BASE_FILE.read_text(encoding="utf-8").strip()
    new = os.environ.get("FORCE_NUVIO_TAG") or latest_upstream_tag()
    out("nuvio_tag", new)
    if new == base or (semver(new) and semver(base) and semver(new) <= semver(base)):
        print(f"Already on Nuvio {base}; newest is {new}. Nothing to do.")
        out("updated", "false")
        return 0

    url = f"https://github.com/{UPSTREAM}.git"
    git("fetch", "--no-tags", url, f"refs/tags/{base}:refs/tags/{base}", f"refs/tags/{new}:refs/tags/{new}")

    # String files: our only change there is the name, so take Nuvio's new copy
    # and rebrand it again below (avoids conflicts next to renamed lines).
    changed = git("diff", "--name-status", base, new).stdout.splitlines()
    for row in changed:
        status, *paths = row.split("\t")
        path = paths[-1]
        if not STRINGS_RE.search(path) or any(path.startswith(e) for e in EXCLUDE):
            continue
        if status.startswith("D"):
            git("rm", "-q", "--ignore-unmatch", "--", path)
        else:
            if status.startswith("R"):
                git("rm", "-q", "--ignore-unmatch", "--", paths[0])
            git("checkout", new, "--", path)

    pathspec = ["--", "."] + [f":(exclude){e}" for e in EXCLUDE] + [
        ":(exclude,glob)**/values*/strings*.xml",
        ":(exclude,glob)**/values*/string.xml",
    ]
    patch = git("diff", "--binary", base, new, *pathspec).stdout
    patch_file = ROOT.parent / "nuvio-update.patch"
    patch_file.write_text(patch, encoding="utf-8", newline="")

    if patch.strip():
        r = git("apply", "--3way", "--index", str(patch_file), check=False)
        print(r.stdout, r.stderr)
        conflicts = git("diff", "--name-only", "--diff-filter=U").stdout.split()
        for f in list(conflicts):
            if Path(f).suffix.lower() in IMAGE_EXT:  # keep our Munk logos
                git("checkout", "--ours", "--", f)
                git("add", "--", f)
                conflicts.remove(f)
        if conflicts:
            out("conflicts", " ".join(conflicts))
            out("updated", "false")
            print("CONFLICTS:", *conflicts, sep="\n  ")
            return 2
        if r.returncode != 0 and not git("diff", "--cached", "--name-only").stdout.strip():
            sys.exit("git apply failed without conflicts:\n" + r.stderr)

    rebrand_strings()
    version = bump_versions(new)
    BASE_FILE.write_text(new + "\n", encoding="utf-8")
    git("add", "-A")
    out("version", version)
    out("updated", "true")
    print(f"Prepared Munk Stream {version} from Nuvio {new}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

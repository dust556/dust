#!/usr/bin/env python3
"""
G3 Research EA - build manifest and source hashes.

Produces:
  manifests/build_manifest.json  - SHA-256 of every source, config and schema
                                   file, plus the aggregate source_hash,
                                   config_hash and schema_hash
  manifests/EA_hash.txt          - placeholder for the compiled .ex5 hash,
                                   which can only be produced by MetaEditor
  manifests/spec_hash.txt        - placeholder for the Master Specification
                                   v0.4 document hash (document not supplied)

Reproducibility rule: a G3 run is only citable when source_hash,
config_hash and the compiled EA_hash of the run are all recorded.
"""
import hashlib
import json
import os
import sys
from datetime import datetime, timezone

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
GROUPS = {
    "source": ("src", (".mq5", ".mqh")),
    "config": ("config", (".set",)),
    "schema": ("schema", (".md",)),
    "tests": ("tests", (".cpp", ".h", ".md")),
    "tools": ("tools", (".py",)),
}


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def collect(folder, exts):
    base = os.path.join(ROOT, folder)
    out = {}
    for dirpath, _dirs, names in os.walk(base):
        for name in sorted(names):
            if not name.endswith(exts):
                continue
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, ROOT).replace(os.sep, "/")
            out[rel] = sha256_file(full)
    return dict(sorted(out.items()))


def aggregate(files):
    """Order independent aggregate: sha256 over 'path:hash' lines, sorted."""
    h = hashlib.sha256()
    for path, digest in sorted(files.items()):
        h.update(("%s:%s\n" % (path, digest)).encode("utf-8"))
    return h.hexdigest()


def main():
    manifest = {
        "artifact": "G3 Research EA",
        "spec_authority": "Master Specification v0.4",
        "ea_version": "0.4.0-research",
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "groups": {},
        "aggregate": {},
        "ea_hash": "PENDING_METAEDITOR_COMPILE",
        "spec_hash": "PENDING_SPEC_DOCUMENT",
        "notes": [
            "ea_hash is the SHA-256 of the compiled .ex5 and can only be produced "
            "by a MetaEditor build; this repository has no MQL5 toolchain.",
            "spec_hash is the SHA-256 of the Master Specification v0.4 document, "
            "which was not supplied to the implementation environment.",
            "No Final Holdout data, path or artifact is referenced anywhere.",
        ],
    }
    for group, (folder, exts) in GROUPS.items():
        files = collect(folder, exts)
        manifest["groups"][group] = files
        manifest["aggregate"][group + "_hash"] = aggregate(files)

    everything = {}
    for group in ("source", "config", "schema"):
        everything.update(manifest["groups"][group])
    manifest["aggregate"]["release_hash"] = aggregate(everything)

    outdir = os.path.join(ROOT, "manifests")
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, "build_manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)
        fh.write("\n")

    with open(os.path.join(outdir, "EA_hash.txt"), "w", encoding="utf-8") as fh:
        fh.write("# SHA-256 of the compiled G3_ResearchEA.ex5\n")
        fh.write("# Cannot be produced here: MetaEditor / MQL5 is not available in\n")
        fh.write("# this environment. Fill this in from the machine that compiles the EA:\n")
        fh.write("#   sha256sum G3_ResearchEA.ex5\n")
        fh.write("EA_HASH=PENDING_METAEDITOR_COMPILE\n")
        fh.write("SOURCE_HASH=%s\n" % manifest["aggregate"]["source_hash"])

    with open(os.path.join(outdir, "spec_hash.txt"), "w", encoding="utf-8") as fh:
        fh.write("# SHA-256 of Master Specification v0.4 (authority document)\n")
        fh.write("# The document was not supplied to this environment, so the hash\n")
        fh.write("# cannot be computed here. See docs/change_requests.md CR-001.\n")
        fh.write("SPEC_HASH=PENDING_SPEC_DOCUMENT\n")

    with open(os.path.join(outdir, "config_hash.txt"), "w", encoding="utf-8") as fh:
        fh.write("CONFIG_HASH=%s\n" % manifest["aggregate"]["config_hash"])
        for path, digest in manifest["groups"]["config"].items():
            fh.write("%s  %s\n" % (digest, path))

    print("source_hash  : %s" % manifest["aggregate"]["source_hash"])
    print("config_hash  : %s" % manifest["aggregate"]["config_hash"])
    print("schema_hash  : %s" % manifest["aggregate"]["schema_hash"])
    print("release_hash : %s" % manifest["aggregate"]["release_hash"])
    print("wrote manifests/build_manifest.json, EA_hash.txt, spec_hash.txt, config_hash.txt")
    return 0


if __name__ == "__main__":
    sys.exit(main())

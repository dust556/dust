#!/usr/bin/env python3
"""
Bind the compiled G3_ResearchEA.ex5 to this source tree.

The MetaEditor build happens outside this environment, so the binary's
SHA-256 is recorded here rather than computed from a local compile. Give it
either the .ex5 file or the digest itself:

    python3 tools/record_ea_hash.py /path/to/G3_ResearchEA.ex5
    python3 tools/record_ea_hash.py 3f5c...64hex

It writes manifests/ea_hash.value, which tools/compute_hashes.py then folds
into the build manifest and manifests/EA_hash.txt. The value file sits
outside the hashed groups, so binding the binary later never disturbs
source_hash, config_hash, schema_hash or release_hash.

A G3 run is only citable when source_hash, config_hash and EA_hash are all
recorded together.
"""
import hashlib
import json
import os
import sys
from datetime import datetime, timezone

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
OUT = os.path.join(ROOT, "manifests", "ea_hash.value")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def source_hash():
    path = os.path.join(ROOT, "manifests", "build_manifest.json")
    if not os.path.exists(path):
        return "UNKNOWN"
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)["aggregate"]["source_hash"]


def main(argv):
    if len(argv) != 2:
        print(__doc__)
        return 2
    arg = argv[1]
    if os.path.exists(arg):
        if not arg.lower().endswith(".ex5"):
            print("refusing to record %s: expected a compiled .ex5" % arg)
            return 1
        digest = sha256_file(arg)
        origin = os.path.basename(arg)
        size = os.path.getsize(arg)
    else:
        digest = arg.strip().lower()
        origin = "digest supplied directly"
        size = None
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            print("not a SHA-256 digest and not an existing file: %r" % arg)
            return 1

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write("# Compiled Expert Advisor binding for this source tree.\n")
        fh.write("# Written by tools/record_ea_hash.py; re-run\n")
        fh.write("#   python3 tools/compute_hashes.py\n")
        fh.write("# afterwards to fold it into the build manifest.\n")
        fh.write("EA_HASH=%s\n" % digest)
        fh.write("EA_ORIGIN=%s\n" % origin)
        if size is not None:
            fh.write("EA_SIZE_BYTES=%d\n" % size)
        fh.write("BOUND_TO_SOURCE_HASH=%s\n" % source_hash())
        fh.write("RECORDED_UTC=%s\n"
                 % datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    print("EA_HASH=%s" % digest)
    print("bound to source_hash=%s" % source_hash())
    print("wrote %s" % OUT)
    print("now run: python3 tools/compute_hashes.py")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

#!/usr/bin/env python3
"""Block large generated files from entering Git commits or pushes.

GitHub rejects individual objects over 100 MB, but by then the large blob is
already in local history and every later push carries it. This guard fails
earlier: pre-commit checks the staged index, while pre-push checks every object
newly reachable from the pushed ref so a file added and deleted in a later
commit is still caught.
"""

import argparse
import subprocess
import sys
from pathlib import Path


MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_STAGED_TOTAL_BYTES = 50 * 1024 * 1024
MAX_PUSH_TOTAL_BYTES = 100 * 1024 * 1024
ZERO_SHA = "0" * 40

# Runtime caches and downloaded binaries are never source. Their names are
# rejected even when a small file happens to live inside one of them.
BLOCKED_SEGMENTS = frozenset(
    {
        ".venv",
        "ms-playwright",
        "node_modules",
        "browser_profile",
        "playwright-report",
        "test-results",
        "blob-report",
    }
)
BLOCKED_PREFIXES = ("desktop/resources/bin",)


class GuardError(RuntimeError):
    pass


def git(root, args, input_bytes=None):
    result = subprocess.run(
        ["git"] + args,
        cwd=str(root),
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", "replace").strip()
        raise GuardError("git %s failed: %s" % (" ".join(args), detail))
    return result.stdout


def repo_root():
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        raise GuardError("not running inside a Git work tree")
    return Path(result.stdout.decode("utf-8", "surrogateescape").strip())


def path_text(raw):
    return raw.decode("utf-8", "surrogateescape").replace("\\", "/")


def is_blocked_path(path):
    normalized = path.replace("\\", "/").lstrip("./")
    segments = normalized.split("/")
    if any(segment in BLOCKED_SEGMENTS for segment in segments):
        return True
    return any(
        normalized == prefix or normalized.startswith(prefix + "/")
        for prefix in BLOCKED_PREFIXES
    )


def format_size(size):
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return ("%.1f %s" % (value, unit)) if unit != "B" else ("%d B" % size)
        value /= 1024.0
    return "%d B" % size


def staged_entries(root):
    """Return (blob_sha, path, size) for files staged for commit."""
    raw = git(root, ["diff", "--cached", "--name-status", "-z", "--diff-filter=ACMR"])
    tokens = raw.split(b"\0")
    paths = []
    index = 0
    while index < len(tokens):
        status = tokens[index]
        index += 1
        if not status:
            break
        if status.startswith((b"R", b"C")):
            if index + 1 >= len(tokens):
                break
            index += 1  # old path is not present in the staged tree
            paths.append(tokens[index])
            index += 1
        else:
            if index >= len(tokens):
                break
            paths.append(tokens[index])
            index += 1

    staged = []
    hashes = []
    for raw_path in paths:
        path = path_text(raw_path)
        listing = git(root, ["ls-files", "--stage", "-z", "--", path])
        for record in listing.split(b"\0"):
            if not record:
                continue
            metadata = record.split(b"\t", 1)[0].split()
            if len(metadata) < 3 or metadata[2] != b"0" or metadata[0] == b"160000":
                continue
            blob_sha = metadata[1].decode("ascii")
            if blob_sha not in hashes:
                hashes.append(blob_sha)
            staged.append((blob_sha, path))
            break

    sizes = blob_sizes(root, hashes)
    entries = []
    for blob_sha, path in staged:
        size = sizes.get(blob_sha)
        if size is not None:
            entries.append((blob_sha, path, size))
    return entries


def blob_sizes(root, hashes):
    if not hashes:
        return {}
    request = ("\n".join(hashes) + "\n").encode("ascii")
    raw = git(
        root,
        ["cat-file", "--batch-check=%(objectname)\t%(objecttype)\t%(objectsize)"],
        input_bytes=request,
    )
    sizes = {}
    for line in raw.splitlines():
        fields = line.split(b"\t")
        if len(fields) != 3 or fields[1] != b"blob":
            continue
        try:
            sizes[fields[0].decode("ascii")] = int(fields[2])
        except ValueError:
            continue
    return sizes


def range_entries(root, rev_args):
    """Return (blob_sha, path, size) for blobs newly reachable in a range."""
    producer = subprocess.Popen(
        ["git", "rev-list", "--objects"] + rev_args,
        cwd=str(root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    inspector = subprocess.Popen(
        [
            "git",
            "cat-file",
            "--batch-check=%(objectname)\t%(objecttype)\t%(objectsize)\t%(rest)",
        ],
        cwd=str(root),
        stdin=producer.stdout,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if producer.stdout is not None:
        producer.stdout.close()
    output, inspect_error = inspector.communicate()
    produce_error = producer.stderr.read() if producer.stderr is not None else b""
    producer_rc = producer.wait()
    if producer_rc != 0 or inspector.returncode != 0:
        detail = (produce_error + inspect_error).decode("utf-8", "replace").strip()
        raise GuardError("could not inspect Git object range: %s" % detail)

    entries = []
    for line in output.splitlines():
        fields = line.split(b"\t", 3)
        if len(fields) != 4 or fields[1] != b"blob":
            continue
        try:
            size = int(fields[2])
        except ValueError:
            continue
        entries.append((fields[0].decode("ascii"), path_text(fields[3].strip()), size))
    return entries


def report(context, entries, max_file_bytes, max_total_bytes):
    blocked = []
    oversized = []
    total = 0
    seen_blobs = set()
    seen_oversized = set()

    for blob_sha, path, size in entries:
        if blob_sha not in seen_blobs:
            seen_blobs.add(blob_sha)
            total += size
        if is_blocked_path(path):
            blocked.append((path, size))
        if size > max_file_bytes and blob_sha not in seen_oversized:
            seen_oversized.add(blob_sha)
            oversized.append((path, size))

    if not blocked and not oversized and total <= max_total_bytes:
        return 0

    print("Git hygiene guard blocked the %s." % context, file=sys.stderr)
    print(
        "Limits: %s per file, %s total, and no runtime/browser cache paths."
        % (format_size(max_file_bytes), format_size(max_total_bytes)),
        file=sys.stderr,
    )
    for path, size in blocked[:20]:
        print("  blocked path: %s (%s)" % (path, format_size(size)), file=sys.stderr)
    for path, size in oversized[:20]:
        print("  oversized file: %s (%s)" % (path, format_size(size)), file=sys.stderr)
    if total > max_total_bytes:
        print(
            "  total new content: %s exceeds %s"
            % (format_size(total), format_size(max_total_bytes)),
            file=sys.stderr,
        )
    print("", file=sys.stderr)
    print("Unstage generated files with: git restore --staged <path>", file=sys.stderr)
    print("Add a matching .gitignore rule; rebuild or download the asset at runtime.", file=sys.stderr)
    print(
        "If a large blob was already committed, deleting it later does not remove it"
        " from history. Rewrite the unpushed commits before pushing.",
        file=sys.stderr,
    )
    print("Do not use Git LFS for browser caches or virtual environments.", file=sys.stderr)
    return 1


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest="mode", required=True)

    staged = modes.add_parser("staged", help="check files staged for commit")
    staged.add_argument("--max-file-bytes", type=int, default=MAX_FILE_BYTES)
    staged.add_argument("--max-total-bytes", type=int, default=MAX_STAGED_TOTAL_BYTES)

    ranged = modes.add_parser("range", help="check blobs newly reachable in base..head")
    ranged.add_argument("base")
    ranged.add_argument("head")
    ranged.add_argument("--max-file-bytes", type=int, default=MAX_FILE_BYTES)
    ranged.add_argument("--max-total-bytes", type=int, default=MAX_PUSH_TOTAL_BYTES)

    new_ref = modes.add_parser("new", help="check blobs not reachable from any remote ref")
    new_ref.add_argument("head")
    new_ref.add_argument("--max-file-bytes", type=int, default=MAX_FILE_BYTES)
    new_ref.add_argument("--max-total-bytes", type=int, default=MAX_PUSH_TOTAL_BYTES)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        root = repo_root()
        if args.mode == "staged":
            entries = staged_entries(root)
            return report("staged commit", entries, args.max_file_bytes, args.max_total_bytes)
        if args.mode == "range":
            if args.base.lower() == ZERO_SHA:
                entries = range_entries(root, [args.head, "--not", "--remotes"])
            else:
                entries = range_entries(root, ["%s..%s" % (args.base, args.head)])
            return report("push", entries, args.max_file_bytes, args.max_total_bytes)
        entries = range_entries(root, [args.head, "--not", "--remotes"])
        return report("new branch push", entries, args.max_file_bytes, args.max_total_bytes)
    except GuardError as error:
        print("Git hygiene guard error: %s" % error, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

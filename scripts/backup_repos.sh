#!/usr/bin/env bash
# Make a complete, verifiable, off-GitHub copy of the three existing repositories.
#
# What you get in OUT_DIR (default: ./repo-backup-YYYY-MM-DD):
#   <repo>.bundle      every branch, tag and commit of the repo in ONE file, including all data history
#                      (the crypto `data` branch, every daily version of the bond database, CSE raw files)
#   SHA256SUMS         fingerprints of every file, so a later copy can be checked with `sha256sum -c SHA256SUMS`
#   README.txt         how to restore
#
# A git bundle is a plain file: copy it to a USB drive, Google Drive, Backblaze, anywhere. To get a working
# repository back from it:  git clone CSE.bundle CSE
#
# Read-only towards GitHub: it only clones. Works for private repos too, as long as your own git login can read them.
#
#   bash scripts/backup_repos.sh                 # writes ./repo-backup-<today>
#   bash scripts/backup_repos.sh /path/to/dir    # writes there
set -euo pipefail

OWNER="MinimumLizard"
REPOS=(CSE Nelson-Siegel Crypto)
OUT_DIR="${1:-./repo-backup-$(date -u +%Y-%m-%d)}"

mkdir -p "$OUT_DIR"
OUT_DIR="$(cd "$OUT_DIR" && pwd)"   # absolute, so later cd/git -C calls agree on it
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

for repo in "${REPOS[@]}"; do
  echo "== $repo"
  # --mirror copies every branch and tag, not just the default branch (the crypto history lives on `data`).
  # OLD_REPOS_TOKEN (optional): a read-only token, needed once the repos are private.
  AUTH=""; [ -n "${OLD_REPOS_TOKEN:-}" ] && AUTH="x-access-token:${OLD_REPOS_TOKEN}@"
  GIT_LFS_SKIP_SMUDGE=1 git clone --quiet --mirror "https://${AUTH}github.com/$OWNER/$repo.git" "$WORK/$repo.git"
  git -C "$WORK/$repo.git" bundle create "$OUT_DIR/$repo.bundle" --all 2>/dev/null
  # Prove the bundle is complete and readable before trusting it.
  git bundle verify "$OUT_DIR/$repo.bundle" >/dev/null
  echo "   $(git -C "$WORK/$repo.git" rev-list --all --count) commits, branches: $(git -C "$WORK/$repo.git" branch --format='%(refname:short)' | tr '\n' ' ')"
done

cat > "$OUT_DIR/README.txt" <<EOF
Backup of github.com/$OWNER/{${REPOS[*]}} taken $(date -u +%Y-%m-%dT%H:%M:%SZ).

Check nothing was damaged in transit:   sha256sum -c SHA256SUMS
Restore a repository:                    git clone <name>.bundle <name>
Restore a specific branch (e.g. crypto data):  git clone -b data Crypto.bundle Crypto-data
EOF

( cd "$OUT_DIR" && sha256sum ./*.bundle README.txt > SHA256SUMS )
echo "Done: $OUT_DIR"
cat "$OUT_DIR/SHA256SUMS"

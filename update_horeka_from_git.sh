#!/usr/bin/env bash
set -euo pipefail

# Update only tracked source files. Generated outputs, credentials and virtual
# environments are outside Git and remain untouched.
PIPELINE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BRANCH="${1:-main}"

cd "${PIPELINE_DIR}"
git rev-parse --is-inside-work-tree >/dev/null
git fetch origin "${BRANCH}"
git switch "${BRANCH}"
git pull --ff-only origin "${BRANCH}"

echo "Updated source to $(git rev-parse --short HEAD) on branch ${BRANCH}."
echo "Run bash bootstrap_env.sh only if requirements.hpc.txt changed."

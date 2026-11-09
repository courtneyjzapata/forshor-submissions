#!/usr/bin/env bash
# Only touch disposable GitHub-hosted Linux machines. Custom runners provision themselves.
set -euo pipefail
if [ "${RUNNER_ENVIRONMENT:-}" != github-hosted ] || [ "${RUNNER_OS:-}" != Linux ]; then
  echo "Using the custom runner's existing resource configuration"
  exit 0
fi
free -h
df -h "$RUNNER_TEMP"
# Make room for two Lean trees, their disposable verification copy, and swap.
sudo rm -rf /usr/share/dotnet /usr/local/lib/android /opt/ghc /opt/hostedtoolcache/CodeQL
swapfile="$RUNNER_TEMP/forshor-policy.swap"
if [ ! -e "$swapfile" ]; then
  sudo fallocate -l 8G "$swapfile"
  sudo chmod 600 "$swapfile"
  sudo mkswap "$swapfile"
  sudo swapon "$swapfile"
fi
free -h
df -h "$RUNNER_TEMP"

#!/usr/bin/env bash
# Scan an archive instead of giving the scanner access to the Docker socket.
set -euo pipefail
image=${1:-runbookops:smoke}
output=${2:-reports/security}
mkdir -p "$(dirname "$output")"
# Refuse to mix a failed scan with reports from an earlier invocation.
mkdir "$output"
output=$(cd "$output" && pwd)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
mkdir "$work/cache"
scanner=aquasec/trivy:0.75.0
docker pull "$scanner"
docker image inspect "$image" --format '{{json .Id}}' > "$output/image-id.json"
docker image inspect "$scanner" --format '{{json .RepoDigests}}' > "$output/scanner-digests.json"
docker save "$image" -o "$work/image.tar"
scan() {
  docker run --rm --user "$(id -u):$(id -g)" --cap-drop ALL \
    --security-opt no-new-privileges \
    -v "$work:/scan:ro" -v "$work/cache:/cache" -v "$output:/output" \
    "$scanner" --cache-dir /cache "$@"
}
# Preserve low-severity and unfixed findings; no repository ignore file is used.
scan image --disable-telemetry --input /scan/image.tar --scanners vuln --pkg-types os,library \
  --ignorefile /dev/null --list-all-pkgs --format json --exit-code 0 \
  --output /output/trivy.json
scan version --format json > "$output/scanner-version.json"
python scripts/check_audit_inventory.py "$output/trivy.json"
# Reuse the same downloaded advisory database for the blocking policy.
scan image --disable-telemetry --input /scan/image.tar --scanners vuln --pkg-types os,library \
  --ignorefile /dev/null --skip-db-update --severity HIGH,CRITICAL \
  --ignore-unfixed --exit-code 1 --format table | tee "$output/blocking-findings.txt"

#!/usr/bin/env bash
# This plugin's own gate: it must pass from this repo's root, with no sibling repo cloned except
# lib_bespok3d. Exits non-zero on any failure.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# The shared gate helpers and the detectors that enforce a workspace-wide rule live in one place.
# See lib_bespok3d/tooling/README.md. This is the only line that knows where they are.
B3D_TOOLING="${B3D_TOOLING:-$REPO_ROOT/lib_bespok3d/tooling}"
# shellcheck source=/dev/null
. "$B3D_TOOLING/gate-lib.sh"

cd "$REPO_ROOT" || exit 1

PLUGIN_DIR="$REPO_ROOT/rfid-ntag"
RFID_SUPPORT="files/klipper/klippy/extras/rfid-support"

echo ""
echo "u1-enhanced-rfid gate"

b3d_python_tools

run_check "pytest"  pytest_in_dir "$PLUGIN_DIR" tests
run_check "ruff"    ruff_in_dir "$PLUGIN_DIR" files tests
# The reader driver talks to Klipper objects mypy cannot resolve; the pure decode path carries the
# type coverage.
run_check "mypy"    mypy_in_dir "$PLUGIN_DIR" \
    "$RFID_SUPPORT/chips/ndef_parser.py" "$RFID_SUPPORT/chips/mifare_classic.py" \
    "$RFID_SUPPORT/payload_mapper.py"

workflow_pinning_check "$REPO_ROOT"
em_dash_check "$REPO_ROOT"
shellcheck_repo "$REPO_ROOT"

gate_summary || exit 1

#!/bin/bash
# rustc_tpde_dynamic.sh

SCRIPT_DIR=$(dirname "$(realpath "$0")")
BACKEND_PATH="${SCRIPT_DIR}/../deps/RustcTpde/target-no-cache/release/librustc_codegen_tpde.so"

exec rustc \
  +nightly-2026-10-28 \
  -Z codegen-backend="${BACKEND_PATH}" \
  "$@"
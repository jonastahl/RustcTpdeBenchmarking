#!/bin/bash
# rustc_tpde_inline.sh, inlining with the default cost factor of the backend

SCRIPT_DIR=$(dirname "$(realpath "$0")")
BACKEND_PATH="${SCRIPT_DIR}/../deps/RustcTpde/target-inline/release/librustc_codegen_tpde.so"

exec rustc \
  +nightly-2026-10-28 \
  -Z codegen-backend="${BACKEND_PATH}" \
  "$@"

#!/bin/bash
# rustc_tpde_dynamic.sh

SCRIPT_DIR=$(dirname "$(realpath "$0")")
BACKEND_PATH="${SCRIPT_DIR}/../deps/RustcTpde/target/release/librustc_codegen_tpde_dylib.so"

exec rustc \
  +nightly-2026-08-19 \
  -Z codegen-backend="${BACKEND_PATH}" \
  "$@"
#!/bin/bash
# rustc_tpde_dynamic.sh

SCRIPT_DIR=$(dirname "$(realpath "$0")")
BACKEND_PATH="${SCRIPT_DIR}/../deps/backend_tpde_llvm/build/cg_tpde/x86_64-unknown-linux-gnu/release/librustc_codegen_tpde.so"

exec rustc \
  +nightly-2025-11-15 \
  -Z codegen-backend="${BACKEND_PATH}" \
  "$@"
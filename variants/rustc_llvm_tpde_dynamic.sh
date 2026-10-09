#!/bin/bash
# rustc_tpde_dynamic.sh

SCRIPT_DIR=$(dirname "$(realpath "$0")")
BACKEND_PATH="${SCRIPT_DIR}/../backend_tpde/target/release/librustc_codegen_llvm_tpde.so"

exec rustc \
  +nightly-2026-08-19 \
  -Z codegen-backend="${BACKEND_PATH}" \
  "$@"
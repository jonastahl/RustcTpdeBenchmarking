#!/bin/bash
# The TPDE backend with its optimizations enabled through -Cllvm-args (the backend ignores the opt-level)

SCRIPT_DIR=$(dirname "$(realpath "$0")")
BACKEND_PATH="${SCRIPT_DIR}/../deps/RustcTpde/target/release/librustc_codegen_tpde.so"

exec rustc \
  +nightly-2026-10-28 \
  -Z codegen-backend="${BACKEND_PATH}" \
  -C llvm-args=inline=yes -C llvm-args=promote=yes \
  "$@"

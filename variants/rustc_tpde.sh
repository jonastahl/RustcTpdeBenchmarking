#!/bin/bash
# rustc_tpde.sh

SCRIPT_DIR=$(dirname "$(realpath "$0")")
RUSTC_TPDE_PATH="${SCRIPT_DIR}/../deps/RustcTpde/target/release/rustc_tpde"

exec $RUSTC_TPDE_PATH \
  "$@"
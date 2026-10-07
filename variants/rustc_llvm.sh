#!/bin/bash
# baseline_llvm.sh

exec rustc \
  +nightly-2026-08-19 \
  "$@"
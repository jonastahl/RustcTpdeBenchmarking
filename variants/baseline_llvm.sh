#!/bin/bash
# baseline_llvm.sh

exec ~/.cargo/bin/rustc \
  +nightly-2026-08-19 \
  "$@"
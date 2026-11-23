#!/bin/bash
# rustc_cranelift.sh

exec rustc \
  +nightly-2026-11-20 \
  -Z codegen-backend=cranelift \
  "$@"
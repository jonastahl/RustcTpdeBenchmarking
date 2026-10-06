#!/bin/bash
# rustc_cranelift.sh

exec rustc \
  +nightly-2026-08-19 \
  -Z codegen-backend=cranelift \
  "$@"
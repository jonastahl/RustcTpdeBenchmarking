#!/bin/bash
# rustc_cranelift.sh

exec rustc \
  +nightly-2026-10-28 \
  -Z codegen-backend=cranelift \
  "$@"
#!/bin/bash
# rustc_gcc.sh

exec rustc \
  +nightly-2026-08-19 \
  -Z codegen-backend=gcc \
  "$@"
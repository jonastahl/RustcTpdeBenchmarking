#!/bin/bash
# rustc_custom_tpde.sh

exec rustc \
  +tpde-release \
  -Z codegen-backend="tpde" \
  "$@"
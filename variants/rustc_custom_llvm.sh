#!/bin/bash
# rustc_custom_llvm.sh

exec rustc \
  +tpde-release \
  "$@"
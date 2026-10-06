

cargo +nightly-2026-08-19 clean --target-dir target-prof-llvm
rm -r prof-llvm
CARGO_PROFILE_DEV_DEBUG=0 RUSTFLAGS="-Znext-solver=coherence -Zself-profile=prof-llvm" cargo +nightly-2026-08-19 build --lib --target x86_64-unknown-linux-gnu --target-dir target-prof-llvm
cargo +nightly-2026-08-19 clean --target-dir target-prof-tpde
rm -r prof-tpde
CARGO_PROFILE_DEV_DEBUG=0 RUSTFLAGS="-Znext-solver=coherence -Zcodegen-backend=$PWD/../../../../backend_tpde/target/release/librustc_codegen_tpde.so -Zself-profile=prof-tpde" cargo +nightly-2026-08-19 build --lib --target x86_64-unknown-linux-gnu --target-dir target-prof-tpde

# Print results to the console (needs: cargo install --git https://github.com/rust-lang/measureme summarize)
for backend in llvm tpde; do
  for f in prof-$backend/*.mm_profdata; do
    echo "=== $backend: $(basename "$f") ==="
    summarize summarize "$f"
  done
done

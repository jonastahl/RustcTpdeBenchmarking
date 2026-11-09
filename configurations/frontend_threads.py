"""Compile time with the parallel frontend (-Zthreads), restricted to different numbers of cores."""
from src.runs import CompileTime

VARIANTS = ["LLVM", "TPDE"]

# None keeps the default of rustc (no parallel frontend)
FRONTEND_THREADS = [None, 1, 100]

# For now, the 32 cores include hyperthreading siblings
CORES = [32, 8]

def get_config():
    return [CompileTime(VARIANTS, cores=cores, threads=threads) for threads in FRONTEND_THREADS for cores in CORES]

def evaluate(results):
    pass
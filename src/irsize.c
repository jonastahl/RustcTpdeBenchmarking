#include <malloc.h>
#include <stdio.h>
typedef struct O *LLVMContextRef; typedef struct O2 *LLVMModuleRef; typedef struct O3 *LLVMMemoryBufferRef;
LLVMContextRef LLVMContextCreate(void);
int LLVMCreateMemoryBufferWithContentsOfFile(const char*, LLVMMemoryBufferRef*, char**);
int LLVMParseIRInContext(LLVMContextRef, LLVMMemoryBufferRef, LLVMModuleRef*, char**);
static size_t used(void){ struct mallinfo2 m = mallinfo2(); return m.uordblks + m.hblkhd; }
int main(int c, char **v){
  for (int i = 1; i < c; i++) {
    LLVMContextRef ctx = LLVMContextCreate();
    LLVMMemoryBufferRef buf; LLVMModuleRef mod; char *err = 0;
    size_t before = used();
    if (LLVMCreateMemoryBufferWithContentsOfFile(v[i], &buf, &err)) { fprintf(stderr, "%s\n", err); return 1; }
    if (LLVMParseIRInContext(ctx, buf, &mod, &err)) { fprintf(stderr, "%s\n", err); return 1; }
    printf("%s %zu\n", v[i], used() - before);
  }
}

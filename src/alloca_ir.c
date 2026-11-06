/* Extracts every alloca of LLVM IR/bitcode modules and how it is used, as JSON lines (one object per line):

     {"module": path}                                      before the functions of a module
     {"function": name, "blocks": n, "instructions": n}    before the allocas of a function
     {"name": .., "type": .., "size": bytes or null (dynamic), "align": n, "b": block, "i": index, "uses": [use, ...]}

   Pointers derived from an alloca by GEPs and casts are followed, the uses of a derived pointer are reported for the
   alloca with "derived": true and the byte "offset" into the alloca (null if not constant). A use has a "kind", its
   position "b"/"i" (block / index in the block) and depending on the kind:
     load, store            the pointer operand: "bytes" accessed, "volatile"
     store_value            the pointer itself is stored somewhere
     copy_dst, copy_src     memcpy/memmove: "bytes" (null if not constant), "callee"
     memset                 "bytes" (null if not constant)
     lifetime               llvm.lifetime.*
     intrinsic              any other llvm.* intrinsic: "callee", "arg"
     call                   passed to a call: "callee" (null if indirect), "arg", "attrs" of the parameter
     gep, cast              derivation of another pointer (its uses follow as derived uses)
     phi, select, icmp, ptrtoint, ret
     other                  "opcode" (LLVMOpcode)

   Usage: alloca_ir <output.jsonl> <module>...
   It has to be linked against the libLLVM of the rustc toolchain to read its bitcode. */
#include <llvm-c/Core.h>
#include <llvm-c/IRReader.h>
#include <llvm-c/Target.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* ---- Growable string buffer ---- */

typedef struct {
    char *data;
    size_t len, cap;
} Buf;

static void buf_put(Buf *b, const char *s, size_t n) {
    if (b->len + n + 1 > b->cap) {
        b->cap = (b->len + n + 1) * 2;
        b->data = realloc(b->data, b->cap);
    }
    memcpy(b->data + b->len, s, n);
    b->len += n;
    b->data[b->len] = 0;
}

static void buf_str(Buf *b, const char *s) { buf_put(b, s, strlen(s)); }

static void buf_fmt(Buf *b, const char *fmt, long long v) {
    char tmp[64];
    buf_put(b, tmp, (size_t)snprintf(tmp, sizeof tmp, fmt, v));
}

static void buf_json(Buf *b, const char *s, size_t n) {
    buf_str(b, "\"");
    for (size_t i = 0; i < n; i++) {
        unsigned char c = (unsigned char)s[i];
        if (c == '"' || c == '\\') {
            char esc[2] = {'\\', (char)c};
            buf_put(b, esc, 2);
        } else if (c < 0x20) {
            buf_fmt(b, "\\u%04llx", c);
        } else {
            buf_put(b, (const char *)&c, 1);
        }
    }
    buf_str(b, "\"");
}

/* ---- Instruction table: value -> position and the alloca it derives from ---- */

typedef struct {
    LLVMValueRef key;
    int block, index;
    int root;          /* index of the alloca this pointer derives from, -1 if none */
    int derived;       /* 0 for the alloca itself */
    int offset_known;
    long long offset;  /* byte offset into the alloca */
} Entry;

typedef struct {
    Entry *entries;
    size_t mask;
} Table;

static Entry *table_slot(Table *t, LLVMValueRef key) {
    size_t h = ((uintptr_t)key >> 4) * 0x9E3779B97F4A7C15ull;
    for (size_t i = h & t->mask;; i = (i + 1) & t->mask)
        if (t->entries[i].key == key || t->entries[i].key == NULL) return &t->entries[i];
}

static Entry *table_get(Table *t, LLVMValueRef key) {
    Entry *e = table_slot(t, key);
    return e->key ? e : NULL;
}

/* ---- Helpers ---- */

static LLVMTargetDataRef layout;
static unsigned attr_kinds[16];
static const char *attr_names[] = {"sret", "byval", "readonly", "writeonly", "readnone", "noalias", "nocapture",
                                   "dereferenceable"};
#define ATTR_COUNT (sizeof attr_names / sizeof *attr_names)
static unsigned captures_kind;

static const char *value_name(LLVMValueRef v, size_t *len) {
    const char *name = LLVMGetValueName2(v, len);
    return name ? name : (*len = 0, "");
}

static int const_int(LLVMValueRef v, long long *out) {
    if (!v || !LLVMIsAConstantInt(v)) return 0;
    *out = LLVMConstIntGetSExtValue(v);
    return 1;
}

/* Byte offset of a GEP relative to its pointer operand, 0 if an index is not constant */
static int gep_offset(LLVMValueRef gep, long long *out) {
    LLVMTypeRef ty = LLVMGetGEPSourceElementType(gep);
    unsigned n = (unsigned)LLVMGetNumOperands(gep);
    long long offset = 0, idx;
    for (unsigned k = 1; k < n; k++) {
        if (!const_int(LLVMGetOperand(gep, k), &idx)) return 0;
        if (k == 1) {
            offset += idx * (long long)LLVMABISizeOfType(layout, ty);
        } else if (LLVMGetTypeKind(ty) == LLVMStructTypeKind) {
            offset += (long long)LLVMOffsetOfElement(layout, ty, (unsigned)idx);
            ty = LLVMStructGetTypeAtIndex(ty, (unsigned)idx);
        } else if (LLVMGetTypeKind(ty) == LLVMArrayTypeKind || LLVMGetTypeKind(ty) == LLVMVectorTypeKind) {
            ty = LLVMGetElementType(ty);
            offset += idx * (long long)LLVMABISizeOfType(layout, ty);
        } else {
            return 0;
        }
    }
    *out = offset;
    return 1;
}

static int starts_with(const char *s, size_t len, const char *prefix) {
    size_t n = strlen(prefix);
    return len >= n && memcmp(s, prefix, n) == 0;
}

static void use_bytes(Buf *b, int known, long long bytes) {
    if (known) buf_fmt(b, ",\"bytes\":%lld", bytes);
    else buf_str(b, ",\"bytes\":null");
}

static void use_callee(Buf *b, const char *name, size_t len) {
    buf_str(b, ",\"callee\":");
    if (len) buf_json(b, name, len);
    else buf_str(b, "null");
}

static void use_attrs(Buf *b, LLVMValueRef call, LLVMValueRef callee, unsigned arg) {
    buf_str(b, ",\"attrs\":[");
    int first = 1;
    for (unsigned a = 0; a < ATTR_COUNT; a++) {
        if (!attr_kinds[a]) continue;
        int has = LLVMGetCallSiteEnumAttribute(call, arg + 1, attr_kinds[a]) != NULL;
        if (!has && callee) has = LLVMGetEnumAttributeAtIndex(callee, arg + 1, attr_kinds[a]) != NULL;
        if (has) {
            if (!first) buf_str(b, ",");
            buf_json(b, attr_names[a], strlen(attr_names[a]));
            first = 0;
        }
    }
    buf_str(b, "]");
    /* captures(...) is an int attribute, its raw CaptureInfo encoding is reported */
    if (captures_kind) {
        LLVMAttributeRef cap = LLVMGetCallSiteEnumAttribute(call, arg + 1, captures_kind);
        if (!cap && callee) cap = LLVMGetEnumAttributeAtIndex(callee, arg + 1, captures_kind);
        if (cap) buf_fmt(b, ",\"captures\":%lld", (long long)LLVMGetEnumAttributeValue(cap));
    }
}

/* Appends the use of operand k of inst, which is the pointer p derived from an alloca */
static void emit_use(Buf *b, LLVMValueRef inst, Entry *at, unsigned k, Entry *p) {
    LLVMOpcode op = LLVMGetInstructionOpcode(inst);
    long long bytes = 0;
    buf_fmt(b, "{\"b\":%lld", at->block);
    buf_fmt(b, ",\"i\":%lld", at->index);
    if (p->derived) {
        buf_str(b, ",\"derived\":true");
        if (p->offset_known) buf_fmt(b, ",\"offset\":%lld", p->offset);
        else buf_str(b, ",\"offset\":null");
    }
    switch (op) {
    case LLVMLoad:
        buf_str(b, ",\"kind\":\"load\"");
        use_bytes(b, 1, (long long)LLVMABISizeOfType(layout, LLVMTypeOf(inst)));
        if (LLVMGetVolatile(inst)) buf_str(b, ",\"volatile\":true");
        break;
    case LLVMStore:
        if (k == 1) {
            buf_str(b, ",\"kind\":\"store\"");
            use_bytes(b, 1, (long long)LLVMABISizeOfType(layout, LLVMTypeOf(LLVMGetOperand(inst, 0))));
            if (LLVMGetVolatile(inst)) buf_str(b, ",\"volatile\":true");
        } else {
            buf_str(b, ",\"kind\":\"store_value\"");
        }
        break;
    case LLVMGetElementPtr:
        buf_str(b, k == 0 ? ",\"kind\":\"gep\"" : ",\"kind\":\"other\"");
        break;
    case LLVMBitCast:
    case LLVMAddrSpaceCast:
        buf_str(b, ",\"kind\":\"cast\"");
        break;
    case LLVMCall:
    case LLVMInvoke:
    case LLVMCallBr: {
        LLVMValueRef callee = LLVMGetCalledValue(inst);
        if (callee && !LLVMIsAFunction(callee)) callee = NULL;
        size_t len = 0;
        const char *name = callee ? value_name(callee, &len) : "";
        if (k >= LLVMGetNumArgOperands(inst)) {
            buf_str(b, ",\"kind\":\"other\"");
            buf_fmt(b, ",\"opcode\":%lld", op);
        } else if (starts_with(name, len, "llvm.lifetime.")) {
            buf_str(b, ",\"kind\":\"lifetime\"");
        } else if (starts_with(name, len, "llvm.memcpy") || starts_with(name, len, "llvm.memmove")) {
            buf_str(b, k == 0 ? ",\"kind\":\"copy_dst\"" : k == 1 ? ",\"kind\":\"copy_src\"" : ",\"kind\":\"other\"");
            use_bytes(b, const_int(LLVMGetOperand(inst, 2), &bytes), bytes);
            use_callee(b, name, len);
        } else if (starts_with(name, len, "llvm.memset") && k == 0) {
            buf_str(b, ",\"kind\":\"memset\"");
            use_bytes(b, const_int(LLVMGetOperand(inst, 2), &bytes), bytes);
        } else if (starts_with(name, len, "llvm.")) {
            buf_str(b, ",\"kind\":\"intrinsic\"");
            use_callee(b, name, len);
            buf_fmt(b, ",\"arg\":%lld", k);
        } else {
            buf_str(b, ",\"kind\":\"call\"");
            use_callee(b, name, len);
            buf_fmt(b, ",\"arg\":%lld", k);
            use_attrs(b, inst, callee, k);
        }
        break;
    }
    case LLVMPHI: buf_str(b, ",\"kind\":\"phi\""); break;
    case LLVMSelect: buf_str(b, ",\"kind\":\"select\""); break;
    case LLVMICmp: buf_str(b, ",\"kind\":\"icmp\""); break;
    case LLVMPtrToInt: buf_str(b, ",\"kind\":\"ptrtoint\""); break;
    case LLVMRet: buf_str(b, ",\"kind\":\"ret\""); break;
    default:
        buf_str(b, ",\"kind\":\"other\"");
        buf_fmt(b, ",\"opcode\":%lld", op);
    }
    buf_str(b, "}");
}

static void process_function(FILE *out, LLVMValueRef fn) {
    size_t blocks = 0, instructions = 0;
    for (LLVMBasicBlockRef bb = LLVMGetFirstBasicBlock(fn); bb; bb = LLVMGetNextBasicBlock(bb), blocks++)
        for (LLVMValueRef inst = LLVMGetFirstInstruction(bb); inst; inst = LLVMGetNextInstruction(inst))
            instructions++;

    size_t len;
    const char *name = value_name(fn, &len);
    Buf line = {0};
    buf_str(&line, "{\"function\":");
    buf_json(&line, name, len);
    buf_fmt(&line, ",\"blocks\":%lld", (long long)blocks);
    buf_fmt(&line, ",\"instructions\":%lld}\n", (long long)instructions);
    fputs(line.data, out);
    free(line.data);

    size_t cap = 16;
    while (cap < 2 * instructions) cap *= 2;
    Table t = {calloc(cap, sizeof(Entry)), cap - 1};
    LLVMValueRef *allocas = malloc(sizeof(LLVMValueRef) * (instructions + 1));
    int n_allocas = 0;

    /* Positions and allocas */
    int b = 0;
    for (LLVMBasicBlockRef bb = LLVMGetFirstBasicBlock(fn); bb; bb = LLVMGetNextBasicBlock(bb), b++) {
        int i = 0;
        for (LLVMValueRef inst = LLVMGetFirstInstruction(bb); inst; inst = LLVMGetNextInstruction(inst), i++) {
            Entry *e = table_slot(&t, inst);
            *e = (Entry){inst, b, i, -1, 0, 1, 0};
            if (LLVMGetInstructionOpcode(inst) == LLVMAlloca) {
                e->root = n_allocas;
                allocas[n_allocas++] = inst;
            }
        }
    }
    if (!n_allocas) goto done;

    /* Pointers derived by GEPs and casts, until a fixed point since the block order needn't follow dominance */
    for (int changed = 1; changed;) {
        changed = 0;
        for (LLVMBasicBlockRef bb = LLVMGetFirstBasicBlock(fn); bb; bb = LLVMGetNextBasicBlock(bb)) {
            for (LLVMValueRef inst = LLVMGetFirstInstruction(bb); inst; inst = LLVMGetNextInstruction(inst)) {
                LLVMOpcode op = LLVMGetInstructionOpcode(inst);
                if (op != LLVMGetElementPtr && op != LLVMBitCast && op != LLVMAddrSpaceCast) continue;
                Entry *e = table_get(&t, inst);
                if (e->root >= 0) continue;
                Entry *p = table_get(&t, LLVMGetOperand(inst, 0));
                if (!p || p->root < 0) continue;
                long long offset = 0;
                int known = p->offset_known && (op != LLVMGetElementPtr || gep_offset(inst, &offset));
                e->root = p->root;
                e->derived = p->derived + 1;
                e->offset_known = known;
                e->offset = known ? p->offset + offset : 0;
                changed = 1;
            }
        }
    }

    /* Uses, collected per alloca */
    Buf *uses = calloc((size_t)n_allocas, sizeof(Buf));
    for (LLVMBasicBlockRef bb = LLVMGetFirstBasicBlock(fn); bb; bb = LLVMGetNextBasicBlock(bb)) {
        for (LLVMValueRef inst = LLVMGetFirstInstruction(bb); inst; inst = LLVMGetNextInstruction(inst)) {
            Entry *at = table_get(&t, inst);
            unsigned n = (unsigned)LLVMGetNumOperands(inst);
            for (unsigned k = 0; k < n; k++) {
                LLVMValueRef operand = LLVMGetOperand(inst, k);
                if (!operand || !LLVMIsAInstruction(operand)) continue;
                Entry *p = table_get(&t, operand);
                if (!p || p->root < 0) continue;
                Buf *u = &uses[p->root];
                if (u->len) buf_str(u, ",");
                emit_use(u, inst, at, k, p);
            }
        }
    }

    for (int a = 0; a < n_allocas; a++) {
        LLVMValueRef alloca = allocas[a];
        Entry *e = table_get(&t, alloca);
        LLVMTypeRef ty = LLVMGetAllocatedType(alloca);
        long long count;
        Buf out_line = {0};
        name = value_name(alloca, &len);
        buf_str(&out_line, "{\"name\":");
        buf_json(&out_line, name, len);
        char *type = LLVMPrintTypeToString(ty);
        buf_str(&out_line, ",\"type\":");
        buf_json(&out_line, type, strlen(type));
        LLVMDisposeMessage(type);
        if (const_int(LLVMGetOperand(alloca, 0), &count))
            buf_fmt(&out_line, ",\"size\":%lld", count * (long long)LLVMABISizeOfType(layout, ty));
        else
            buf_str(&out_line, ",\"size\":null");
        buf_fmt(&out_line, ",\"align\":%lld", LLVMGetAlignment(alloca));
        buf_fmt(&out_line, ",\"b\":%lld", e->block);
        buf_fmt(&out_line, ",\"i\":%lld", e->index);
        buf_str(&out_line, ",\"uses\":[");
        if (uses[a].len) buf_str(&out_line, uses[a].data);
        buf_str(&out_line, "]}\n");
        fputs(out_line.data, out);
        free(out_line.data);
        free(uses[a].data);
    }
    free(uses);

done:
    free(allocas);
    free(t.entries);
}

int main(int argc, char **argv) {
    if (argc < 2) {
        fprintf(stderr, "Usage: %s <output.jsonl> <module>...\n", argv[0]);
        return 2;
    }
    FILE *out = fopen(argv[1], "w");
    if (!out) {
        perror(argv[1]);
        return 1;
    }
    for (unsigned a = 0; a < ATTR_COUNT; a++)
        attr_kinds[a] = LLVMGetEnumAttributeKindForName(attr_names[a], strlen(attr_names[a]));
    captures_kind = LLVMGetEnumAttributeKindForName("captures", strlen("captures"));

    for (int m = 2; m < argc; m++) {
        LLVMContextRef ctx = LLVMContextCreate();
        LLVMMemoryBufferRef buffer;
        LLVMModuleRef module;
        char *err = NULL;
        if (LLVMCreateMemoryBufferWithContentsOfFile(argv[m], &buffer, &err) ||
            LLVMParseIRInContext(ctx, buffer, &module, &err)) {
            fprintf(stderr, "%s: %s\n", argv[m], err);
            return 1;
        }
        layout = LLVMCreateTargetData(LLVMGetDataLayoutStr(module));

        Buf line = {0};
        buf_str(&line, "{\"module\":");
        buf_json(&line, argv[m], strlen(argv[m]));
        buf_str(&line, "}\n");
        fputs(line.data, out);
        free(line.data);

        for (LLVMValueRef fn = LLVMGetFirstFunction(module); fn; fn = LLVMGetNextFunction(fn))
            if (!LLVMIsDeclaration(fn)) process_function(out, fn);

        LLVMDisposeTargetData(layout);
        LLVMDisposeModule(module);
        LLVMContextDispose(ctx);
    }
    return fclose(out) != 0;
}

FROM adaivy-phase3b-gate:lean-v4.32.1 AS builder
USER 0:0

COPY elan-aarch64-unknown-linux-gnu.tar.gz /acquisition/elan-aarch64-unknown-linux-gnu.tar.gz
RUN echo "bb78726ace6a912c7122a389018bcd69d9122ce04659800101392f7db380d3b3  /acquisition/elan-aarch64-unknown-linux-gnu.tar.gz" | sha256sum --check --strict \
    && mkdir /acquisition/elan-v4.2.1 \
    && tar --extract --gzip --file /acquisition/elan-aarch64-unknown-linux-gnu.tar.gz --directory /acquisition/elan-v4.2.1 \
    && /acquisition/elan-v4.2.1/elan-init --version

COPY landlock_launcher.c /build/landlock_launcher.c
COPY landlock_hardener.c /build/landlock_hardener.c
COPY aarch64_start.S /build/aarch64_start.S
COPY copy_module_closure.sh /build/copy_module_closure.sh
RUN /home/lean/.elan/toolchains/leanprover--lean4---v4.32.1/bin/clang \
      -O2 -Wall -Wextra -Werror -fPIE -fno-stack-protector -fno-builtin \
      -c -o /build/launcher.o /build/landlock_launcher.c \
    && /home/lean/.elan/toolchains/leanprover--lean4---v4.32.1/bin/clang \
      -fPIE -c -o /build/aarch64_start.o /build/aarch64_start.S \
    && /home/lean/.elan/toolchains/leanprover--lean4---v4.32.1/bin/ld.lld \
      -pie --dynamic-linker /lib/ld-linux-aarch64.so.1 \
      -z relro -z now -o /build/launcher /build/aarch64_start.o \
      /build/launcher.o /lib/aarch64-linux-gnu/libc.so.6 \
    && /home/lean/.elan/toolchains/leanprover--lean4---v4.32.1/bin/clang \
      -O2 -Wall -Wextra -Werror -fPIC -fno-stack-protector -fno-builtin \
      -c -o /build/landlock_hardener.o /build/landlock_hardener.c \
    && /home/lean/.elan/toolchains/leanprover--lean4---v4.32.1/bin/ld.lld \
      -shared -soname landlock_hardener.so -z relro -z now \
      -o /build/landlock_hardener.so /build/landlock_hardener.o \
      /lib/aarch64-linux-gnu/libc.so.6

RUN mkdir -p /runtime/checker /runtime/opt/lean/bin /runtime/opt/lean/lib/lean \
      /runtime/lib/aarch64-linux-gnu /runtime/trusted /runtime/tmp \
    && cp /build/launcher /runtime/checker/launcher \
    && cp /build/landlock_hardener.so /runtime/checker/landlock_hardener.so \
    && cp /home/lean/.elan/toolchains/leanprover--lean4---v4.32.1/bin/lean /runtime/opt/lean/bin/lean \
    && cp -a /home/lean/.elan/toolchains/leanprover--lean4---v4.32.1/lib/lean/Init /runtime/opt/lean/lib/lean/ \
    && cp -a /home/lean/.elan/toolchains/leanprover--lean4---v4.32.1/lib/lean/Lean /runtime/opt/lean/lib/lean/ \
    && cp -a /home/lean/.elan/toolchains/leanprover--lean4---v4.32.1/lib/lean/Std /runtime/opt/lean/lib/lean/ \
    && cp /home/lean/.elan/toolchains/leanprover--lean4---v4.32.1/lib/lean/Init.olean* /runtime/opt/lean/lib/lean/ \
    && cp /home/lean/.elan/toolchains/leanprover--lean4---v4.32.1/lib/lean/Init.ir* /runtime/opt/lean/lib/lean/ \
    && cp /home/lean/.elan/toolchains/leanprover--lean4---v4.32.1/lib/lean/Lean.olean* /runtime/opt/lean/lib/lean/ \
    && cp /home/lean/.elan/toolchains/leanprover--lean4---v4.32.1/lib/lean/Lean.ir* /runtime/opt/lean/lib/lean/ \
    && cp /home/lean/.elan/toolchains/leanprover--lean4---v4.32.1/lib/lean/Std.olean* /runtime/opt/lean/lib/lean/ \
    && cp /home/lean/.elan/toolchains/leanprover--lean4---v4.32.1/lib/lean/Std.ir* /runtime/opt/lean/lib/lean/ \
    && cp /home/lean/.elan/toolchains/leanprover--lean4---v4.32.1/lib/lean/libInit_shared.so /runtime/opt/lean/lib/lean/ \
    && cp /home/lean/.elan/toolchains/leanprover--lean4---v4.32.1/lib/lean/libleanshared.so /runtime/opt/lean/lib/lean/ \
    && cp /home/lean/.elan/toolchains/leanprover--lean4---v4.32.1/lib/lean/libleanshared_1.so /runtime/opt/lean/lib/lean/ \
    && cp /home/lean/.elan/toolchains/leanprover--lean4---v4.32.1/lib/lean/libleanshared_2.so /runtime/opt/lean/lib/lean/ \
    && sh /build/copy_module_closure.sh \
    && cp /lib/ld-linux-aarch64.so.1 /runtime/lib/ld-linux-aarch64.so.1 \
    && cp /lib/aarch64-linux-gnu/libc.so.6 /runtime/lib/aarch64-linux-gnu/ \
    && cp /lib/aarch64-linux-gnu/libpthread.so.0 /runtime/lib/aarch64-linux-gnu/ \
    && cp /lib/aarch64-linux-gnu/libdl.so.2 /runtime/lib/aarch64-linux-gnu/ \
    && cp /lib/aarch64-linux-gnu/libm.so.6 /runtime/lib/aarch64-linux-gnu/ \
    && cp /lib/aarch64-linux-gnu/librt.so.1 /runtime/lib/aarch64-linux-gnu/ \
    && chmod 0555 /runtime/checker/launcher /runtime/opt/lean/bin/lean /runtime/lib/ld-linux-aarch64.so.1 \
    && find /runtime/opt/lean/lib/lean /runtime/opt/mathlib -type f -exec chmod 0444 {} \; \
    && chmod 0444 /runtime/lib/aarch64-linux-gnu/* /runtime/checker/landlock_hardener.so

COPY fixtures/ /runtime/trusted/
RUN chmod 0444 /runtime/trusted/*.lean \
    && find /runtime -xdev -type f -perm /111 -print | LC_ALL=C sort > /build/executable-inventory.txt \
    && printf '%s\n' /runtime/checker/launcher /runtime/lib/ld-linux-aarch64.so.1 /runtime/opt/lean/bin/lean > /build/executable-allowlist.txt \
    && cmp /build/executable-allowlist.txt /build/executable-inventory.txt

FROM scratch
COPY --from=builder /runtime/ /
USER 65532:65532
WORKDIR /trusted
ENTRYPOINT ["/checker/launcher"]

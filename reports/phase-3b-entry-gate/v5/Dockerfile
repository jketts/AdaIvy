FROM adaivy-phase3b-gate:lean-v4.32.1 AS builder
USER 0:0

COPY reports/phase-3b-entry-gate/v5/landlock_launcher.c /build/landlock_launcher_v5.c
COPY reports/phase-3b-entry-gate/v5/aarch64_start.S /build/aarch64_start_v5.S
RUN /home/lean/.elan/toolchains/leanprover--lean4---v4.32.1/bin/clang \
      -O2 -Wall -Wextra -Werror -fPIE -fno-stack-protector -fno-builtin \
      -c -o /build/launcher_v5.o /build/landlock_launcher_v5.c \
    && /home/lean/.elan/toolchains/leanprover--lean4---v4.32.1/bin/clang \
      -fPIE -c -o /build/aarch64_start_v5.o /build/aarch64_start_v5.S \
    && /home/lean/.elan/toolchains/leanprover--lean4---v4.32.1/bin/ld.lld \
      -pie --dynamic-linker /lib/ld-linux-aarch64.so.1 \
      -z relro -z now -o /build/launcher_v5 /build/aarch64_start_v5.o \
      /build/launcher_v5.o /lib/aarch64-linux-gnu/libc.so.6 \
    && chmod 0555 /build/launcher_v5

FROM adaivy-phase3b-gate-v4:lean-v4.32.1
COPY --from=builder /build/launcher_v5 /checker/launcher
USER 65532:65532
WORKDIR /trusted
ENTRYPOINT ["/checker/launcher"]

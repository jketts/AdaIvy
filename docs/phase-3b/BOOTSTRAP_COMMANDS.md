# Proposed Authorized Bootstrap Commands

These commands are documentation only and were not run. They require explicit
authorization because they download executables and create files below the
user's elan directory and a future disposable Phase 3B acquisition workspace.
They do not use Homebrew or edit shell startup files.

The upstream installer must be downloaded, reviewed, and hashed before use:

```bash
mkdir -p /private/tmp/adaivy-lean-bootstrap
curl -fL https://raw.githubusercontent.com/leanprover/elan/v4.2.1/elan-init.sh -o /private/tmp/adaivy-lean-bootstrap/elan-init.sh
shasum -a 256 /private/tmp/adaivy-lean-bootstrap/elan-init.sh
less /private/tmp/adaivy-lean-bootstrap/elan-init.sh
sh /private/tmp/adaivy-lean-bootstrap/elan-init.sh -y --no-modify-path --default-toolchain none
```

Use an explicit PATH only in the current shell, then install the exact
toolchain:

```bash
export PATH="/Users/joshuakettlewell/.elan/bin:$PATH"
elan --version
elan toolchain install leanprover/lean4:v4.32.1
elan toolchain list
```

After a reviewed Phase 3B fixture project contains the proposed
`lean-toolchain` and `lakefile.toml`, acquisition is:

```bash
export PATH="/Users/joshuakettlewell/.elan/bin:$PATH"
lake update
lake exe cache get
lean --version
lake --version
shasum -a 256 lean-toolchain lakefile.toml lake-manifest.json
du -sh .lake /Users/joshuakettlewell/.elan
```

`lake update` and `lake exe cache get` are the networked acquisition step. They
must never run inside a research/checker execution. After acquisition, checker
execution must use the committed lock with networking disabled and must not
invoke any update/cache command.

Before authorization, capture or establish an independent expected SHA-256 for
the versioned elan installer. If no trustworthy upstream checksum is available,
record the observed hash and the exact TLS URL as acquisition evidence, but do
not mislabel it as independent integrity verification.

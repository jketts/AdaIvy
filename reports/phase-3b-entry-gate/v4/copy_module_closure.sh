#!/bin/sh
set -eu

project=/opt/adaivy-phase3b-gate
destination=/runtime/opt/mathlib
queue=/closure/todo
seen=/closure/seen

mkdir -p "$destination/lib/lean" "$destination/source" "$queue" "$seen"
touch "$queue/Mathlib.Data.Nat.Basic"

while :; do
    module=
    for candidate in "$queue"/*; do
        if [ -f "$candidate" ]; then
            module=${candidate##*/}
            break
        fi
    done
    [ -n "$module" ] || break
    rm "$queue/$module"
    [ -f "$seen/$module" ] && continue
    touch "$seen/$module"

    case "$module" in
        Init|Init.*|Lean|Lean.*|Std|Std.*) continue ;;
    esac

    relative=$(printf '%s' "$module" | tr . /)
    package=
    for candidate in "$project/.lake/packages/mathlib" "$project/.lake/packages"/*; do
        if [ -f "$candidate/$relative.lean" ]; then
            package=$candidate
            break
        fi
    done
    if [ -z "$package" ]; then
        printf 'unresolved module: %s\n' "$module" >&2
        exit 31
    fi

    source_file="$package/$relative.lean"
    artifact_root="$package/.lake/build/lib/lean"
    mkdir -p "$destination/source/$(dirname "$relative")" \
             "$destination/lib/lean/$(dirname "$relative")"
    cp "$source_file" "$destination/source/$relative.lean"
    found=0
    for artifact in "$artifact_root/$relative".olean*; do
        if [ -f "$artifact" ]; then
            cp "$artifact" "$destination/lib/lean/$(dirname "$relative")/"
            found=1
        fi
    done
    if [ "$found" -ne 1 ]; then
        printf 'missing compiled artifact: %s\n' "$module" >&2
        exit 32
    fi
    for artifact in "$artifact_root/$relative".ir*; do
        if [ -f "$artifact" ]; then
            cp "$artifact" "$destination/lib/lean/$(dirname "$relative")/"
        fi
    done

    /home/lean/.elan/toolchains/leanprover--lean4---v4.32.1/bin/lean \
        --deps "$source_file" |
    sed -n 's#^.*/lib/lean/\(.*\)\.olean$#\1#p' |
    tr / . |
    while IFS= read -r dependency; do
        [ -n "$dependency" ] || continue
        case "$dependency" in
            [A-Z]*) ;;
            *) continue ;;
        esac
        [ -f "$seen/$dependency" ] || touch "$queue/$dependency"
    done
done

find "$seen" -type f -exec basename {} \; | LC_ALL=C sort > /closure/module-closure.txt
wc -l /closure/module-closure.txt

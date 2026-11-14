#!/usr/bin/env bash
# Start C++ and Java bridge processes (optional). Python core runs separately.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$ROOT/apps/cpp" "$ROOT/apps/java"
if [[ ! -x "$ROOT/apps/cpp/kavosh_cpp_bridge" ]]; then
  g++ -O2 -std=c++17 -o "$ROOT/apps/cpp/kavosh_cpp_bridge" "$ROOT/apps/cpp/kavosh_cpp_bridge.cpp"
fi
if [[ ! -f "$ROOT/apps/java/KavoshJavaBridge.class" ]]; then
  javac -d "$ROOT/apps/java" "$ROOT/apps/java/KavoshJavaBridge.java"
fi
echo "[start] C++ on 9101"
"$ROOT/apps/cpp/kavosh_cpp_bridge" &
echo $! > "$ROOT/apps/cpp/cpp.pid"
echo "[start] Java on 9102"
(cd "$ROOT/apps/java" && java KavoshJavaBridge) &
echo $! > "$ROOT/apps/java/java.pid"
echo "[start] bridges running (Python core is separate: python main.py)"

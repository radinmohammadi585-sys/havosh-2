#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
echo "[build] C++ bridge..."
g++ -O2 -std=c++17 -o "$ROOT/apps/cpp/kavosh_cpp_bridge" "$ROOT/apps/cpp/kavosh_cpp_bridge.cpp"
echo "[build] Java bridge..."
javac -d "$ROOT/apps/java" "$ROOT/apps/java/KavoshJavaBridge.java"
echo "[build] done"

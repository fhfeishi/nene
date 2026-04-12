#!/usr/bin/env bash
# scripts/llm_tts/gen_proto.sh
# 从 .proto 生成 Python gRPC 代码
# 运行方式: bash gen_proto.sh
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROTO_DIR="$SCRIPT_DIR"
OUT_DIR="$SCRIPT_DIR/generated"

mkdir -p "$OUT_DIR"

# 确保依赖已安装
pip install grpcio grpcio-tools --break-system-packages -q

echo "🔧 Generating gRPC Python code from tts.proto..."

python -m grpc_tools.protoc \
    -I "$PROTO_DIR" \
    --python_out="$OUT_DIR" \
    --grpc_python_out="$OUT_DIR" \
    "$PROTO_DIR/tts.proto"

# 修复生成代码中的 import 路径（grpc_tools 生成的是绝对导入，需改为相对）
sed -i 's/^import tts_pb2/from . import tts_pb2/' "$OUT_DIR/tts_pb2_grpc.py" 2>/dev/null || true

# 添加 __init__.py 使其成为包
touch "$OUT_DIR/__init__.py"

echo "✅ Generated files in: $OUT_DIR"
ls -la "$OUT_DIR"
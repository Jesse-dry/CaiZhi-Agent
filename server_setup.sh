#!/bin/bash
# ============================================================
# CaiZhi Agent - 服务器环境一键配置 + PDF转换
# 在服务器上执行: bash server_setup.sh
# ============================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
echo "Working dir: $SCRIPT_DIR"

# ---------- Step 1: 使用 CUDA 12.8 ----------
echo ""
echo "===== [1/6] Setting CUDA 12.8 ====="
export CUDA_HOME=/usr/local/cuda-12.8
export PATH=$CUDA_HOME/bin:$PATH
export LD_LIBRARY_PATH=$CUDA_HOME/lib64:$LD_LIBRARY_PATH
echo "CUDA_HOME=$CUDA_HOME"
$CUDA_HOME/bin/nvcc --version | grep release

# ---------- Step 2: 创建 venv ----------
echo ""
echo "===== [2/6] Creating virtual environment ====="
python3 -m venv .venv
.venv/bin/pip install --upgrade pip -q

# ---------- Step 3: 安装 PyTorch 2.7.0 (CUDA 12.8) ----------
echo ""
echo "===== [3/6] Installing PyTorch 2.7.0 (CUDA 12.8) ====="
.venv/bin/pip install torch torchvision torchaudio \
  --index-url https://download.pytorch.org/whl/cu128

echo ""
echo "Verifying PyTorch CUDA..."
.venv/bin/python3 -c "
import torch
print(f'PyTorch: {torch.__version__}')
print(f'CUDA available: {torch.cuda.is_available()}')
if torch.cuda.is_available():
    print(f'CUDA version: {torch.version.cuda}')
    print(f'GPU: {torch.cuda.get_device_name(0)}')
    print(f'GPU count: {torch.cuda.device_count()}')
"

# ---------- Step 4: 安装项目依赖 (清华镜像) ----------
echo ""
echo "===== [4/6] Installing project dependencies (Tsinghua mirror) ====="
.venv/bin/pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple

.venv/bin/pip install \
  marker-pdf \
  langchain-text-splitters \
  sentence-transformers \
  chromadb \
  langchain \
  langchain-community \
  llama-index \
  anthropic \
  openai \
  networkx \
  streamlit \
  gradio \
  pandas \
  numpy \
  python-docx \
  python-dotenv \
  pydantic \
  tiktoken

echo ""
echo "Checking marker-pdf..."
.venv/bin/pip show marker-pdf | head -3

# ---------- Step 5: 预热 Marker 模型 (走 HF 镜像) ----------
echo ""
echo "===== [5/6] Pre-downloading Marker models (via hf-mirror.com) ====="
export HF_ENDPOINT=https://hf-mirror.com
.venv/bin/python3 -c "
from marker.models import create_model_dict
m = create_model_dict()
print('Marker models loaded successfully!')
print('Models:', list(m.keys()))
"

# ---------- Step 6: 运行 PDF -> Markdown 转换 ----------
echo ""
echo "===== [6/6] Running PDF -> Markdown conversion ====="
export HF_ENDPOINT=https://hf-mirror.com
.venv/bin/python3 -m rag.prepare_chunks --pdf-only

echo ""
echo "===== DONE! ====="
echo "Results in: $SCRIPT_DIR/data/processed/"
ls -la "$SCRIPT_DIR/data/processed/markdown/"*/ 2>/dev/null || echo "(check markdown dir)"
ls -la "$SCRIPT_DIR/data/processed/images/"*/ 2>/dev/null || echo "(check images dir)"

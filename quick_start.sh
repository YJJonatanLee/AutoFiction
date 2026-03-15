#!/bin/bash
set -e

# ── 색상 ──────────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info()    { echo -e "${CYAN}[INFO]${NC}  $1"; }
success() { echo -e "${GREEN}[OK]${NC}    $1"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $1"; }
error()   { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# ── 스크립트 위치로 이동 ───────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo ""
echo -e "${CYAN}╔══════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║   LangGraph Narrative Agent — Quick Start ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════╝${NC}"
echo ""

# ── 1. Python 확인 ────────────────────────────────────────────────────────────
info "Python 버전 확인 중..."
if command -v python3 &>/dev/null; then
    PYTHON=python3
elif command -v python &>/dev/null; then
    PYTHON=python
else
    error "Python이 설치되어 있지 않습니다."
fi

PY_VERSION=$($PYTHON -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PY_MAJOR=$($PYTHON -c "import sys; print(sys.version_info.major)")
PY_MINOR=$($PYTHON -c "import sys; print(sys.version_info.minor)")

if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]; }; then
    error "Python 3.10 이상이 필요합니다. 현재: $PY_VERSION"
fi
success "Python $PY_VERSION"

# ── 2. 가상환경 ───────────────────────────────────────────────────────────────
VENV_DIR=".venv"
if [ ! -d "$VENV_DIR" ]; then
    info "가상환경 생성 중 (.venv)..."
    $PYTHON -m venv "$VENV_DIR"
    success "가상환경 생성 완료"
else
    success "가상환경 이미 존재 (.venv)"
fi

# 가상환경 활성화
source "$VENV_DIR/bin/activate"
PYTHON="$VENV_DIR/bin/python"

# ── 3. 의존성 설치 ────────────────────────────────────────────────────────────
info "의존성 설치 중..."
pip install -q -r requirements.txt
success "의존성 설치 완료"

# ── 4. API 키 확인 ────────────────────────────────────────────────────────────
if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo ""
    warn "ANTHROPIC_API_KEY 환경 변수가 설정되어 있지 않습니다."
    echo -n "  API 키를 입력하세요 (Enter로 건너뜀): "
    read -r INPUT_KEY
    if [ -n "$INPUT_KEY" ]; then
        export ANTHROPIC_API_KEY="$INPUT_KEY"
        success "API 키 설정됨 (현재 세션에만 적용)"
        echo ""
        warn "영구 적용하려면 ~/.zshrc 또는 ~/.bashrc에 아래 줄을 추가하세요:"
        echo "    export ANTHROPIC_API_KEY=\"$INPUT_KEY\""
    else
        error "API 키가 없으면 실행할 수 없습니다."
    fi
else
    success "ANTHROPIC_API_KEY 확인됨"
fi

# ── 5. 실행 옵션 ──────────────────────────────────────────────────────────────
echo ""
echo "생성할 시퀀스 수를 입력하세요."
echo -n "  max-sequences [기본값: 1]: "
read -r MAX_SEQ
MAX_SEQ="${MAX_SEQ:-1}"

echo -n "  start-sequence [기본값: 1]: "
read -r START_SEQ
START_SEQ="${START_SEQ:-1}"

# ── 6. 실행 ───────────────────────────────────────────────────────────────────
echo ""
info "Agent 실행: Sequence $START_SEQ → $((START_SEQ + MAX_SEQ - 1)) 생성"
echo ""

$PYTHON -m agent.main \
    --max-sequences "$MAX_SEQ" \
    --start-sequence "$START_SEQ"

echo ""
success "완료! 생성된 파일을 확인하세요:"
for i in $(seq "$START_SEQ" $((START_SEQ + MAX_SEQ - 1))); do
    SEQ_DIR="Sequence $((i + 1))"
    if [ -d "$SEQ_DIR" ]; then
        echo "    📁 $SEQ_DIR/"
        [ -f "$SEQ_DIR/narrative.md" ]                  && echo "       ├── narrative.md"
        [ -f "$SEQ_DIR/characters_and_factions.yaml" ]  && echo "       ├── characters_and_factions.yaml"
        [ -f "$SEQ_DIR/sequence_trigger.yaml" ]         && echo "       └── sequence_trigger.yaml"
    fi
done
echo ""

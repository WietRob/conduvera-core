#!/bin/bash
# Matrix OS Launcher Script

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}"
echo "╔═══════════════════════════════════════╗"
echo "║                                       ║"
echo "║         MATRIX OS LAUNCHER            ║"
echo "║                                       ║"
echo "╚═══════════════════════════════════════╝"
echo -e "${NC}"

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Check Python version
echo -e "${YELLOW}Checking Python version...${NC}"
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Python 3 is not installed!${NC}"
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
REQUIRED_VERSION="3.10"

if [ "$(printf '%s\n' "$REQUIRED_VERSION" "$PYTHON_VERSION" | sort -V | head -n1)" != "$REQUIRED_VERSION" ]; then
    echo -e "${RED}Python 3.10+ required, found $PYTHON_VERSION${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Python $PYTHON_VERSION${NC}"

# Check if venv exists
if [ ! -d "venv" ]; then
    echo -e "${YELLOW}Creating virtual environment...${NC}"
    python3 -m venv venv
    echo -e "${GREEN}✓ Virtual environment created${NC}"
fi

# Activate venv
echo -e "${YELLOW}Activating virtual environment...${NC}"
source venv/bin/activate

# Install/upgrade dependencies
if [ ! -f "venv/.installed" ] || [ "requirements.txt" -nt "venv/.installed" ]; then
    echo -e "${YELLOW}Installing dependencies...${NC}"
    pip install --upgrade pip -q
    pip install -r requirements.txt -q
    touch venv/.installed
    echo -e "${GREEN}✓ Dependencies installed${NC}"
else
    echo -e "${GREEN}✓ Dependencies up to date${NC}"
fi

# Parse command line arguments
MODE=${1:-textual}

case "$MODE" in
    textual|main|t)
        echo -e "${GREEN}Launching Matrix OS (Textual)...${NC}"
        python3 -m src.core.app
        ;;
    rich|r)
        echo -e "${GREEN}Launching Matrix OS (Rich Demo)...${NC}"
        python3 examples/rich_demo.py
        ;;
    curses|c)
        echo -e "${GREEN}Launching Matrix OS (Curses Demo)...${NC}"
        python3 examples/curses_demo.py
        ;;
    test)
        echo -e "${GREEN}Running tests...${NC}"
        pytest tests/ -v
        ;;
    dev)
        echo -e "${GREEN}Starting development mode with Textual DevTools...${NC}"
        textual run --dev src/core/app.py:MatrixOS
        ;;
    *)
        echo -e "${YELLOW}Usage: $0 [mode]${NC}"
        echo ""
        echo "Modes:"
        echo "  textual, main, t  - Launch main Matrix OS (Textual) [default]"
        echo "  rich, r           - Launch Rich demo"
        echo "  curses, c         - Launch Curses demo"
        echo "  test              - Run tests"
        echo "  dev               - Development mode with DevTools"
        echo ""
        exit 1
        ;;
esac

# Deactivate venv
deactivate

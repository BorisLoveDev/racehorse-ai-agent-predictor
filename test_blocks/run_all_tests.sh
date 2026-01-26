#!/bin/bash
# Run all test blocks in sequence

set -e  # Exit on error

echo "=============================================="
echo "Running All Test Blocks"
echo "=============================================="
echo ""

# Check if venv is activated
if [ -z "$VIRTUAL_ENV" ]; then
    echo "⚠️  Warning: Virtual environment not activated"
    echo "   Attempting to activate venv..."
    if [ -f "venv/bin/activate" ]; then
        source venv/bin/activate
        echo "✅ Virtual environment activated"
    else
        echo "❌ venv not found. Please create it first:"
        echo "   python -m venv venv"
        exit 1
    fi
fi

# Determine Python command
PYTHON_CMD="python"
if ! command -v python &> /dev/null; then
    PYTHON_CMD="python3"
fi

# Step 1
echo ""
echo "=========================================="
echo "STEP 1: Fetching Next Race"
echo "=========================================="
$PYTHON_CMD test_blocks/test_step1_next_race.py
if [ $? -ne 0 ]; then
    echo "❌ Step 1 failed"
    exit 1
fi

# Step 2
echo ""
echo "=========================================="
echo "STEP 2: Getting Race Details"
echo "=========================================="
$PYTHON_CMD test_blocks/test_step2_race_details.py
if [ $? -ne 0 ]; then
    echo "❌ Step 2 failed"
    exit 1
fi

# Step 3
echo ""
echo "=========================================="
echo "STEP 3: Getting Raw Agent Responses"
echo "=========================================="
$PYTHON_CMD test_blocks/test_step3_raw_response.py
if [ $? -ne 0 ]; then
    echo "❌ Step 3 failed"
    exit 1
fi

# Step 4
echo ""
echo "=========================================="
echo "STEP 4: Getting Structured Output"
echo "=========================================="
$PYTHON_CMD test_blocks/test_step4_structured.py
if [ $? -ne 0 ]; then
    echo "❌ Step 4 failed"
    exit 1
fi

echo ""
echo "=============================================="
echo "✅ All Tests Completed Successfully"
echo "=============================================="
echo ""
echo "Output files created in test_blocks/:"
ls -lh test_blocks/*.txt test_blocks/*.json 2>/dev/null || echo "No output files found"

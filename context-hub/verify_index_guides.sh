#!/bin/bash
# Quick verification script for Index Guide feature

echo "Verifying Index Guide implementation..."
echo "======================================"

# Check if the API code compiles
echo -n "1. Checking Rust compilation... "
if cargo check 2>/dev/null; then
    echo "✓ OK"
else
    echo "✗ FAILED"
    exit 1
fi

# Check for the new endpoint in the router
echo -n "2. Checking for /folders/{id}/guide endpoint... "
if grep -q "folders/{id}/guide" src/api/legacy.rs; then
    echo "✓ OK"
else
    echo "✗ FAILED"
    exit 1
fi

# Check for index_guide field in DocumentResponse
echo -n "3. Checking for index_guide in DocumentResponse... "
if grep -q "index_guide: Option<String>" src/api/legacy.rs; then
    echo "✓ OK"
else
    echo "✗ FAILED"
    exit 1
fi

# Check for index_guide field in DocumentSummary
echo -n "4. Checking for index_guide in DocumentSummary... "
if grep -q "pub index_guide: Option<String>," src/api/legacy.rs; then
    echo "✓ OK"
else
    echo "✗ FAILED"
    exit 1
fi

# Check Python side updates
echo -n "5. Checking ChatAgentDriver system prompt update... "
if grep -q "Index Guides" ../core/lightning_core/vextir_os/core_drivers.py; then
    echo "✓ OK"
else
    echo "✗ FAILED"
    exit 1
fi

# Check for index guide handling in search function
echo -n "6. Checking search function handles index guides... "
if grep -q "index_guides = set()" ../core/lightning_core/vextir_os/core_drivers.py; then
    echo "✓ OK"
else
    echo "✗ FAILED"
    exit 1
fi

echo ""
echo "======================================"
echo "✅ All checks passed!"
echo ""
echo "To run functional tests:"
echo "  1. Start Context Hub: cargo run"
echo "  2. Run API test: python test_index_guides.py"
echo "  3. Run ChatAgent test: cd ../core && python test_chat_with_index_guides.py"
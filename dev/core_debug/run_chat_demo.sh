#!/bin/bash
# Run Vextir OS Chat Demo

echo "Starting Vextir OS Chat Demo..."
echo "=============================="

# Kill any existing Python processes from previous runs
pkill -f "python run_vextir_os.py" 2>/dev/null

# Start Vextir OS in background
echo "1. Starting Vextir OS event processor..."
python run_vextir_os.py > vextir_os.log 2>&1 &
VEXTIR_PID=$!

# Wait for OS to initialize
sleep 3

# Check if Vextir OS is running
if ! ps -p $VEXTIR_PID > /dev/null; then
    echo "Error: Vextir OS failed to start. Check vextir_os.log"
    exit 1
fi

echo "   ✓ Vextir OS running (PID: $VEXTIR_PID)"
echo ""

# Run the chat test
echo "2. Sending chat event through event bus..."
python test_event_chat.py

echo ""
echo "3. Checking Vextir OS logs..."
tail -n 20 vextir_os.log

# Cleanup
echo ""
echo "4. Stopping Vextir OS..."
kill $VEXTIR_PID 2>/dev/null
wait $VEXTIR_PID 2>/dev/null

echo "✓ Demo complete"
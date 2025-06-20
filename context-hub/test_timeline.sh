#!/bin/bash

# Test script for timeline API

echo "Testing Timeline API"
echo "==================="

# Base URL
BASE_URL="http://localhost:3000/timeline"

# Test 1: Get timeline info
echo -e "\n1. Getting timeline info..."
curl -s "$BASE_URL/info" | jq .

# Test 2: Get timeline changes
echo -e "\n2. Getting timeline changes..."
curl -s "$BASE_URL/changes" | jq .

# Test 3: Get state at current time
echo -e "\n3. Getting state at current timestamp..."
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
curl -s "$BASE_URL/state?timestamp=$TIMESTAMP" | jq .

# Test 4: Get state at past timestamp (1 hour ago)
echo -e "\n4. Getting state at 1 hour ago..."
PAST_TIMESTAMP=$(date -u -d "1 hour ago" +"%Y-%m-%dT%H:%M:%SZ")
curl -s "$BASE_URL/state?timestamp=$PAST_TIMESTAMP" | jq .

# Test 5: Test WebSocket connection
echo -e "\n5. Testing WebSocket connection..."
echo "Run this command to test WebSocket:"
echo "wscat -c ws://localhost:3000/timeline/stream"
echo "Then send: {\"type\":\"scrub_position\",\"timestamp\":\"$(date -u +"%Y-%m-%dT%H:%M:%SZ")\"}"

echo -e "\nDone!"
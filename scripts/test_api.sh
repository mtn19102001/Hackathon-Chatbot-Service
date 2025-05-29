#!/bin/bash

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color
BLUE='\033[0;34m'

# Function to print section headers
print_header() {
    echo -e "\n${BLUE}=== $1 ===${NC}\n"
}

# Function to test an endpoint and check response
test_endpoint() {
    local description=$1
    local command=$2
    local expected_pattern=$3
    
    echo -e "${BLUE}Testing: ${description}${NC}"
    echo "Command: $command"
    
    response=$(eval $command)
    echo "Response: $response"
    
    if echo "$response" | grep -q "$expected_pattern"; then
        echo -e "${GREEN}✓ Test passed${NC}"
    else
        echo -e "${RED}✗ Test failed${NC}"
        echo "Expected pattern: $expected_pattern"
    fi
    echo "----------------------------------------"
}

# Test Database Connection
print_header "Testing Database Connection"
test_endpoint "Database Tables" \
    "docker-compose exec -T db psql -U postgres -d chatbot -c '\dt'" \
    "chat_history"

# Test Context Service
print_header "Testing Context Service"
test_endpoint "Create Context" \
    "curl -s -X POST http://localhost:8001/context/test_user -H 'Content-Type: application/json' -d '{\"user_id\": \"test_user\", \"preferences\": {\"language\": \"en\", \"style\": \"friendly\"}}'" \
    "success"

test_endpoint "Get Context" \
    "curl -s http://localhost:8001/context/test_user" \
    "test_user"

# Test Chatbot Service
print_header "Testing Chatbot Service"
test_endpoint "Send Message" \
    "curl -s -X POST http://localhost:8000/ask -H 'Content-Type: application/json' -d '{\"userId\": \"test_user\", \"question\": \"Hello! How are you?\"}'" \
    "answer"

# Test Chat History
print_header "Testing Chat History"
test_endpoint "Get Chat History" \
    "curl -s http://localhost:8000/history/test_user" \
    "question" 
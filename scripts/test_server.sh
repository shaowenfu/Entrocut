#!/bin/bash
#
# Server 端 API 验证脚本
# 用于 Round 2 联调验证
#

set -e

# 本地联调时避免走代理
export NO_PROXY="${NO_PROXY:-127.0.0.1,localhost}"

# 配置
SERVER_HOST="${SERVER_HOST:-localhost}"
SERVER_PORT="${SERVER_PORT:-8001}"
BASE_URL="http://${SERVER_HOST}:${SERVER_PORT}"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 测试结果统计
PASSED=0
FAILED=0

# 打印函数
print_header() {
    echo -e "\n${YELLOW}=== $1 ===${NC}"
}

print_test() {
    echo -e "\n${GREEN}TEST:${NC} $1"
}

print_pass() {
    echo -e "${GREEN}✓ PASS:${NC} $1"
    PASSED=$((PASSED + 1))
}

print_fail() {
    echo -e "${RED}✗ FAIL:${NC} $1"
    FAILED=$((FAILED + 1))
}

# ============================================
# 测试函数
# ============================================

test_health() {
    print_test "Health Check"
    response=$(curl -s -w "\n%{http_code}" "${BASE_URL}/health")
    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | head -n-1)

    if [ "$http_code" = "200" ]; then
        status=$(echo "$body" | grep -o '"status":"[^"]*"' | cut -d'"' -f4)
        if [ "$status" = "healthy" ]; then
            print_pass "Health check returned 200 OK with status=healthy"
            return 0
        fi
    fi
    print_fail "Health check failed (HTTP $http_code)"
    echo "Response: $body"
    return 1
}

test_mock_analyze() {
    print_test "Mock Analyze API"

    request='{
        "job_id": "test-job-001",
        "contract_version": "0.1.0-mock",
        "video_path": "/home/sherwen/MyProjects/Entrocut/屏幕录制.mp4",
        "frames": [
            {"timestamp": 1.0, "frame_number": 30, "file_path": "/path/to/frame_001.jpg"},
            {"timestamp": 2.0, "frame_number": 60, "file_path": "/path/to/frame_002.jpg"}
        ]
    }'

    response=$(curl -s -w "\n%{http_code}" \
        -X POST \
        -H "Content-Type: application/json" \
        -H "X-Request-ID: test-req-001" \
        -d "$request" \
        "${BASE_URL}/api/v1/mock/analyze")

    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | head -n-1)

    if [ "$http_code" = "200" ]; then
        job_id=$(echo "$body" | grep -o '"job_id":"[^"]*"' | cut -d'"' -f4)
        if [ "$job_id" = "test-job-001" ]; then
            print_pass "Analyze API returned correct job_id"
            return 0
        fi
    fi
    print_fail "Analyze API failed (HTTP $http_code)"
    echo "Response: $body"
    return 1
}

test_mock_edl_with_video_path() {
    print_test "Mock EDL API with video_path"

    request='{
        "job_id": "test-job-002",
        "contract_version": "0.1.0-mock",
        "video_path": "/home/sherwen/MyProjects/Entrocut/屏幕录制.mp4",
        "segments": [
            {"segment_id": "seg_001", "start_time": 0.0, "end_time": 3.2},
            {"segment_id": "seg_002", "start_time": 3.2, "end_time": 7.0}
        ],
        "rule": "highlight_first"
    }'

    response=$(curl -s -w "\n%{http_code}" \
        -X POST \
        -H "Content-Type: application/json" \
        -H "X-Request-ID: test-req-002" \
        -d "$request" \
        "${BASE_URL}/api/v1/mock/edl")

    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | head -n-1)

    if [ "$http_code" = "200" ]; then
        # 验证 clips[].src 等于请求中的 video_path
        src=$(echo "$body" | grep -o '"src":"/home/sherwen/MyProjects/Entrocut/屏幕录制.mp4"' | wc -l)
        if [ "$src" -gt 0 ]; then
            print_pass "EDL API returns real video_path as clips[].src"
            return 0
        fi
    fi
    print_fail "EDL API failed or clips[].src not correct (HTTP $http_code)"
    echo "Response: $body"
    return 1
}

test_mock_edl_validation_error() {
    print_test "Mock EDL API validation (empty segments)"

    request='{
        "job_id": "test-job-003",
        "contract_version": "0.1.0-mock",
        "segments": [],
        "rule": "highlight_first"
    }'

    response=$(curl -s -w "\n%{http_code}" \
        -X POST \
        -H "Content-Type: application/json" \
        -d "$request" \
        "${BASE_URL}/api/v1/mock/edl")

    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | head -n-1)

    if [ "$http_code" = "400" ]; then
        error_code=$(echo "$body" | grep -o '"code":"[^"]*"' | cut -d'"' -f4)
        if [ "$error_code" = "VAL_EMPTY_INPUT" ]; then
            print_pass "EDL API returns 400 validation error for empty segments"
            return 0
        fi
    fi
    print_fail "EDL API validation failed (HTTP $http_code)"
    echo "Response: $body"
    return 1
}

test_request_id_tracking() {
    print_test "Request ID tracking"

    request='{
        "job_id": "test-job-004",
        "contract_version": "0.1.0-mock",
        "video_path": "/test/video.mp4",
        "segments": [
            {"segment_id": "seg_001", "start_time": 0.0, "end_time": 10.0}
        ],
        "rule": "highlight_first"
    }'

    # 从响应头获取 X-Request-ID（使用 -i 包含 headers）
    response_with_headers=$(curl -s -i \
        -X POST \
        -H "Content-Type: application/json" \
        -H "X-Request-ID: round2-test-tracking" \
        -d "$request" \
        "${BASE_URL}/api/v1/mock/edl")

    if echo "$response_with_headers" | grep -i -q "^x-request-id: round2-test-tracking"; then
        print_pass "Request ID tracked in response header"
        return 0
    fi

    print_fail "Request ID not found in response header"
    return 1
}

# ============================================
# 主流程
# ============================================

main() {
    print_header "Entrocut Server API 验证 (Round 2)"
    echo "Server URL: $BASE_URL"

    # 检查服务是否运行
    print_test "Checking if server is running..."
    if ! curl -s -f "${BASE_URL}/health" > /dev/null 2>&1; then
        print_fail "Server is not running at $BASE_URL"
        echo "Please start the server first:"
        echo "  cd server && python3 -m uvicorn main:app --host 0.0.0.0 --port 8001"
        exit 1
    fi
    print_pass "Server is running"

    # 运行测试
    test_health
    test_mock_analyze
    test_mock_edl_with_video_path
    test_mock_edl_validation_error
    test_request_id_tracking

    # 打印总结
    print_header "测试总结"
    echo -e "${GREEN}通过: $PASSED${NC}"
    echo -e "${RED}失败: $FAILED${NC}"
    echo -e "总计: $((PASSED + FAILED))"

    if [ $FAILED -eq 0 ]; then
        echo -e "\n${GREEN}所有测试通过！${NC}"
        exit 0
    else
        echo -e "\n${RED}有测试失败，请检查${NC}"
        exit 1
    fi
}

# 运行主流程
main

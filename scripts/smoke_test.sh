#!/bin/bash
#
# Server 冒烟测试脚本
#
# 用途：快速验证 Server 服务是否可用
# 用法：./scripts/smoke_test.sh [BASE_URL]
#       默认 BASE_URL=http://localhost:8001
#

set -euo pipefail

# ============================================
# 配置
# ============================================

BASE_URL="${1:-http://localhost:8001}"
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
REQUEST_ID="smoke-test-$(date +%s)"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 测试计数
PASSED=0
FAILED=0

# ============================================
# 工具函数
# ============================================

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 执行测试并检查结果
# 参数: $1=测试名称, $2=curl命令
run_test() {
    local test_name="$1"
    local curl_cmd="$2"
    local expected_code="${3:-200}"
    local response
    local http_code

    echo ""
    log_info "测试: $test_name"

    response=$(eval "$curl_cmd" 2>&1)
    http_code=$(echo "$response" | grep -oP "HTTP_CODE:\K\d+" || echo "000")

    if [ "$http_code" = "$expected_code" ]; then
        log_info "  ✓ 通过 (HTTP $http_code)"
        PASSED=$((PASSED + 1))
        return 0
    else
        log_error "  ✗ 失败 (期望 $expected_code, 实际 $http_code)"
        echo "$response"
        FAILED=$((FAILED + 1))
        return 1
    fi
}

# ============================================
# 测试用例
# ============================================

test_health_check() {
    run_test "健康检查" \
        "curl -s -o /dev/null -w 'HTTP_CODE:%{http_code}' '$BASE_URL/health'"
}

test_root_endpoint() {
    run_test "根路径" \
        "curl -s -o /dev/null -w 'HTTP_CODE:%{http_code}' '$BASE_URL/'"
}

test_mock_analyze_success() {
    run_test "Mock Analyze - 成功场景" \
        "curl -s -o /dev/null -w 'HTTP_CODE:%{http_code}' -X POST \
            -H 'Content-Type: application/json' \
            -H 'X-Request-ID: $REQUEST_ID' \
            -d '{
                \"job_id\": \"550e8400-e29b-41d4-a716-446655440000\",
                \"contract_version\": \"0.1.0-mock\",
                \"video_path\": \"/test/path/video.mp4\",
                \"frames\": [
                    {\"timestamp\": 1.0, \"frame_number\": 30, \"file_path\": \"/test/frame1.jpg\"},
                    {\"timestamp\": 2.0, \"frame_number\": 60, \"file_path\": \"/test/frame2.jpg\"}
                ]
            }' \
            '$BASE_URL/api/v1/mock/analyze'"
}

test_mock_analyze_invalid_contract_version() {
    run_test "Mock Analyze - 无效 contract_version (应返回 400)" \
        "curl -s -o /dev/null -w 'HTTP_CODE:%{http_code}' -X POST \
            -H 'Content-Type: application/json' \
            -d '{
                \"job_id\": \"not-a-uuid\",
                \"contract_version\": \"invalid-contract-version\",
                \"video_path\": \"/test/path/video.mp4\",
                \"frames\": [
                    {\"timestamp\": 1.0, \"frame_number\": 30, \"file_path\": \"/test/frame1.jpg\"}
                ]
            }' \
            '$BASE_URL/api/v1/mock/analyze'" \
        "400"
}

test_mock_analyze_empty_video_path() {
    run_test "Mock Analyze - 空 video_path (应返回 400)" \
        "curl -s -o /dev/null -w 'HTTP_CODE:%{http_code}' -X POST \
            -H 'Content-Type: application/json' \
            -d '{
                \"job_id\": \"550e8400-e29b-41d4-a716-446655440000\",
                \"contract_version\": \"0.1.0-mock\",
                \"video_path\": \"\",
                \"frames\": [
                    {\"timestamp\": 1.0, \"frame_number\": 30, \"file_path\": \"/test/frame1.jpg\"}
                ]
            }' \
            '$BASE_URL/api/v1/mock/analyze'" \
        "400"
}

test_mock_edl_success() {
    run_test "Mock EDL - 成功场景" \
        "curl -s -o /dev/null -w 'HTTP_CODE:%{http_code}' -X POST \
            -H 'Content-Type: application/json' \
            -d '{
                \"job_id\": \"550e8400-e29b-41d4-a716-446655440000\",
                \"contract_version\": \"0.1.0-mock\",
                \"video_path\": \"/test/path/video.mp4\",
                \"segments\": [
                    {\"segment_id\": \"seg_001\", \"start_time\": 0.0, \"end_time\": 5.0},
                    {\"segment_id\": \"seg_002\", \"start_time\": 5.0, \"end_time\": 10.0}
                ],
                \"rule\": \"highlight_first\"
            }' \
            '$BASE_URL/api/v1/mock/edl'"
}

test_mock_edl_invalid_time_range() {
    run_test "Mock EDL - 无效时间范围 (应返回 400)" \
        "curl -s -o /dev/null -w 'HTTP_CODE:%{http_code}' -X POST \
            -H 'Content-Type: application/json' \
            -d '{
                \"job_id\": \"550e8400-e29b-41d4-a716-446655440000\",
                \"contract_version\": \"0.1.0-mock\",
                \"segments\": [
                    {\"segment_id\": \"seg_001\", \"start_time\": 10.0, \"end_time\": 5.0}
                ]
            }' \
            '$BASE_URL/api/v1/mock/edl'" \
        "400"
}

test_request_id_tracking() {
    local test_id="req-track-$(date +%s)"
    response=$(curl -s -X POST \
        -H 'Content-Type: application/json' \
        -H "X-Request-ID: $test_id" \
        -d '{
            "job_id": "550e8400-e29b-41d4-a716-446655440000",
            "contract_version": "0.1.0-mock",
            "video_path": "/test/video.mp4",
            "frames": [{"timestamp": 1.0, "frame_number": 30, "file_path": "/test/f.jpg"}]
        }' \
        "$BASE_URL/api/v1/mock/analyze")

    if echo "$response" | grep -q "$test_id"; then
        log_info "测试: Request ID 追踪"
        log_info "  ✓ 通过 (request_id: $test_id)"
        PASSED=$((PASSED + 1))
    else
        log_error "测试: Request ID 追踪"
        log_error "  ✗ 失败 (未找到 request_id: $test_id)"
        echo "$response"
        FAILED=$((FAILED + 1))
    fi
}

# ============================================
# 主流程
# ============================================

main() {
    echo "=========================================="
    echo "Server 冒烟测试"
    echo "目标: $BASE_URL"
    echo "时间: $TIMESTAMP"
    echo "=========================================="

    # 检查服务是否可访问
    log_info "检查服务可达性..."
    if ! curl -s -f "$BASE_URL/health" > /dev/null 2>&1; then
        log_error "服务不可访问: $BASE_URL"
        log_error "请确认："
        log_error "  1. 服务已启动"
        log_error "  2. BASE_URL 正确"
        exit 1
    fi
    log_info "服务可达 ✓"

    # 运行测试
    test_health_check
    test_root_endpoint
    test_mock_analyze_success
    test_mock_analyze_invalid_contract_version
    test_mock_analyze_empty_video_path
    test_mock_edl_success
    test_mock_edl_invalid_time_range
    test_request_id_tracking

    # 输出结果
    echo ""
    echo "=========================================="
    echo "测试结果"
    echo "=========================================="
    echo "通过: $PASSED"
    echo "失败: $FAILED"
    echo "总计: $((PASSED + FAILED))"
    echo "=========================================="

    if [ $FAILED -eq 0 ]; then
        log_info "所有测试通过! ✓"
        exit 0
    else
        log_error "$FAILED 个测试失败"
        exit 1
    fi
}

# 执行主流程
main

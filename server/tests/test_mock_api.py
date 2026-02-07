"""
Mock API 测试

验证 Mock API 的基本功能
"""

import pytest
from fastapi.testclient import TestClient
from main import app
from models.schemas import CONTRACT_VERSION


# ============================================
# Fixtures
# ============================================

client = TestClient(app)


def get_valid_analyze_request():
    """获取有效的分析请求"""
    return {
        "job_id": "test-job-001",
        "contract_version": CONTRACT_VERSION,
        "video_path": "/local/path/to/test.mp4",
        "frames": [
            {
                "timestamp": 1.0,
                "frame_number": 30,
                "file_path": "/local/path/to/frame_001.jpg"
            },
            {
                "timestamp": 2.0,
                "frame_number": 60,
                "file_path": "/local/path/to/frame_002.jpg"
            }
        ]
    }


def get_valid_edl_request():
    """获取有效的 EDL 请求"""
    return {
        "job_id": "test-job-001",
        "contract_version": CONTRACT_VERSION,
        "segments": [
            {
                "segment_id": "seg_001",
                "start_time": 0.0,
                "end_time": 10.0
            },
            {
                "segment_id": "seg_002",
                "start_time": 10.0,
                "end_time": 20.0
            }
        ],
        "rule": "highlight_first"
    }


# ============================================
# Health Check Tests
# ============================================

def test_health_check():
    """测试健康检查"""
    response = client.get("/health")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "entrocut-mock-server"
    assert "version" in data
    assert "timestamp" in data


# ============================================
# Mock Analyze API Tests
# ============================================

def test_mock_analyze_success():
    """测试 Mock 分析接口 - 成功场景"""
    request_data = get_valid_analyze_request()
    response = client.post("/api/v1/mock/analyze", json=request_data)

    assert response.status_code == 200

    data = response.json()
    assert data["contract_version"] == CONTRACT_VERSION
    assert data["job_id"] == "test-job-001"
    assert "request_id" in data
    assert "analysis" in data
    assert "segments" in data["analysis"]


def test_mock_analyze_missing_job_id():
    """测试 Mock 分析接口 - 缺少 job_id"""
    request_data = get_valid_analyze_request()
    del request_data["job_id"]

    response = client.post("/api/v1/mock/analyze", json=request_data)

    assert response.status_code == 400

    data = response.json()
    assert "error" in data
    assert data["error"]["type"] == "validation_error"


def test_mock_analyze_empty_frames():
    """测试 Mock 分析接口 - 空帧列表"""
    request_data = {
        "job_id": "test-job-001",
        "contract_version": CONTRACT_VERSION,
        "video_path": "/local/path/to/test.mp4",
        "frames": []
    }

    response = client.post("/api/v1/mock/analyze", json=request_data)

    assert response.status_code == 400

    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "VAL_EMPTY_INPUT"


def test_mock_analyze_invalid_contract_version():
    """测试 Mock 分析接口 - 不支持的契约版本"""
    request_data = get_valid_analyze_request()
    request_data["contract_version"] = "9.9.9-invalid"

    response = client.post("/api/v1/mock/analyze", json=request_data)

    assert response.status_code == 400

    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "VAL_CONTRACT_VERSION_MISMATCH"


# ============================================
# Mock EDL API Tests
# ============================================

def test_mock_edl_success():
    """测试 Mock EDL 接口 - 成功场景"""
    request_data = get_valid_edl_request()
    response = client.post("/api/v1/mock/edl", json=request_data)

    assert response.status_code == 200

    data = response.json()
    assert data["contract_version"] == CONTRACT_VERSION
    assert data["job_id"] == "test-job-001"
    assert "request_id" in data
    assert "edl" in data
    assert "clips" in data["edl"]
    assert data["edl"]["output_name"] == "final.mp4"


def test_mock_edl_empty_segments():
    """测试 Mock EDL 接口 - 空片段列表"""
    request_data = {
        "job_id": "test-job-001",
        "contract_version": CONTRACT_VERSION,
        "segments": [],
        "rule": "highlight_first"
    }

    response = client.post("/api/v1/mock/edl", json=request_data)

    assert response.status_code == 400

    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "VAL_EMPTY_INPUT"


def test_mock_edl_different_rule():
    """测试 Mock EDL 接口 - 不同规则"""
    request_data = get_valid_edl_request()
    request_data["rule"] = "all_segments"

    response = client.post("/api/v1/mock/edl", json=request_data)

    assert response.status_code == 200

    data = response.json()
    assert data["edl"]["output_name"] == "final.mp4"


# ============================================
# Request ID Tracking Tests
# ============================================

def test_request_id_tracked():
    """测试请求 ID 追踪"""
    request_data = get_valid_analyze_request()
    response = client.post(
        "/api/v1/mock/analyze",
        json=request_data,
        headers={"X-Request-ID": "test-request-123"}
    )

    assert response.status_code == 200
    assert "X-Request-ID" in response.headers
    assert response.headers["X-Request-ID"] == "test-request-123"


def test_request_id_generated():
    """测试自动生成请求 ID"""
    request_data = get_valid_analyze_request()
    response = client.post("/api/v1/mock/analyze", json=request_data)

    assert response.status_code == 200
    assert "X-Request-ID" in response.headers
    # 自动生成的应该是 UUID 格式
    request_id = response.headers["X-Request-ID"]
    assert len(request_id) == 36  # UUID v4 长度


# ============================================
# Root Endpoint Tests
# ============================================

def test_root_endpoint():
    """测试根路径"""
    response = client.get("/")

    assert response.status_code == 200

    data = response.json()
    assert "service" in data
    assert "version" in data
    assert "docs" in data
    assert "health" in data
    assert "mock_api" in data

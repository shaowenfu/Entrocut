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


# ============================================
# Round 2 新增测试
# ============================================

def test_mock_edl_with_video_path():
    """测试 Mock EDL 接口 - 提供真实 video_path"""
    real_video_path = "/home/sherwen/MyProjects/Entrocut/屏幕录制.mp4"
    request_data = {
        "job_id": "test-job-002",
        "contract_version": CONTRACT_VERSION,
        "video_path": real_video_path,
        "segments": [
            {
                "segment_id": "seg_001",
                "start_time": 0.0,
                "end_time": 3.2
            },
            {
                "segment_id": "seg_002",
                "start_time": 3.2,
                "end_time": 7.0
            }
        ],
        "rule": "highlight_first"
    }

    response = client.post("/api/v1/mock/edl", json=request_data)

    assert response.status_code == 200

    data = response.json()
    assert data["edl"]["clips"][0]["src"] == real_video_path
    assert data["edl"]["clips"][1]["src"] == real_video_path


def test_mock_edl_without_video_path_uses_fallback():
    """测试 Mock EDL 接口 - 未提供 video_path 使用回退路径"""
    request_data = {
        "job_id": "test-job-fallback",
        "contract_version": CONTRACT_VERSION,
        "segments": [
            {
                "segment_id": "seg_001",
                "start_time": 0.0,
                "end_time": 10.0
            }
        ],
        "rule": "highlight_first"
    }

    response = client.post("/api/v1/mock/edl", json=request_data)

    assert response.status_code == 200

    data = response.json()
    # 应使用回退路径 /local/path/to/{job_id}.mp4
    expected_fallback = "/local/path/to/test-job-fallback.mp4"
    assert data["edl"]["clips"][0]["src"] == expected_fallback


def test_mock_edl_clips_time_validation():
    """测试 Mock EDL 接口 - clips 时间范围正确性"""
    request_data = {
        "job_id": "test-job-time",
        "contract_version": CONTRACT_VERSION,
        "video_path": "/test/path/video.mp4",
        "segments": [
            {
                "segment_id": "seg_001",
                "start_time": 1.0,
                "end_time": 5.0
            },
            {
                "segment_id": "seg_002",
                "start_time": 6.0,
                "end_time": 10.0
            }
        ],
        "rule": "highlight_first"
    }

    response = client.post("/api/v1/mock/edl", json=request_data)

    assert response.status_code == 200

    data = response.json()
    clips = data["edl"]["clips"]

    # 验证每个 clip 的 end > start
    for clip in clips:
        assert clip["end"] > clip["start"], f"Clip {clip['clip_id']} has invalid time range"

    # 验证 src 等于请求中的 video_path
    for clip in clips:
        assert clip["src"] == "/test/path/video.mp4"


def test_request_id_in_response_body():
    """测试 request_id 在响应体中正确返回"""
    request_data = get_valid_edl_request()
    response = client.post(
        "/api/v1/mock/edl",
        json=request_data,
        headers={"X-Request-ID": "round2-test-123"}
    )

    assert response.status_code == 200

    data = response.json()
    # 响应体中应包含 request_id
    assert "request_id" in data
    # 响应头中应透传 request_id
    assert response.headers["X-Request-ID"] == "round2-test-123"


def test_job_id_tracking_in_analyze():
    """测试 job_id 在 analyze 接口中的追踪"""
    request_data = get_valid_analyze_request()
    response = client.post("/api/v1/mock/analyze", json=request_data)

    assert response.status_code == 200
    data = response.json()
    assert data["job_id"] == "test-job-001"


def test_job_id_tracking_in_edl():
    """测试 job_id 在 edl 接口中的追踪"""
    request_data = get_valid_edl_request()
    response = client.post("/api/v1/mock/edl", json=request_data)

    assert response.status_code == 200
    data = response.json()
    assert data["job_id"] == "test-job-001"


def test_mock_edl_round2_sample_data():
    """
    测试 Mock EDL 接口 - Round 2 演示用样例数据

    根据 round2.md 的约定：
    - Analyze segments 建议返回 3 段：0.0-3.2, 3.2-7.0, 7.0-10.8
    - EDL clips 建议返回 2-3 段
    - output_name 固定 final.mp4
    """
    sample_video_path = "/home/sherwen/MyProjects/Entrocut/屏幕录制.mp4"
    request_data = {
        "job_id": "round2-sample-job",
        "contract_version": CONTRACT_VERSION,
        "video_path": sample_video_path,
        "segments": [
            {
                "segment_id": "seg_001",
                "start_time": 0.0,
                "end_time": 3.2
            },
            {
                "segment_id": "seg_002",
                "start_time": 3.2,
                "end_time": 7.0
            },
            {
                "segment_id": "seg_003",
                "start_time": 7.0,
                "end_time": 10.8
            }
        ],
        "rule": "highlight_first"
    }

    response = client.post("/api/v1/mock/edl", json=request_data)

    assert response.status_code == 200

    data = response.json()
    # 验证 output_name
    assert data["edl"]["output_name"] == "final.mp4"

    # 验证 clips 数量（highlight_first 规则返回前 3 个）
    clips = data["edl"]["clips"]
    assert len(clips) == 3

    # 验证所有 clips 使用真实 video_path
    for clip in clips:
        assert clip["src"] == sample_video_path

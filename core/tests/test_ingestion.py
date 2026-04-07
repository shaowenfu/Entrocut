import base64
import io
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from ingestion import (
    detect_scenes,
    extract_and_stitch_frames,
    stitch_frames_to_base64,
)

def test_stitch_frames_to_base64():
    # Create 4 dummy JPEG images in memory
    frame_bytes_list = []
    for color in ["red", "green", "blue", "yellow"]:
        img = Image.new("RGB", (320, 240), color=color)
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        frame_bytes_list.append(buf.getvalue())
        
    b64_str = stitch_frames_to_base64(frame_bytes_list)
    assert b64_str
    assert isinstance(b64_str, str)
    
    # Verify it can be decoded back to a valid JPEG
    decoded_bytes = base64.b64decode(b64_str)
    stitched_img = Image.open(io.BytesIO(decoded_bytes))
    assert stitched_img.size == (640, 480)

@patch("ingestion.detect")
def test_detect_scenes(mock_detect):
    # Mock scenedetect output
    mock_scene_1 = (MagicMock(), MagicMock())
    mock_scene_1[0].get_seconds.return_value = 0.0
    mock_scene_1[1].get_seconds.return_value = 5.5
    
    mock_scene_2 = (MagicMock(), MagicMock())
    mock_scene_2[0].get_seconds.return_value = 5.5
    mock_scene_2[1].get_seconds.return_value = 10.0
    
    mock_detect.return_value = [mock_scene_1, mock_scene_2]
    
    scenes = detect_scenes("dummy.mp4")
    assert len(scenes) == 2
    assert scenes[0] == (0, 5500)
    assert scenes[1] == (5500, 10000)

@patch("ingestion.ffmpeg")
def test_extract_and_stitch_frames(mock_ffmpeg):
    # Mock ffmpeg extract frame
    mock_run = MagicMock()
    # Provide a dummy valid JPEG for ffmpeg mock output
    img = Image.new("RGB", (320, 240), color="white")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    dummy_jpeg = buf.getvalue()
    
    mock_run.run.return_value = (dummy_jpeg, b"")
    mock_output = MagicMock()
    mock_output.output.return_value = mock_run
    mock_filter = MagicMock()
    mock_filter.filter.return_value = mock_output
    mock_input = MagicMock()
    mock_input.input.return_value = mock_filter
    
    mock_ffmpeg.input = mock_input.input
    
    b64_str = extract_and_stitch_frames("dummy.mp4", 0, 10000)
    assert b64_str
    assert isinstance(b64_str, str)
    
    # Verify ffmpeg was called 4 times
    assert mock_input.input.call_count == 4
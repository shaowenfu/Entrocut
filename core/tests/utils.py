"""测试工具函数。"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path


def create_temp_dir(prefix: str = "entrocut_test_") -> Path:
    return Path(tempfile.mkdtemp(prefix=prefix)).resolve()


def create_sample_video(output_path: Path) -> Path:
    """
    生成一个 2 秒测试视频：
    - 第 1 秒黑色
    - 第 2 秒白色
    用于验证 scene cut、抽帧与渲染。
    """
    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        "color=c=black:s=320x240:d=1:r=24",
        "-f",
        "lavfi",
        "-i",
        "color=c=white:s=320x240:d=1:r=24",
        "-filter_complex",
        "[0:v][1:v]concat=n=2:v=1:a=0",
        "-pix_fmt",
        "yuv420p",
        str(output_path),
    ]
    subprocess.run(command, check=True, capture_output=True, text=True)
    return output_path

import base64
import io
import logging
from pathlib import Path
from typing import Any

import ffmpeg
from scenedetect import ContentDetector, detect

logger = logging.getLogger(__name__)

def detect_scenes(video_path: str | Path) -> list[tuple[int, int]]:
    """
    Detect scenes in a video using content-aware detection.
    Returns a list of (start_ms, end_ms).
    """
    path_str = str(video_path)
    logger.info(f"Detecting scenes for {path_str}")
    scene_list = detect(path_str, ContentDetector())
    
    result = []
    for scene in scene_list:
        start_ms = int(scene[0].get_seconds() * 1000)
        end_ms = int(scene[1].get_seconds() * 1000)
        result.append((start_ms, end_ms))
        
    # If no scenes were detected (e.g. single continuous shot), return the whole video as one scene
    if not result:
        # We need the video duration to return one single scene. 
        # For MVP, we can fallback to extracting duration via ffmpeg or returning a default
        import ffmpeg
        try:
            probe = ffmpeg.probe(path_str)
            duration_sec = float(probe['format']['duration'])
            result = [(0, int(duration_sec * 1000))]
        except Exception as e:
            logger.warning(f"Failed to probe duration for fallback scene detection: {e}")
            result = [(0, 0)]
            
    return result

def extract_frame_at(video_path: str | Path, time_ms: float, width: int = 320, height: int = 240) -> bytes:
    """
    Extract a single frame from the video at the given timestamp in milliseconds.
    """
    try:
        out, _ = (
            ffmpeg
            .input(str(video_path), ss=time_ms / 1000.0)
            .filter('scale', width, height)
            .output('pipe:', vframes=1, format='image2', vcodec='mjpeg')
            .run(capture_stdout=True, capture_stderr=True, quiet=True)
        )
        return out
    except ffmpeg.Error as e:
        logger.error(f"FFmpeg frame extraction failed: {e.stderr.decode('utf8', errors='ignore')}")
        raise RuntimeError("Failed to extract frame") from e

def stitch_frames_to_base64(frame_bytes_list: list[bytes]) -> str:
    """
    Stitch 4 frames into a 2x2 grid, add index numbers, and return as base64 string.
    """
    from PIL import Image, ImageDraw, ImageFont
    
    if len(frame_bytes_list) != 4:
        raise ValueError("Exactly 4 frames are required for stitching")
        
    images = []
    for fb in frame_bytes_list:
        try:
            img = Image.open(io.BytesIO(fb)).convert('RGB')
            images.append(img)
        except Exception as e:
            logger.warning(f"Failed to open frame bytes: {e}. Using empty image.")
            images.append(Image.new('RGB', (320, 240), color='black'))
            
    width, height = images[0].size
    stitched = Image.new('RGB', (width * 2, height * 2))
    positions = [(0, 0), (width, 0), (0, height), (width, height)]
    
    try:
        # Try to load a larger default font or basic font
        font = ImageFont.truetype("arial.ttf", 36)
    except IOError:
        font = ImageFont.load_default()
        
    for i, (img, pos) in enumerate(zip(images, positions)):
        # If images are somehow different sizes, resize to match the first
        if img.size != (width, height):
            img = img.resize((width, height))
            
        stitched.paste(img, pos)
        draw = ImageDraw.Draw(stitched)
        
        # Add index number overlay (1, 2, 3, 4)
        # Background for the text for visibility
        text = str(i + 1)
        # Using simple hardcoded box for MVP visibility
        draw.rectangle([pos[0], pos[1], pos[0] + 40, pos[1] + 40], fill="black")
        draw.text((pos[0] + 10, pos[1] + 5), text, fill="white", font=font)
        
    buffer = io.BytesIO()
    stitched.save(buffer, format="JPEG", quality=85)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")

def extract_and_stitch_frames(video_path: str | Path, start_ms: int, end_ms: int) -> str:
    """
    Extract 4 key frames from the given clip and stitch them into a base64 encoded image.
    """
    # 1st frame at start
    # 4th frame at slightly before the end
    t1 = float(start_ms)
    t4 = float(end_ms) - min(100.0, max(0.0, (end_ms - start_ms) / 2.0))
    duration = max(0.0, t4 - t1)
    
    t2 = t1 + duration / 3.0
    t3 = t1 + 2.0 * duration / 3.0
    
    timestamps = [t1, t2, t3, t4]
    
    frames = []
    for t in timestamps:
        frame_bytes = extract_frame_at(video_path, t)
        if not frame_bytes:
            # Fallback to empty black image bytes if extraction returns empty
            # Pillow can't open empty bytes, so we handle it gracefully inside stitch_frames_to_base64
            # But let's pass dummy bytes here that Pillow would fail to open but handle
            frame_bytes = b''
        frames.append(frame_bytes)
        
    return stitch_frames_to_base64(frames)

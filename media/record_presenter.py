"""Records webcam + mic while the demo plays full screen, then builds the picture-in-picture video.

    python3 media/record_presenter.py

The camera takes a few seconds to start, so recording begins first; the countdown and the video only start once
frames are arriving. The take is then trimmed from the moment the video started, so nothing you say is cut.
"""

import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW, CAM = HERE / "presenter_raw.mov", HERE / "presenter.mov"
DEMO, OUT = HERE / "hubai-demo.mp4", HERE / "hubai-demo-presenter.mp4"
DURATION = 18.2
PLAYER_STARTUP = 0.3  # seconds for ffplay to put the first frame on screen

RAW.unlink(missing_ok=True)
rec = subprocess.Popen(
    ["ffmpeg", "-y", "-loglevel", "error", "-f", "avfoundation", "-framerate", "30", "-video_size", "1280x720",
     "-i", "0:0", "-t", "40", str(RAW)],
    stdin=subprocess.PIPE,
)
start = time.time()
while not RAW.exists() or RAW.stat().st_size < 300_000:  # frames are really arriving
    if time.time() - start > 15:
        rec.kill()
        raise SystemExit("Camera didn't start (check camera/microphone permission for the terminal).")
    time.sleep(0.05)
camera_live = time.time()
subprocess.run(["say", "Recording in three, two, one"], check=True)
video_start = time.time() + PLAYER_STARTUP
subprocess.run(["ffplay", "-loglevel", "error", "-autoexit", "-fs", str(DEMO)], check=True)
time.sleep(0.5)
rec.communicate(b"q")  # stop recording cleanly

# The file's t=0 is roughly when it first appeared; frames were arriving by camera_live.
offset = max(0.0, video_start - camera_live + 0.4)
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{offset:.2f}", "-i", str(RAW), "-t", str(DURATION),
                "-c:v", "libx264", "-c:a", "aac", str(CAM)], check=True)
subprocess.run(["sh", str(HERE / "add_presenter.sh"), str(CAM), str(DEMO), str(OUT)], check=True)
print(f"trimmed {offset:.2f}s from the start of the take")

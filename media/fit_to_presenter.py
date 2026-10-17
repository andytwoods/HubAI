"""Transcribe a presenter recording, time the five demo scenes to its five beats, and build the final video.

    uvx --with faster-whisper --with pillow python media/fit_to_presenter.py media/presenter.mov

Beats are found by keywords; any beat not found is spaced evenly. Captions are the presenter's own words.
"""

import json
import subprocess
import sys
from pathlib import Path

import numpy
from faster_whisper import WhisperModel

HERE = Path(__file__).resolve().parent
CAM = Path(sys.argv[1])
SCENE_COUNT = 5  # overloaded Mac, idle PCs, HubAI splits work, Claude Max machines, robot army

words = []
# Decode with ffmpeg (16 kHz mono float) rather than faster-whisper's PyAV path, which breaks on some PyAV versions.
pcm = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(CAM), "-ac", "1", "-ar", "16000", "-f", "f32le", "-"],
                     capture_output=True, check=True).stdout
audio = numpy.frombuffer(pcm, dtype=numpy.float32)
segments, info = WhisperModel("small.en", device="cpu", compute_type="int8").transcribe(audio, word_timestamps=True)
for seg in segments:
    words += [(w.start, w.end, w.word.strip()) for w in seg.words]
total = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(CAM)],
                             capture_output=True, text=True).stdout)
print("transcript:", " ".join(w for _, _, w in words))

# One scene per sentence: merge the closest-together sentences until there are SCENE_COUNT, or split the longest
# sentence at its longest pause if there are too few.
sentences, current = [], []
for w in words:
    current.append(w)
    if w[2].endswith((".", "!", "?")):
        sentences.append(current)
        current = []
if current:
    sentences.append(current)
while len(sentences) > SCENE_COUNT:
    i = min(range(len(sentences) - 1), key=lambda k: len(sentences[k]) + len(sentences[k + 1]))
    sentences[i:i + 2] = [sentences[i] + sentences[i + 1]]
while len(sentences) < SCENE_COUNT:
    i = max(range(len(sentences)), key=lambda k: len(sentences[k]))
    s_ = sentences[i]
    if len(s_) < 6:
        break
    mid = len(s_) / 2  # biggest pause, preferring the middle; never leave fewer than 3 words either side
    cut = max(range(3, len(s_) - 2), key=lambda k: (s_[k][0] - s_[k - 1][1]) - abs(k - mid) * 0.02)
    sentences[i:i + 1] = [s_[:cut], s_[cut:]]
starts = [0.0] + [max(0.0, sent[0][0] - 0.15) for sent in sentences[1:]]
while len(starts) < SCENE_COUNT:  # too few words: space the rest evenly
    starts.append(starts[-1] + (total - starts[-1]) / 2)
TAIL = 3.0  # extra seconds after the last word so the robot army and logo get their moment
ends = starts[1:] + [total + TAIL]

scenes = []
for (start, end) in zip(starts, ends):
    said = " ".join(w for ws, _, w in words if start - 0.2 <= ws < end - 0.2).strip()
    scenes.append([round(start, 2), round(end, 2), said or "…"])
plan = HERE / "scenes.json"
plan.write_text(json.dumps(scenes, indent=1))
print(json.dumps(scenes, indent=1))

subprocess.run([sys.executable, str(HERE / "make_demo_video.py"), str(HERE / "hubai-demo.mp4"), str(plan)], check=True)
crop = sys.argv[2:3]  # optional "w:h:x:y" face crop
subprocess.run(["sh", str(HERE / "add_presenter.sh"), str(CAM), str(HERE / "hubai-demo.mp4"),
                str(HERE / "hubai-demo-presenter.mp4"), *crop], check=True)

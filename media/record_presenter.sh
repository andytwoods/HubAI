#!/bin/sh
# Records webcam + mic while the demo plays full screen, then makes the picture-in-picture version.
#   sh media/record_presenter.sh
set -e
cd "$(dirname "$0")"
say "Recording in three, two, one"
# Camera takes ~1 s to warm up: record 1 s extra up front and trim it off afterwards.
ffmpeg -y -loglevel error -f avfoundation -framerate 30 -video_size 1280x720 -i "0:0" -t 19.5 presenter_raw.mov &
REC=$!
sleep 1
ffplay -loglevel error -autoexit -fs hubai-demo.mp4
wait $REC
ffmpeg -y -loglevel error -ss 1 -i presenter_raw.mov -t 18.2 -c:v libx264 -c:a aac presenter.mov
sh add_presenter.sh presenter.mov hubai-demo.mp4 hubai-demo-presenter.mp4

#!/bin/sh
# Overlay a webcam clip as a circle in the bottom-right corner of the demo, with its audio.
#   sh media/add_presenter.sh CAM DEMO OUT [CROP]
# CROP is an ffmpeg crop "w:h:x:y" around the face; default is the centred square.
set -e
CAM="$1"; DEMO="$2"; OUT="$3"; CROP="${4:-min(iw\,ih):min(iw\,ih)}"; SIZE="${SIZE:-240}"
ffmpeg -y -loglevel error -i "$DEMO" -i "$CAM" -filter_complex "\
[1:v]tpad=stop_mode=clone:stop_duration=${TAIL:-3},crop=$CROP,scale=$SIZE:$SIZE,format=rgba,\
geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='if(lte(hypot(X-$SIZE/2,Y-$SIZE/2),$SIZE/2-2),255,0)'[cam];\
color=c=0xffdd57:s=$((SIZE+12))x$((SIZE+12)),format=rgba,\
geq=r='255':g='221':b='87':a='if(lte(hypot(X-(W/2),Y-(H/2)),W/2),255,0)'[ring];\
[0:v][ring]overlay=W-w-34:H-h-120[bg];[bg][cam]overlay=W-w-40:H-h-126:eof_action=repeat[v]" \
  -map "[v]" -map 1:a? -af apad -c:v libx264 -pix_fmt yuv420p -crf 20 -c:a aac -b:a 160k -t "$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$DEMO")" -movflags +faststart "$OUT"
echo "$OUT"

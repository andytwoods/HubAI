#!/bin/sh
# Overlay a webcam clip as a circle in the bottom-right corner of the demo, with its audio.
#   sh media/add_presenter.sh media/presenter.mov media/hubai-demo.mp4 media/hubai-demo-presenter.mp4
set -e
CAM="$1"; DEMO="$2"; OUT="$3"; SIZE=300
ffmpeg -y -loglevel error -i "$DEMO" -i "$CAM" -filter_complex "\
[1:v]crop='min(iw,ih)':'min(iw,ih)',scale=$SIZE:$SIZE,format=rgba,\
geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='if(lte(hypot(X-$SIZE/2,Y-$SIZE/2),$SIZE/2-2),255,0)'[cam];\
color=c=0xffdd57:s=$((SIZE+12))x$((SIZE+12)),format=rgba,\
geq=r='255':g='221':b='87':a='if(lte(hypot(X-(W/2),Y-(H/2)),W/2),255,0)'[ring];\
[0:v][ring]overlay=W-w-34:H-h-120[bg];[bg][cam]overlay=W-w-40:H-h-126:shortest=1[v]" \
  -map "[v]" -map 1:a? -c:v libx264 -pix_fmt yuv420p -crf 20 -c:a aac -b:a 160k -shortest -movflags +faststart "$OUT"
echo "$OUT"

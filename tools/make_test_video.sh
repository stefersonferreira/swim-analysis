#!/bin/sh
# Gera um vídeo sintético 720p/30 fps com áudio (bipe em 1 s) para testes de fumaça.
# Uso: sh tools/make_test_video.sh saida.mp4 [segundos]
set -e
OUT=${1:-test.mp4}
DUR=${2:-12}
ffmpeg -y -v error \
  -f lavfi -i "testsrc2=size=1280x720:rate=30:duration=$DUR" \
  -f lavfi -i "sine=frequency=2000:duration=0.2,adelay=1000|1000,apad=whole_dur=$DUR" \
  -c:v libx264 -preset veryfast -pix_fmt yuv420p -c:a aac -shortest "$OUT"
echo "$OUT"

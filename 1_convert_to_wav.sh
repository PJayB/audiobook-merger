#!/bin/bash
die() { echo "$*" >&2 ; exit 1 ; }

set -e

# Convert to raw
while read -r file ; do
    echo "$file"
    bn="$(echo "$file" | sed -r 's/\.[0-9a-zA-Z]+$//g')".wav
    ffmpeg -y -i "$file" -f wav -ac 2 -ar 44100 -acodec pcm_s16le "$bn" </dev/null >/dev/null 2>&1 &
done < <(find "$1" '(' -iname '*.flac' ')' | sort)

wait

# Ensure all files were created
# TODO: figure out why the [ -e ] check doesn't work immediately after ffmpeg (without & obvs)
while read -r file ; do
    bn="$(echo "$file" | sed -r 's/\.[0-9a-zA-Z]+$//g')".wav
    [ -e "$bn" ] || die "No file was produced for $file"
done < <(find "$1" '(' -iname '*.flac' ')' | sort)

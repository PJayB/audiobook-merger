#!/bin/bash

process_lst() {
    output_file="$(basename "$1" .lst).mp3" # todo: flac
    dir_file="$1"
    if [ ! -e "$output_file" ]; then
        ffmpeg -f concat -safe 0 -i "$dir_file" -c copy "$output_file" || (rm "$output_file" 2>/dev/null)
    fi
}

while [ -n "$1" ]; do
    process_lst "$1" &
    shift
done
wait

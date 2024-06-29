#!/bin/bash

process_merged() {
    out_ext="mp4"
    codec="mp4"

    base_name="$(basename "${1%.*}")"
    output_file="$base_name.$out_ext"

    if [ -e "$output_file" ]; then
        echo "Skipping $1"
        return
    fi

    ffmpeg -i "$1" -threads "$(nproc)" -strict -2 "-vn" "-f" "$codec" "$output_file" || : # todo error handling
}

while [ -n "$1" ]; do
    process_merged "$1" &
    shift
done
wait


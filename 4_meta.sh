#!/bin/bash

process_meta() {
    meta_ext=".timestamps.txt"
    out_ext="m4b"
    base_name="$(basename "$1" .mp4)"
    meta_file="$base_name.$meta_ext"
    output_file="$base_name.$out_ext"

    if [ -e "$output_file" ]; then
        echo "Skipping $1"
        return
    fi

    cmdline=( )

    # metadata
    if [ -e "$meta_file" ]; then
        cmdline+=( -i "$meta_file" )
    fi

    # find thumbnail
    # todo: find thumbnail properly
    thumb="$(find "." -iname '*.png' -or -iname '*.jpg' | head -n 1)"
    if [ -z "$thumb" ]; then
        echo "No thumbnail for $1" >&2
    else
        cmdline+=( "-i" "$thumb" -map 0:0 )
        [ -e "$meta_file" ] && cmdline+=( -map 2:0 )
        [ -e "$meta_file" ] || cmdline+=( -map 1:0 )
    fi

    ffmpeg "-i" "$1" "${cmdline[@]}" -f mp4 -codec copy \
        -map_metadata 1 -id3v2_version 3 \
        -metadata:s:v title="Album cover" -metadata:s:v comment="Cover (front)" \
        "$output_file"
}

while [ -n "$1" ]; do
    process_meta "$1" &
    shift
done
wait

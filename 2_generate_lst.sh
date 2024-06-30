#!/bin/bash

set -e

get_duration() {
    ffprobe -i "$1" -show_entries format=duration -v quiet -of csv="p=0"
}

create_lst() {
    echo "ffconcat version 1.0"
    while read -r file ; do
        echo "$file" | sed "s/'/'\\\\''/g" | awk '{ print "file '"'"'" $0 "'"'"'" }'
        dur="$(get_duration "$file")"
        echo "duration ${dur}"
    done
}

create_chaps() {
    echo "file,length,offset,chapter"
    while read -r flac ; do
        timestr="$(get_duration "$flac")"
        chapterguess="$(echo "$flac" | sed -nr 's/.*[Cc]hapter 0*([0-9]+).*/\1/p')"
        echo '"'"$flac"'"'";$timestr;0;$chapterguess"
    done
}

create_meta() {
    ofile="$(mktemp)"
    ffile="$1"
    ffmpeg -y -i "$ffile" -f ffmetadata "$ofile" >/dev/null
    grep -iE -e ';FFMETADATA1' -e "^artist=" -e "^album=" -e "^date=" "$ofile"
    rm "$ofile"
}

process_file() {
    input_path="$(basename "${1%.*}")"
    dir_file="$input_path.lst"
    chaps_file="$input_path.csv"
    meta_file="$input_path.meta"

    if [ ! -e "$1" ]; then
        echo "Not a file: $1" >&2
        return
    fi

    if [ ! -e "$dir_file" ]; then
        create_lst < <(cat "$1") > "$dir_file" &
    fi

    if [ ! -e "$chaps_file" ]; then
        create_chaps < <(cat "$1") > "$chaps_file" &
    fi

    if [ ! -e "$meta_file" ]; then
        ffile="$(cat "$1" | head -n 1)"
        create_meta "$ffile" > "$meta_file" &
    fi

    wait
}

while [ -n "$1" ]; do
    if [ -d "$1" ]; then
        echo "$1 must be a file" >&2
        exit 1
    else
        process_file "$1" &
    fi
    shift
done
wait

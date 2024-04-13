#!/bin/bash

# todo: parameterize
input_file_ext="mp3" #flac

create_lst() {
    while read -r file ; do
        echo "$file" | sed "s/'/'\\\\''/g" | awk '{ print "file '"'"'" $0 "'"'"'" }'
    done
}

create_chaps() {
    echo "file,length,offset,chapter"
    while read -r flac ; do
        timestr="$(ffprobe -i "$flac" 2>&1 | grep 'Duration:' | awk '{ print $2 $4 }')"
        chapterguess="$(echo "$flac" | sed -nr 's/.*[Cc]hapter 0*([0-9]+).*/\1/p')"
        echo '"'"$flac"'"'",$timestr$chapterguess"
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

    if [ ! -f "$1" ]; then
        echo "Not a file: $1" >&2
        return
    fi

    if [ ! -e "$dir_file" ]; then
        create_lst < <(cat "$1") > "$dir_file"
    fi

    if [ ! -e "$chaps_file" ]; then
        create_chaps < <(cat "$1") > "$chaps_file"
    fi

    if [ ! -e "$meta_file" ]; then
        ffile="$(cat "$1" | head -n 1)"
        create_meta "$ffile" > "$meta_file"
    fi
}

process_dir() {
    input_path="$(basename "$1")"
    dir_file="$input_path.lst"
    chaps_file="$input_path.csv"
    meta_file="$input_path.meta"

    if [ ! -d "$1" ]; then
        echo "Not a folder: $1" >&2
        return
    fi

    if [ ! -e "$dir_file" ]; then
        create_lst < <(find "$1" -iname "*.$input_file_ext") > "$dir_file"
    fi

    if [ ! -e "$chaps_file" ]; then
        create_chaps < <(find "$1" -iname "*.$input_file_ext") > "$chaps_file"
    fi

    if [ ! -e "$meta_file" ]; then
        ffile="$(find "$1" -iname "*.$input_file_ext" | head -n 1)"
        create_meta "$ffile" > "$meta_file"
    fi
}

if [ -n "$1" ]; then
    while [ -n "$1" ]; do
        if [ -d "$1" ]; then
            process_dir "$1" &
        else
            process_file "$1" &
        fi
        shift
    done
else
    while read -r folder; do
        process_dir "$folder" &
    done < <(find . -mindepth 1 -maxdepth 1 -type d -not -name '.*')
fi
wait

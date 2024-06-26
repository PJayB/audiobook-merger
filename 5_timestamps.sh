#!/bin/bash
dur_to_time() {
    echo "$*" | awk -F ':' '
        $0 ~ "^[0-9+]:[0-9]+:[0-9]+:[0-9.]+$" { printf "%0.2f", $1 * (24 * 60 * 60) + $2 * 3600 + $3 * 60 + $4 }
        $0 ~ "^[0-9]+:[0-9]+:[0-9.]+$" { printf "%0.2f", $1 * 3600 + $2 * 60 + $3 }
        $0 ~ "^[0-9]+:[0-9.]+$" { printf "%0.2f", $1 * 60 + $2 }
        $0 ~ "^[0-9.]+$" { printf "%0.2f", $1 }
        '
}

write_chapter() {
        echo "
[CHAPTER]
TIMEBASE=1/1000
START=${2}
END=${3}
title=Chapter ${1}
"
}

process_csv() {
    read -r header # skip first line

    chapter_start=0
    last_start=0
    last_chapter=

    while IFS=';' read -ra toks ; do
        chapter="${toks[-1]}"
        if [ -z "$last_chapter" ]; then
            last_chapter="$chapter"
        fi

        # write previous chapter if relevant
        if [ "$last_chapter" != "$chapter" ]; then
            write_chapter "$last_chapter" "$chapter_start" "$last_start"
            last_chapter="$chapter"
            chapter_start="$last_start"
        fi

        offset="${toks[-2]}"
        length="${toks[-3]}"

        # convert to timestamps
        #offset="$(dur_to_time "$offset")"
        #length="$(dur_to_time "$length")"

        # output
        start="$(echo "$offset * 1000 + $last_start" | bc -l)"
        end="$(echo "$start + $length * 1000" | bc -l)"

        echo "; chapter '$chapter' $start -> $end"

        last_start="$end"
        last_chapter="$chapter"
    done

    # write previous chapter if relevant
    if [ -n "$last_chapter" ]; then
        write_chapter "$last_chapter" "$chapter_start" "$last_start"
    fi
}

process_meta() {
    local base_name="$1"
    local meta_file="$2"
    local csv_file="$3"

    grep -viE -e '^title=' -e '^album=' "$meta_file"
    echo "title=$base_name"
    echo "album=$base_name"

    if [ -e "$csv_file" ]; then
        process_csv < "$csv_file"
    else
        echo "No chapters found for $1" >&2
    fi
}

#while read -r meta ; do
while [ -n "$1" ]; do
    base_name="$(basename "$1" .meta)"
    csv="$base_name.csv"
    out_file="$base_name.timestamps.txt"
    process_meta "$base_name" "$1" "$csv" > "$out_file"
    shift
done

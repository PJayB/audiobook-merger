#!/bin/bash
if uname -a | grep -q Msys ; then
    echo "Run in WSL, silly" >&2
    exit 1
fi

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

process_lst() {
    output_file="$(basename "$1" .lst).flac"
    dir_file="$1"
    if [ ! -e "$output_file" ]; then
        ffmpeg -f concat -safe 0 -i "$dir_file" "$output_file" || :
    fi
}

process_flac() {
    out_ext="mp4"
    codec="mp4"

    base_name="$(basename "$1" ".flac")"
    output_file="$base_name.$out_ext"

    if [ -e "$output_file" ]; then
        echo "Skipping $1"
        return
    fi

    ffmpeg -i "$1" -strict -2 "-vn" "-f" "$codec" "$output_file" || :
}

process_meta() {
    meta_ext="txt"
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
    thumb="$(find "./$base_name/" -iname '*.png' -or -iname '*.jpg' | head -n 1)"
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

#while read -r lst; do
#    process_lst "$lst" &
#done < <(find . -mindepth 1 -maxdepth 1 -type f -name '*.lst')
#wait
#
#while read -r flac; do
#    process_flac "$flac" &
#done < <(find . -mindepth 1 -maxdepth 1 -type f -name '*.flac')
#wait
#
#while read -r meta; do
#    process_meta "$meta" &
#done < <(find . -mindepth 1 -maxdepth 1 -type f -name '*.mp4')
#wait

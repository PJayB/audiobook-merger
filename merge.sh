#!/bin/bash
process_dir() {
    output_file="$1.flac"
    dir_file="$1.lst"
    chaps_file="$1.csv"
    meta_file="$1.meta"

    if [ ! -d "$1" ]; then
        echo "Not a folder: $1" >&2
        return
    fi

    if [ ! -e "$dir_file" ]; then
        find "$1" -iname '*.flac' | sed "s/'/'\\\\''/g" | awk '{ print "file '"'"'" $0 "'"'"'" }' > "$dir_file"
    fi

    if [ ! -e "$chaps_file" ]; then
        echo "file,length,offset,chapter" > "$chaps_file"
        while read -r flac ; do
            echo -ne "Processing $flac...\r"
            timestr="$(ffprobe -i "$flac" 2>&1 | grep 'Duration:' | awk '{ print $2 $4 }')"
            chapterguess="$(echo "$flac" | sed -nr 's/.*[Cc]hapter 0*([0-9]+).*/\1/p')"
            echo '"'"$flac"'"'",$timestr$chapterguess" >> "$chaps_file"
        done < <(find "$1" -iname '*.flac')
        echo
    fi

    if [ ! -e "$meta_file" ]; then
        ofile="$(mktemp)"
        ffile="$(find "$1" -iname '*.flac' | head -n 1)"
        ffmpeg -y -i "$ffile" -f ffmetadata "$ofile"
        grep -iE -e ';FFMETADATA1' -e "^artist=" -e "^album=" -e "^date=" "$ofile" > "$meta_file"
        rm "$ofile"
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

    base_name="$(basename "$1" .flac)"
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

    if [ -e "$meta_file" ]; then
        cmdline+=( -i "$meta_file" )
    fi

    # find thumbnail
    thumb="$(find "./$base_name/" -iname '*.png' -or -iname '*.jpg' | head -n 1)"
    if [ -z "$thumb" ]; then
        echo "No thumbnail for $1" >&2
    else
        cmdline+=( "-i" "$thumb" )
    fi

    ffmpeg "-i" "$1" "${cmdline[@]}" -map_metadata 1 -vn -f mp4 -codec copy "$output_file"
}

while read -r folder; do
    process_dir "$folder"
done < <(find . -mindepth 1 -maxdepth 1 -type d)

while read -r lst; do
    process_lst "$lst"
done < <(find . -mindepth 1 -maxdepth 1 -type f -name '*.lst')

while read -r flac; do
    process_flac "$flac"
done < <(find . -mindepth 1 -maxdepth 1 -type f -name '*.flac')

while read -r meta; do
    process_meta "$meta"
done < <(find . -mindepth 1 -maxdepth 1 -type f -name '*.mp4')

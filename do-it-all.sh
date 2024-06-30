#!/bin/bash
set -e

if [ -z "$1" ] ; then
    echo "Usage: $0 <book title>" >&2
    exit 1
fi

script_root="$(dirname "$(realpath "$0")")"
book="$1"
"$script_root/1_convert_to_wav.sh" .
find . -iname '*.wav' | sort > "${book}.src"
"$script_root/2_generate_lst.sh" "${book}.src"
"$script_root/3_merge.sh" "${book}.lst"
"$script_root/4_encode.sh" "${book}.wav"
"$script_root/5_timestamps.sh" "${book}.meta"
"$script_root/6_meta.sh" "${book}.mp4"

#!/bin/bash

while read -r file ; do
    sha256sum "$file"
done < <(find "$1" -type f | sort)


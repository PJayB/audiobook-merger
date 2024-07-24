#!/usr/bin/python3
import argparse
import csv
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from tqdm import tqdm

# todo: update an existing file with new metadata
# todo: switch from csv to some kind of manifest file
# todo: override metadata: artist, title, year, etc. in manifest
# todo: add optional album art in manifest
# todo: iff. all inputs have chapters, use those instead

def run_stream(args, capture_stdout=True, capture_stderr=True):
    stdin_stream = subprocess.PIPE if input is not None else None
    stdout_stream = subprocess.PIPE if capture_stdout else None
    stderr_stream = subprocess.PIPE if capture_stderr else None
    return subprocess.Popen(
        args, stdin=stdin_stream, stdout=stdout_stream, stderr=stderr_stream
    )

#
# Hacked together from ffmpeg.run to run a custom command line
#
def run_custom(
    args,
    capture_stdout=True,
    capture_stderr=True,
    input=None
):
    process = run_stream(args, capture_stdout, capture_stderr)
    out, err = process.communicate(input)
    retcode = process.poll()
    if retcode:
        raise RuntimeError(f'ffmpeg error: {bytes.decode(err)}')
    return out, err


def write_chapters_metadata_file(chapters, output_file):
    chapter_start = 0
    chapter_end = 0
    num_segments = 0

    output_file.write(';FFMETADATA1\n')

    for chapter in chapters:
        output_file.write('\n[CHAPTER]\n')
        output_file.write('TIMEBASE=1/1000\n')

        for (file, duration) in chapter['files']:
            # tot up chapter lengths
            chapter_end += duration * 1000

            # accumulate the number of audio segments
            num_segments += 1

        # add to chapter metadata
        output_file.write(f'START={chapter_start}\n')
        output_file.write(f'END={chapter_end}\n')
        output_file.write(f'TITLE={chapter["name"]}\n')

        chapter_start = chapter_end


# to convert to raw: ffmpeg -f s16le -ac 2 -ar 44100 -i pipe:0 -f mp4 test.mp4
# to convert from raw: ffmpeg -f s16le -ac 2 -ar 44100 -i pipe:0 -i ffmetadata.txt -f mp4 test.mp4 -map_chapters 1 -y
def write_merged_audio_file(chapters, ffmetadata_filename, output_filename):
    # This is the output process. We'll stream data to this via its stdin.
    output_process = run_stream([
        'ffmpeg',
        '-f', 's16le',
        '-ac', '2',
        '-ar', '44100',
        '-i', 'pipe:0',
        '-i', ffmetadata_filename,
        '-map_chapters', '1',
        '-f', 'mp4',
        '-v', 'error',
        '-y', output_filename
    ])

    # Open the input pipe and send each file over for processing
    files = []
    for chapter in chapters:
        for file, duration in chapter['files']:
            files.append(file)

    with tqdm(total=len(files)) as pbar:
        for file in files:
            pbar.set_description(f'Writing {file}')
            # convert the file to PCM on-the-fly
            input_data, _ = run_custom([
                'ffmpeg',
                '-i', file,
                '-f', 's16le',
                '-ac', '2',
                '-ar', '44100',
                '-v', 'error',
                '-y', '-'
                ])

            # Send the data to the output process
            output_process.stdin.write(input_data)
            pbar.update(1)

    # Close the door!
    output_process.stdin.close()

    # Wait for the write to complete
    output_process.wait()

    # Grab output and error
    retcode = output_process.poll()
    if retcode:
        raise RuntimeError('ffmpeg') # todo: error handling


def update_audio_file(ffmetadata_filename, output_filename):
    # create a temporary file that we'll use to overwrite the original
    _, temp_filename = tempfile.mkstemp(
        prefix=Path(output_filename).stem,
        suffix=Path(output_filename).suffix)
    try:
        # annotate the original with the "copy" codec
        run_custom([
            'ffmpeg',
            '-i', output_filename,
            '-i', ffmetadata_filename,
            '-map_chapters', '1',
            '-codec', 'copy',
            '-v', 'error',
            '-y', temp_filename
            ],
            capture_stdout=False)

        # move the file over the original
        shutil.move(temp_filename, output_filename)
    except Exception as e:
        # Something went wrong, so delete the temporary file
        os.remove(temp_filename)
        # Rethrow the exception
        raise e


def read_chapters_csv(input_file):
    # ordered chapter names
    chapter_names = []
    # map of file lists for each chapter
    chapter_map = {}

    def add_file(file, chap):
        if not chap in chapter_map:
            chapter_names.append(chap)
            chapter_map[chap] = []

        # resolve the filename
        file = os.path.abspath(file)

        # Probe the file for length
        # Can't use regular ffmpeg.probe here as it doesn't handle
        # apostrophes properly, and also it's pretty heavyweight anyway
        duration_str, err = run_custom(['ffprobe',
                                    '-i', file,
                                    '-show_entries', 'format=duration',
                                    '-v', 'error',
                                    '-of', 'csv=p=0'])

        # Add tuple of name and duration
        chapter_map[chap].append((file, float(duration_str.strip())))

    # Read the CSV file
    input_files_and_chapters = []
    reader = csv.reader(input_file, delimiter=',', quotechar='"')
    for row in reader:
        if len(row) > 1:
            input_files_and_chapters.append(row)
        elif len(row) > 0:
            raise ValueError(f"Expected <filename>,<chapter>: '{row}'")

    # Process each file and extract a duration for each one using ffprobe
    with tqdm(total=len(input_files_and_chapters)) as pbar:
        for row in input_files_and_chapters:
            pbar.set_description(f'Analyzing {row[0]}')
            add_file(row[0], row[1])
            pbar.update(1)

    # flattens all files in unordered chapters into ordered chapters
    def flatten_chapters(chapter_names, chapter_map):
        sorted_chapters = []
        for name in chapter_names:
            sorted_chapters.append({
                'name': name,
                'files': chapter_map[name]
                })
        return sorted_chapters

    return flatten_chapters(chapter_names, chapter_map)


def get_input_output_file():
    parser = argparse.ArgumentParser()

    parser.add_argument('input_filename', type=str,
                        help='A CSV file listing <"file","chapter">.')
    parser.add_argument('-o', '--output', type=str, required=False,
                        help='The output filename.')
    parser.add_argument('-u', '--update', action='store_true',
                        help="Update metadata only; don't process audio data.")

    args = parser.parse_args()

    # Derive a filename if output file is not provided
    if not args.output:
        args.output = f'{Path(args.input_filename).stem}.m4b'

    # Ensure both input and output paths are fully qualified
    args.input_filename = os.path.abspath(args.input_filename)
    args.output = os.path.abspath(args.output)

    return (args.input_filename, args.output, args.update)


if __name__ == '__main__':
    # parse command line
    input_filename, merged_filename, update_only = get_input_output_file()

    # set the current working directory to the directory of the input file
    # so that relative paths work correctly
    os.chdir(os.path.dirname(input_filename))

    # Read the chapters
    with open(input_filename, 'r', newline='', encoding='utf-8') as input_file:
        chapters = read_chapters_csv(input_file)

    # Write the metadata file with the chapters and stuff
    fd, ffmetadata_filename = tempfile.mkstemp()
    try:
        with os.fdopen(fd, 'w') as ffmetadata_file:
            write_chapters_metadata_file(chapters, ffmetadata_file)

        # Write the merged file
        if update_only and os.path.isfile(merged_filename):
            update_audio_file(
                ffmetadata_filename,
                merged_filename)
        else:
            write_merged_audio_file(
                chapters,
                ffmetadata_filename,
                merged_filename)
    finally:
        os.remove(ffmetadata_filename)

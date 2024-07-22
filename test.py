#!/usr/bin/python3
import csv
import ffmpeg
import os.path
from pprint import pprint
import subprocess

# todo: find album art from any of the inputs and use that
# todo: take optional album art from command line
# todo: derive chapter markers, make timestamps meta file, use it

#
# Hacked together from ffmpeg.run to run a custom command line
#
def run_custom(
    args,
    capture_stdout=False,
    capture_stderr=False,
    input=None,
    quiet=False
):
    stdin_stream = subprocess.PIPE if input is not None else None
    stdout_stream = subprocess.PIPE if capture_stdout or quiet else None
    stderr_stream = subprocess.PIPE if capture_stderr or quiet else None
    process = subprocess.Popen(
        args, stdin=stdin_stream, stdout=stdout_stream, stderr=stderr_stream
    )
    out, err = process.communicate(input)
    retcode = process.poll()
    if retcode:
        raise ffmpeg.Error('ffmpeg', out, err)
    return out, err


def write_chapters_metadata_file(chapters, output_filename):
    chapter_start = 0
    chapter_end = 0
    bookmarks = []
    num_segments = 0

    with open(output_filename, 'w') as output_file:
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
            output_file.write(f'TITLE={chapter['name']}\n')

            chapter_start = chapter_end


def write_ffconcat_file(chapters, output_filename):
    # example:
    #ffconcat version 1.0
    #file './CD 01/01 Chapter 1 The Boy Who Lived.wav'
    #duration 64.840000
    #file './CD 01/02 Chapter 1 The Boy Who Lived.wav'
    #duration 58.306667

    with open(output_filename, 'w') as output_file:
        output_file.write('ffconcat version 1.0\n')

        for chapter in chapters:
            for file, duration in chapter['files']:
                output_file.write(f"file '{file}'\n")
                output_file.write(f"duration {duration}\n")


def write_merged_audio_file(ffconcat_filename, output_filename):
    # ffmpeg-python injects -maps into the command line that are not applicable
    # here, so we have to construct the command line manually
    custom_args = [
        'ffmpeg',
        '-f', 'concat',
        '-safe', '0',
        '-i', ffconcat_filename,
        '-vn',
        '-acodec', 'copy',
        '-rf64', 'auto',
        '-y', output_filename
    ]

    print(custom_args)

    return run_custom(custom_args)


# todo: delete me
def write_merged_audio_file_old(chapters, output_file):
    concatenated_input = None

    # todo: generate a list file for input to ffmpeg
    # todo: get rid of ffmpeg-python

    # chain the audio tracks together for each chapter
    for chapter in chapters:
        for file, _ in chapter['files']:
            input_file = ffmpeg.input(file)
            if not concatenated_input:
                concatenated_input = input_file.audio
            else:
                concatenated_input = ffmpeg.concat(concatenated_input, input_file.audio, a=1, v=0)

    # write the output file
    output = ffmpeg.output(concatenated_input, output_file, format='mp4').overwrite_output()

    # todo: if verbose, print this
    args = output.compile()
    print(args)

    return (output.run())


#
# Attach a metadata file to an existing mp4
#
def audio_file_attach_chapters(audio_filename, ffmetadata_filename, output_filename):
    # ffmpeg-python injects -maps into the command line that are not applicable
    # here, so we have to construct the command line manually
    custom_args = [
        'ffmpeg',
        '-i', audio_filename,
        '-i', ffmetadata_filename,
        '-map_chapters', '1',
        '-codec', 'copy',
        '-y', output_filename
    ]

    print(custom_args)

    return run_custom(custom_args)

def read_chapters_csv(input_filename):
    # ordered chapter names
    chapter_names = []
    # map of file lists for each chapter
    chapter_map = {}

    def add_file(file, chap):
        if not chap in chapter_map:
            chapter_names.append(chap)
            chapter_map[chap] = []

        # Probe the file for length
        # Can't use regular ffmpeg.probe here as it doesn't handle
        # apostrophes properly, and also it's pretty heavyweight anyway
        duration_str, err = run_custom(['ffprobe',
                                    '-i', file,
                                    '-show_entries', 'format=duration',
                                    '-v', 'quiet',
                                    '-of', 'csv=p=0'],
                                    capture_stdout=True)

        # Add tuple of name and duration
        chapter_map[chap].append((file, float(duration_str.strip())))

    # todo: parse lines
    with open(input_filename, newline='', encoding='utf-8') as input_file:
        reader = csv.reader(input_file, delimiter=',', quotechar='"')
        for row in reader:
            if len(row) > 1:
                add_file(row[0], row[1])
            elif len(row) > 0:
                raise ValueError(f"Expected <filename>,<chapter>: '{row}'")

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

if __name__ == '__main__':
    input_filename = "Night Watch.csv" #"Harry Potter and the Philosopher's Stone.csv"
    ffmetadata_filename = 'ffmetadata.txt' # todo: make temporary file and clean up
    ffconcat_filename = 'ffconcat.txt' # todo: make temporary file and clean up
    merged_filename = 'merged.mp4' # todo: make temporary file and clean up
    output_filename = 'output.m4b'

    # Read the chapters
    chapters = read_chapters_csv(input_filename)

    # Write the metadata file with the chapters and stuff
    write_chapters_metadata_file(chapters, ffmetadata_filename)

    # Write the ffconcat file
    write_ffconcat_file(chapters, ffconcat_filename)

    # Write the merged file
    # todo: remove the if !exists check here
    #if not os.path.isfile(merged_filename):
    write_merged_audio_file(ffconcat_filename, merged_filename)
    #write_merged_audio_file_old(chapters, merged_filename)

    # Attach chapter metadata
    audio_file_attach_chapters(merged_filename, ffmetadata_filename, output_filename)

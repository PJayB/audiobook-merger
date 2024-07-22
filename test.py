#!/usr/bin/python3
import ffmpeg
import os.path
from pprint import pprint
import subprocess

# todo: find album art from any of the inputs and use that
# todo: take optional album art from command line
# todo: derive chapter markers, make timestamps meta file, use it

def write_chapters_metadata_file(chapters, output_file):

    chapter_start = 0
    chapter_end = 0
    bookmarks = []
    num_segments = 0

    for chapter in chapters:
        for file in chapter['files']:
            # tot up chapter lengths
            input_info = ffmpeg.probe(file)
            chapter_end += float(input_info['format']['duration']) * 1000

            # accumulate the number of audio segments
            num_segments += 1

        # add to chapter metadata
        bookmarks.append({
            'name': chapter['name'],
            'start': chapter_start,
            'end': chapter_end
        })
        chapter_start = chapter_end

    with open(output_file, 'w') as ffmd:
        ffmd.write(';FFMETADATA1\n')
        for bookmark in bookmarks:
            ffmd.write('\n[CHAPTER]\n')
            ffmd.write('TIMEBASE=1/1000\n')
            ffmd.write(f'START={bookmark['start']}\n')
            ffmd.write(f'END={bookmark['end']}\n')
            ffmd.write(f'TITLE={bookmark['name']}\n')


def write_merged_audio_file(chapters, output_file):
    concatenated_input = None

    # chain the audio tracks together for each chapter
    for chapter in chapters:
        for file in chapter['files']:
            input_file = ffmpeg.input(file)
            if not concatenated_input:
                concatenated_input = input_file.audio
            else:
                concatenated_input = ffmpeg.concat(concatenated_input, input_file.audio, a=1, v=0)

    # write the output file
    output = ffmpeg.output(concatenated_input, output_file, format='mp4').overwrite_output() #, map_metadata=1, id3v2_version=3, **metadata)

    #print(output.compile())

    return (output.run())

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

if __name__ == '__main__':
    chapters = [
        {
            'name': 'Chapter 1',
            'files': [
                "H:/Audiobooks/Terry Pratchett/Night Watch/01 001.mp3",
                "H:/Audiobooks/Terry Pratchett/Night Watch/02 002.mp3",
            ],
        },
        {
            'name': 'Chapter 2',
            'files': [
                "H:/Audiobooks/Terry Pratchett/Night Watch/03 003.mp3",
            ],
        },
    ]

    ffmetadata_filename = 'ffmetadata.txt' # todo: make temporary file and clean up
    merged_filename = 'merged.mp4' # todo: make temporary file and clean up
    output_filename = 'output.m4b'

    # Write the metadata file with the chapters and stuff
    write_chapters_metadata_file(chapters, ffmetadata_filename)

    # Write the merged file
    # todo: remove the if !exists check here
    if not os.path.isfile(merged_filename):
        write_merged_audio_file(chapters, merged_filename)

    # Attach chapter metadata
    audio_file_attach_chapters(merged_filename, ffmetadata_filename, output_filename)

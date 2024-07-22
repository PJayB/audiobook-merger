#!/usr/bin/python3
import csv
import subprocess
from tqdm import tqdm

# todo: find album art from any of the inputs and use that
# todo: take optional album art from command line
# todo: derive chapter markers, make timestamps meta file, use it

def run_stream(args, capture_stdout=False, capture_stderr=False, quiet=False):
    stdin_stream = subprocess.PIPE if input is not None else None
    stdout_stream = subprocess.PIPE if capture_stdout or quiet else None
    stderr_stream = subprocess.PIPE if capture_stderr or quiet else None
    return subprocess.Popen(
        args, stdin=stdin_stream, stdout=stdout_stream, stderr=stderr_stream
    )

#
# Hacked together from ffmpeg.run to run a custom command line
#
def run_custom(
    args,
    capture_stdout=False,
    capture_stderr=False,
    quiet=False,
    input=None
):
    process = run_stream(args, capture_stdout, capture_stderr, quiet)
    out, err = process.communicate(input)
    retcode = process.poll()
    if retcode:
        raise RuntimeError('ffmpeg', out, err)
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


# to convert to raw: ffmpeg -f s16le -ac 2 -ar 44100 -i pipe:0 -f mp4 test.mp4
# to convert from raw: ffmpeg -f s16le -ac 2 -ar 44100 -i pipe:0 -i ffmetadata.txt -f mp4 test.mp4 -map_chapters 1 -y
def write_merged_audio_file(chapters, ffmetadata_file, output_filename):
    # This is the output process. We'll stream data to this via its stdin.
    output_process = run_stream([
        'ffmpeg',
        '-f', 's16le',
        '-ac', '2',
        '-ar', '44100',
        '-i', 'pipe:0',
        '-i', ffmetadata_file,
        '-map_chapters', '1',
        '-f', 'mp4',
        '-v', 'quiet',
        '-y', output_filename
    ])

    # Open the input pipe and send each file over for processing
    files = []
    for chapter in chapters:
        for file, duration in chapter['files']:
            files.append(file)

    for file in tqdm(files, desc="Writing"):
        # convert the file to PCM on-the-fly
        input_data, _ = run_custom([
            'ffmpeg',
            '-i', file,
            '-f', 's16le',
            '-ac', '2',
            '-ar', '44100',
            '-v', 'quiet',
            '-y', '-'
            ],
            capture_stdout=True)

        # Send the data to the output process
        output_process.stdin.write(input_data)

    # Close the door!
    output_process.stdin.close()

    # Wait for the write to complete
    output_process.wait()

    # Grab output and error
    retcode = output_process.poll()
    if retcode:
        raise RuntimeError('ffmpeg') # todo: error handling


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

    # Read the CSV file
    input_files_and_chapters = []
    with open(input_filename, newline='', encoding='utf-8') as input_file:
        reader = csv.reader(input_file, delimiter=',', quotechar='"')
        for row in reader:
            if len(row) > 1:
                input_files_and_chapters.append(row)
            elif len(row) > 0:
                raise ValueError(f"Expected <filename>,<chapter>: '{row}'")

    # Process each file and extract a duration for each one using ffprobe
    for row in tqdm(input_files_and_chapters, desc='Gathering information'):
        add_file(row[0], row[1])

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
    # todo: command line arguments
    input_filename = "HPsmall.csv"
    ffmetadata_filename = 'ffmetadata.txt' # todo: make temporary file and clean up
    merged_filename = 'output.m4b'

    # Read the chapters
    chapters = read_chapters_csv(input_filename)

    # Write the metadata file with the chapters and stuff
    # todo: attempt to stream this via stdin too, maybe? Depends how fancy
    # we can get with input pipes...
    write_chapters_metadata_file(chapters, ffmetadata_filename)

    # Write the merged file
    # todo: remove the if !exists check here
    #if not os.path.isfile(merged_filename):
    write_merged_audio_file(chapters, ffmetadata_filename, merged_filename)

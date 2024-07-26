#!/usr/bin/python3
import argparse
import csv
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from tqdm import tqdm

# todo: fix chapter names metadata not "sticking"
# todo: a manifest generation tool that dumps a template manifest
# todo: chapter regex option that pulls from filenames and/or track names
# todo: iff. all inputs have chapters, use those instead

def run_stream(args, capture_stdout=True, capture_stderr=True):
    stdin_stream = subprocess.PIPE if input is not None else None
    stdout_stream = subprocess.PIPE if capture_stdout else None
    stderr_stream = subprocess.PIPE if capture_stderr else None
    return subprocess.Popen(
        args, stdin=stdin_stream, stdout=stdout_stream, stderr=stderr_stream
    )


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
        cmdline_str = ' '.join([f"'{a}'" for a in args])
        raise RuntimeError(f'ffmpeg error:\n'
                           f'Command line: {cmdline_str}\n'
                           f'{bytes.decode(err)}')
    return out, err


class _ParseDirective(Exception):
    def __init__(self, directive):
        self.directive = directive
class _ParseEnd(Exception):
    pass
class ParseException(Exception):
    def __init__(self, error, file_name, line_no):
        self.line = line_no
        self.file_name = file_name
        self.message = error

    def __str__(self):
        return(f'{self.file_name}({self.line}): {self.message}')


class Manifest:
    def __init__(self):
        self.key_value_pairs = {}
        self.album_art = None
        self.files = []
        self.chapters = []


class ManifestParser:
    def __init__(self, file_name, manifest):
        self._parse_file_name = file_name
        self._parse_line_number = 0
        self._manifest = manifest

        # todo: read the file
        with open(file_name, 'r', encoding='utf-8') as input_file:
            self._parse_toplevel(input_file)

    #
    # Parsing functions
    #
    def _parse_exception(self, message):
        raise ParseException(
            message,
            self._parse_file_name,
            self._parse_line_number)

    # Ignores blank lines, comment lines, and strips leading/trailing whitespace
    # Also jumps back to top level if a [ is hit
    def _parse_get_line(self, file, top_level=False):
        while True:
            self._parse_line_number += 1
            line = file.readline()
            if not line:
                raise _ParseEnd()

            # trim the line
            line = line.strip()
            if len(line) == 0:
                continue
            if line[0] == '#':
                continue
            if not top_level and line[0] == '[':
                raise _ParseDirective(line)
            return line

    def _parse_get_section_key(self, line):
        if line.startswith('[') and line.endswith(']'):
            line = line[1:-1] # remove []s
            tokens = [x.strip() for x in line.partition(':')[::2]]
            if not tokens or not tokens[0]:
                self._parse_exception('Expected [key]')
            return tokens
        else:
            self._parse_exception('Expected section key "[key(: value)]"')

    def _parse_toplevel(self, file):
        try:
            # get the first line
            line = self._parse_get_line(file, top_level=True)

            # keep looping over lines until we're done
            while True:
                try:
                    key, value = self._parse_get_section_key(line)
                    if key == 'metadata':
                        if value: self._parse_exception(
                                f'unexpected value "{value}" for "[metadata]"')
                        self._parse_metadata(file)
                    elif key == 'chapter':
                        self._parse_chapter(file, value)
                    else:
                        self._parse_exception(f'Unexpected [{key}]')
                except _ParseDirective as d:
                    line = d.directive
        except _ParseEnd:
            return

    def _parse_metadata(self, file):
        while line := self._parse_get_line(file):
            # get the key value pair
            key, value = [x.strip() for x in line.partition('=')[::2]]
            if not key:
                self._parse_exception('Expected: metadata key')

            # special case the album art key
            if key == 'album_art' or key == 'album_cover':
                self._manifest.album_art = value
            else:
                self._manifest.key_value_pairs[key] = value

    def _parse_chapter(self, file, chapter):
        # find or append the chapter
        chapter_matches = [x for x in \
                            self._manifest.chapters if x['name'] == chapter]
        if len(chapter_matches) > 0:
            c = chapter_matches[-1]
        else:
            c = {
                'name': chapter,
                'files': files
            }
            self._manifest.chapters.append(c)

        # accumulate a list of files
        files = c['files']
        while line := self._parse_get_line(file):
            files.append(line)
            self._manifest.files.append(line)


class CsvParser:
    def __init__(self, input_filename, manifest):
        self._parse_file_name = input_filename
        self._parse_line_number = 0

        with open(input_filename, 'r', newline='', encoding='utf-8') as input_file:
            chapters = self._parse(input_file)

        # Merge chapters and files into the manifest
        for c in chapters:
            chapter_matches = [x for x in \
                               manifest.chapters if x['name'] == c['name']]
            if len(chapter_matches) == 0:
                manifest.chapters.append(c)
            else:
                chapter_matches[-1]['files'].extend(c['files'])

            manifest.files.extend(c['files'])

    def _parse(self, input_file):
        # ordered chapter names
        chapter_names = []
        # map of file lists for each chapter
        chapter_map = {}

        def add_file(file, chap):
            if not chap in chapter_map:
                chapter_names.append(chap)
                chapter_map[chap] = []

            # Add tuple of name and duration
            chapter_map[chap].append(file)

        # Read the CSV file
        reader = csv.reader(input_file, delimiter=',', quotechar='"')
        self._parse_line_number = 0
        for row in reader:
            self._parse_line_number += 1
            if len(row) > 1:
                add_file(row[0], row[1])
            elif len(row) > 0:
                raise ParseException(
                    f"Expected <filename>,<chapter>: '{row}'",
                    self._parse_file_name,
                    self._parse_line_number)

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


class FFmpegCommandLine:
    def __init__(self, output_file=None, format='mp4', overwrite=False):
        self._input_files = []
        self._base = [
            'ffmpeg',
            '-v', 'error'
        ]
        self._format = format
        self._args = []
        self.set_output(output_file, overwrite)

    def __str__(self):
        return ' '.join([f"'{a}'" for a in self.get_cmdline()])

    def add_args(self, *args):
        self._args.extend([str(arg) for arg in args])

    # adds a metadata input and maps it
    def add_metadata_file(self, file):
        index = self.add_file(file)
        self.add_args('-map_metadata', index)
        return index

    # maps a file index to a stream index
    def add_map(self, file_index, stream_index):
        self.add_args('-map', f'{file_index}:{stream_index}')

    # adds album art to a given stream
    def add_album_art_to_index(self, art_file, stream_index):
        # add the art file as input
        art_index = self.add_file(art_file)
        # map the art file to the main stream
        self.add_map(art_index, stream_index)
        # add extra args
        self.add_args(
            '-id3v2_version', 3,
            '-metadata:s:v', 'title="Album cover"',
            '-metadata:s:v', 'comment="Cover (front)"'
        )
        return art_index

    def add_file(self, file, mapping=None, pre_input_args=[]):
        index = len(self._input_files)
        self._input_files.append((file, pre_input_args))
        if mapping != None:
            self.add_map(index, mapping)
        return index

    def set_output(self, file, overwrite=False):
        self._output_file = file
        self._overwrite = overwrite

    def get_cmdline(self):
        cl = list(self._base)

        for file in self._input_files:
            cl.extend(file[1])
            cl.append('-i')
            cl.append(file[0])

        if self._format:
            cl.extend(['-f', self._format])

        cl.extend(self._args)

        if self._overwrite:
            cl.append('-y')
        if self._output_file:
            cl.append(self._output_file)
        return cl


def make_temporary_filename(base_filename, new_extension=None):
    path_parts = Path(base_filename)
    if not new_extension:
        new_extension = path_parts.suffix
    return tempfile.mkstemp(
        dir=path_parts.parent,
        prefix=path_parts.stem,
        suffix=f'.tmp{new_extension}')


def get_file_metadata(file_name):
    cmd = FFmpegCommandLine(
        output_file='-',
        overwrite=True,
        format='ffmetadata')
    cmd.add_file(file_name)

    input_data, _ = run_custom(cmd.get_cmdline())

    metadata = {}

    lines = input_data.decode("utf-8").split('\n')

    if len(lines) == 0:
        return metadata

    if lines[0] != ';FFMETADATA1':
        raise RuntimeError(f'Unknown metadata format: "{lines[0]}"')

    # Convert to key value pairs
    for line in lines[1:]:
        key, value = [x.strip() for x in line.partition('=')[::2]]
        metadata[key] = value

    return metadata


def _copy_metadata(metadata, overrides):
    for key, value in overrides.items():
        if not key:
            continue
        if value == None: # this is a delete
            if key in metadata:
                del metadata[key]
        else:
            metadata[key] = value


def merge_metadata(*overrides):
    metadata = {}
    for i in overrides:
        _copy_metadata(metadata, i)
    return metadata


def write_metadata_file(
    metadata,
    chapters,
    output_file
):
    chapter_start = 0
    chapter_end = 0
    num_segments = 0

    output_file.write(';FFMETADATA1\n')

    for key, value in metadata.items():
        output_file.write(f'{key}={value}\n')

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

        # todo: escape special characters (‘=’, ‘;’, ‘#’, ‘\’ and a newline)
        output_file.write(f'title={chapter["name"]}\n')

        chapter_start = chapter_end


def write_merged_audio_file(chapters, ffmetadata_filename, album_art_filename, output_filename):

    # Build a commandline for the *output*
    encode_cmd = FFmpegCommandLine()
    encode_cmd.add_file('pipe:0', 0, pre_input_args=[
        '-f', 's16le',
        '-ac', '2',
        '-ar', '44100'
    ])
    encode_cmd.add_metadata_file(ffmetadata_filename)
    if album_art_filename:
        encode_cmd.add_album_art_to_index(album_art_filename, 0)
    encode_cmd.set_output(output_filename, True)

    # This is the output process. We'll stream data to this via its stdin.
    output_process = run_stream(encode_cmd.get_cmdline())

    # Open the input pipe and send each file over for processing
    files = []
    for chapter in chapters:
        for file, duration in chapter['files']:
            files.append(file)

    with tqdm(total=len(files)) as pbar:
        for file in files:
            pbar.set_description(f'Writing {file}')

            decode_cmd = FFmpegCommandLine(format='s16le')
            decode_cmd.add_file(file)
            decode_cmd.add_args(
                '-ac', '2',
                '-ar', '44100'
            )
            decode_cmd.set_output('-', overwrite=True)

            # convert the file to PCM on-the-fly
            input_data, _ = run_custom(decode_cmd.get_cmdline())

            # check the process health
            ret = output_process.poll()
            if ret:
                err = bytes.decode(output_process.stderr.read())
                raise RuntimeError(f'ffmpeg aborted unexpectedly: {err}')

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


def update_audio_file(ffmetadata_filename, album_art_filename, output_filename):
    # create a temporary file that we'll use to overwrite the original
    _, temp_filename = make_temporary_filename(output_filename)

    # Build a commandline
    copy_cmd = FFmpegCommandLine()
    copy_cmd.add_file(output_filename, 0)
    copy_cmd.add_metadata_file(ffmetadata_filename)
    if album_art_filename:
        copy_cmd.add_album_art_to_index(album_art_filename, 0)
    copy_cmd.add_args('-codec', 'copy')
    copy_cmd.set_output(temp_filename, True)

    try:
        # annotate the original with the "copy" codec
        run_custom(copy_cmd.get_cmdline(), capture_stdout=False)

        # move the file over the original
        shutil.move(temp_filename, output_filename)
    except Exception as e:
        # Something went wrong, so delete the temporary file
        os.remove(temp_filename)
        # Rethrow the exception
        raise e


def get_chapter_metadata(input_chapters):
    chapters = []

    # quickly tally the number of files
    file_count = 0
    for input_chapter in input_chapters:
        file_count += len(input_chapter['files'])

    with tqdm(total=file_count) as pbar:
        for input_chapter in input_chapters:
            files = []
            c = {
                'name': input_chapter['name'],
                'files': files
            }
            for file in input_chapter['files']:
                pbar.set_description(f'Analyzing {file}')

                # resolve the filename
                file = os.path.abspath(file)

                # Probe the file for length
                duration_str, err = run_custom(['ffprobe',
                                            '-i', file,
                                            '-show_entries', 'format=duration',
                                            '-v', 'error',
                                            '-of', 'csv=p=0'])

                # Add tuple of name and duration
                files.append((file, float(duration_str.strip())))

                pbar.update(1)

            chapters.append(c)

    return chapters


def parse_command_line():
    parser = argparse.ArgumentParser()

    parser.add_argument('input_filenames', type=str, nargs='+', metavar="FILE",
                        help='A manifest, or CSV file listing <"file","chapter">.')
    parser.add_argument('-o', '--output', type=str, required=False,
                        dest='output_filename',
                        help='The output filename.')
    parser.add_argument('-u', '--update', action='store_true',
                        dest='update_only',
                        help="Update metadata only; don't process audio data.")
    parser.add_argument('--no-default-meta', action='store_true',
                        help="*Don't* overwrite metadata with some built-in defaults.")
    parser.add_argument('--no-inherit-meta', action='store_true',
                        help="*Don't* inherit metadata from the first input file.")
    parser.add_argument('-r', '--root', type=str, dest='root_dir',
                        help="The base directory to work from.")

    args = parser.parse_args()

    if len(args.input_filenames) == 0:
        raise RuntimeError('Expected input filenames')

    # Derive a filename if output file is not provided
    if not args.output_filename:
        args.output_filename = f'{Path(args.input_filenames[0]).stem}.m4b'

    # Ensure both input and output paths are fully qualified
    args.input_filenames = [os.path.abspath(x) for x in args.input_filenames]
    args.output_filename = os.path.abspath(args.output_filename)

    # Derive the root if not provided
    if not args.root_dir:
        args.root_dir = os.path.dirname(args.input_filenames[0])

    return args


if __name__ == '__main__':
    # parse command line
    args = parse_command_line()

    # set the current working directory to the directory of the input file
    # so that relative paths work correctly
    os.chdir(args.root_dir)

    # Read the manifest(s)
    manifest = Manifest()
    for input_file in args.input_filenames:
        if input_file.endswith('.csv'):
            CsvParser(input_file, manifest)
        else:
            ManifestParser(input_file, manifest)

    # Abort if there are no files
    if len(manifest.files) == 0:
        raise RuntimeError(
            f'No input files in {",".join(args.input_filenames)}')

    # get metadata from the first file and merge it into all the rest
    title = Path(args.input_filenames[0]).stem
    default_metadata = {
        'genre': 'Audiobook',
        'title': title,
        'album': title,
    }
    # delete some entries:
    cleanup_metadata = {
        'track': None,
        'TLEN': None,
        'iTunPGAP': None,
        'iTunNORM': None,
        'TIT1': None,
    }
    metadata = merge_metadata(
        get_file_metadata(manifest.files[0]) \
            if not args.no_inherit_meta else {},
        cleanup_metadata,
        default_metadata if not args.no_default_meta else {},
        manifest.key_value_pairs
    )

    # check the album art if any
    if manifest.album_art and not os.path.isfile(manifest.album_art):
        raise FileNotFoundError(f'File not found: {manifest.album_art}')

    # get chapter metadata from the input files
    chapters = get_chapter_metadata(manifest.chapters)

    # Write the metadata file with the chapters and stuff
    ffmetadata_fd, ffmetadata_filename = make_temporary_filename(
        args.output_filename, '.txt')
    try:
        with os.fdopen(ffmetadata_fd, 'w') as ffmetadata_file:
            write_metadata_file(
                metadata,
                chapters,
                ffmetadata_file)

        # Write the merged file
        if args.update_only and os.path.isfile(args.output_filename):
            update_audio_file(
                ffmetadata_filename,
                manifest.album_art,
                args.output_filename)
        else:
            write_merged_audio_file(
                chapters,
                ffmetadata_filename,
                manifest.album_art,
                args.output_filename)
    finally:
        os.remove(ffmetadata_filename)

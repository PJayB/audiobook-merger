#!/usr/bin/python3
import ffmpeg
from pprint import pprint

# todo: find album art from any of the inputs and use that
# todo: take optional album art from command line
# todo: derive chapter markers, make timestamps meta file, use it

if __name__ == '__main__':
    files = [
        "H:/Audiobooks/Terry Pratchett/Night Watch/01 001.mp3",
        "H:/Audiobooks/Terry Pratchett/Night Watch/02 002.mp3",
    ]

    inputs = []
    for file in files:
        input_file = ffmpeg.input(file)

        inputs.append(
            input_file.audio
            # todo: convert to pcm?
        )

        #pprint(ffmpeg.probe(file)) # this might get you the title and author? ['format']['tags']['album'/'artist']

    metadata = {
        #"metadata": "title=Hello There", # redundant - copied from source
        #"metadata": "artist=General Kenobi", # redundant - copied from source
    }

    # merge the audio tracks
    audio = ffmpeg.concat(inputs[0], inputs[1], n=len(inputs), a=1, v=0)

    # converting to wav, for reference:
    #.output('output.wav', format='wav', acodec='pcm_s16le', ac=2, ar=44100) # todo: need rf64

    out, something = (ffmpeg
                        .output(audio, 'output.mp4', format='mp4', map_metadata=1, id3v2_version=3, **metadata)
                        .overwrite_output()
                        .run()
    )


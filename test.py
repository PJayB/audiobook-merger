#!/usr/bin/python3
import ffmpeg

# todo: find album art from any of the inputs and use that
# todo: take optional album art from command line
# todo: derive chapter markers, make timestamps meta file, use it

if __name__ == '__main__':
    files = [
        "../Night Watch/01 001.mp3",
        "../Night Watch/02 002.mp3"
    ]

    inputs = []
    for file in files:
        inputs.append(
            ffmpeg.input(file).audio
            # todo: convert to pcm?
        )

    out, something = (ffmpeg
                        .concat(inputs[0], inputs[1], n=len(inputs), a=1, v=0)
                        #.output('output.wav', format='wav', acodec='pcm_s16le', ac=2, ar=44100) # todo: need rf64
                        .output('output.mp4', format='mp4') # todo: need rf64
                        .overwrite_output()
                        .run()
    )


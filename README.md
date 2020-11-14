# FBED - FFmpeg Batch Encoding Dashboard

A commandline python application for monitoring the progress of video encoding with FFmpeg.
FBED makes use of [ffmpeg-python]() and [urwid]().

## Usage

`fbed.py` takes the number of parallel ffmpeg tasks to run followed by the list of files
or directories to encode. If passed a directory, the script will find all videos within
the directory and its subdirectories. The encoded videos are output to `encode_output`
in the working directory.

```
Usage:
    ./reencode_videos.py <parallel_encodes> <items>...

Guide:
    <items> can be a single files or a directories. If a directory is passed all
    files in the directory and it subdirectories besides those in one named
    'encode_output' will be re-encoded
```

By default FBED will use the `h264_v4l2m2m` encoder for hardware accelerated encoding
on the Raspberry Pi 4. You may need to build FFmpeg from source to get a recent
version with some bugs in this encoder fixed (version 4.3 or higher is required).
If you're using hardware accelerated encoding on the Raspberry Pi keep in mind
the limitations of the hardware: It can only run a single 1080p encode at a time.
If your videos are lower resultion it may be able to run 2 or 3 in parallel,
but if the encoding appears to freeze check the log files written out in `encode_output`
for errors.



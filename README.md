# FBED - FFmpeg Batch Encoding Dashboard

A commandline python application for monitoring the progress of video encoding with FFmpeg.
FBED makes use of [ffmpeg-python](https://github.com/kkroening/ffmpeg-python)
and [urwid](http://urwid.org/).

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

## Configuring FBED

FBED has a few settings hard-coded in it that I found to work well for my use case.
The script will pick the output target bitrate based on the video resolution, which you
can increase or decrease as desired by editing [the script](https://github.com/Twinklebear/fbed/blob/main/fbed.py#L52-L57):

```python
# Pick bitrate based on resolution, 1080p (8Mbps), 720p (5Mbps), smaller (3Mbps)
bitrate = "3M"
if info["height"] > 720:
    bitrate = "8M"
elif info["height"] > 480:
    bitrate = "5M"
```

You can also change the encoder used to select a different hardware encoder (e.g., `h264_nvenc` on Nvidia GPUs,
`h264_qsv` on Intel GPUs, etc.) by changing the value of `c:v` in the [`encoding_args`](https://github.com/Twinklebear/fbed/blob/main/fbed.py#L58-L67)
to your desired encoder. You can also pass additional arguments to the encoder by adding them here.
If you're on the RPi4 using `h264_v4l2m2m` I recommend leaving the `num_output_buffers` and
`num_capture_buffers` as I've set them, which raises their values above the defaults of 16 and 4 respectively.
When running parallel encodes of 720p and smaller videos I would get warnings from ffmpeg that the
capture buffers where flushed out to user space, and to consider increasing them. These are set
high enough that I don't seem to get these warnings, though exceed the memory capacity of the encoder
if trying to do two 1080p streams in parallel. In that case you'd want to set them to half their current value (i.e.,
to 16 and 8 respectively). Do not modify or remove `progress` parameter, as this is required by the dashboard.

```python
encoding_args = {
    # HWAccel for RPi4, may need to pick a different encoder
    # for HW accel on other systems
    "c:v": "h264_v4l2m2m",
    "num_output_buffers": 32,
    "num_capture_buffers": 16,
    "b:v": bitrate,
    "c:a": "copy",
    "progress": f"pipe:{self.pipe_write}"
}
```


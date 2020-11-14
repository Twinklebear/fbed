import ffmpeg
import concurrent.futures
import os
import sys

output_dir = "output"

def encode_video(filename):
    out_filename = os.path.splitext(os.path.join(output_dir, os.path.basename(filename)))[0] + ".mp4"
    print(out_filename)
    stream = ffmpeg.input(filename)
    encoding_args = {
        "c:v": "libx264",
        "crf": "23",
        "c:a": "aac",
        "pix_fmt": "yuv420p"
    }
    stream = stream.output(out_filename, **encoding_args)
    stream.run(quiet=True)

if len(sys.argv) == 1:
    print("Pass a directory to convert the video files within")
    sys.exit(1)

videos = []
for in_dir in sys.argv[1:]:
    for path, dirs, files in os.walk(in_dir):
        for f in files:
            filename = os.path.join(path, f)
            try:
                probe = ffmpeg.probe(filename)
            except ffmpeg.Error as e:
                print(e.stderr)
                continue

            if len([s for s in probe["streams"] if s["codec_type"] == "video"]) == 0:
                continue
            videos.append(filename)

os.makedirs(output_dir, exist_ok=True)
with concurrent.futures.ProcessPoolExecutor() as executor:
    executor.map(encode_video, videos)


#!/usr/bin/env python3

import time
import ffmpeg
import os
import sys
import docopt
import subprocess
import datetime
import re
import asyncio
import urwid
from collections import deque

USAGE = """Reencode Videos
Usage:
    ./reencode_videos.py <parallel_encodes> <items>...

Guide:
    <items> can be a single files or a directories. If a directory is passed all
    files in the directory and it subdirectories besides those in one named
    'encode_output' will be re-encoded
"""

output_dir = "encode_output"
match_out_time = re.compile("(\d+):(\d+):(\d+\.\d+)")

def parse_out_time(out_time):
    m = match_out_time.match(out_time)
    hours = int(m.group(1))
    minutes = int(m.group(2))
    seconds_millis = float(m.group(3))
    seconds = int(seconds_millis)
    milliseconds = int((seconds_millis - seconds) * 1000)
    return datetime.timedelta(hours=hours, minutes=minutes, seconds=seconds, milliseconds=milliseconds)

class EncodingTask:
    def __init__(self, filename):
        self.out_basename = os.path.splitext(os.path.join(output_dir, os.path.basename(filename)))[0]
        self.out_filename = self.out_basename + ".mp4"
        self.stderr = open(self.out_basename + ".log", "w", encoding="utf8")
        self.pipe_read, self.pipe_write = os.pipe()
        self.pipe_read_file = os.fdopen(self.pipe_read)

        probe = ffmpeg.probe(filename)
        duration = float(probe["format"]["duration"])
        seconds = int(duration)
        milliseconds = int((duration - seconds) * 1000)
        self.duration = datetime.timedelta(seconds=seconds, milliseconds=milliseconds)

        info = [s for s in probe["streams"] if s["codec_type"] == "video"][0]
        # Pick bitrate based on resolution, 1080p (8Mbps), 720p (5Mbps), smaller (3Mbps)
        bitrate = "3M"
        if info["height"] > 720:
            bitrate = "8M"
        elif info["height"] > 480:
            bitrate = "5M"
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
        self.start = datetime.datetime.now()
        in_stream = ffmpeg.input(filename)
        video = in_stream.video.filter("format", **{"pix_fmts": "yuv420p"})
        enc = ffmpeg.output(video, in_stream.audio, self.out_filename, **encoding_args)
        args = ffmpeg.compile(enc, overwrite_output=True)
        self.proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=self.stderr, pass_fds=[self.pipe_write])
        self.encode_stats = {}

    def is_complete(self):
        encode_done = False
        while True:
            l = self.pipe_read_file.readline()
            if not l:
                break
            l = l.strip()
            key, val = l.split("=")
            if key == "out_time":
                out_time = parse_out_time(val)
                self.encode_stats["percent_done"] = (100.0 * out_time.total_seconds()) / self.duration.total_seconds()
                self.encode_stats[key] = out_time
            elif key == "fps":
                self.encode_stats[key] = float(val)
            else:
                self.encode_stats[key] = val

            if l.startswith("progress="):
                encode_done = l == "progress=end"
                break

        if not encode_done:
            speed = float(self.encode_stats["speed"][:-1])
            remaining_time = (self.duration - self.encode_stats["out_time"]) / speed
            self.encode_stats["estimate_remaining"] = remaining_time
        else:
            self.encode_stats["estimate_remaining"] = datetime.timedelta(minutes=0)

        if encode_done:
            status = self.proc.wait()
            end = datetime.datetime.now()
            self.elapsed = end - self.start
            os.close(self.pipe_write)
            os.close(self.pipe_read)
            self.stderr.write(f"Encoding finished in {str(self.elapsed)}")
            self.stderr.close()
        return encode_done

    def cancel(self):
        self.proc.terminate()
        self.proc.wait()
        os.remove(self.out_filename)
        os.remove(self.out_basename + ".log")

class EncodingManager:
    def __init__(self, videos, parallel_encodes, main_widget, todo_list, active_list, completed_list):
        self.videos = deque(videos)
        self.parallel_encodes = parallel_encodes
        self.main_widget = main_widget
        self.todo_list = todo_list
        self.active_list = active_list
        self.completed_list = completed_list
        self.active_encodes = {}

        for v in videos:
            self.todo_list.body.append(urwid.Text(v))

    def monitor_encoding(self):
        # Start more encodes if we're able to 
        if len(self.videos) > 0 and len(self.active_encodes) < self.parallel_encodes:
            self.todo_list.body.pop(0)
            v = self.videos.popleft()
            self.active_encodes[v] = EncodingTask(v)
            active_encode_ui = urwid.Pile([
                urwid.Text(v),
                urwid.Text(""),
                urwid.ProgressBar("normal", "complete"),
                urwid.Text(f"Output: {self.active_encodes[v].out_filename}"),
                urwid.Divider("-")])
            self.active_list.body.append(active_encode_ui)

        self.check_task_completion()

        total_fps = 0
        for k, enc in self.active_encodes.items():
            total_fps += enc.encode_stats["fps"]
        self.main_widget.footer.set_text(f"Todo: {len(self.videos)}. Total FPS: {round(total_fps, 2)}. ESC to Cancel/Quit")

        # Check which UI column is selected and style the title to indicate it
        columns = self.main_widget.body
        for c in columns.contents:
            title = c[0].title_widget
            if c[0] == columns.focus:
                title.set_text(("selected_column", title.text))
            else:
                title.set_text(("default_text", title.text))

    def check_task_completion(self):
        complete = []
        for k, enc in self.active_encodes.items():
            ui = [x for x in self.active_list.body if x.contents[0][0].text == k][0]
            if enc.is_complete():
                complete.append(k)
                ui.contents[1][0].set_text(f"Bitrate: {enc.encode_stats['bitrate']}\n" +
                        f"FPS: {enc.encode_stats['fps']}\n" +
                        f"Speed: {enc.encode_stats['speed']}\n" +
                        f"Elapsed: {str(enc.elapsed)}")
                ui.contents[2][0].set_completion(100)
                self.completed_list.body.append(ui)
                self.active_list.body = [x for x in self.active_list.body if x.contents[0][0].text != k]
            else:
                ui.contents[1][0].set_text(f"Bitrate: {enc.encode_stats['bitrate']}\n" +
                        f"FPS: {enc.encode_stats['fps']}\n" +
                        f"Speed: {enc.encode_stats['speed']}\n" +
                        f"Est. Remaining: {str(enc.encode_stats['estimate_remaining'])}")
                ui.contents[2][0].set_completion(enc.encode_stats["percent_done"])
        for k in complete:
            del self.active_encodes[k]

    def cancel_active_encodes(self):
        for k, enc in self.active_encodes.items():
            enc.cancel()

manager = None

def quit_on_escape(key):
    if key == "esc":
        manager.cancel_active_encodes()
        raise urwid.ExitMainLoop()

def monitor_encoding(loop, man):
    man.monitor_encoding()
    loop.set_alarm_in(0.5, monitor_encoding, user_data=man)

if __name__ == "__main__":
    args = docopt.docopt(USAGE)

    print("Collecting input video list...")
    videos = []
    for it in args["<items>"]:
        if os.path.isdir(it):
            for path, dirs, files in os.walk(it):
                if output_dir in path:
                    continue
                for f in files:
                    filename = os.path.join(path, f)
                    try:
                        probe = ffmpeg.probe(filename)
                    except ffmpeg.Error as e:
                        #print(e.stderr.decode("utf8"))
                        continue

                    if len([s for s in probe["streams"] if s["codec_type"] == "video"]) == 0:
                        continue
                    videos.append(filename)
        else:
            videos.append(it)

    os.makedirs(output_dir, exist_ok=True)
    parallel_encodes = 1
    if args["<parallel_encodes>"]:
        parallel_encodes = int(args["<parallel_encodes>"])

    # Setup our UI
    todo_list = urwid.ListBox(urwid.SimpleFocusListWalker([]))
    active_list = urwid.ListBox(urwid.SimpleFocusListWalker([]))
    completed_list = urwid.ListBox(urwid.SimpleFocusListWalker([]))
    columns = urwid.Columns([urwid.LineBox(todo_list, title="Todo"),
        urwid.LineBox(active_list, title="Active"),
        urwid.LineBox(completed_list, title="Completed")])
    frame = urwid.Frame(columns,
            header=urwid.Text("FFmpeg Batch Encoding Dashboard"),
            footer=urwid.Text(""))

    palette = [
        ("normal", "black", "light gray"),
        ("complete", "black", "dark green"),
        ("selected_column", "black", "white"),
        ("default_text", "white", "black")
    ]

    manager = EncodingManager(videos, parallel_encodes, frame, todo_list, active_list, completed_list)

    loop = urwid.MainLoop(frame,
            unhandled_input=quit_on_escape,
            palette=palette)
    loop.set_alarm_in(0.5, monitor_encoding, user_data=manager)
    loop.run()


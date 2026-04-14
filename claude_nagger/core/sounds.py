import glob
import os
import random
import subprocess
import sys
import shutil

SOUND_EXTENSIONS = (".mp3", ".wav", ".ogg", ".flac")


class SoundPlayer:
    def __init__(self, sound_dirs: list[str] | None = None):
        defaults = [
            os.path.join(os.path.dirname(__file__), "..", "..", "sounds"),  # project sounds/
            os.path.expanduser("~/bin"),  # legacy ~/bin/farts, ~/bin/hasselhoff
            os.path.join(os.path.dirname(__file__), "..", "assets"),
        ]
        self.sound_dirs = sound_dirs or defaults

    def list_categories(self) -> list[str]:
        categories = set()
        for base in self.sound_dirs:
            if not os.path.isdir(base):
                continue
            for entry in os.listdir(base):
                full = os.path.join(base, entry)
                if os.path.isdir(full):
                    for f in os.listdir(full):
                        if any(f.lower().endswith(ext) for ext in SOUND_EXTENSIONS):
                            categories.add(entry)
                            break
        return sorted(categories)

    def list_category(self, category: str) -> list[str]:
        files = []
        for base in self.sound_dirs:
            cat_dir = os.path.join(base, category)
            if not os.path.isdir(cat_dir):
                continue
            for f in os.listdir(cat_dir):
                if any(f.lower().endswith(ext) for ext in SOUND_EXTENSIONS):
                    files.append(os.path.join(cat_dir, f))
        return sorted(files)

    def pick_random(self, category: str) -> str | None:
        files = self.list_category(category)
        return random.choice(files) if files else None

    def play(self, filepath: str) -> None:
        if not os.path.exists(filepath):
            return
        if sys.platform == "win32":
            subprocess.Popen(
                ["powershell", "-c",
                 f"(New-Object Media.SoundPlayer '{filepath}').PlaySync()"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        else:
            for cmd in ["ffplay", "cvlc", "aplay"]:
                if shutil.which(cmd):
                    args = {
                        "ffplay": [cmd, "-nodisp", "-autoexit", "-loglevel", "quiet", filepath],
                        "cvlc": [cmd, "--play-and-exit", "--no-loop", filepath],
                        "aplay": [cmd, filepath],
                    }[cmd]
                    subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    return

    def play_random(self, category: str) -> None:
        path = self.pick_random(category)
        if path:
            self.play(path)

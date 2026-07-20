"""Non-blocking local speech feedback with neural Japanese TTS."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading


class Speaker:
    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self._process = None
        self._lock = threading.Lock()

    def speak(self, text: str):
        if not self.enabled or not text.strip():
            return
        threading.Thread(target=self._speak_now, args=(text,), daemon=True).start()

    def stop(self):
        with self._lock:
            process = self._process
            self._process = None
        if process is not None and process.poll() is None:
            process.terminate()

    def _speak_now(self, text: str):
        self.stop()
        if sys.platform.startswith("linux") and self._speak_with_piper(text):
            return
        command = self._native_command(text)
        if command is None:
            print("[speech] Japanese text-to-speech is unavailable; skipping audio.")
            return
        self._run(command)

    def _speak_with_piper(self, text: str) -> bool:
        root = Path.home() / ".cache" / "voice-term" / "tts"
        binary = root / "piper" / "bin" / "piper"
        library_dir = root / "piper" / "lib"
        model = root / "models" / "tsukuyomi-chan-6lang-fp16.onnx"
        config = root / "models" / "config.json"
        player = shutil.which("pw-play") or shutil.which("aplay")
        if not (binary.is_file() and model.is_file() and config.is_file() and player):
            return False

        wav_path = None
        try:
            handle = tempfile.NamedTemporaryFile(prefix="voice-term-", suffix=".wav", delete=False)
            wav_path = handle.name
            handle.close()
            env = os.environ.copy()
            env["LD_LIBRARY_PATH"] = str(library_dir) + os.pathsep + env.get("LD_LIBRARY_PATH", "")
            synth = [
                str(binary), "--model", str(model), "--config", str(config),
                "--language", "ja", "--noise_scale", "0.5", "--length_scale", "1.05",
                "--text", text, "--output_file", wav_path, "--quiet",
            ]
            if not self._run(synth, env=env):
                return False
            return self._run([player, wav_path])
        finally:
            if wav_path:
                try:
                    Path(wav_path).unlink(missing_ok=True)
                except OSError:
                    pass

    def _run(self, command, env=None) -> bool:
        process = None
        try:
            process = subprocess.Popen(
                command, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            with self._lock:
                self._process = process
            return process.wait() == 0
        except Exception as exc:
            print(f"[speech] Failed: {exc}")
            return False
        finally:
            with self._lock:
                if process is not None and self._process is process:
                    self._process = None

    @staticmethod
    def _native_command(text: str):
        if sys.platform == "win32":
            script = (
                "Add-Type -AssemblyName System.Speech;"
                "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer;"
                "$s.Speak($args[0])"
            )
            return ["powershell.exe", "-NoProfile", "-Command", script, text]
        if sys.platform == "darwin":
            return ["say", text]
        # Do not fall back to speech-dispatcher/espeak for Japanese: on systems
        # without a Japanese voice they spell Unicode categories such as
        # "Japanese Letter" and "Chinese Letter" instead of reading the text.
        return None

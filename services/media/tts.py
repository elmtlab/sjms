"""Pluggable TTS adapter layer.

Contract: synth(text, voice, rate, out_wav) -> TTSResult
  - audio written as 44.1kHz stereo WAV at out_wav
  - duration in seconds (measured from the actual audio, not estimated)
  - words: word-level timestamps [{word, start, end}] when the provider
    supports them (edge does; `say` does not)

Providers are swappable behind get_tts(); production swaps in Volcengine /
iFlytek by adding a class here — callers never change.
"""
import asyncio
import subprocess


class TTSResult:
    def __init__(self, audio_path, duration, words=None, chars=0):
        self.audio_path = audio_path
        self.duration = duration
        self.words = words or []
        self.chars = chars

    def as_dict(self):
        return {"audio_path": self.audio_path, "duration": self.duration,
                "words": self.words, "chars": self.chars}


def _probe_duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", path],
        capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


def _to_wav(src, dst):
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", src,
                    "-ar", "44100", "-ac", "2", dst], check=True)


class EdgeTTS:
    """Microsoft Edge neural voices via the edge-tts package."""

    def synth(self, text, voice, rate, out_wav):
        import edge_tts

        mp3 = out_wav + ".mp3"
        words = []

        async def run():
            # edge-tts >= 7 defaults to SentenceBoundary; word-level
            # timestamps are part of the adapter contract (karaoke subtitles)
            com = edge_tts.Communicate(text, voice, rate=rate,
                                       boundary="WordBoundary")
            with open(mp3, "wb") as f:
                async for chunk in com.stream():
                    if chunk["type"] == "audio":
                        f.write(chunk["data"])
                    elif chunk["type"] == "WordBoundary":
                        words.append({
                            "word": chunk["text"],
                            "start": chunk["offset"] / 1e7,
                            "end": (chunk["offset"] + chunk["duration"]) / 1e7,
                        })

        asyncio.run(run())
        _to_wav(mp3, out_wav)
        return TTSResult(out_wav, _probe_duration(out_wav), words, len(text))


class SayTTS:
    """macOS `say` fallback — offline, no word timestamps."""

    def synth(self, text, voice, rate, out_wav):
        aiff = out_wav + ".aiff"
        v = voice if not voice.startswith("zh-CN-") else "Tingting"
        subprocess.run(["say", "-v", v, "-o", aiff, text], check=True)
        _to_wav(aiff, out_wav)
        return TTSResult(out_wav, _probe_duration(out_wav), [], len(text))


_PROVIDERS = {"edge": EdgeTTS, "say": SayTTS}


def get_tts(provider="edge"):
    return _PROVIDERS[provider]()

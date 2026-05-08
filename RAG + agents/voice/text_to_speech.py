import os
import uuid
import re
from gtts import gTTS
from pydub import AudioSegment

os.makedirs("audio", exist_ok=True)

# ----------------------------------------
# CLEAN TEXT (Urdu safe cleaning)
# ----------------------------------------
def clean_text(text: str) -> str:
    # Remove symbols that break gTTS
    text = re.sub(r"[^\u0600-\u06FFA-Za-z0-9 .,؟!?]", " ", text)
    text = text.replace("  ", " ")
    return text.strip()


# ----------------------------------------
# CHUNK long text (gTTS max ~200 chars)
# ----------------------------------------
def chunk_text(text, limit=180):
    words = text.split()
    chunks = []
    current = ""

    for w in words:
        if len(current) + len(w) + 1 > limit:
            chunks.append(current)
            current = w
        else:
            current += " " + w if current else w

    if current:
        chunks.append(current)

    return chunks


# ----------------------------------------
# MAIN TTS — Google TTS only (no ElevenLabs for playback)
# ----------------------------------------
def generate_tts(text: str, lang="ur"):
    cleaned = clean_text(text)
    chunks = chunk_text(cleaned)

    file_path = f"audio/{uuid.uuid4()}.mp3"
    combined = None

    for ch in chunks:
        tts = gTTS(ch, lang=lang, slow=False)  # slow=False = faster speech
        temp_file = f"audio/temp_{uuid.uuid4()}.mp3"
        tts.save(temp_file)

        segment = AudioSegment.from_mp3(temp_file)

        if combined is None:
            combined = segment
        else:
            combined += segment  # append smoothly

        os.remove(temp_file)

    combined.export(file_path, format="mp3")
    return file_path

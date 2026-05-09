import os

# =============================================================================
# STT BACKEND SELECTOR
# -----------------------------------------------------------------------------
# Set STT_BACKEND in your .env (or environment) to choose which engine runs:
#
#   STT_BACKEND=elevenlabs   → uses ElevenLabs Scribe v2 API  (default)
#   STT_BACKEND=whisper      → uses local fine-tuned Whisper model
#
# When switching:
#   • To go back to local Whisper: set STT_BACKEND=whisper  (or comment the
#     ElevenLabs block and un-comment the Whisper block below).
#   • No other file needs to change — the public interface is identical.
# =============================================================================

_STT_BACKEND = os.getenv("STT_BACKEND", "elevenlabs").strip().lower()

# ─────────────────────────────────────────────────────────────────────────────
# BACKEND A — ElevenLabs Scribe v2 (API)          ← ACTIVE when STT_BACKEND=elevenlabs
# ─────────────────────────────────────────────────────────────────────────────
if _STT_BACKEND == "elevenlabs":
    from elevenlabs.client import ElevenLabs as _ElevenLabsClient

    # Strip whitespace/newlines — pasted Railway vars sometimes include trailing spaces.
    _ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "").strip()
    if not _ELEVENLABS_API_KEY:
        raise RuntimeError(
            "ELEVENLABS_API_KEY is not set. "
            "Add it to your .env file or set STT_BACKEND=whisper to use the local model."
        )

    _el_client = _ElevenLabsClient(api_key=_ELEVENLABS_API_KEY)

    def warmup_transcriber() -> None:
        """No-op for API backend — no model to warm up."""
        print("[STT] ElevenLabs Scribe v2 — API mode, no warmup required.")

    def transcribe_audio(audio_path: str, language_hint: str = "ur") -> str:
        """
        Transcribe audio using ElevenLabs Scribe v2.

        Returns:
            Urdu text when language_hint == 'ur' (raw transcription, NOT translated).
            English text when language_hint == 'en'.

        The caller (main.py) is responsible for passing the Urdu text through
        translate_urdu_to_english() before sending it to the LLM.
        """
        normalized_hint = (language_hint or "ur").strip().lower()
        if normalized_hint not in {"ur", "en"}:
            normalized_hint = "ur"

        # ElevenLabs language codes for Urdu / English
        lang_code = "ur" if normalized_hint == "ur" else "en"

        with open(audio_path, "rb") as audio_file:
            result = _el_client.speech_to_text.convert(
                file=audio_file,
                model_id="scribe_v2",
                language_code=lang_code,
                tag_audio_events=False,   # no [laughter] / [applause] tags needed
                diarize=False,            # single speaker — customer at kiosk
            )

        # SDK returns a SpeechToTextChunkResponseModel; .text is the transcript
        return (result.text or "").strip()

# ─────────────────────────────────────────────────────────────────────────────
# BACKEND B — Local Fine-tuned Whisper             ← ACTIVE when STT_BACKEND=whisper
# ─────────────────────────────────────────────────────────────────────────────
elif _STT_BACKEND == "whisper":
    import wave
    import numpy as np
    import torch
    import librosa
    from transformers import WhisperProcessor, WhisperForConditionalGeneration

    # Resolve model path relative to this repo, or override via .env
    _DEFAULT_MODEL_PATH = os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "..", "voice", "whisper_urdu_final")
    )
    MODEL_PATH = os.getenv("WHISPER_MODEL_PATH", _DEFAULT_MODEL_PATH)

    print("Loading Whisper model (safetensors)...")
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print("Device =", device)
    print("Whisper model path =", MODEL_PATH)

    # Load processor
    processor = WhisperProcessor.from_pretrained(MODEL_PATH)

    # Load model (supports safetensors automatically)
    model = WhisperForConditionalGeneration.from_pretrained(
        MODEL_PATH,
        dtype=torch.float32,   # safe for CPU
        low_cpu_mem_usage=True
    ).to(device)

    def warmup_transcriber() -> None:
        # File-free warmup to avoid dependency on empty.wav validity.
        sr = 16000
        audio = np.zeros(sr, dtype=np.float32)
        inputs = processor(audio, sampling_rate=sr, return_tensors="pt")
        input_features = inputs.input_features.to(device)
        with torch.inference_mode():
            model.generate(
                input_features,
                max_new_tokens=8,
                num_beams=1,
                do_sample=False,
                language="ur",
                task="transcribe",
            )

    def transcribe_audio(audio_path: str, language_hint: str = "ur") -> str:
        # Fast path for PCM WAV (used by Flutter voice recorder now).
        # Avoids slow/fragile librosa audioread fallback on some Windows setups.
        audio = None
        sr = 16000
        try:
            with wave.open(audio_path, "rb") as wf:
                if wf.getnchannels() == 1 and wf.getsampwidth() == 2:
                    sr = wf.getframerate()
                    frames = wf.readframes(wf.getnframes())
                    audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
        except Exception:
            audio = None

        if audio is None:
            # Fallback for non-WAV or unsupported WAV.
            audio, sr = librosa.load(audio_path, sr=None, mono=True, duration=9.0)

        # Keep ASR bounded for command-style voice UX.
        max_samples = int(sr * 9)
        if audio.shape[0] > max_samples:
            audio = audio[:max_samples]

        if sr != 16000:
            audio = librosa.resample(audio, orig_sr=sr, target_sr=16000)
            sr = 16000

        inputs = processor(
            audio,
            sampling_rate=sr,
            return_tensors="pt"
        )
        input_features = inputs.input_features.to(device)
        attention_mask = getattr(inputs, "attention_mask", None)
        if attention_mask is not None:
            attention_mask = attention_mask.to(device)

        normalized_hint = (language_hint or "ur").strip().lower()
        if normalized_hint not in {"ur", "en"}:
            normalized_hint = "ur"
        # Urdu/Hindi speech is translated to English for downstream NLP.
        if normalized_hint == "ur":
            gen_kwargs = {"language": "ur", "task": "translate"}
        else:
            gen_kwargs = {"language": "en", "task": "transcribe"}

        with torch.inference_mode():
            predicted_ids = model.generate(
                input_features,
                attention_mask=attention_mask,
                max_new_tokens=96,
                num_beams=1,
                do_sample=False,
                **gen_kwargs,
            )
        text = processor.batch_decode(
            predicted_ids,
            skip_special_tokens=True
        )[0]

        return text

# ─────────────────────────────────────────────────────────────────────────────
else:
    raise ValueError(
        f"Unknown STT_BACKEND={_STT_BACKEND!r}. "
        "Valid values: 'elevenlabs' (default) or 'whisper'."
    )

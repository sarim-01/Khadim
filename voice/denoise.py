import librosa
import noisereduce as nr
import soundfile as sf
import matplotlib.pyplot as plt
import numpy as np

AUDIO_PATH = r"C:\Users\zaina\OneDrive\Desktop\Khadim-Whisper\Test audio.m4a"

#audio
audio, sr = librosa.load(AUDIO_PATH, sr=16000)
print(f"Loaded audio: {AUDIO_PATH}")
print(f"Sample rate: {sr}, Duration: {len(audio)/sr:.2f}s")

print("\nApplying noise reduction...")
denoised_audio = nr.reduce_noise(y=audio, sr=sr)

sf.write("original_audio.wav", audio, sr)
sf.write("denoised_audio.wav", denoised_audio, sr)
print("Saved 'original_audio.wav' and 'denoised_audio.wav' for comparison.")

print(f"\nAverage amplitude before: {np.mean(np.abs(audio)):.6f}")
print(f"Average amplitude after:  {np.mean(np.abs(denoised_audio)):.6f}")

plt.figure(figsize=(12, 5))

#plots
plt.subplot(2, 1, 1)
plt.plot(audio, color='gray')
plt.title("Original Audio")
plt.xlabel("Samples")
plt.ylabel("Amplitude")

plt.subplot(2, 1, 2)
plt.plot(denoised_audio, color='green')
plt.title("Denoised Audio")
plt.xlabel("Samples")
plt.ylabel("Amplitude")

plt.tight_layout()
plt.show()


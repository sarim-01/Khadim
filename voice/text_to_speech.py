from gtts import gTTS
import os

# Urdu text from Whisper transcription
urdu_text = "السلام علیکم، مجھے بریانی چاہیے اور ایک پلاؤ چاہیے۔ بریانی آپ نے تھوڑی اسپائسی رکھنی ہے۔"

# Convert to speech
tts = gTTS(text=urdu_text, lang='ur')

# Save as mp3
output_path = r"D:\FAST\FYP\Khadim\voice\urdu_output.mp3"
tts.save(output_path)

print(f"Audio saved at: {output_path}")
os.system(f'start {output_path}')  # plays the file (on Windows)
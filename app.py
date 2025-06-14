from flask import Flask, render_template, request, jsonify
import google.generativeai as genai
from google.cloud import texttospeech
import os
import time

app = Flask(__name__)

# Настройка Gemini API
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
gemini_model = genai.GenerativeModel("gemini-pro")

# Google Cloud TTS client (предполагается, что GOOGLE_APPLICATION_CREDENTIALS установлен)
tts_client = texttospeech.TextToSpeechClient()

def generate_tts(text, filename):
    synthesis_input = texttospeech.SynthesisInput(text=text)
    voice = texttospeech.VoiceSelectionParams(
        language_code="ru-RU",
        name="ru-RU-Wavenet-C"
    )
    audio_config = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3)

    response = tts_client.synthesize_speech(input=synthesis_input, voice=voice, audio_config=audio_config)
    path = os.path.join("static", "voices", filename)
    with open(path, "wb") as out:
        out.write(response.audio_content)
    return f"/static/voices/{filename}"

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/start", methods=["POST"])
def start_radio():
    username = request.json.get("username", "Гость")
    greeting = f"Привет, {username}! Что ты хочешь послушать? Можешь написать или подожди немного — я сам что-нибудь включу."
    tts_path = generate_tts(greeting, f"greeting_{int(time.time())}.mp3")
    return jsonify({"voice": tts_path})

@app.route("/suggest", methods=["POST"])
def suggest():
    user_input = request.json.get("input")

    if not user_input:
        topic = "что-нибудь спокойное и приятное"
    else:
        topic = user_input

    prompt = f"Предложи трек по запросу: '{topic}'. Ответь в формате: Название — Исполнитель."
    response = gemini_model.generate_content(prompt)
    song = response.text.strip().split("\n")[0]

    voice_intro = f"Вот что я нашёл: {song}. Надеюсь, тебе понравится!"
    tts_path = generate_tts(voice_intro, f"song_{int(time.time())}.mp3")

    # Пока просто один трек — заглушка
    music_path = "/static/music/sample.mp3"

    return jsonify({"voice": tts_path, "track": music_path, "title": song})

if __name__ == "__main__":
    app.run(debug=True)

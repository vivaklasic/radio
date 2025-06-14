import os
import random
import json
import gspread
import google.generativeai as genai
from flask import Flask, jsonify, request
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)
CORS(app)

# --- Настройка (без изменений) ---
# ... (весь ваш блок настройки остается без изменений) ...
tracks_worksheet = None
model = None

try:
    gcp_credentials_json = os.getenv('GCP_CREDENTIALS')
    if gcp_credentials_json:
        credentials_dict = json.loads(gcp_credentials_json)
        gc = gspread.service_account_from_dict(credentials_dict)
        print("Успешное подключение к Google Sheets через переменные окружения.")
    else:
        gc = gspread.service_account(filename='credentials.json')
        print("Успешное подключение к Google Sheets через локальный файл.")

    sh = gc.open_by_key('1NDTPGtwDlqo0djTQlsegZtI8-uTl1ojTtbT0PmtR5YU')
    tracks_worksheet = sh.worksheet('tracks')
    print("Успешно получен доступ к листу 'tracks'.")
except Exception as e:
    print(f"КРИТИЧЕСКАЯ ОШИБКА ПОДКЛЮЧЕНИЯ К GOOGLE SHEETS: {e}")

GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash-latest')
    print("Успешная настройка Gemini API с моделью gemini-1.5-flash-latest.")
else:
    print("КРИТИЧЕСКАЯ ОШИБКА: API ключ для Gemini не найден.")
    model = None

# --- Логика (без изменений) ---
# ... (функции get_all_tracks и format_tracks_for_ai остаются без изменений) ...
def get_all_tracks():
    if not tracks_worksheet: return []
    try: return tracks_worksheet.get_all_records()
    except Exception as e: return []

def format_tracks_for_ai(tracks):
    library_text = ""
    for track in tracks:
        track_info = (f"ID: {track.get('id', 'N/A')}, Title: {track.get('title', 'N/A')}, "
                      f"Artist: {track.get('artist', 'N/A')}, Genre: {track.get('genre', 'N/A')}, "
                      f"Mood: {track.get('mood', 'N/A')}, Description: {track.get('description', 'N/A')}\n")
        library_text += track_info
    return library_text

# --- API Эндпоинт (с новыми проверками) ---
@app.route('/')
def index():
    return "Flask-сервер для AI Радио работает!"

@app.route('/get-radio-play', methods=['POST'])
def get_radio_play():
    if not model or not tracks_worksheet:
        return jsonify({"error": "Сервер не настроен должным образом."}), 500
    try:
        data = request.get_json()
        user_request = data.get('request', 'удиви меня')
        user_name = data.get('userName', 'слушатель')
    except Exception:
        return jsonify({"error": "Неверный формат запроса"}), 400

    all_tracks = get_all_tracks()
    if not all_tracks:
        return jsonify({"error": "Библиотека музыки пуста."}), 500
        
    library_description = format_tracks_for_ai(all_tracks)

    prompt = f"""
        Ты AI-диджей. Твоя задача - составить плейлист из подходящих песен, который соответствует запросу слушателя.
        Подбери столько треков, сколько сможешь найти подходящих, но не более 5. 
        ВАЖНО: Если подходящих треков нет или их меньше двух, верни в поле "playlist" пустой массив [].
        После этого напиши одну общую, короткую и дружелюбную подводку для всего этого музыкального блока. Если плейлист пуст, твоя подводка должна говорить, что ты ничего не нашел.

        Запрос от слушателя по имени {user_name}: "{user_request}"

        Музыкальная библиотека:
        {library_description}

        Ответь в формате JSON, и только JSON.
        Структура: {{ "playlist": [ID_трека_1, ID_трека_2, ...], "speechText": "Текст твоей подводки" }}
    """

    try:
        response = model.generate_content(prompt)
        ai_data = json.loads(response.text)
        
        # Улучшенная проверка ответа от AI
        playlist_ids = ai_data.get('playlist', [])
        speech_text = ai_data.get('speechText', "Что-то пошло не так...")
        
        # Проверяем, что плейлист - это список, и он не пустой
        if not isinstance(playlist_ids, list) or not playlist_ids:
            print("AI вернул пустой или некорректный плейлист.")
            # Отправляем на фронт текст от AI, но с пустым плейлистом
            return jsonify({"speechText": speech_text, "playlist": []})

        playlist_tracks = []
        for track_id in playlist_ids:
            selected_track = next((track for track in all_tracks if int(track['id']) == int(track_id)), None)
            if selected_track:
                playlist_tracks.append({
                    "title": selected_track.get('title'),
                    "artist": selected_track.get('artist'),
                    "musicUrl": selected_track.get('music_url')
                })
        
        # Финальная проверка: если мы не смогли найти ни одного трека по ID от AI
        if not playlist_tracks:
            return jsonify({"error": "AI выбрал несуществующие треки."}), 404

        final_response = {
            "speechText": speech_text,
            "playlist": playlist_tracks 
        }
        
        return jsonify(final_response)

    except Exception as e:
        print(f"Произошла непредвиденная ошибка: {e}")
        return jsonify({"error": "Внутренняя ошибка сервера при обработке запроса"}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    app.run(debug=False, host='0.0.0.0', port=port)

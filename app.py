import os
import random
import gspread
import google.generativeai as genai
from flask import Flask, jsonify, request
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv() # Загружаем переменные окружения из файла .env

# --- НАСТРОЙКА ---

# Настройка Flask
app = Flask(__name__)
CORS(app) # Разрешаем кросс-доменные запросы (чтобы ваш сайт мог обращаться к серверу)

# Настройка доступа к Google Sheets
try:
    gc = gspread.service_account(filename='credentials.json') # Укажите путь к вашему JSON-ключу
    sh = gc.open_by_key('YOUR_GOOGLE_SHEET_KEY') # Вставьте сюда ключ вашей таблицы из URL
    tracks_worksheet = sh.worksheet('tracks') # Укажите имя листа
    print("Успешное подключение к Google Sheets.")
except Exception as e:
    print(f"Ошибка подключения к Google Sheets: {e}")
    tracks_worksheet = None

# Настройка Gemini API
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-pro')
    print("Успешная настройка Gemini API.")
else:
    print("API ключ для Gemini не найден в .env файле.")
    model = None

# --- ЛОГИКА ---

def get_all_tracks():
    """Получает все треки из Google Таблицы."""
    if not tracks_worksheet:
        return []
    records = tracks_worksheet.get_all_records() # Получаем данные как список словарей
    return records

def format_tracks_for_ai(tracks):
    """Форматирует список треков в текстовое описание для Gemini."""
    description = ""
    for track in tracks:
        description += f"ID: {track['id']}, Title: {track['title']}, Artist: {track['artist']}, Mood: {track['mood']}\n"
    return description

# --- API ЭНДПОИНТ ---

@app.route('/get-radio-play', methods=['POST'])
def get_radio_play():
    if not model or not tracks_worksheet:
        return jsonify({"error": "Сервер не настроен"}), 500

    # Получаем запрос от пользователя из тела POST-запроса
    user_request = request.json.get('request', 'удиви меня')
    user_name = request.json.get('userName', 'слушатель')

    # 1. Получаем треки и форматируем их для AI
    all_tracks = get_all_tracks()
    if not all_tracks:
        return jsonify({"error": "Не удалось загрузить треки из базы"}), 500
        
    library_description = format_tracks_for_ai(all_tracks)

    # 2. Создаем промпт для Gemini
    prompt = f"""
        Ты AI-диджей. Твоя задача - подобрать один трек из библиотеки для слушателя и написать короткую подводку.
        Запрос от слушателя по имени {user_name}: "{user_request}"

        Музыкальная библиотека:
        {library_description}

        Ответь в формате JSON, и только JSON.
        Структура: {{ "trackId": ID_трека_из_библиотеки, "speechText": "Текст твоей подводки" }}
    """

    try:
        # 3. Отправляем запрос в Gemini
        response = model.generate_content(prompt)
        # Очищаем ответ от возможных лишних символов
        clean_response = response.text.replace('```json', '').replace('```', '').strip()
        ai_data = json.loads(clean_response)
        
        selected_track_id = int(ai_data['trackId'])
        speech_text = ai_data['speechText']

        # 4. Находим выбранный трек в нашем списке
        selected_track = next((track for track in all_tracks if track['id'] == selected_track_id), None)

        if not selected_track:
            return jsonify({"error": "AI выбрал несуществующий трек"}), 404

        # 5. Собираем финальный ответ для фронтенда
        final_response = {
            "speechText": speech_text, # Здесь просто текст, не аудио
            "musicUrl": selected_track['music_url'],
            "title": selected_track['title'],
            "artist": selected_track['artist']
        }
        
        return jsonify(final_response)

    except Exception as e:
        print(f"Произошла ошибка: {e}")
        return jsonify({"error": "Внутренняя ошибка сервера при обработке запроса"}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5001)

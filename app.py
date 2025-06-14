import os
import random
import json
import gspread
import google.generativeai as genai
from flask import Flask, jsonify, request
from flask_cors import CORS
from dotenv import load_dotenv

# --- Инициализация и настройка ---
load_dotenv()
app = Flask(__name__)
# Разрешаем CORS-запросы со всех доменов для разработки
CORS(app) 

# Глобальные переменные для хранения подключений
tracks_worksheet = None
model = None

# --- Подключение к Google Sheets ---
try:
    # Пробуем подключиться через переменные окружения (для Render/Heroku)
    gcp_credentials_json = os.getenv('GCP_CREDENTIALS')
    if gcp_credentials_json:
        credentials_dict = json.loads(gcp_credentials_json)
        gc = gspread.service_account_from_dict(credentials_dict)
        print("Успешное подключение к Google Sheets через переменные окружения.")
    else:
        # Пробуем подключиться через локальный файл (для локальной разработки)
        gc = gspread.service_account(filename='credentials.json')
        print("Успешное подключение к Google Sheets через локальный файл.")

    # Открываем таблицу по ключу и получаем доступ к листу
    sh = gc.open_by_key('1NDTPGtwDlqo0djTQlsegZtI8-uTl1ojTtbT0PmtR5YU')
    tracks_worksheet = sh.worksheet('tracks')
    print("Успешно получен доступ к листу 'tracks'.")
except Exception as e:
    print(f"КРИТИЧЕСКАЯ ОШИБКА ПОДКЛЮЧЕНИЯ К GOOGLE SHEETS: {e}")

# --- Настройка Gemini API ---
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash-latest')
    print("Успешная настройка Gemini API с моделью gemini-1.5-flash-latest.")
else:
    print("КРИТИЧЕСКАЯ ОШИБКА: API ключ для Gemini не найден.")
    model = None

# --- Вспомогательные функции ---
def get_all_tracks():
    """Получает все треки из Google Sheets."""
    if not tracks_worksheet:
        print("Ошибка: объект tracks_worksheet не инициализирован.")
        return []
    try:
        return tracks_worksheet.get_all_records()
    except Exception as e:
        print(f"Ошибка при получении записей из Google Sheets: {e}")
        return []

def format_tracks_for_ai(tracks):
    """Форматирует список треков в одну строку для промпта."""
    library_text = ""
    for track in tracks:
        track_info = (f"ID: {track.get('id', 'N/A')}, Title: {track.get('title', 'N/A')}, "
                      f"Artist: {track.get('artist', 'N/A')}, Genre: {track.get('genre', 'N/A')}, "
                      f"Mood: {track.get('mood', 'N/A')}, Description: {track.get('description', 'N/A')}\n")
        library_text += track_info
    return library_text

# --- API ЭНДПОИНТЫ ---

@app.route('/')
def index():
    """Корневой эндпоинт для проверки работы сервера."""
    return "Flask-сервер для AI Радио работает!"

@app.route('/get-full-playlist', methods=['GET'])
def get_full_playlist_route():
    """Отдает всю музыкальную библиотеку в виде простого плейлиста."""
    print("Запрос на /get-full-playlist получен.")
    all_tracks = get_all_tracks()
    if not all_tracks:
        return jsonify({"error": "Библиотека музыки пуста"}), 404
    
    playlist = []
    for track in all_tracks:
        playlist.append({
            "title": track.get('title'),
            "artist": track.get('artist'),
            "musicUrl": track.get('music_url')
        })
    return jsonify({"playlist": playlist})


@app.route('/get-radio-play', methods=['POST'])
def get_radio_play():
    """Основной эндпоинт, который обращается к AI для генерации плейлиста."""
    if not model or not tracks_worksheet:
        return jsonify({"error": "Сервер не настроен должным образом (проблема с Google Sheets или Gemini API)."}), 500
    
    # Безопасно получаем данные из POST-запроса
    try:
        data = request.get_json(force=True) # force=True поможет если Content-Type неверный
        user_request = data.get('request', 'удиви меня')
        user_name = data.get('userName', 'слушатель')
    except Exception as e:
        print(f"Ошибка получения JSON из запроса: {e}")
        return jsonify({"error": "Неверный формат запроса. Ожидается JSON."}), 400

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
        Ответь в формате JSON, и только JSON. Не добавляй никаких пояснений или markdown.
        Структура: {{ "playlist": [ID_трека_1, ID_трека_2, ...], "speechText": "Текст твоей подводки" }}
    """

    raw_text = "" # Инициализируем переменную для логгирования в случае ошибки
    try:
        # --- НАЧАЛО ИЗМЕНЕНИЙ: УСИЛЕННАЯ ОБРАБОТКА ОТВЕТА ---
        response = model.generate_content(prompt)

        # 1. Проверяем, не был ли ответ заблокирован фильтрами безопасности Gemini
        if not response.parts:
            block_reason = "Причина не указана"
            if response.prompt_feedback:
                block_reason = response.prompt_feedback.block_reason
            print(f"ОТВЕТ ОТ GEMINI ЗАБЛОКИРОВАН. Причина: {block_reason}")
            return jsonify({
                "speechText": "К сожалению, ваш запрос не может быть обработан. Пожалуйста, попробуйте переформулировать его.",
                "playlist": []
            }), 400

        # 2. Безопасно извлекаем и очищаем текст от мусора
        raw_text = response.text
        json_text = raw_text.strip()
        if json_text.startswith('```json'):
            json_text = json_text[7:-3].strip()

        if not json_text:
             print("Ошибка: Gemini вернул пустой ответ.")
             raise ValueError("Gemini returned an empty string.")

        # 3. Только теперь парсим очищенный JSON
        ai_data = json.loads(json_text)
        
        # --- КОНЕЦ ИЗМЕНЕНИЙ ---
        
        playlist_ids = ai_data.get('playlist', [])
        speech_text = ai_data.get('speechText', "Что-то пошло не так...")
        
        if not isinstance(playlist_ids, list) or not playlist_ids:
            return jsonify({"speechText": speech_text, "playlist": []})

        playlist_tracks = []
        for track_id in playlist_ids:
            # ВАЖНОЕ ИСПРАВЛЕНИЕ: Сравниваем ID как строки для надежности
            selected_track = next((track for track in all_tracks if str(track['id']) == str(track_id)), None)
            if selected_track:
                playlist_tracks.append({
                    "title": selected_track.get('title'),
                    "artist": selected_track.get('artist'),
                    "musicUrl": selected_track.get('music_url')
                })
        
        if not playlist_tracks and playlist_ids:
            print(f"AI выбрал несуществующие треки с ID: {playlist_ids}")
            return jsonify({"error": "AI выбрал несуществующие треки."}), 404

        final_response = {
            "speechText": speech_text,
            "playlist": playlist_tracks 
        }
        
        return jsonify(final_response)

    # Разделяем обработку ошибок для лучшей диагностики
    except json.JSONDecodeError as e:
        print(f"ОШИБКА ДЕКОДИРОВАНИЯ JSON. Ответ от Gemini был: '{raw_text}'. Ошибка: {e}")
        return jsonify({"error": "AI вернул некорректный формат данных. Попробуйте еще раз."}), 500
    except Exception as e:
        print(f"ПРОИЗОШЛА НЕПРЕДВИДЕННАЯ ОШИБКА: {e}")
        return jsonify({"error": "Внутренняя ошибка сервера при обработке запроса"}), 500

# --- Запуск сервера ---
if __name__ == '__main__':
    # PORT берется из окружения (для Render), по умолчанию 5001 для локального запуска
    port = int(os.environ.get('PORT', 5001))
    # debug=False важно для продакшена. host='0.0.0.0' делает сервер доступным извне.
    app.run(debug=False, host='0.0.0.0', port=port)

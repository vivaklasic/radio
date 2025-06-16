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

origins = [
    "https://stop-neurodeception.web.app",      # Ваш основной сайт на Firebase
    "https://stop-neurodeception.firebaseapp.com", # Дополнительный домен Firebase (лучше добавить оба)
    # Если вы разрабатываете локально, раскомментируйте следующие строки,
    # указав порт, который использует ваш локальный сервер (например, 5500 для Live Server в VS Code).
    # "http://localhost:5500",
    # "http://127.0.0.1:5500"
]

# Применяем политику: разрешаем доступ к любым ресурсам (/*)
# только сайтам из списка 'origins'.
CORS(app, resources={r"/*": {"origins": origins}})
# --- КОНЕЦ НАСТРОЙКИ CORS ---

# Глобальные переменные для хранения подключений
tracks_worksheet = None
model = None

# --- Подключение к Google Sheets ---
sh = None

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
    print("Успешно получен доступ к таблице.")
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


# --- Вставьте этот код вместо вашей текущей функции get_radio_play ---
@app.route('/get-radio-play', methods=['POST'])
def get_radio_play():
    """Основной эндпоинт, который обращается к AI в два этапа для генерации плейлиста."""
    if not model or not sh:
        return jsonify({"error": "Сервер не настроен должным образом (проблема с Google Sheets или Gemini API)."}), 500
    
    try:
        data = request.get_json(force=True)
        user_request = data.get('request', 'удиви меня')
        user_name = data.get('userName', 'слушатель')
        lang = data.get('language', 'ru') 
    except Exception as e:
        print(f"Ошибка получения JSON из запроса: {e}")
        return jsonify({"error": "Неверный формат запроса. Ожидается JSON."}), 400

    # --- ЭТАП 1: AI ВЫБИРАЕТ ЛИСТ ---
    try:
        all_worksheets = sh.worksheets()
        worksheet_names = [ws.title for ws in all_worksheets]
        print(f"Доступные плейлисты (листы): {worksheet_names}")
    except Exception as e:
        print(f"Критическая ошибка: не удалось получить список листов. Ошибка: {e}")
        return jsonify({"error": "Не удалось загрузить список плейлистов."}), 500

    prompt_stage1 = f"""
        Ты — музыкальный менеджер. Проанализируй запрос слушателя и выбери ОДИН, самый подходящий плейлист из списка.
        В ответе укажи ТОЛЬКО ТОЧНОЕ НАЗВАНИЕ листа, без лишних слов.
        Запрос слушателя: "{user_request}"
        Список доступных плейлистов: {', '.join(worksheet_names)}
    """
    
    selected_sheet_name = ""
    try:
        response_stage1 = model.generate_content(prompt_stage1)
        selected_sheet_name = response_stage1.text.strip()
        print(f"AI выбрал плейлист: '{selected_sheet_name}'")
        if selected_sheet_name not in worksheet_names:
            print(f"Предупреждение: AI вернул несуществующее имя листа. Выбираю случайный.")
            selected_sheet_name = random.choice(worksheet_names)
    except Exception as e:
        print(f"Ошибка на 1-м этапе вызова AI: {e}. Выбираю случайный плейлист.")
        selected_sheet_name = random.choice(worksheet_names)

    # --- ЭТАП 2: AI ВЫБИРАЕТ ТРЕКИ ИЗ ЛИСТА ---
    try:
        selected_worksheet = sh.worksheet(selected_sheet_name)
        all_tracks = selected_worksheet.get_all_records()
        if not all_tracks:
            return jsonify({"error": f"Плейлист '{selected_sheet_name}' пуст."}), 500
    except gspread.exceptions.WorksheetNotFound:
         return jsonify({"error": f"Плейлист с названием '{selected_sheet_name}' не найден."}), 404
    except Exception as e:
        return jsonify({"error": f"Не удалось загрузить плейлист '{selected_sheet_name}'."}), 500
        
    library_description = format_tracks_for_ai(all_tracks)
    
    prompt_stage2 = f"""
        Ты — AI-диджей по имени Джем. Твоя задача — подобрать плейлист из примерно 1 трек из предоставленной музыкальной библиотеки (это плейлист '{selected_sheet_name}').
        После подбора треков, напиши "подводку" (speechText) к этому музыкальному блоку.
        В подводке обратись к слушателю ({user_name}), упомяни его запрос ("{user_request}") и можешь упомянуть название плейлиста '{selected_sheet_name}'.
        Твой ответ ДОЛЖЕН БЫТЬ ТОЛЬКО в формате JSON.
        ЗАПРОС ОТ СЛУШАТЕЛЯ:
        - Имя: {user_name}
        - Пожелание: "{user_request}"
        МУЗЫКАЛЬНАЯ БИБЛИОТЕКА (плейлист '{selected_sheet_name}'):
        {library_description}
        СТРУКТУРА ОТВЕТА (только JSON):
        {{
          "playlist": [ID_трека_1, ID_трека_2, ...],
          "speechText": "Текст твоей живой и интересной подводки здесь."
        }}
    """
    
    raw_text = ""
    try:
        response_stage2 = model.generate_content(prompt_stage2)
        raw_text = response_stage2.text
        json_text = raw_text.strip().replace('```json', '').replace('```', '').strip()
        ai_data = json.loads(json_text)
        
        playlist_ids = ai_data.get('playlist', [])
        speech_text = ai_data.get('speechText', "Что-то пошло не так...")
        
        playlist_tracks = []
        for track_id in playlist_ids:
            selected_track = next((track for track in all_tracks if str(track.get('id')) == str(track_id)), None)
            if selected_track:
                playlist_tracks.append({
                    "title": selected_track.get('title'),
                    "artist": selected_track.get('artist'),
                    "musicUrl": selected_track.get('music_url')
                })
        
        # --- НОВОЕ ИЗМЕНЕНИЕ: ГОТОВИМ ПОЛНЫЙ ПЛЕЙЛИСТ С ЛИСТА ---
        full_playlist_from_sheet = []
        for track in all_tracks:
            full_playlist_from_sheet.append({
                "title": track.get('title'),
                "artist": track.get('artist'),
                "musicUrl": track.get('music_url')
            })

        # --- НОВОЕ ИЗМЕНЕНИЕ: ДОБАВЛЯЕМ ПОЛНЫЙ ПЛЕЙЛИСТ В ОТВЕТ ---
        final_response = {
            "speechText": speech_text,
            "playlist": playlist_tracks,
            "full_playlist_from_sheet": full_playlist_from_sheet
        }
        
        return jsonify(final_response)

    except Exception as e:
        print(f"ПРОИЗОШЛА НЕПРЕДВИДЕННАЯ ОШИБКА НА ЭТАПЕ 2: {e}\nОтвет от Gemini был: '{raw_text}'")
        return jsonify({"error": "Внутренняя ошибка сервера при обработке запроса."}), 500

# --- Запуск сервера ---
if __name__ == '__main__':
    # PORT берется из окружения (для Render), по умолчанию 5001 для локального запуска
    port = int(os.environ.get('PORT', 5001))
    # debug=False важно для продакшена. host='0.0.0.0' делает сервер доступным извне.
    app.run(debug=False, host='0.0.0.0', port=port)

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


@app.route('/get-radio-play', methods=['POST'])
def get_radio_play():
    """Основной эндпоинт, который обращается к AI в два этапа для генерации плейлиста."""
    # Проверяем, что все глобальные объекты на месте
    if not model or not sh:
        return jsonify({"error": "Сервер не настроен должным образом (проблема с Google Sheets или Gemini API)."}), 500
    
    # Получаем данные от пользователя
    try:
        data = request.get_json(force=True)
        user_request = data.get('request', 'удиви меня')
        user_name = data.get('userName', 'слушатель')
        # Получаем язык (пока не используем в format_tracks_for_ai, но уже готово)
        lang = data.get('language', 'ru') 
    except Exception as e:
        print(f"Ошибка получения JSON из запроса: {e}")
        return jsonify({"error": "Неверный формат запроса. Ожидается JSON."}), 400

    # ===================================================================
    # ЭТАП 1: AI ВЫБИРАЕТ НУЖНЫЙ ЛИСТ (ПЛЕЙЛИСТ)
    # ===================================================================
    try:
        all_worksheets = sh.worksheets()
        worksheet_names = [ws.title for ws in all_worksheets]
        print(f"Доступные плейлисты (листы): {worksheet_names}")
    except Exception as e:
        print(f"Критическая ошибка: не удалось получить список листов из таблицы. Ошибка: {e}")
        return jsonify({"error": "Не удалось загрузить список плейлистов."}), 500

    prompt_stage1 = f"""
        Ты — музыкальный менеджер. Проанализируй запрос слушателя и выбери ОДИН, самый подходящий плейлист из списка.
        В ответе укажи ТОЛЬКО ТОЧНОЕ НАЗВАНИЕ листа, без лишних слов и знаков препинания.

        Запрос слушателя: "{user_request}"
        
        Список доступных плейлистов:
        {', '.join(worksheet_names)}
    """
    
    selected_sheet_name = ""
    try:
        response_stage1 = model.generate_content(prompt_stage1)
        selected_sheet_name = response_stage1.text.strip()
        print(f"AI выбрал плейлист: '{selected_sheet_name}'")

        if selected_sheet_name not in worksheet_names:
            print(f"Предупреждение: AI вернул несуществующее имя листа '{selected_sheet_name}'. Выбираю случайный.")
            selected_sheet_name = random.choice(worksheet_names)
            
    except Exception as e:
        print(f"Ошибка на 1-м этапе вызова AI: {e}. Выбираю случайный плейлист.")
        selected_sheet_name = random.choice(worksheet_names)

    # ===================================================================
    # ЭТАП 2: AI ВЫБИРАЕТ ТРЕКИ ИЗ ВЫБРАННОГО ЛИСТА
    # ===================================================================
    try:
        selected_worksheet = sh.worksheet(selected_sheet_name)
        all_tracks = selected_worksheet.get_all_records()
        if not all_tracks:
            return jsonify({"error": f"Плейлист '{selected_sheet_name}' пуст."}), 500
    except gspread.exceptions.WorksheetNotFound:
         return jsonify({"error": f"Плейлист с названием '{selected_sheet_name}' не найден."}), 404
    except Exception as e:
        print(f"Ошибка при получении данных с листа '{selected_sheet_name}': {e}")
        return jsonify({"error": f"Не удалось загрузить плейлист '{selected_sheet_name}'."}), 500
        
    library_description = format_tracks_for_ai(all_tracks) # Используем вашу функцию
    
    prompt_stage2 = f"""
        Ты — AI-диджей по имени Джем. Твоя личность: дружелюбная, немного остроумная и увлеченная музыкой.
        Твоя задача — проанализировать запрос слушателя и подобрать для него плейлист из примерно 10 треков из предоставленной музыкальной библиотеки (это плейлист '{selected_sheet_name}').
        
        После подбора треков, ты должен написать "подводку" (speechText) к этому музыкальному блоку.
        В своей подводке ты должен:
        1. Обратиться к слушателю по имени ({user_name}).
        2. Упомянуть, что ты понял его запрос ("{user_request}").
        3. Рассказать, сколько треков ты подобрал и почему они ему понравятся. МОЖЕШЬ УПОМЯНУТЬ НАЗВАНИЕ ПЛЕЙЛИСТА '{selected_sheet_name}', из которого ты их взял.
        4. Завершить подводку позитивной и энергичной фразой.
        
        ВАЖНО:
        - Если подходящих треков нет, верни в поле "playlist" пустой массив [].
        - Твой ответ ДОЛЖЕН БЫТЬ ТОЛЬКО в формате JSON.

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

    # Этот блок try-except остается почти без изменений, он обрабатывает второй вызов AI
    raw_text = ""
    try:
        response_stage2 = model.generate_content(prompt_stage2)

        # ... (здесь весь ваш существующий код для обработки ответа: проверка на block, парсинг json, и т.д.) ...
        if not response_stage2.parts:
            # ...
            return jsonify({ "speechText": "...", "playlist": [] }), 400

        raw_text = response_stage2.text
        json_text = raw_text.strip().replace('```json', '').replace('```', '').strip()

        ai_data = json.loads(json_text)
        playlist_ids = ai_data.get('playlist', [])
        speech_text = ai_data.get('speechText', "Что-то пошло не так...")
        
        # ... (и далее весь ваш код для формирования final_response и его возврата) ...
        playlist_tracks = []
        for track_id in playlist_ids:
            # ВАЖНО: ищем треки в all_tracks, который мы загрузили из нужного листа
            selected_track = next((track for track in all_tracks if str(track.get('id')) == str(track_id)), None)
            if selected_track:
                playlist_tracks.append({
                    "title": selected_track.get('title'),
                    "artist": selected_track.get('artist'),
                    "musicUrl": selected_track.get('music_url')
                })
        
        final_response = {
            "speechText": speech_text,
            "playlist": playlist_tracks 
        }
        return jsonify(final_response)

    except json.JSONDecodeError as e:
        print(f"ОШИБКА ДЕКОДИРОВАНИЯ JSON. Ответ от Gemini был: '{raw_text}'. Ошибка: {e}")
        return jsonify({"error": "AI вернул некорректный формат данных. Попробуйте еще раз."}), 500
    except Exception as e:
        print(f"ПРОИЗОШЛА НЕПРЕДВИДЕННАЯ ОШИБКА НА ЭТАПЕ 2: {e}")
        return jsonify({"error": "Внутренняя ошибка сервера при обработке запроса."}), 500

# --- Запуск сервера ---
if __name__ == '__main__':
    # PORT берется из окружения (для Render), по умолчанию 5001 для локального запуска
    port = int(os.environ.get('PORT', 5001))
    # debug=False важно для продакшена. host='0.0.0.0' делает сервер доступным извне.
    app.run(debug=False, host='0.0.0.0', port=port)

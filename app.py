import os
import random
import json
import gspread
import google.generativeai as genai
from flask import Flask, jsonify, request
from flask_cors import CORS
from dotenv import load_dotenv
import re

# --- Инициализация и настройка ---
load_dotenv()
app = Flask(__name__)

origins = [
    "https://stop-neurodeception.web.app",
    "https://stop-neurodeception.firebaseapp.com",
    # "http://localhost:5500",
    # "http://127.0.0.1:5500"
]

CORS(app, resources={r"/*": {"origins": origins}})

# Глобальные переменные для хранения подключений
# MODIFIED: tracks_worksheet is not used globally in the new structure, sh.worksheet() is used directly.
model = None
sh = None # NEW: Google Sheets connection object

# --- Подключение к Google Sheets ---
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
    print("Успешно получен доступ к таблице.")
except Exception as e:
    print(f"КРИТИЧЕСКАЯ ОШИБКА ПОДКЛЮЧЕНИЯ К GOOGLE SHEETS: {e}")
    sh = None # Ensure sh is None on failure

# --- Настройка Gemini API ---
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash-latest')
    print("Успешная настройка Gemini API с моделью gemini-1.5-flash-latest.")
else:
    print("КРИТИЧЕСКАЯ ОШИБКА: API ключ для Gemini не найден.")
    model = None

# --- NEW: Промпты для разных языков ---
PROMPT_TEMPLATES = {
    'ru': {
        'stage1': """Ты — музыкальный менеджер. Проанализируй запрос слушателя и выбери ОДИН, самый подходящий плейлист из списка.
В ответе укажи ТОЛЬКО ТОЧНОЕ НАЗВАНИЕ листа, без лишних слов.
Запрос слушателя: "{user_request}"
Список доступных плейлистов: {worksheet_names_joined}""",
        'stage2': """Ты — AI-диджей по имени Джем. Твоя задача — подобрать плейлист из нескольких треков из предоставленной музыкальной библиотеки (это плейлист '{selected_sheet_name}').
После подбора треков, напиши "подводку" (speechText) к этому музыкальному блоку на русском языке.
В подводке обратись к слушателю ({user_name}), упомяни его запрос ("{user_request}") и можешь упомянуть название плейлиста '{selected_sheet_name}'.
Твой ответ ДОЛЖЕН БЫТЬ ТОЛЬКО в формате JSON.
ЗАПРОС ОТ СЛУШАТЕЛЯ:
- Имя: {user_name}
- Пожелание: "{user_request}"
МУЗЫКАЛЬНАЯ БИБЛИОТЕКА (плейлист '{selected_sheet_name}'):
{library_description}
СТРУКТУРА ОТВЕТА (только JSON):
{{
  "playlist": ["ID_трека_1", "ID_трека_2"],
  "speechText": "Текст твоей живой и интересной подводки здесь."
}}"""
    },
    'en': {
        'stage1': """You are a music manager. Analyze the listener's request and choose ONE, the most suitable playlist from the list.
In your response, provide ONLY THE EXACT NAME of the sheet, without any extra words.
Listener's request: "{user_request}"
List of available playlists: {worksheet_names_joined}""",
        'stage2': """You are an AI DJ named Gem. Your task is to select a playlist of a few tracks from the provided music library (this is the playlist '{selected_sheet_name}').
After selecting the tracks, write an intro (speechText) for this music block in English.
In the intro, address the listener ({user_name}), mention their request ("{user_request}"), and you can mention the playlist name '{selected_sheet_name}'.
Your response MUST BE ONLY in JSON format.
LISTENER'S REQUEST:
- Name: {user_name}
- Wish: "{user_request}"
MUSIC LIBRARY (playlist '{selected_sheet_name}'):
{library_description}
RESPONSE STRUCTURE (JSON only):
{{
  "playlist": ["track_ID_1", "track_ID_2"],
  "speechText": "Text of your lively and interesting intro here."
}}"""
    },
    'uk': {
        'stage1': """Ти — музичний менеджер. Проаналізуй запит слухача та вибери ОДИН, найбільш підходящий плейлист зі списку.
У відповіді вкажи ТІЛЬКИ ТОЧНУ НАЗВУ аркуша, без зайвих слів.
Запит слухача: "{user_request}"
Список доступних плейлистів: {worksheet_names_joined}""",
        'stage2': """Ти — AI-діджей на ім'я Джем. Твоє завдання — підібрати плейлист з декількох треків з наданої музичної бібліотеки (це плейлист '{selected_sheet_name}').
Після підбору треків, напиши "підводку" (speechText) до цього музичного блоку українською мовою.
У підводці звернись до слухача ({user_name}), згадай його запит ("{user_request}") і можеш згадати назву плейлиста '{selected_sheet_name}'.
Твоя відповідь ПОВИННА БУТИ ТІЛЬКИ у форматі JSON.
ЗАПИТ ВІД СЛУХАЧА:
- Ім'я: {user_name}
- Побажання: "{user_request}"
МУЗИЧНА БІБЛІОТЕКА (плейлист '{selected_sheet_name}'):
{library_description}
СТРУКТУРА ВІДПОВІДІ (тільки JSON):
{{
  "playlist": ["ID_треку_1", "ID_треку_2"],
  "speechText": "Текст твоєї живої та цікавої підводки тут."
}}"""
    }
}

# --- Вспомогательные функции ---
def get_all_tracks_from_sheet(worksheet): # MODIFIED: Takes worksheet object
    """Получает все треки из указанного листа Google Sheets."""
    if not worksheet:
        print("Ошибка: объект worksheet не предоставлен.")
        return []
    try:
        return worksheet.get_all_records()
    except Exception as e:
        print(f"Ошибка при получении записей из Google Sheets: {e}")
        return []

def format_tracks_for_ai(tracks):
    """Форматирует список треков в одну строку для промпта."""
    library_text = ""
    for track in tracks:
        # MODIFIED: Ensure mood and description are included
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
    """Отдает всю музыкальную библиотеку из ПЕРВОГО листа в виде плейлиста."""
    print("Запрос на /get-full-playlist получен.")
    if not sh:
        return jsonify({"error": "Сервис Google Sheets не инициализирован."}), 500
    try:
        # NEW: Get the first sheet as a default for "full playlist"
        # You might want to make this configurable or choose a specific sheet
        first_worksheet = sh.sheet1
        if not first_worksheet:
            return jsonify({"error": "Не удалось получить доступ к первому листу таблицы."}), 500
        print(f"Загрузка треков для /get-full-playlist с листа: {first_worksheet.title}")
        all_tracks = get_all_tracks_from_sheet(first_worksheet) # MODIFIED
    except Exception as e:
        print(f"Ошибка при получении первого листа или треков: {e}")
        return jsonify({"error": "Не удалось загрузить музыкальную библиотеку."}), 500

    if not all_tracks:
        return jsonify({"error": "Библиотека музыки пуста или не удалось загрузить треки"}), 404
    
    playlist = []
    for track in all_tracks:
        playlist.append({
            "title": track.get('title'),
            "artist": track.get('artist'),
            "musicUrl": track.get('music_url'),
            "mood": track.get('mood'),             # NEW: Added mood
            "description": track.get('description') # NEW: Added description
        })
    return jsonify({"playlist": playlist})


@app.route('/get-radio-play', methods=['POST'])
def get_radio_play():
    """Основной эндпоинт, который обращается к AI в два этапа для генерации плейлиста."""
    if not model or not sh:
        return jsonify({"error": "Сервер не настроен должным образом (проблема с Google Sheets или Gemini API)."}), 500
    
    try:
        data = request.get_json(force=True)
        user_request = data.get('request', 'удиви меня')
        user_name = data.get('userName', 'слушатель')
        # MODIFIED: Language handling
        lang_code = data.get('language', 'ru').lower()
        if lang_code not in PROMPT_TEMPLATES:
            print(f"Предупреждение: Неподдерживаемый код языка '{lang_code}'. Используется 'ru'.")
            lang_code = 'ru' # Default to Russian if language not supported
    except Exception as e:
        print(f"Ошибка получения JSON из запроса: {e}")
        return jsonify({"error": "Неверный формат запроса. Ожидается JSON."}), 400

    # --- ЭТАП 1: AI ВЫБИРАЕТ ЛИСТ ---
    try:
        all_worksheets = sh.worksheets()
        worksheet_names = [ws.title for ws in all_worksheets]
        print(f"Доступные плейлисты (листы): {worksheet_names}")
        if not worksheet_names:
             return jsonify({"error": "В таблице Google Sheets нет доступных листов (плейлистов)."}), 500
    except Exception as e:
        print(f"Критическая ошибка: не удалось получить список листов. Ошибка: {e}")
        return jsonify({"error": "Не удалось загрузить список плейлистов."}), 500

    # MODIFIED: Use language-specific prompt
    prompt_stage1_template = PROMPT_TEMPLATES[lang_code]['stage1']
    prompt_stage1 = prompt_stage1_template.format(
        user_request=user_request,
        worksheet_names_joined=', '.join(worksheet_names)
    )
    
    selected_sheet_name = ""
    try:
        response_stage1 = model.generate_content(prompt_stage1)
        selected_sheet_name = response_stage1.text.strip()
        print(f"AI выбрал плейлист: '{selected_sheet_name}' (Запрос на языке: {lang_code})")
        if selected_sheet_name not in worksheet_names:
            print(f"Предупреждение: AI вернул несуществующее имя листа ('{selected_sheet_name}'). Выбираю случайный из доступных.")
            selected_sheet_name = random.choice(worksheet_names)
    except Exception as e:
        print(f"Ошибка на 1-м этапе вызова AI: {e}. Выбираю случайный плейлист.")
        selected_sheet_name = random.choice(worksheet_names)

    # --- ЭТАП 2: AI ВЫБИРАЕТ ТРЕКИ ИЗ ЛИСТА ---
    try:
        selected_worksheet = sh.worksheet(selected_sheet_name)
        all_tracks_from_selected_sheet = get_all_tracks_from_sheet(selected_worksheet) # MODIFIED
        if not all_tracks_from_selected_sheet:
            # Try to give a more informative error if the sheet was AI's choice vs random fallback
            source_of_sheet_name = "выбранного AI" if selected_sheet_name in worksheet_names else "случайно выбранного"
            return jsonify({"error": f"Плейлист '{selected_sheet_name}' ({source_of_sheet_name}) пуст или не удалось загрузить треки."}), 500
    except gspread.exceptions.WorksheetNotFound:
         return jsonify({"error": f"Плейлист с названием '{selected_sheet_name}' не найден."}), 404
    except Exception as e:
        return jsonify({"error": f"Не удалось загрузить плейлист '{selected_sheet_name}': {e}"}), 500
        
    library_description = format_tracks_for_ai(all_tracks_from_selected_sheet)
    
    # MODIFIED: Use language-specific prompt
    prompt_stage2_template = PROMPT_TEMPLATES[lang_code]['stage2']
    prompt_stage2 = prompt_stage2_template.format(
        selected_sheet_name=selected_sheet_name,
        user_name=user_name,
        user_request=user_request,
        library_description=library_description
    )
    
    raw_text = ""
    try:
        response_stage2 = model.generate_content(prompt_stage2)
        raw_text = response_stage2.text
        # Enhanced JSON parsing to handle potential markdown
        json_text_match = re.search(r"```json\s*([\s\S]*?)\s*```|({[\s\S]*})", raw_text)
        if json_text_match:
            json_text = json_text_match.group(1) or json_text_match.group(2)
            json_text = json_text.strip()
        else:
            # Fallback if no clear JSON block is found, try to clean and parse
            json_text = raw_text.strip() 
            # Basic cleaning: remove potential leading/trailing non-JSON text if it's simple
            if not json_text.startswith('{') and '{' in json_text:
                json_text = json_text[json_text.find('{'):]
            if not json_text.endswith('}') and '}' in json_text:
                json_text = json_text[:json_text.rfind('}')+1]

        ai_data = json.loads(json_text)
        
        playlist_ids = ai_data.get('playlist', [])
        speech_text = ai_data.get('speechText', "Что-то пошло не так с генерацией текста...") # Default message
        
        playlist_tracks = []
        for track_id_input in playlist_ids:
            # AI might return ID as int or string, normalize to string for comparison
            track_id_str = str(track_id_input).strip()
            selected_track = next((track for track in all_tracks_from_selected_sheet if str(track.get('id')).strip() == track_id_str), None)
            if selected_track:
                playlist_tracks.append({
                    "title": selected_track.get('title'),
                    "artist": selected_track.get('artist'),
                    "musicUrl": selected_track.get('music_url'),
                    "mood": selected_track.get('mood'),         # NEW: Added mood
                    "description": selected_track.get('description') # NEW: Added description
                })
            else:
                print(f"Предупреждение: Трек с ID '{track_id_str}' не найден в плейлисте '{selected_sheet_name}'.")

        
        full_playlist_from_sheet = []
        for track in all_tracks_from_selected_sheet:
            full_playlist_from_sheet.append({
                "title": track.get('title'),
                "artist": track.get('artist'),
                "musicUrl": track.get('music_url'),
                "mood": track.get('mood'),                 # NEW: Added mood
                "description": track.get('description')    # NEW: Added description
            })

        final_response = {
            "speechText": speech_text,
            "playlist": playlist_tracks, # AI selected tracks
            "full_playlist_from_sheet": full_playlist_from_sheet # All tracks from the chosen sheet
        }
        
        return jsonify(final_response)

    except json.JSONDecodeError as e:
        print(f"ОШИБКА ДЕКОДИРОВАНИЯ JSON НА ЭТАПЕ 2: {e}\nОтвет от Gemini (ожидался JSON) был: '{raw_text}'")
        # Try to provide a fallback or a more user-friendly error
        # For simplicity, returning a generic error, but you could attempt to extract speechText if possible
        return jsonify({"error": "Ошибка обработки ответа от AI. Не удалось разобрать JSON.", "raw_response": raw_text if len(raw_text) < 500 else raw_text[:500] + "..."}), 500
    except Exception as e:
        print(f"НЕПРЕДВИДЕННАЯ ОШИБКА НА ЭТАПЕ 2: {e}\nОтвет от Gemini был: '{raw_text}'")
        return jsonify({"error": "Внутренняя ошибка сервера при обработке запроса AI."}), 500

# --- Запуск сервера ---
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    app.run(debug=False, host='0.0.0.0', port=port)

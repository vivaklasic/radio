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
    "https://aifake.pro",           
    "https://aiforma.web.app",      
    "https://aiforma.firebaseapp.com",
]

CORS(app, resources={r"/*": {"origins": origins}})

# Глобальные переменные
model = None
sh = None
PLAYLIST_METADATA_SHEET_NAME = "_PlaylistMetadata" # Название мета-листа
PLAYLIST_METADATA = {} # Словарь для хранения метаданных плейлистов

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

    sh = gc.open_by_key('1NDTPGtwDlqo0djTQlsegZtI8-uTl1ojTtbT0PmtR5YU') # ЗАМЕНИ НА СВОЙ КЛЮЧ
    print("Успешно получен доступ к таблице.")

    # --- NEW: Загрузка метаданных плейлистов ---
    def load_playlist_metadata(spreadsheet_obj):
        global PLAYLIST_METADATA
        try:
            metadata_sheet = spreadsheet_obj.worksheet(PLAYLIST_METADATA_SHEET_NAME)
            records = metadata_sheet.get_all_records()
            for record in records:
                # Проверяем, что есть SheetName, чтобы избежать пустых строк
                if record.get('SheetName'):
                    PLAYLIST_METADATA[record['SheetName']] = record
            if PLAYLIST_METADATA:
                print(f"Метаданные для {len(PLAYLIST_METADATA)} плейлистов успешно загружены.")
            else:
                print(f"Предупреждение: Метаданные плейлистов из листа '{PLAYLIST_METADATA_SHEET_NAME}' не загружены или лист пуст.")
        except gspread.exceptions.WorksheetNotFound:
            print(f"КРИТИЧЕСКАЯ ОШИБКА: Мета-лист '{PLAYLIST_METADATA_SHEET_NAME}' не найден в таблице.")
            PLAYLIST_METADATA = {}
        except Exception as e:
            print(f"Ошибка при загрузке метаданных плейлистов: {e}")
            PLAYLIST_METADATA = {}

    load_playlist_metadata(sh) # Загружаем метаданные сразу после подключения

except Exception as e:
    print(f"КРИТИЧЕСКАЯ ОШИБКА ПОДКЛЮЧЕНИЯ К GOOGLE SHEETS ИЛИ ЗАГРУЗКИ МЕТАДАННЫХ: {e}")
    sh = None
    PLAYLIST_METADATA = {}

# --- Настройка Gemini API ---
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-2.0-flash')
    print("Успешная настройка Gemini API с моделью gemini-1.5-flash-latest.")
else:
    print("КРИТИЧЕСКАЯ ОШИБКА: API ключ для Gemini не найден.")
    model = None

# --- NEW: Обновленные промпты ---
PROMPT_TEMPLATES = {
    'ru': {
        'stage1': """Ты — музыкальный менеджер. Проанализируй запрос слушателя и выбери ОДИН, самый подходящий плейлист из списка ниже.
В ответе укажи ТОЛЬКО ТОЧНОЕ НАЗВАНИЕ листа (значение из поля 'Название плейлиста:'), без лишних слов.
Запрос слушателя: "{user_request}"
Список доступных плейлистов с их описаниями и тегами:
{worksheet_details_joined}""",
        'stage2': """Ты — AI-диджей по имени Джем. Твоя задача — подобрать плейлист из десяти треков из предоставленной музыкальной библиотеки (это плейлист '{selected_sheet_name}').
После подбора треков, напиши "подводку" (speechText) к этому музыкальному блоку на русском языке.
В подводке обратись к слушателю ({user_name}), упомяни его запрос ("{user_request}") и можешь упомянуть название плейлиста '{selected_sheet_name}'.
Твой ответ ДОЛЖЕН БЫТЬ ТОЛЬКО в формате JSON.
ЗАПРОС ОТ СЛУШАТЕЛЯ:
- Имя: {user_name}
- Пожелание: "{user_request}"
МУЗЫКАЛЬНАЯ БИБЛИОТЕКА (плейлист '{selected_sheet_name}'). Каждый трек включает ID, Название, Исполнителя, Жанр, Настроение (если есть), Описание и Теги:
{library_description}
СТРУКТУРА ОТВЕТА (только JSON):
{{
  "playlist": ["ID_трека_1", "ID_трека_2"],
  "speechText": "Текст твоей живой и интересной подводки здесь."
}}"""
    },
    'en': {
        'stage1': """You are a music manager. Analyze the listener's request and choose ONE, the most suitable playlist from the list below.
In your response, provide ONLY THE EXACT NAME of the sheet (value from 'Playlist Name:'), without any extra words.
Listener's request: "{user_request}"
List of available playlists with their descriptions and tags:
{worksheet_details_joined}""",
        'stage2': """You are an AI DJ named Gem. Your task is to create a playlist of ten tracks from the provided music library (this is the playlist '{selected_sheet_name}').
After selecting the tracks, write an intro (speechText) for this music block in English.
In the intro, address the listener ({user_name}), mention their request ("{user_request}"), and you can mention the playlist name '{selected_sheet_name}'.
Your response MUST BE ONLY in JSON format.
LISTENER'S REQUEST:
- Name: {user_name}
- Wish: "{user_request}"
MUSIC LIBRARY (playlist '{selected_sheet_name}'). Each track includes ID, Title, Artist, Genre, Mood (if available), Description, and Tags:
{library_description}
RESPONSE STRUCTURE (JSON only):
{{
  "playlist": ["track_ID_1", "track_ID_2"],
  "speechText": "Text of your lively and interesting intro here."
}}"""
    },
    'uk': {
        'stage1': """Ти — музичний менеджер. Проаналізуй запит слухача та вибери ОДИН, найбільш підходящий плейлист зі списку нижче.
У відповіді вкажи ТІЛЬКИ ТОЧНУ НАЗВУ аркуша (значення з поля 'Назва плейлисту:'), без зайвих слів.
Запит слухача: "{user_request}"
Список доступних плейлистів з їх описами та тегами:
{worksheet_details_joined}""",
        'stage2': """Ти — AI-діджей на ім'я Джем. Твоє завдання — підібрати плейлист з десяти треків з наданої музичної бібліотеки (це плейлист '{selected_sheet_name}').
Після підбору треків, напиши "підводку" (speechText) до цього музичного блоку українською мовою.
У підводці звернись до слухача ({user_name}), згадай його запит ("{user_request}") і можеш згадати назву плейлиста '{selected_sheet_name}'.
Твоя відповідь ПОВИННА БУТИ ТІЛЬКИ у форматі JSON.
ЗАПИТ ВІД СЛУХАЧА:
- Ім'я: {user_name}
- Побажання: "{user_request}"
МУЗИЧНА БІБЛІОТЕКА (плейлист '{selected_sheet_name}'). Кожен трек включає ID, Назву, Виконавця, Жанр, Настрій (якщо є), Опис та Теги:
{library_description}
СТРУКТУРА ВІДПОВІДІ (тільки JSON):
{{
  "playlist": ["ID_треку_1", "ID_треку_2"],
  "speechText": "Текст твоєї живої та цікавої підводки тут."
}}"""
    }
}

# --- Вспомогательные функции ---
def get_all_tracks_from_sheet(worksheet):
    if not worksheet:
        print("Ошибка: объект worksheet не предоставлен.")
        return []
    try:
        return worksheet.get_all_records()
    except Exception as e:
        print(f"Ошибка при получении записей из Google Sheets '{worksheet.title}': {e}")
        return []

def format_tracks_for_ai(tracks, lang_code='ru'):
    """Форматирует список треков в одну строку для промпта, используя языковые поля."""
    library_text = ""
    # Определяем ключи для языковых столбцов
    desc_key_lang = f'description_{lang_code}'
    tags_key_lang = f'tags_{lang_code}'

    # Запасные ключи, если языковой столбец отсутствует или пуст
    default_desc_key_1 = 'description_en'
    default_desc_key_2 = 'description_ru' # Если lang_code не en
    general_desc_key = 'description' # Самый общий

    default_tags_key_1 = 'tags_en'
    default_tags_key_2 = 'tags_ru'
    general_tags_key = 'tags'


    for track in tracks:
        # Получаем описание и теги для нужного языка с фоллбэками
        description = (track.get(desc_key_lang) or
                       track.get(default_desc_key_1 if lang_code != 'en' else default_desc_key_2) or # Пробуем другой основной язык
                       track.get(general_desc_key) or # Пробуем общий description
                       "") # Пусто, если ничего нет

        tags = (track.get(tags_key_lang) or
                track.get(default_tags_key_1 if lang_code != 'en' else default_tags_key_2) or
                track.get(general_tags_key) or
                "")

        track_info_parts = [
            f"ID: {track.get('id', 'N/A')}",
            f"Title: {track.get('title', 'N/A')}",
            f"Artist: {track.get('artist', 'N/A')}",
            f"Genre: {track.get('genre', 'N/A')}"
        ]
        if track.get('mood'): # Добавляем mood, если он есть
            track_info_parts.append(f"Mood: {track.get('mood')}")
        track_info_parts.append(f"Description: {description.strip()}")
        track_info_parts.append(f"Tags: {tags.strip()}")

        library_text += ", ".join(track_info_parts) + "\n"
    return library_text

def get_track_details_for_playlist(track_data, lang_code='ru'):
    """Возвращает словарь с деталями трека для конечного JSON ответа, используя языковые поля."""
    desc_key_lang = f'description_{lang_code}'
    # Фоллбэки для описания
    description = (track_data.get(desc_key_lang) or
                   track_data.get('description_en') or
                   track_data.get('description_ru') or
                   track_data.get('description_uk') or # Убедимся, что все языки проверены
                   track_data.get('description', '')) # Общий фоллбек

    return {
        "title": track_data.get('title'),
        "artist": track_data.get('artist'),
        "musicUrl": track_data.get('music_url'),
        "mood": track_data.get('mood'),
        "description": description.strip() # Отдаем описание на нужном языке (с фоллбэком)
        # Теги можно не отдавать клиенту, если они не нужны для отображения,
        # но если нужны, добавьте их аналогично описанию.
    }


# --- API ЭНДПОИНТЫ ---

@app.route('/')
def index():
    return "Flask-сервер для AI Радио работает! Метаданные плейлистов загружены: " + ("Да" if PLAYLIST_METADATA else "Нет")

@app.route('/get-full-playlist', methods=['GET'])
def get_full_playlist_route():
    print("Запрос на /get-full-playlist получен.")
    if not sh:
        return jsonify({"error": "Сервис Google Sheets не инициализирован."}), 500

    lang_code = request.args.get('language', 'ru').lower() # Получаем язык из query params

    try:
        # Попробуем взять первый лист, который есть в метаданных, как основной
        # Или просто первый лист, если метаданные пусты
        target_sheet_title = None
        if PLAYLIST_METADATA:
            target_sheet_title = next(iter(PLAYLIST_METADATA.keys()), None)

        if target_sheet_title:
            worksheet = sh.worksheet(target_sheet_title)
            print(f"Загрузка треков для /get-full-playlist с листа (из метаданных): {worksheet.title}")
        else:
            # Фоллбек: просто первый лист, исключая мета-лист
            all_sheets = sh.worksheets()
            app_sheets = [s for s in all_sheets if s.title != PLAYLIST_METADATA_SHEET_NAME]
            if not app_sheets:
                 return jsonify({"error": "В таблице нет листов с треками (кроме, возможно, мета-листа)."}), 500
            worksheet = app_sheets[0]
            print(f"Загрузка треков для /get-full-playlist с первого доступного листа: {worksheet.title}")

        all_tracks_raw = get_all_tracks_from_sheet(worksheet)
    except Exception as e:
        print(f"Ошибка при получении первого листа или треков: {e}")
        return jsonify({"error": "Не удалось загрузить музыкальную библиотеку."}), 500

    if not all_tracks_raw:
        return jsonify({"error": "Библиотека музыки пуста или не удалось загрузить треки"}), 404

    playlist = [get_track_details_for_playlist(track, lang_code) for track in all_tracks_raw]
    return jsonify({"playlist": playlist})


@app.route('/get-radio-play', methods=['POST'])
def get_radio_play():
    if not model or not sh:
        return jsonify({"error": "Сервер не настроен должным образом (проблема с Google Sheets или Gemini API)."}), 500
    if not PLAYLIST_METADATA:
        return jsonify({"error": f"Метаданные плейлистов не загружены. Проверьте лист '{PLAYLIST_METADATA_SHEET_NAME}'."}), 500

    try:
        data = request.get_json(force=True)
        user_request = data.get('request', 'удиви меня')
        user_name = data.get('userName', 'слушатель')
        lang_code = data.get('language', 'ru').lower()
        if lang_code not in PROMPT_TEMPLATES:
            print(f"Предупреждение: Неподдерживаемый код языка '{lang_code}'. Используется 'ru'.")
            lang_code = 'ru'
    except Exception as e:
        print(f"Ошибка получения JSON из запроса: {e}")
        return jsonify({"error": "Неверный формат запроса. Ожидается JSON."}), 400

    # --- ЭТАП 1: AI ВЫБИРАЕТ ЛИСТ НА ОСНОВЕ МЕТАДАННЫХ ---
    playlist_info_for_prompt = []
    available_playlist_names = list(PLAYLIST_METADATA.keys()) # Плейлисты, для которых есть метаданные

    if not available_playlist_names:
         return jsonify({"error": f"В таблице Google Sheets нет плейлистов с метаданными в '{PLAYLIST_METADATA_SHEET_NAME}'."}), 500

    for sheet_name in available_playlist_names:
        meta = PLAYLIST_METADATA.get(sheet_name)
        if meta:
            # Формируем ключи для текущего языка
            desc_key = f'Description{lang_code.upper()}' # DescriptionRU, DescriptionEN, etc.
            tags_key = f'Tags{lang_code.upper()}'

            # Фоллбэки: сначала пробуем язык запроса, потом EN, потом RU, потом первый попавшийся
            description = (meta.get(desc_key) or
                           meta.get('DescriptionEN') or
                           meta.get('DescriptionRU') or
                           meta.get('DescriptionUK') or
                           "Описание отсутствует")
            tags = (meta.get(tags_key) or
                    meta.get('TagsEN') or
                    meta.get('TagsRU') or
                    meta.get('TagsUK') or
                    "Теги отсутствуют")
            playlist_info_for_prompt.append(f"- Название плейлиста: '{sheet_name}', Описание: {description}, Теги: {tags}")

    worksheet_details_joined = "\n".join(playlist_info_for_prompt)

    prompt_stage1_template = PROMPT_TEMPLATES[lang_code]['stage1'] # Используем обновленный stage1
    prompt_stage1 = prompt_stage1_template.format(
        user_request=user_request,
        worksheet_details_joined=worksheet_details_joined
    )

    selected_sheet_name = ""
    try:
        print(f"\n--- Промпт для Этапа 1 (язык: {lang_code}) ---\n{prompt_stage1}\n----------------------------")
        response_stage1 = model.generate_content(prompt_stage1)
        selected_sheet_name = response_stage1.text.strip()
        # Иногда AI может добавить кавычки, убираем их
        selected_sheet_name = selected_sheet_name.strip("'\"")
        print(f"AI выбрал плейлист: '{selected_sheet_name}' (Запрос на языке: {lang_code})")

        if selected_sheet_name not in available_playlist_names:
            print(f"Предупреждение: AI вернул имя листа ('{selected_sheet_name}'), которого нет в метаданных. Выбираю случайный из доступных.")
            selected_sheet_name = random.choice(available_playlist_names)
    except Exception as e:
        print(f"Ошибка на 1-м этапе вызова AI: {e}. Выбираю случайный плейлист из метаданных.")
        selected_sheet_name = random.choice(available_playlist_names)

    # --- ЭТАП 2: AI ВЫБИРАЕТ ТРЕКИ ИЗ ЛИСТА ---
    try:
        selected_worksheet = sh.worksheet(selected_sheet_name)
        all_tracks_from_selected_sheet = get_all_tracks_from_sheet(selected_worksheet)
        if not all_tracks_from_selected_sheet:
            return jsonify({"error": f"Плейлист '{selected_sheet_name}' пуст или не удалось загрузить треки."}), 500
    except gspread.exceptions.WorksheetNotFound:
         return jsonify({"error": f"Плейлист с названием '{selected_sheet_name}' не найден в таблице."}), 404
    except Exception as e:
        return jsonify({"error": f"Не удалось загрузить плейлист '{selected_sheet_name}': {e}"}), 500

    library_description = format_tracks_for_ai(all_tracks_from_selected_sheet, lang_code)

    prompt_stage2_template = PROMPT_TEMPLATES[lang_code]['stage2']
    prompt_stage2 = prompt_stage2_template.format(
        selected_sheet_name=selected_sheet_name,
        user_name=user_name,
        user_request=user_request,
        library_description=library_description
    )

    raw_text = ""
    try:
        print(f"\n--- Промпт для Этапа 2 (плейлист: {selected_sheet_name}, язык: {lang_code}) ---\n{prompt_stage2}\n----------------------------")
        response_stage2 = model.generate_content(prompt_stage2)
        raw_text = response_stage2.text

        json_text_match = re.search(r"```json\s*([\s\S]*?)\s*```|({[\s\S]*})", raw_text)
        if json_text_match:
            json_text = json_text_match.group(1) or json_text_match.group(2)
            json_text = json_text.strip()
        else:
            json_text = raw_text.strip()
            if not json_text.startswith('{') and '{' in json_text:
                json_text = json_text[json_text.find('{'):]
            if not json_text.endswith('}') and '}' in json_text:
                json_text = json_text[:json_text.rfind('}')+1]

        ai_data = json.loads(json_text)
        playlist_ids_from_ai = ai_data.get('playlist', [])
        speech_text = ai_data.get('speechText', "Что-то пошло не так с генерацией текста...")

        # Формируем плейлист с полными данными треков
        selected_playlist_tracks = []
        for track_id_input in playlist_ids_from_ai:
            track_id_str = str(track_id_input).strip()
            # Ищем трек по ID в загруженных данных
            track_data = next((t for t in all_tracks_from_selected_sheet if str(t.get('id')).strip() == track_id_str), None)
            if track_data:
                selected_playlist_tracks.append(get_track_details_for_playlist(track_data, lang_code))
            else:
                print(f"Предупреждение: Трек с ID '{track_id_str}' не найден в плейлисте '{selected_sheet_name}'.")

        # Формируем полный плейлист из выбранного листа для клиента
        full_playlist_from_sheet = [get_track_details_for_playlist(track, lang_code) for track in all_tracks_from_selected_sheet]

        final_response = {
            "speechText": speech_text,
            "playlist": selected_playlist_tracks, # Треки, выбранные AI
            "full_playlist_from_sheet": full_playlist_from_sheet # Все треки из выбранного AI листа
        }
        return jsonify(final_response)

    except json.JSONDecodeError as e:
        print(f"ОШИБКА ДЕКОДИРОВАНИЯ JSON НА ЭТАПЕ 2: {e}\nОтвет от Gemini (ожидался JSON) был: '{raw_text}'")
        return jsonify({"error": "Ошибка обработки ответа от AI. Не удалось разобрать JSON.", "raw_response": raw_text[:500] + "..."}), 500
    except Exception as e:
        print(f"НЕПРЕДВИДЕННАЯ ОШИБКА НА ЭТАПЕ 2: {e}\nОтвет от Gemini (если был): '{raw_text}'")
        return jsonify({"error": "Внутренняя ошибка сервера при обработке запроса AI."}), 500

# --- Запуск сервера ---
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    app.run(debug=False, host='0.0.0.0', port=port)

import os
import random
import json # <-- ДОБАВЛЕН ЭТОТ ИМПОРТ
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

# --- ИЗМЕНЕННЫЙ БЛОК НАСТРОЙКИ GOOGLE SHEETS ---
try:
    # Пытаемся получить учетные данные из переменной окружения (для Render)
    gcp_credentials_json = os.getenv('GCP_CREDENTIALS')
    if gcp_credentials_json:
        # Если переменная найдена, используем ее
        credentials_dict = json.loads(gcp_credentials_json)
        gc = gspread.service_account_from_dict(credentials_dict)
        print("Успешное подключение к Google Sheets через переменные окружения.")
    else:
        # Если переменной нет, ищем локальный файл (для разработки на своем компьютере)
        gc = gspread.service_account(filename='credentials.json')
        print("Успешное подключение к Google Sheets через локальный файл.")

    # Общий код для обоих случаев
    sh = gc.open_by_key('1NDTPGtwDlqo0djTQlsegZtI8-uTl1ojTtbT0PmtR5YU') # !!! НЕ ЗАБУДЬТЕ ВСТАВИТЬ ВАШ КЛЮЧ ТАБЛИЦЫ !!!
    tracks_worksheet = sh.worksheet('tracks') # Укажите имя листа
    
except Exception as e:
    print(f"КРИТИЧЕСКАЯ ОШИБКА: Не удалось подключиться к Google Sheets. Ошибка: {e}")
    tracks_worksheet = None
# --- КОНЕЦ ИЗМЕНЕННОГО БЛОКА ---


# Настройка Gemini API
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-pro')
    print("Успешная настройка Gemini API.")
else:
    print("КРИТИЧЕСКАЯ ОШИБКА: API ключ для Gemini не найден.")
    model = None

# --- ЛОГИКА ---

def get_all_tracks():
    """Получает все треки из Google Таблицы."""
    if not tracks_worksheet:
        print("Ошибка: объект tracks_worksheet не инициализирован.")
        return []
    try:
        records = tracks_worksheet.get_all_records() # Получаем данные как список словарей
        return records
    except Exception as e:
        print(f"Ошибка при получении записей из Google Sheets: {e}")
        return []


def format_tracks_for_ai(tracks):
    """Форматирует список треков в текстовое описание для Gemini."""
    description = ""
    for track in tracks:
        # Добавим проверку на наличие ключей, чтобы избежать ошибок
        track_id = track.get('id', 'N/A')
        title = track.get('title', 'N/A')
        artist = track.get('artist', 'N/A')
        mood = track.get('mood', 'N/A')
        description += f"ID: {track_id}, Title: {title}, Artist: {artist}, Mood: {mood}\n"
    return description

# --- API ЭНДПОИНТ ---

@app.route('/')
def index():
    # Просто тестовый эндпоинт, чтобы проверить, что сервер работает
    return "Flask-сервер для AI Радио работает!"

@app.route('/get-radio-play', methods=['POST'])
def get_radio_play():
    if not model or not tracks_worksheet:
        return jsonify({"error": "Сервер не настроен должным образом. Проверьте логи."}), 500

    # Получаем запрос от пользователя из тела POST-запроса
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Пустое тело запроса"}), 400
        user_request = data.get('request', 'удиви меня')
        user_name = data.get('userName', 'слушатель')
    except Exception:
        return jsonify({"error": "Неверный формат запроса, ожидается JSON"}), 400


    # 1. Получаем треки и форматируем их для AI
    all_tracks = get_all_tracks()
    if not all_tracks:
        return jsonify({"error": "Не удалось загрузить треки из базы данных. Проверьте Google Sheets."}), 500
        
    library_description = format_tracks_for_ai(all_tracks)

    # 2. Создаем промпт для Gemini
    prompt = f"""
        Ты AI-диджей. Твоя задача - подобрать один трек из библиотеки для слушателя и написать короткую подводку.
        Запрос от слушателя по имени {user_name}: "{user_request}"

        Музыкальная библиотека:
        {library_description}

        Ответь в формате JSON, и только JSON. Не добавляй ```json или другие символы.
        Структура: {{ "trackId": ID_трека_из_библиотеки, "speechText": "Текст твоей подводки" }}
    """

    try:
        # 3. Отправляем запрос в Gemini
        response = model.generate_content(prompt)
        ai_data = json.loads(response.text)
        
        selected_track_id = int(ai_data['trackId'])
        speech_text = ai_data['speechText']

        # 4. Находим выбранный трек в нашем списке
        selected_track = next((track for track in all_tracks if int(track['id']) == selected_track_id), None)

        if not selected_track:
            return jsonify({"error": f"AI выбрал несуществующий трек с ID: {selected_track_id}"}), 404

        # 5. Собираем финальный ответ для фронтенда
        final_response = {
            "speechText": speech_text,
            "musicUrl": selected_track.get('music_url'),
            "title": selected_track.get('title'),
            "artist": selected_track.get('artist')
        }
        
        return jsonify(final_response)

    except json.JSONDecodeError:
        # Если Gemini ответил не в формате JSON
        print(f"Ошибка декодирования JSON. Ответ от Gemini: {response.text}")
        return jsonify({"error": "Ошибка формата ответа от AI. Попробуйте снова."}), 500
    except Exception as e:
        print(f"Произошла непредвиденная ошибка: {e}")
        return jsonify({"error": "Внутренняя ошибка сервера при обработке запроса"}), 500

if __name__ == '__main__':
    # Для Render.com порт обычно устанавливается через переменную окружения PORT
    port = int(os.environ.get('PORT', 5001))
    # debug=False для продакшена
    app.run(debug=False, host='0.0.0.0', port=port)

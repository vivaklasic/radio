document.addEventListener('DOMContentLoaded', () => {
    // --- Элементы страницы (без изменений) ---
    const userRequestInput = document.getElementById('user-request');
    const playButton = document.getElementById('play-button');
    const buttonText = document.querySelector('.button-text');
    const spinner = document.getElementById('spinner');
    const speechTextElement = document.getElementById('speech-text');
    const nowPlayingContainer = document.getElementById('now-playing');
    const trackInfoElement = document.getElementById('track-info');
    const audioPlayer = document.getElementById('audio-player');

    // --- URL бэкенда (без изменений) ---
    const backendUrl = 'https://radio-2gyc.onrender.com/get-radio-play';

    // --- НОВЫЕ ПЕРЕМЕННЫЕ ДЛЯ УПРАВЛЕНИЯ ПЛЕЙЛИСТОМ ---
    let currentPlaylist = [];
    let currentTrackIndex = 0;

    // --- Функция для общения с бэкендом (без изменений) ---
    async function fetchRadioPlay(userRequest) {
        // ... эта функция остается точно такой же
        try {
            const response = await fetch(backendUrl, {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ request: userRequest, userName: "Слушатель" }),
            });
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || `Ошибка сервера: ${response.status}`);
            }
            return response.json();
        } catch (error) {
            console.error('Ошибка сети или запроса:', error);
            return { error: `Не удалось связаться с сервером. ${error.message}` };
        }
    }

    // --- Функция для управления кнопкой (без изменений) ---
    function setButtonLoading(isLoading) {
        // ... эта функция остается точно такой же
        playButton.disabled = isLoading;
        buttonText.style.display = isLoading ? 'none' : 'inline';
        spinner.style.display = isLoading ? 'block' : 'none';
    }

    // --- НОВАЯ ФУНКЦИЯ ДЛЯ ЗАПУСКА ТРЕКА ИЗ ПЛЕЙЛИСТА ---
    function playTrack(trackIndex) {
        if (trackIndex < currentPlaylist.length) {
            const track = currentPlaylist[trackIndex];
            trackInfoElement.textContent = `${track.artist} - ${track.title}`;
            nowPlayingContainer.style.display = 'block';
            audioPlayer.src = track.musicUrl;
            audioPlayer.play();
        } else {
            // Плейлист закончился
            speechTextElement.textContent = "Музыкальный блок завершен. Что поставим дальше?";
            nowPlayingContainer.style.display = 'none';
        }
    }
    
    // --- ОБНОВЛЕННЫЙ ОБРАБОТЧИК НАЖАТИЯ НА КНОПКУ ---
    playButton.addEventListener('click', async () => {
        const userRequest = userRequestInput.value.trim();
        if (!userRequest) {
            speechTextElement.textContent = "Пожалуйста, введите ваш запрос.";
            return;
        }

        setButtonLoading(true);
        speechTextElement.textContent = "AI-диджей составляет плейлист...";
        nowPlayingContainer.style.display = 'none';

        const data = await fetchRadioPlay(userRequest);

        setButtonLoading(false);

        if (data.error) {
            speechTextElement.textContent = `Произошла ошибка: ${data.error}`;
        } else {
            // УСПЕШНЫЙ ОТВЕТ С ПЛЕЙЛИСТОМ
            speechTextElement.textContent = data.speechText; // Показываем общую подводку
            
            currentPlaylist = data.playlist; // Сохраняем полученный плейлист
            currentTrackIndex = 0; // Сбрасываем счетчик на начало

            if (currentPlaylist && currentPlaylist.length > 0) {
                playTrack(currentTrackIndex); // Запускаем первый трек
            } else {
                speechTextElement.textContent = "Не удалось найти подходящие треки. Попробуйте другой запрос.";
            }
        }
    });

    // --- НОВЫЙ ОБРАБОТЧИК: АВТОМАТИЧЕСКОЕ ПЕРЕКЛЮЧЕНИЕ НА СЛЕДУЮЩИЙ ТРЕК ---
    audioPlayer.addEventListener('ended', () => {
        currentTrackIndex++; // Переходим к следующему треку
        playTrack(currentTrackIndex); // Запускаем его
    });


    // --- Обработчик Enter (без изменений) ---
    userRequestInput.addEventListener('keyup', (event) => {
        if (event.key === 'Enter') {
            event.preventDefault();
            playButton.click();
        }
    });
});

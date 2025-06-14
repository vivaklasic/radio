document.addEventListener('DOMContentLoaded', () => {
    // --- Элементы страницы (согласно вашему HTML) ---
    const userRequestInput = document.getElementById('user-request');
    const playButton = document.getElementById('play-button');
    const buttonText = document.querySelector('.button-text');
    const spinner = document.getElementById('spinner');
    const speechTextElement = document.getElementById('speech-text');
    const nowPlayingContainer = document.getElementById('now-playing');
    const trackInfoElement = document.getElementById('track-info');
    const audioPlayer = document.getElementById('audio-player');

    // --- URLы бэкенда ---
    const aiBackendUrl = 'https://radio-2gyc.onrender.com/get-radio-play';
    const libraryBackendUrl = 'https://radio-2gyc.onrender.com/get-full-playlist';

    // --- Переменные для управления состоянием радио ---
    let fullLibrary = [];
    let currentAiPlaylist = [];
    let currentTrackIndex = 0;
    let isAiMode = false;

    // --- Функции fetchFullLibrary и fetchAiPlaylist (без изменений) ---
    async function fetchFullLibrary() {
        try {
            const response = await fetch(libraryBackendUrl);
            const data = await response.json();
            if (data.playlist && data.playlist.length > 0) {
                fullLibrary = data.playlist;
                console.log(`Загружена полная библиотека из ${fullLibrary.length} треков.`);
            }
        } catch (error) { console.error("Не удалось загрузить полную библиотеку:", error); }
    }
    fetchFullLibrary();

    async function fetchAiPlaylist(userRequest) {
        try {
            const response = await fetch(aiBackendUrl, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
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

    // --- Функция setButtonLoading (без изменений) ---
    function setButtonLoading(isLoading) {
        playButton.disabled = isLoading;
        buttonText.style.display = isLoading ? 'none' : 'inline';
        spinner.style.display = isLoading ? 'block' : 'none';
    }

    // --- Главная функция проигрывания (правильная версия) ---
    function playNextTrack() {
        let trackToPlay = null;

        if (isAiMode && currentTrackIndex < currentAiPlaylist.length) {
            // РЕЖИМ AI: берем трек из плейлиста диджея
            trackToPlay = currentAiPlaylist[currentTrackIndex];
        } else {
            // РЕЖИМ СЛУЧАЙНОГО РАДИО
            if (isAiMode) { // Если мы ТОЛЬКО ЧТО вышли из режима AI
                speechTextElement.textContent = "Подборка от AI завершена. Перехожу в режим радио.";
            }
            isAiMode = false;
            
            if (fullLibrary.length > 0) {
                const randomIndex = Math.floor(Math.random() * fullLibrary.length);
                trackToPlay = fullLibrary[randomIndex];
            }
        }

        if (trackToPlay) {
            // ЗАПОЛНЯЕМ ПОЛЕ С НАЗВАНИЕМ ТРЕКА
            trackInfoElement.textContent = `${trackToPlay.artist} - ${trackToPlay.title}`;
            // ПОКАЗЫВАЕМ ВЕСЬ БЛОК
            nowPlayingContainer.style.display = 'block';
            audioPlayer.src = trackToPlay.musicUrl;
            audioPlayer.play();
        } else {
            // Музыки нет, скрываем блок
            speechTextElement.textContent = "Музыка закончилась или библиотека пуста.";
            nowPlayingContainer.style.display = 'none';
        }
    }
    
    // --- Обработчик нажатия кнопки (правильная версия) ---
    playButton.addEventListener('click', async () => {
        const userRequest = userRequestInput.value.trim();
        if (!userRequest) return;

        setButtonLoading(true);
        // Готовим UI к ответу от AI
        speechTextElement.textContent = "AI-диджей составляет плейлист...";
        nowPlayingContainer.style.display = 'none'; // Скрываем старый трек
        audioPlayer.pause(); 

        const data = await fetchAiPlaylist(userRequest);
        setButtonLoading(false);

        if (data.error) {
            speechTextElement.textContent = `Произошла ошибка: ${data.error}`;
            return;
        }
        
        // ПОМЕЩАЕМ РЕЧЬ ДИДЖЕЯ В ЕГО ПОЛЕ
        speechTextElement.textContent = data.speechText || "К сожалению, не удалось найти подходящие треки.";

        if (data.playlist && data.playlist.length > 0) {
            // Успех! Готовимся к запуску AI-плейлиста
            currentAiPlaylist = data.playlist;
            currentTrackIndex = 0;
            isAiMode = true;
            playNextTrack(); // Запускаем воспроизведение
        } else {
            isAiMode = false;
        }
    });

    // --- Обработчик окончания трека (без изменений) ---
    audioPlayer.addEventListener('ended', () => {
        if (isAiMode) {
            currentTrackIndex++;
        }
        playNextTrack();
    });

    // --- Обработчик Enter (без изменений) ---
    userRequestInput.addEventListener('keyup', (event) => {
        if (event.key === 'Enter') {
            event.preventDefault();
            playButton.click();
        }
    });
});

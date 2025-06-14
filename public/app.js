document.addEventListener('DOMContentLoaded', () => {
    // --- Элементы страницы ---
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

    // --- Функция: Загружает всю библиотеку при старте ---
    async function fetchFullLibrary() {
        try {
            const response = await fetch(libraryBackendUrl);
            const data = await response.json();
            if (data.playlist && data.playlist.length > 0) {
                fullLibrary = data.playlist;
                console.log(`Загружена полная библиотека из ${fullLibrary.length} треков.`);
            }
        } catch (error) {
            console.error("Не удалось загрузить полную библиотеку:", error);
        }
    }
    fetchFullLibrary();

    // --- Функция: Отправляет запрос к AI ---
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

    // --- Функция: Управляет состоянием кнопки ---
    function setButtonLoading(isLoading) {
        playButton.disabled = isLoading;
        buttonText.style.display = isLoading ? 'none' : 'inline';
        spinner.style.display = isLoading ? 'block' : 'none';
    }

    // --- Главная функция проигрывания (МОЗГ РАДИО) ---
    function playNextTrack() {
        let trackToPlay = null;

        // ШАГ 1: ПРОВЕРЯЕМ, АКТИВЕН ЛИ РЕЖИМ AI И ЕСТЬ ЛИ В НЕМ ЕЩЕ ТРЕКИ
        if (isAiMode && currentTrackIndex < currentAiPlaylist.length) {
            // Да, мы в режиме AI. Берем следующий трек из него.
            trackToPlay = currentAiPlaylist[currentTrackIndex];
            
            // Показываем "Далее в эфире..." ТОЛЬКО для второго и последующих треков.
            // Для первого трека (index=0) подводку уже показал диджей.
            if (currentTrackIndex > 0) {
                speechTextElement.textContent = `Далее: ${trackToPlay.title}`;
            }
        } else {
            // ШАГ 2: РЕЖИМ AI ЗАКОНЧИЛСЯ ИЛИ НЕ НАЧИНАЛСЯ. ПЕРЕХОДИМ К СЛУЧАЙНОМУ РАДИО.
            isAiMode = false; // Убеждаемся, что режим AI выключен.
            if (fullLibrary.length > 0) {
                const randomIndex = Math.floor(Math.random() * fullLibrary.length);
                trackToPlay = fullLibrary[randomIndex];
                speechTextElement.textContent = "В эфире случайный трек...";
            }
        }

        // ШАГ 3: ВОСПРОИЗВОДИМ ВЫБРАННЫЙ ТРЕК (ИЛИ СООБЩАЕМ ОБ ОШИБКЕ)
        if (trackToPlay) {
            trackInfoElement.textContent = `${trackToPlay.artist} - ${trackToPlay.title}`;
            nowPlayingContainer.style.display = 'block';
            audioPlayer.src = trackToPlay.musicUrl;
            audioPlayer.play();
        } else {
            speechTextElement.textContent = "Музыка закончилась или библиотека пуста. Сделайте новый запрос.";
            nowPlayingContainer.style.display = 'none';
        }
    }
    
    // --- Обработчик нажатия кнопки (ЗАПУСКАЕТ РЕЖИМ AI) ---
    playButton.addEventListener('click', async () => {
        const userRequest = userRequestInput.value.trim();
        if (!userRequest) return;

        setButtonLoading(true);
        speechTextElement.textContent = "AI-диджей составляет плейлист...";
        nowPlayingContainer.style.display = 'none';
        audioPlayer.pause(); 

        const data = await fetchAiPlaylist(userRequest);
        setButtonLoading(false);

        if (data.error) {
            speechTextElement.textContent = `Произошла ошибка: ${data.error}`;
            isAiMode = false; // Сбрасываем режим AI в случае ошибки
            return;
        }

        // 1. Показываем подводку диджея, которую он прислал.
        speechTextElement.textContent = data.speechText || "К сожалению, не удалось найти подходящие треки.";

        if (data.playlist && data.playlist.length > 0) {
            // 2. Успех! Готовимся к запуску AI-плейлиста.
            currentAiPlaylist = data.playlist;
            currentTrackIndex = 0;
            isAiMode = true; // Включаем режим AI
            
            // 3. Запускаем первый трек. Дальше все пойдет по цепочке.
            playNextTrack();
        } else {
            // AI ничего не нашел, остаемся в режиме случайного радио.
            isAiMode = false;
        }
    });

    // --- Обработчик окончания трека (ПЕРЕКЛЮЧАТЕЛЬ) ---
    audioPlayer.addEventListener('ended', () => {
        // Если мы были в режиме AI, увеличиваем счетчик, чтобы перейти к следующему треку.
        if (isAiMode) {
            currentTrackIndex++;
        }
        // Просто вызываем "мозг" радио. Он сам решит, что делать дальше.
        playNextTrack();
    });

    // --- Обработчик Enter ---
    userRequestInput.addEventListener('keyup', (event) => {
        if (event.key === 'Enter') {
            event.preventDefault();
            playButton.click();
        }
    });
});

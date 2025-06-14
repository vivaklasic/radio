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
    fetchFullLibrary(); // Запускаем загрузку сразу

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

    // --- Главная функция проигрывания ---
    function playNextTrack() {
        let trackToPlay = null;

        if (isAiMode && currentTrackIndex < currentAiPlaylist.length) {
            // РЕЖИМ AI: Играем следующий трек из сгенерированного плейлиста
            trackToPlay = currentAiPlaylist[currentTrackIndex];
            speechTextElement.textContent = `В эфире: ${trackToPlay.title}`; // Обновляем статус
        } else {
            // РЕЖИМ ФОНОВОГО РАДИО
            isAiMode = false; // Выключаем режим AI
            if (fullLibrary.length > 0) {
                const randomIndex = Math.floor(Math.random() * fullLibrary.length);
                trackToPlay = fullLibrary[randomIndex];
                speechTextElement.textContent = "В эфире случайный трек...";
            }
        }

        if (trackToPlay) {
            trackInfoElement.textContent = `${trackToPlay.artist} - ${trackToPlay.title}`;
            nowPlayingContainer.style.display = 'block';
            audioPlayer.src = trackToPlay.musicUrl;
            audioPlayer.play();
        } else {
            speechTextElement.textContent = "Музыка закончилась. Сделайте новый запрос.";
            nowPlayingContainer.style.display = 'none';
        }
    }
    
    // --- Обработчик нажатия кнопки ---
    playButton.addEventListener('click', async () => {
        const userRequest = userRequestInput.value.trim();
        if (!userRequest) return;

        setButtonLoading(true);
        speechTextElement.textContent = "AI-диджей составляет плейлист...";
        nowPlayingContainer.style.display = 'none';

        const data = await fetchAiPlaylist(userRequest);
        setButtonLoading(false);

        if (data.error) {
            speechTextElement.textContent = `Произошла ошибка: ${data.error}`;
        } else if (data.playlist && data.playlist.length > 0) {
            speechTextElement.textContent = data.speechText;
            currentAiPlaylist = data.playlist;
            currentTrackIndex = 0;
            isAiMode = true;
            playNextTrack();
        } else {
            speechTextElement.textContent = data.speechText || "К сожалению, не удалось найти подходящие треки.";
        }
    });

    // --- Обработчик окончания трека ---
    audioPlayer.addEventListener('ended', () => {
        if (isAiMode) {
            currentTrackIndex++;
        }
        playNextTrack(); // Запускаем следующий трек (логика решит, какой именно)
    });

    // --- Обработчик Enter ---
    userRequestInput.addEventListener('keyup', (event) => {
        if (event.key === 'Enter') {
            event.preventDefault();
            playButton.click();
        }
    });
});

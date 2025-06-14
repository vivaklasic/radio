// Код app.js остается точно таким же, как в моем ответе про плейлист,
// но я продублирую его здесь с одним важным исправлением в обработчике кнопки.

document.addEventListener('DOMContentLoaded', () => {
    const userRequestInput = document.getElementById('user-request');
    const playButton = document.getElementById('play-button');
    const buttonText = document.querySelector('.button-text');
    const spinner = document.getElementById('spinner');
    const speechTextElement = document.getElementById('speech-text');
    const nowPlayingContainer = document.getElementById('now-playing');
    const trackInfoElement = document.getElementById('track-info');
    const audioPlayer = document.getElementById('audio-player');

    const backendUrl = 'https://radio-2gyc.onrender.com/get-radio-play';

    let currentPlaylist = [];
    let currentTrackIndex = 0;

    async function fetchRadioPlay(userRequest) {
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

    function setButtonLoading(isLoading) {
        playButton.disabled = isLoading;
        buttonText.style.display = isLoading ? 'none' : 'inline';
        spinner.style.display = isLoading ? 'block' : 'none';
    }

    function playTrack(trackIndex) {
        if (currentPlaylist && trackIndex < currentPlaylist.length) { // Добавлена проверка на существование плейлиста
            const track = currentPlaylist[trackIndex];
            trackInfoElement.textContent = `${track.artist} - ${track.title}`;
            nowPlayingContainer.style.display = 'block';
            audioPlayer.src = track.musicUrl;
            audioPlayer.play();
        } else {
            speechTextElement.textContent = "Музыкальный блок завершен. Что поставим дальше?";
            nowPlayingContainer.style.display = 'none';
        }
    }
    
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

        setButtonlong>
        setButtonLoading(false);

        if (data.error) {
            speechTextElement.textContent = `Произошла ошибка: ${data.error}`;
        } else {
            speechTextElement.textContent = data.speechText;
            
            // --- ГЛАВНОЕ ИЗМЕНЕНИЕ ЗДЕСЬ ---
            // Проверяем, что плейлист существует и в нем есть хотя бы одна песня
            if (data.playlist && data.playlist.length > 0) {
                currentPlaylist = data.playlist;
                currentTrackIndex = 0;
                playTrack(currentTrackIndex);
            } else {
                // Если плейлист пустой, просто выводим сообщение и ничего не проигрываем
                console.log("Получен пустой плейлист. Музыка не будет проигрываться.");
                nowPlayingContainer.style.display = 'none';
                // Текст от AI уже установлен, он скажет, что ничего не нашел
            }
        }
    });

    audioPlayer.addEventListener('ended', () => {
        currentTrackIndex++;
        playTrack(currentTrackIndex);
    });

    userRequestInput.addEventListener('keyup', (event) => {
        if (event.key === 'Enter') {
            event.preventDefault();
            playButton.click();
        }
    });
});

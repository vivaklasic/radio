document.addEventListener('DOMContentLoaded', () => {
    // --- Получаем элементы со страницы ---
    const userRequestInput = document.getElementById('user-request');
    const playButton = document.getElementById('play-button');
    const buttonText = document.querySelector('.button-text');
    const spinner = document.getElementById('spinner');
    const speechTextElement = document.getElementById('speech-text');
    const nowPlayingContainer = document.getElementById('now-playing');
    const trackInfoElement = document.getElementById('track-info');
    const audioPlayer = document.getElementById('audio-player');

    // --- URL вашего бэкенда на Render ---
    // !!! ИСПРАВЛЕНА ЭТА СТРОКА !!!
    const backendUrl = 'https://radio-2gyc.onrender.com/get-radio-play';
    // Для локальных тестов:
    // const backendUrl = 'http://127.0.0.1:5001/get-radio-play';

    // --- Функция для общения с бэкендом ---
    async function fetchRadioPlay(userRequest) {
        try {
            const response = await fetch(backendUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    request: userRequest,
                    userName: "Слушатель" // Имя можно сделать настраиваемым
                }),
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || `Ошибка сервера: ${response.status}`);
            }

            return response.json();
        } catch (error) {
            console.error('Ошибка сети или запроса:', error);
            // Возвращаем объект ошибки, чтобы обработать его в вызывающей функции
            return { error: `Не удалось связаться с сервером. ${error.message}` };
        }
    }

    // --- Функция для управления состоянием кнопки ---
    function setButtonLoading(isLoading) {
        if (isLoading) {
            playButton.disabled = true;
            buttonText.style.display = 'none';
            spinner.style.display = 'block';
        } else {
            playButton.disabled = false;
            buttonText.style.display = 'inline';
            spinner.style.display = 'none';
        }
    }

    // --- Главный обработчик нажатия на кнопку ---
    playButton.addEventListener('click', async () => {
        const userRequest = userRequestInput.value.trim();
        if (!userRequest) {
            speechTextElement.textContent = "Пожалуйста, введите ваш запрос.";
            return;
        }

        setButtonLoading(true);
        speechTextElement.textContent = "AI-диджей думает над вашим запросом...";
        nowPlayingContainer.style.display = 'none';

        const data = await fetchRadioPlay(userRequest);

        setButtonLoading(false);

        if (data.error) {
            speechTextElement.textContent = `Произошла ошибка: ${data.error}`;
        } else {
            // Успешный ответ от сервера
            speechTextElement.textContent = data.speechText;
            trackInfoElement.textContent = `${data.artist} - ${data.title}`;
            nowPlayingContainer.style.display = 'block';
            
            audioPlayer.src = data.musicUrl;
            audioPlayer.play();
        }
    });

    // Добавляем возможность отправки по нажатию Enter в поле ввода
    userRequestInput.addEventListener('keyup', (event) => {
        if (event.key === 'Enter') {
            event.preventDefault(); // Предотвращаем стандартное поведение (например, отправку формы)
            playButton.click(); // Имитируем нажатие на кнопку
        }
    });
});

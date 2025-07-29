// Отдельный модуль для отправки логов (можно вынести в отдельный файл sendLog.js)
export async function sendLogToTelegram(message, token) {
    try {
        const response = await fetch('/log', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Access-Token': token // Временный токен для проверки доступа
            },
            body: JSON.stringify({ message })
        });

        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(`Ошибка при отправке лога: ${response.status} ${response.statusText} — ${errorText}`);
        }
    } catch (err) {
        console.error(err);
        alert(`Ошибка при отправке лога: ${err.message}`);
    }
}

// Основной скрипт
document.addEventListener('DOMContentLoaded', function() {
    const ACCESS_TOKEN = getAccessToken(); // Получаем токен из cookie или sessionStorage

    // --- Проверка доступа для логов ---
    function getAccessToken() {
        // Пример получения токена из cookie
        const match = document.cookie.match(/(^| )access_token=([^;]+)/);
        return match ? match[2] : null;
    }

    // --- Проверка блокировки сторонних скриптов ---
    function detectScriptBlocking() {
        // Пример проверки: проверим, есть ли fetch и console.log
        if (typeof fetch !== 'function') {
            console.warn('Fetch API заблокирован');
            alert('Обнаружена блокировка скриптов — некоторые функции могут не работать.');
        }
        if (typeof console === 'undefined' || typeof console.log !== 'function') {
            console.warn('Консоль заблокирована');
            alert('Обнаружена блокировка консоли — некоторые ошибки не будут показаны.');
        }
        // Можно добавить больше детекторов по необходимости
    }

    detectScriptBlocking();

    // --- Модальное окно дисклеймера ---
    const modal = document.getElementById('disclaimerModal');
    if (sessionStorage.getItem('disclaimerAccepted') === 'true') {
        if (modal) modal.style.display = 'none';
    } else {
        if (modal) modal.style.display = 'flex';
    }

    // --- Отправка логов через серверный эндпоинт ---
    async function sendLog(message) {
        if (!ACCESS_TOKEN) {
            console.warn('Нет доступа для отправки логов (токен отсутствует)');
            return;
        }
        await sendLogToTelegram(message, ACCESS_TOKEN);
    }

    // --- Событие принятия дисклеймера ---
    const acceptBtn = document.getElementById('acceptBtn');
    if (acceptBtn) {
        acceptBtn.addEventListener('click', function() {
            if (modal) modal.style.display = 'none';
            sessionStorage.setItem('disclaimerAccepted', 'true');
            sendLog('✅ Пользователь принял дисклеймер');
        });
    }

    // --- Переключение вкладок с анимацией ---
    const tabButtons = document.querySelectorAll('.tab-btn');
    const tabContents = document.querySelectorAll('.tab-content');
    let currentTabIndex = 0;

    if (tabButtons[0]) tabButtons[0].classList.add('active');

    function switchTab(index) {
        if (index === currentTabIndex) return;

        const currentContent = tabContents[currentTabIndex];
        const nextContent = tabContents[index];
        const direction = index > currentTabIndex ? 'right' : 'left';

        tabContents.forEach(content => {
            content.classList.remove('enter-from-left', 'enter-from-right', 'enter-active', 'active');
            content.style.display = 'none';
        });

        nextContent.style.display = 'block';
        nextContent.classList.add(`enter-from-${direction}`);
        nextContent.offsetWidth; // Force reflow
        nextContent.classList.add('enter-active', 'active');

        tabButtons.forEach(btn => btn.classList.remove('active'));
        tabButtons[index].classList.add('active');

        currentTabIndex = index;

        setTimeout(() => {
            nextContent.classList.remove(`enter-from-${direction}`, 'enter-active');
        }, 400);
    }

    tabButtons.forEach((button, index) => {
        button.addEventListener('click', () => switchTab(index));
    });

    tabContents.forEach((content, i) => {
        content.style.display = i === 0 ? 'block' : 'none';
        if (i === 0) content.classList.add('active');
    });

    // --- Переключение языка с перезагрузкой страницы ---
    const langButtons = document.querySelectorAll('.lang-btn');
    langButtons.forEach(button => {
        button.addEventListener('click', function() {
            const lang = this.getAttribute('data-lang');
            window.location.href = `/change_language/${lang}`;
        });
    });

    // --- Переключение темы с плавной сменой CSS переменных ---
    const themeToggle = document.querySelector('.theme-toggle');
    const body = document.body;
    const themeIcon = themeToggle ? themeToggle.querySelector('i') : null;

    function setLightTheme() {
        body.classList.add('light-theme');
        if (themeIcon) {
            themeIcon.classList.remove('fa-moon');
            themeIcon.classList.add('fa-sun');
        }
        document.documentElement.style.setProperty('--bg-dark', '#f5f5f5');
        document.documentElement.style.setProperty('--bg-darker', '#e0e0e0');
        document.documentElement.style.setProperty('--bg-card', '#ffffff');
        document.documentElement.style.setProperty('--text-primary', '#333333');
        document.documentElement.style.setProperty('--text-secondary', '#666666');
        localStorage.setItem('theme', 'light');
    }

    function setDarkTheme() {
        body.classList.remove('light-theme');
        if (themeIcon) {
            themeIcon.classList.remove('fa-sun');
            themeIcon.classList.add('fa-moon');
        }
        document.documentElement.style.setProperty('--bg-dark', '#121212');
        document.documentElement.style.setProperty('--bg-darker', '#0a0a0a');
        document.documentElement.style.setProperty('--bg-card', '#1e1e1e');
        document.documentElement.style.setProperty('--text-primary', '#e0e0e0');
        document.documentElement.style.setProperty('--text-secondary', '#b0b0b0');
        localStorage.setItem('theme', 'dark');
    }

    function toggleTheme() {
        if (body.classList.contains('light-theme')) {
            setDarkTheme();
        } else {
            setLightTheme();
        }
    }

    if (themeToggle) themeToggle.addEventListener('click', toggleTheme);

    // Инициализация темы из localStorage
    if (localStorage.getItem('theme') === 'light') {
        setLightTheme();
    } else {
        setDarkTheme();
    }

    // --- Анимации при наведении на карточки ---
    const cards = document.querySelectorAll('.card');
    cards.forEach(card => {
        card.addEventListener('mouseenter', () => {
            card.classList.add('animate__pulse');
        });
        card.addEventListener('mouseleave', () => {
            card.classList.remove('animate__pulse');
        });
    });

    // --- Плавающая анимация логотипа ---
    const logo = document.querySelector('.logo i');
    if (logo) logo.classList.add('floating');

    // --- IntersectionObserver для появления элементов при скролле ---
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('animate__fadeInUp');
                observer.unobserve(entry.target);
            }
        });
    }, { threshold: 0.1 });

    document.querySelectorAll('.card, footer').forEach(el => observer.observe(el));
});

// --- Прелоадер — скрытие по загрузке страницы ---
window.addEventListener("load", () => {
    const preloader = document.getElementById("preloader");
    if (preloader) preloader.classList.add("hidden");
});

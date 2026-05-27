/**
 * Логин и регистрация. Работает с новым API: JSON-тело, JWT в ответе.
 */

document.addEventListener('DOMContentLoaded', function() {
    // Если уже залогинен — сразу в дашборд.
    if (Auth.getToken() && window.location.pathname === '/login') {
        window.location.href = '/dashboard';
        return;
    }

    document.getElementById('loginForm')?.addEventListener('submit', handleLogin);
    document.getElementById('registerForm')?.addEventListener('submit', handleRegister);

    // Live-фильтры на ввод: телефон — только цифры и +, имя — без цифр.
    const phoneInput = document.getElementById('regPhone');
    if (phoneInput) {
        phoneInput.addEventListener('input', (e) => {
            // Оставляем только цифры и опциональный + в начале.
            let v = e.target.value;
            const hasPlus = v.startsWith('+');
            v = v.replace(/\D/g, '');
            e.target.value = (hasPlus ? '+' : '') + v;
        });
    }
    const nameInput = document.getElementById('regName');
    if (nameInput) {
        nameInput.addEventListener('input', (e) => {
            // Убираем все цифры.
            e.target.value = e.target.value.replace(/[0-9]/g, '');
        });
    }
});

async function handleLogin(e) {
    e.preventDefault();
    const email = document.getElementById('loginEmail').value.trim();
    const password = document.getElementById('loginPassword').value;

    const btn = e.target.querySelector('button[type="submit"]');
    const oldText = btn.textContent;
    btn.disabled = true;
    btn.textContent = '⏳ Вход...';

    try {
        const data = await apiFetch('/auth/login', {
            method: 'POST',
            body: JSON.stringify({ email, password })
        });
        Auth.save(data);
        showSuccess('Вход выполнен!');
        setTimeout(() => { window.location.href = '/dashboard'; }, 600);
    } catch (error) {
        showError(error.message);
    } finally {
        btn.disabled = false;
        btn.textContent = oldText;
    }
}

async function handleRegister(e) {
    e.preventDefault();
    const payload = {
        full_name: document.getElementById('regName').value.trim(),
        email: document.getElementById('regEmail').value.trim(),
        phone: document.getElementById('regPhone').value.trim(),
        password: document.getElementById('regPassword').value
    };

    // Имя: только буквы (кириллица/латиница), пробелы и дефисы. Без цифр.
    if (!/^[A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё\s\-]{1,99}$/.test(payload.full_name)) {
        showError('Имя должно содержать только буквы (без цифр), минимум 2 символа.');
        return;
    }

    // Email: должен содержать @ и точку после неё. Простая проверка.
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(payload.email)) {
        showError('Введите корректный email (например, ivan@mail.ru).');
        return;
    }

    // Телефон: только цифры, опционально + в начале. Длина 10-15 цифр.
    if (!/^\+?\d{10,15}$/.test(payload.phone)) {
        showError('Телефон должен содержать только цифры (можно с + в начале), 10–15 цифр.');
        return;
    }

    if (payload.password.length < 8) {
        showError('Пароль должен быть не короче 8 символов.');
        return;
    }

    const btn = e.target.querySelector('button[type="submit"]');
    const oldText = btn.textContent;
    btn.disabled = true;
    btn.textContent = '⏳ Регистрация...';

    try {
        const data = await apiFetch('/auth/register', {
            method: 'POST',
            body: JSON.stringify(payload)
        });
        Auth.save(data);
        showSuccess('Регистрация успешна!');
        setTimeout(() => { window.location.href = '/dashboard'; }, 600);
    } catch (error) {
        showError(error.message);
    } finally {
        btn.disabled = false;
        btn.textContent = oldText;
    }
}

function showError(message) {
    const el = document.getElementById('errorMessage');
    if (!el) { alert(message); return; }
    el.textContent = `⚠️ ${message}`;
    el.classList.remove('d-none');
    document.getElementById('successMessage')?.classList.add('d-none');
}

function showSuccess(message) {
    const el = document.getElementById('successMessage');
    if (!el) return;
    el.textContent = `✅ ${message}`;
    el.classList.remove('d-none');
    document.getElementById('errorMessage')?.classList.add('d-none');
}

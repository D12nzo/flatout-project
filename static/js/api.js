/**
 * Общий API-клиент для FlatOut.
 * Хранит JWT-токен в localStorage и автоматически добавляет его в заголовки.
 */

const API_BASE = '/api';
const TOKEN_KEY = 'flatout_token';
const USER_KEY = 'flatout_user';

const Auth = {
    getToken() {
        return localStorage.getItem(TOKEN_KEY);
    },
    getUser() {
        const raw = localStorage.getItem(USER_KEY);
        return raw ? JSON.parse(raw) : null;
    },
    save(tokenResponse) {
        localStorage.setItem(TOKEN_KEY, tokenResponse.access_token);
        // role нормализуется в нижний регистр — упрощает все последующие сравнения в JS.
        localStorage.setItem(USER_KEY, JSON.stringify({
            user_id: tokenResponse.user_id,
            role: (tokenResponse.role || '').toLowerCase(),
            full_name: tokenResponse.full_name,
            email: tokenResponse.email
        }));
    },
    clear() {
        localStorage.removeItem(TOKEN_KEY);
        localStorage.removeItem(USER_KEY);
    },
    requireLogin() {
        if (!this.getToken()) {
            window.location.href = '/login';
            return false;
        }
        return true;
    }
};

/**
 * Универсальная обёртка над fetch с JWT.
 * Бросает Error с .message, в котором текст из поля detail сервера.
 */
async function apiFetch(path, options = {}) {
    const headers = options.headers ? { ...options.headers } : {};
    if (!(options.body instanceof FormData)) {
        headers['Content-Type'] = headers['Content-Type'] || 'application/json';
    }
    const token = Auth.getToken();
    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }

    const response = await fetch(API_BASE + path, { ...options, headers });

    if (response.status === 401) {
        // Токен просрочен или невалиден — выкидываем в логин.
        Auth.clear();
        if (window.location.pathname !== '/login') {
            window.location.href = '/login';
        }
        throw new Error('Сессия истекла, войдите снова');
    }

    if (!response.ok) {
        let detail = `HTTP ${response.status}`;
        try {
            const err = await response.json();
            detail = err.detail || JSON.stringify(err);
        } catch (_) { /* пусто */ }
        throw new Error(detail);
    }

    if (response.status === 204) return null;
    return response.json();
}

// Доступ из других скриптов.
window.Auth = Auth;
window.apiFetch = apiFetch;
window.API_BASE = API_BASE;

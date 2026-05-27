/**
 * Личный кабинет.
 * Загружает /api/auth/me, потом /api/appointments/me — этот эндпоинт сам разруливает
 * фильтрацию по роли. Для клиентов показывает вкладку "Записаться".
 */

let CURRENT_USER = null;

document.addEventListener('DOMContentLoaded', async () => {
    if (!Auth.requireLogin()) return;
    try {
        const me = await apiFetch('/auth/me');
        // Бэкенд возвращает role в верхнем регистре (CLIENT/BARBER/...).
        // Внутри фронта работаем в нижнем — нормализуем один раз.
        me.role = (me.role || '').toLowerCase();
        CURRENT_USER = me;
        renderHeader(CURRENT_USER);
        toggleBookingTab(CURRENT_USER);
        await loadAppointments();
        setInterval(loadAppointments, 30000);
    } catch (e) {
        console.error(e);
    }
});

function renderHeader(me) {
    const el = document.getElementById('userName');
    if (el) el.textContent = `${me.full_name || me.email} (${roleName(me.role)})`;
    const title = document.getElementById('apts-title');
    if (title) {
        const map = {
            client:  'Мои записи',
            barber:  'Записи на меня',
            manager: 'Записи моего филиала',
            admin:   'Все записи',
        };
        title.textContent = map[me.role] || 'Записи';
    }
}

function roleName(role) {
    return {
        client:  'Клиент',
        barber:  'Барбер',
        manager: 'Менеджер',
        admin:   'Администратор',
    }[role] || role;
}

function toggleBookingTab(me) {
    const li = document.getElementById('tab-booking-li');
    if (!li) return;
    if (me.role === 'client') li.classList.remove('d-none');
    else li.classList.add('d-none');
}

async function loadAppointments() {
    const container = document.getElementById('appointmentsList');
    if (!container) return;
    let apts;
    try {
        apts = await apiFetch('/appointments/me');
    } catch (e) {
        container.innerHTML = `<div class="alert alert-danger">⚠️ ${escapeHtml(e.message)}</div>`;
        return;
    }
    renderAppointments(apts);
    updateStats(apts);
}

function renderAppointments(apts) {
    const container = document.getElementById('appointmentsList');
    const me = CURRENT_USER;
    if (!me) return;

    if (apts.length === 0) {
        container.innerHTML = '<div class="alert alert-info">ℹ️ Записей пока нет</div>';
        return;
    }
    const isStaff = me.role === 'manager' || me.role === 'admin';
    const isBarber = me.role === 'barber';

    let html = '<div class="table-responsive"><table class="table table-hover">';
    html += `
        <thead class="table-dark">
            <tr>
                <th>Дата</th><th>Время</th>
                ${me.role !== 'client' ? '<th>Клиент</th>' : ''}
                <th>Услуга</th>
                ${me.role !== 'barber' ? '<th>Барбер</th>' : ''}
                <th>Филиал</th>
                <th>Цена</th>
                <th>Статус</th>
                <th>Действия</th>
            </tr>
        </thead><tbody>`;

    apts.forEach(a => {
        // Парсим ISO-строку напрямую, без new Date() — иначе браузер
        // сдвинет время на свою таймзону. Мы сохраняли локальное время филиала
        // под видом UTC, и так же показываем его обратно.
        const iso = a.scheduled_at || '';
        const datePart = iso.slice(0, 10);     // 2026-05-26
        const timePart = iso.slice(11, 16);    // 06:30
        // Переворачиваем в формат дд.мм.гггг
        const date = datePart.length === 10
            ? `${datePart.slice(8, 10)}.${datePart.slice(5, 7)}.${datePart.slice(0, 4)}`
            : datePart;
        const time = timePart;
        html += '<tr>';
        html += `<td>${date}</td><td><strong>${time}</strong></td>`;
        if (me.role !== 'client') {
            html += `<td>${escapeHtml(a.client_name) || '<small class="text-muted">—</small>'}<br>
                <small class="text-muted">${escapeHtml(a.client_comment || '')}</small></td>`;
        }
        html += `<td>${escapeHtml(a.service_name) || a.service_id}</td>`;
        if (me.role !== 'barber') {
            html += `<td>${escapeHtml(a.barber_name) || a.barber_id}</td>`;
        }
        html += `<td><small>${escapeHtml(a.branch_address) || a.branch_id}</small></td>`;
        html += `<td>${a.final_price}₽</td>`;
        html += `<td>${statusBadge(a.status)}</td>`;
        html += '<td>';
        if (a.status === 'PENDING' && (isStaff || isBarber)) {
            html += `<button class="btn btn-success btn-sm me-1" onclick="actConfirm('${a.id}')">✅</button>`;
        }
        if (a.status === 'CONFIRMED' && (isStaff || isBarber)) {
            html += `<button class="btn btn-primary btn-sm me-1" onclick="actComplete('${a.id}')">🏁</button>`;
        }
        if (a.status === 'PENDING' || a.status === 'CONFIRMED') {
            html += `<button class="btn btn-danger btn-sm" onclick="actCancel('${a.id}')">❌</button>`;
        }
        html += '</td></tr>';
    });
    html += '</tbody></table></div>';
    container.innerHTML = html;
}

function statusBadge(status) {
    return {
        PENDING:     '<span class="badge bg-warning text-dark">⏳ Ожидает</span>',
        CONFIRMED:   '<span class="badge bg-success">✅ Подтверждено</span>',
        COMPLETED:   '<span class="badge bg-primary">🏁 Завершено</span>',
        CANCELLED:   '<span class="badge bg-danger">❌ Отменено</span>',
    }[status] || `<span class="badge bg-secondary">${status}</span>`;
}

function updateStats(apts) {
    const total = apts.length;
    const pending   = apts.filter(a => a.status === 'PENDING').length;
    const confirmed = apts.filter(a => a.status === 'CONFIRMED').length;
    const completed = apts.filter(a => a.status === 'COMPLETED').length;
    setText('totalAppointments', total);
    setText('pendingAppointments', pending);
    setText('confirmedAppointments', confirmed);
    setText('completedAppointments', completed);
}

function setText(id, v) {
    const el = document.getElementById(id);
    if (el) el.textContent = v;
}

async function actConfirm(id) {
    if (!confirm('Подтвердить запись?')) return;
    await safeCall(`/appointments/${id}/confirm`, 'PUT');
}
async function actComplete(id) {
    if (!confirm('Отметить как выполненную?')) return;
    await safeCall(`/appointments/${id}/complete`, 'PUT');
}
async function actCancel(id) {
    const reason = prompt('Причина отмены (необязательно):') || null;
    await safeCall(`/appointments/${id}/cancel`, 'PUT', { reason });
}
async function safeCall(path, method, body) {
    try {
        await apiFetch(path, { method, body: body ? JSON.stringify(body) : undefined });
        await loadAppointments();
    } catch (e) {
        alert('❌ ' + e.message);
    }
}

function escapeHtml(s) {
    if (s == null) return '';
    return String(s)
        .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;').replaceAll("'", '&#39;');
}

function logout() {
    Auth.clear();
    window.location.href = '/login';
}

window.actConfirm = actConfirm;
window.actComplete = actComplete;
window.actCancel = actCancel;
window.logout = logout;

// Делаем глобальный аксессор для booking.js (он использует CURRENT_USER и loadAppointments).
window.getCurrentUser = () => CURRENT_USER;
window.reloadAppointments = loadAppointments;

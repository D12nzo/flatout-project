/**
 * Главная страница (лендинг).
 * Показывает: филиалы (карточками), услуги и барберов (в модалках).
 * Никакой формы записи — она в личном кабинете.
 */

document.addEventListener('DOMContentLoaded', async () => {
    updateAuthUI();
    await loadBranchesCards();

    document.getElementById('barbersModal')?.addEventListener('show.bs.modal', loadBarbersModal);
    document.getElementById('servicesModal')?.addEventListener('show.bs.modal', loadServicesModal);
});

function updateAuthUI() {
    const user = Auth.getUser();
    const loginLink = document.getElementById('navLoginLink');
    const userBox = document.getElementById('navUserBox');
    const userNameEl = document.getElementById('navUserName');
    if (user && loginLink && userBox) {
        loginLink.classList.add('d-none');
        userBox.classList.remove('d-none');
        if (userNameEl) userNameEl.textContent = user.full_name || user.email;
    }
}

// ==================== Карточки филиалов на главной ====================
async function loadBranchesCards() {
    const container = document.getElementById('branchesCards');
    if (!container) return;
    try {
        const branches = await apiFetch('/branches/');
        if (!branches || branches.length === 0) {
            container.innerHTML = '<div class="col-12 text-center text-muted">Филиалы не найдены</div>';
            return;
        }
        let html = '';
        branches.forEach(b => {
            const opens = (b.opens_at || '').slice(0, 5);
            const closes = (b.closes_at || '').slice(0, 5);
            html += `
                <div class="col-md-4 mb-3">
                    <div class="card h-100 shadow-sm">
                        <div class="card-body">
                            <h5 class="card-title">📍 ${escapeHtml(b.address)}</h5>
                            <p class="card-text mb-1"><strong>Телефон:</strong> ${escapeHtml(b.phone)}</p>
                            <p class="card-text mb-1"><strong>Часы работы:</strong> ${opens}–${closes}</p>
                            <p class="card-text"><strong>Рабочих мест:</strong> ${b.work_stations}</p>
                        </div>
                    </div>
                </div>`;
        });
        container.innerHTML = html;
    } catch (e) {
        container.innerHTML = `<div class="col-12 text-center text-danger">⚠️ ${escapeHtml(e.message)}</div>`;
    }
}

// ==================== Модалка услуг ====================
async function loadServicesModal() {
    const list = document.getElementById('servicesList');
    if (!list) return;
    list.innerHTML = '<div class="text-center"><div class="spinner-border"></div></div>';
    try {
        const services = await apiFetch('/services/');
        const byCategory = {};
        services.forEach(s => { (byCategory[s.category] = byCategory[s.category] || []).push(s); });
        let html = '';
        Object.entries(byCategory).forEach(([cat, items]) => {
            html += `<h5 class="mt-3 mb-3">${escapeHtml(cat)}</h5><div class="list-group mb-3">`;
            items.forEach(s => {
                html += `
                    <div class="list-group-item d-flex justify-content-between align-items-center">
                        <div>
                            <h6 class="mb-1">${escapeHtml(s.name)}</h6>
                            <small class="text-muted">⏱️ ${s.duration_minutes} мин</small>
                        </div>
                        <strong class="text-primary">${s.base_price}₽</strong>
                    </div>`;
            });
            html += '</div>';
        });
        list.innerHTML = html;
    } catch (e) {
        list.innerHTML = `<div class="alert alert-danger">${escapeHtml(e.message)}</div>`;
    }
}

// ==================== Модалка барберов ====================
async function loadBarbersModal() {
    const list = document.getElementById('barbersList');
    if (!list) return;
    list.innerHTML = '<div class="text-center"><div class="spinner-border"></div></div>';
    try {
        const [barbers, branches] = await Promise.all([
            apiFetch('/barbers/'),
            apiFetch('/branches/'),
        ]);
        const branchById = Object.fromEntries(branches.map(b => [b.id, b.address]));
        let html = '<div class="row">';
        barbers.forEach(b => {
            const rating = (typeof b.rating === 'number') ? b.rating.toFixed(1) : b.rating;
            html += `
                <div class="col-md-6 mb-3">
                    <div class="card h-100">
                        <div class="card-body">
                            <h5 class="card-title">👨‍🦰 ${escapeHtml(b.full_name || '—')}</h5>
                            <p class="card-text mb-1">
                                <small class="text-muted">📍 ${escapeHtml(branchById[b.branch_id] || b.branch_id)}</small>
                            </p>
                            <p class="card-text">
                                <strong>Рейтинг:</strong> ⭐ ${rating}/5.0
                            </p>
                        </div>
                    </div>
                </div>`;
        });
        html += '</div>';
        list.innerHTML = html;
    } catch (e) {
        list.innerHTML = `<div class="alert alert-danger">${escapeHtml(e.message)}</div>`;
    }
}

// ==================== utils ====================
function escapeHtml(s) {
    if (s == null) return '';
    return String(s)
        .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;').replaceAll("'", '&#39;');
}

function logout() {
    Auth.clear();
    window.location.href = '/';
}
window.logout = logout;

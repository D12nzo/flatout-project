/**
 * Форма записи в личном кабинете.
 * Поддерживает два режима:
 *   1) "Сначала время" — клиент выбирает время → видит барберов, свободных в этот момент.
 *   2) "Сначала барбер" — клиент выбирает барбера → видит его свободные слоты.
 * Источник слотов — один и тот же эндпоинт /api/appointments/available.
 */

const BOOK = {
    branches: [],
    services: [],
    barbers: [],          // все барберы (с branch_id)
    slots: [],            // последний загруженный массив слотов
    selectedBranchId: null,
    selectedServiceId: null,
    selectedDate: null,
    mode: 'time',         // 'time' | 'barber'
    selection: null,      // {barber_id, barber_name, start, duration_minutes}
};

document.addEventListener('DOMContentLoaded', initBooking);

async function initBooking() {
    // Инициализируем только если форма вообще есть в DOM (мы на странице с дашбордом).
    if (!document.getElementById('bookSubmit')) return;

    // Подгружаем каталоги.
    try {
        const [branches, services, barbers] = await Promise.all([
            apiFetch('/branches/'),
            apiFetch('/services/'),
            apiFetch('/barbers/'),
        ]);
        BOOK.branches = branches;
        BOOK.services = services;
        BOOK.barbers = barbers;
        renderBranches();
        renderServiceSelect();
        setMinDate();
        bindHandlers();
    } catch (e) {
        showBookError('Не удалось загрузить каталог: ' + e.message);
    }
}

function setMinDate() {
    const di = document.getElementById('bookDate');
    if (di) di.min = new Date().toISOString().split('T')[0];
}

// ==================== Рендер исходных контролов ====================

function renderBranches() {
    const wrap = document.getElementById('bookBranches');
    if (!wrap) return;
    wrap.innerHTML = BOOK.branches.map((b, i) => {
        const opens = (b.opens_at || '').slice(0, 5);
        const closes = (b.closes_at || '').slice(0, 5);
        const id = `bookBranch_${b.id}`;
        return `
            <div class="form-check">
                <input class="form-check-input" type="radio" name="bookBranch"
                       id="${id}" value="${b.id}" ${i === 0 ? 'checked' : ''}>
                <label class="form-check-label" for="${id}">
                    📍 ${escapeHtml(b.address)} (${opens}–${closes})
                </label>
            </div>`;
    }).join('');
    BOOK.selectedBranchId = BOOK.branches[0]?.id || null;
}

function renderServiceSelect() {
    const sel = document.getElementById('bookService');
    if (!sel) return;
    sel.innerHTML = '<option value="">Выберите услугу...</option>';
    const byCategory = {};
    BOOK.services.forEach(s => { (byCategory[s.category] = byCategory[s.category] || []).push(s); });
    Object.entries(byCategory).forEach(([cat, items]) => {
        const og = document.createElement('optgroup');
        og.label = cat;
        items.forEach(s => {
            const opt = document.createElement('option');
            opt.value = s.id;
            opt.textContent = `${s.name} — ${s.base_price}₽ (${s.duration_minutes} мин)`;
            og.appendChild(opt);
        });
        sel.appendChild(og);
    });
}

// ==================== Обработчики ====================

function bindHandlers() {
    document.body.addEventListener('change', (e) => {
        const t = e.target;
        if (!t) return;
        if (t.name === 'bookBranch') {
            BOOK.selectedBranchId = t.value;
            BOOK.selection = null;
            refreshStep();
        } else if (t.id === 'bookService') {
            BOOK.selectedServiceId = t.value;
            BOOK.selection = null;
            refreshStep();
        } else if (t.id === 'bookDate') {
            BOOK.selectedDate = t.value;
            BOOK.selection = null;
            refreshStep();
        } else if (t.name === 'bookMode') {
            BOOK.mode = t.value;
            BOOK.selection = null;
            refreshStep();
        }
    });

    document.getElementById('bookSubmit').addEventListener('click', submitBooking);
    document.getElementById('confirmBookingButton')?.addEventListener('click', reallySubmitBooking);
}

// ==================== Главный метод: пересчёт содержимого "Шага 4" ====================

async function refreshStep() {
    const area = document.getElementById('bookStepArea');
    updateSelectionLine();
    updateSubmitState();
    if (!area) return;

    if (!BOOK.selectedBranchId || !BOOK.selectedServiceId || !BOOK.selectedDate) {
        area.innerHTML = `<div class="text-muted small">
            Выберите филиал, услугу и дату — появится выбор времени/мастера.
        </div>`;
        return;
    }

    area.innerHTML = '<div class="text-muted small">⏳ Загрузка слотов...</div>';
    try {
        const url = `/appointments/available`
            + `?branch_id=${encodeURIComponent(BOOK.selectedBranchId)}`
            + `&service_id=${encodeURIComponent(BOOK.selectedServiceId)}`
            + `&target_date=${encodeURIComponent(BOOK.selectedDate)}`;
        const data = await apiFetch(url);
        BOOK.slots = data.slots || [];
        if (BOOK.slots.length === 0) {
            area.innerHTML = '<div class="alert alert-warning mb-0">На эту дату свободных слотов нет.</div>';
            return;
        }
        if (BOOK.mode === 'time') renderModeByTime(area);
        else renderModeByBarber(area);
    } catch (e) {
        area.innerHTML = `<div class="alert alert-danger mb-0">⚠️ ${escapeHtml(e.message)}</div>`;
    }
}

// ==================== Режим "Сначала время" ====================

function renderModeByTime(area) {
    // Уникальные времена → список кнопок.
    const timeSet = new Set(BOOK.slots.map(s => s.start.slice(11, 16)));
    const times = Array.from(timeSet).sort();
    let html = '<div class="mb-2"><strong>🕐 Свободное время</strong></div>';
    html += '<div id="timesRow" class="d-flex flex-wrap mb-3">';
    times.forEach(t => {
        html += `<button type="button" class="btn btn-outline-primary btn-sm m-1 time-btn"
                         data-time="${t}">${t}</button>`;
    });
    html += '</div>';
    html += '<div id="barbersForTime"></div>';
    area.innerHTML = html;

    area.querySelectorAll('.time-btn').forEach(b => {
        b.addEventListener('click', () => {
            area.querySelectorAll('.time-btn').forEach(x => {
                x.classList.remove('btn-primary', 'active'); x.classList.add('btn-outline-primary');
            });
            b.classList.remove('btn-outline-primary');
            b.classList.add('btn-primary', 'active');
            showBarbersForTime(b.dataset.time);
        });
    });
}

function showBarbersForTime(time) {
    const wrap = document.getElementById('barbersForTime');
    if (!wrap) return;
    const matching = BOOK.slots.filter(s => s.start.slice(11, 16) === time);

    let html = '<div class="mb-2"><strong>👨‍🦰 Свободные мастера в это время</strong></div><div class="row">';
    matching.forEach(s => {
        // Найдём барбера в каталоге для рейтинга/цены.
        const barber = BOOK.barbers.find(b => b.id === s.barber_id);
        const rating = barber ? `⭐ ${Number(barber.rating).toFixed(1)}` : '';
        const priceNote = barber && barber.price_multiplier !== 1.0
            ? ` <small class="text-muted">×${barber.price_multiplier}</small>` : '';
        html += `
            <div class="col-md-6 mb-2">
                <button type="button"
                        class="btn btn-outline-dark text-start w-100 barber-btn"
                        data-barber-id="${s.barber_id}"
                        data-start="${s.start}"
                        data-duration="${s.duration_minutes}"
                        data-barber-name="${escapeHtml(s.barber_name || '')}">
                    <strong>${escapeHtml(s.barber_name || '?')}</strong> ${rating}${priceNote}
                </button>
            </div>`;
    });
    html += '</div>';
    wrap.innerHTML = html;

    wrap.querySelectorAll('.barber-btn').forEach(b => {
        b.addEventListener('click', () => {
            wrap.querySelectorAll('.barber-btn').forEach(x => {
                x.classList.remove('btn-dark', 'active'); x.classList.add('btn-outline-dark');
            });
            b.classList.remove('btn-outline-dark');
            b.classList.add('btn-dark', 'active');
            BOOK.selection = {
                barber_id: b.dataset.barberId,
                barber_name: b.dataset.barberName,
                start: b.dataset.start,
                duration_minutes: parseInt(b.dataset.duration, 10),
            };
            updateSelectionLine();
            updateSubmitState();
        });
    });
}

// ==================== Режим "Сначала барбер" ====================

function renderModeByBarber(area) {
    // Группируем слоты по barber_id.
    const byBarber = {};
    BOOK.slots.forEach(s => {
        (byBarber[s.barber_id] = byBarber[s.barber_id] || []).push(s);
    });
    const entries = Object.entries(byBarber);

    let html = '<div class="mb-2"><strong>👨‍🦰 Мастера филиала</strong></div>';
    html += '<div id="barbersRow" class="d-flex flex-wrap mb-3">';
    entries.forEach(([barberId, slots]) => {
        const barber = BOOK.barbers.find(b => b.id === barberId);
        const name = slots[0].barber_name || barber?.full_name || '?';
        const rating = barber ? `⭐ ${Number(barber.rating).toFixed(1)}` : '';
        html += `
            <button type="button" class="btn btn-outline-dark m-1 master-btn"
                    data-barber-id="${barberId}">
                <strong>${escapeHtml(name)}</strong> ${rating}
            </button>`;
    });
    html += '</div>';
    html += '<div id="timesForBarber"></div>';
    area.innerHTML = html;

    area.querySelectorAll('.master-btn').forEach(b => {
        b.addEventListener('click', () => {
            area.querySelectorAll('.master-btn').forEach(x => {
                x.classList.remove('btn-dark', 'active'); x.classList.add('btn-outline-dark');
            });
            b.classList.remove('btn-outline-dark');
            b.classList.add('btn-dark', 'active');
            showTimesForBarber(b.dataset.barberId);
        });
    });
}

function showTimesForBarber(barberId) {
    const wrap = document.getElementById('timesForBarber');
    if (!wrap) return;
    const matching = BOOK.slots.filter(s => s.barber_id === barberId)
                              .sort((a, b) => a.start.localeCompare(b.start));

    let html = '<div class="mb-2"><strong>🕐 Свободное время этого мастера</strong></div>';
    html += '<div class="d-flex flex-wrap">';
    matching.forEach(s => {
        const t = s.start.slice(11, 16);
        html += `<button type="button" class="btn btn-outline-primary btn-sm m-1 slot-btn"
                         data-barber-id="${s.barber_id}"
                         data-start="${s.start}"
                         data-duration="${s.duration_minutes}"
                         data-barber-name="${escapeHtml(s.barber_name || '')}">${t}</button>`;
    });
    html += '</div>';
    wrap.innerHTML = html;

    wrap.querySelectorAll('.slot-btn').forEach(b => {
        b.addEventListener('click', () => {
            wrap.querySelectorAll('.slot-btn').forEach(x => {
                x.classList.remove('btn-primary', 'active'); x.classList.add('btn-outline-primary');
            });
            b.classList.remove('btn-outline-primary');
            b.classList.add('btn-primary', 'active');
            BOOK.selection = {
                barber_id: b.dataset.barberId,
                barber_name: b.dataset.barberName,
                start: b.dataset.start,
                duration_minutes: parseInt(b.dataset.duration, 10),
            };
            updateSelectionLine();
            updateSubmitState();
        });
    });
}

// ==================== Подсказка под формой + кнопка submit ====================

// Возвращает {basePrice, multiplier, final} для текущего выбора, или null.
function computePrice() {
    if (!BOOK.selectedServiceId || !BOOK.selection) return null;
    const service = BOOK.services.find(s => s.id === BOOK.selectedServiceId);
    if (!service) return null;
    const barber = BOOK.barbers.find(b => b.id === BOOK.selection.barber_id);
    const mult = (barber && typeof barber.price_multiplier === 'number') ? barber.price_multiplier : 1;
    return {
        basePrice: service.base_price,
        multiplier: mult,
        final: Math.round(service.base_price * mult * 100) / 100,
        serviceName: service.name,
        durationMinutes: service.duration_minutes,
    };
}

// Адрес выбранного филиала (для модалки/подсказки).
function selectedBranchAddress() {
    const b = BOOK.branches.find(x => x.id === BOOK.selectedBranchId);
    return b ? b.address : '';
}

function updateSelectionLine() {
    const line = document.getElementById('bookSelection');
    if (!line) return;
    if (!BOOK.selection) {
        line.classList.add('d-none');
        line.innerHTML = '';
        return;
    }
    const t = BOOK.selection.start.slice(11, 16);
    const d = BOOK.selection.start.slice(0, 10);
    const p = computePrice();

    let priceLine = '';
    if (p) {
        if (p.multiplier !== 1) {
            priceLine = `<br><strong>💰 Цена:</strong> ${p.basePrice}₽ × ${p.multiplier} = <strong>${p.final}₽</strong>
                <small class="text-muted">(коэффициент мастера ${p.multiplier})</small>`;
        } else {
            priceLine = `<br><strong>💰 Цена:</strong> <strong>${p.final}₽</strong>`;
        }
    }
    line.innerHTML = `📋 <strong>Вы выбрали:</strong> ${d} в ${t}, мастер ${escapeHtml(BOOK.selection.barber_name)}${priceLine}`;
    line.classList.remove('d-none');
}

function updateSubmitState() {
    const btn = document.getElementById('bookSubmit');
    if (!btn) return;
    btn.disabled = !(BOOK.selection
                     && BOOK.selectedBranchId
                     && BOOK.selectedServiceId);
}

// ==================== Отправка через модалку подтверждения ====================

// Клик по кнопке "Подтвердить запись" — открывает модалку с резюме.
async function submitBooking() {
    hideBookMessages();
    const me = window.getCurrentUser ? window.getCurrentUser() : null;
    if (!me || me.role !== 'client') {
        showBookError('Записываться могут только клиенты.');
        return;
    }
    if (!BOOK.selection) {
        showBookError('Выберите свободный слот.');
        return;
    }
    openConfirmModal();
}

function openConfirmModal() {
    const p = computePrice();
    const t = BOOK.selection.start.slice(11, 16);
    const d = BOOK.selection.start.slice(0, 10);
    const comment = (document.getElementById('bookComment').value || '').trim();

    const html = `
        <table class="table table-sm mb-0">
            <tbody>
                <tr><th class="w-25">📍 Филиал</th><td>${escapeHtml(selectedBranchAddress())}</td></tr>
                <tr><th>✂️ Услуга</th><td>${escapeHtml(p ? p.serviceName : '—')}
                    <small class="text-muted">(${p ? p.durationMinutes : '?'} мин)</small></td></tr>
                <tr><th>📅 Дата</th><td><strong>${d}</strong></td></tr>
                <tr><th>🕐 Время</th><td><strong>${t}</strong></td></tr>
                <tr><th>👨‍🦰 Мастер</th><td>${escapeHtml(BOOK.selection.barber_name)}</td></tr>
                <tr><th>💰 Стоимость</th>
                    <td>
                        ${p && p.multiplier !== 1
                            ? `${p.basePrice}₽ × ${p.multiplier} = <strong class="text-warning">${p.final}₽</strong>
                               <br><small class="text-muted">Цена включает индивидуальный коэффициент мастера</small>`
                            : `<strong class="text-warning">${p ? p.final : '?'}₽</strong>`}
                    </td>
                </tr>
                ${comment ? `<tr><th>💬 Комментарий</th><td>${escapeHtml(comment)}</td></tr>` : ''}
            </tbody>
        </table>
        <div class="alert alert-warning small mt-3 mb-0">
            ⚠️ Проверьте данные. После подтверждения слот будет забронирован.
        </div>`;
    document.getElementById('confirmModalBody').innerHTML = html;

    // Получаем/создаём Bootstrap модальный объект.
    const modalEl = document.getElementById('confirmBookingModal');
    const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
    modal.show();
}

// Реальная отправка вызывается из обработчика кнопки модалки.
async function reallySubmitBooking() {
    hideBookMessages();
    const me = window.getCurrentUser ? window.getCurrentUser() : null;
    if (!me || me.role !== 'client') { showBookError('Записываться могут только клиенты.'); return; }
    if (!BOOK.selection) { showBookError('Выберите свободный слот.'); return; }

    const submitBtn = document.getElementById('bookSubmit');
    const oldText = submitBtn.textContent;
    submitBtn.disabled = true;
    submitBtn.textContent = '⏳ Отправка...';

    const modalEl = document.getElementById('confirmBookingModal');
    bootstrap.Modal.getInstance(modalEl)?.hide();

    const payload = {
        branch_id:    BOOK.selectedBranchId,
        barber_id:    BOOK.selection.barber_id,
        service_id:   BOOK.selectedServiceId,
        scheduled_at: BOOK.selection.start,
        client_comment: (document.getElementById('bookComment').value || '').trim() || null,
    };

    try {
        const created = await apiFetch('/appointments/', {
            method: 'POST',
            body: JSON.stringify(payload),
        });
        showBookSuccess(
            `Запись создана! ${created.scheduled_at.slice(0,10)} в ${created.scheduled_at.slice(11,16)}, итог: ${created.final_price}₽`
        );
        BOOK.selection = null;
        document.getElementById('bookComment').value = '';
        await refreshStep();
        if (window.reloadAppointments) await window.reloadAppointments();
    } catch (e) {
        showBookError(e.message);
    } finally {
        submitBtn.textContent = oldText;
        updateSubmitState();
    }
}

// ==================== UI helpers ====================

function showBookSuccess(msg) {
    const el = document.getElementById('bookSuccess');
    if (!el) return;
    el.textContent = '✅ ' + msg;
    el.classList.remove('d-none');
    document.getElementById('bookError')?.classList.add('d-none');
    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
}
function showBookError(msg) {
    const el = document.getElementById('bookError');
    if (!el) return;
    el.textContent = '⚠️ ' + msg;
    el.classList.remove('d-none');
    document.getElementById('bookSuccess')?.classList.add('d-none');
    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
}
function hideBookMessages() {
    document.getElementById('bookSuccess')?.classList.add('d-none');
    document.getElementById('bookError')?.classList.add('d-none');
}
function escapeHtml(s) {
    if (s == null) return '';
    return String(s)
        .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;').replaceAll("'", '&#39;');
}

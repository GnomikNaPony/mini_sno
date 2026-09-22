'use strict';
const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const paths = {
  chat: '<path d="M21 11.5a8.4 8.4 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.4 8.4 0 0 1-3.8-.9L3 21l1.9-5.7a8.4 8.4 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.4 8.4 0 0 1 3.8-.9h.5a8.5 8.5 0 0 1 8 8v.5Z"/><path d="M8 10h8M8 14h5"/>',
  folder: '<path d="M3 7V5a2 2 0 0 1 2-2h5l2 3h7a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z"/><path d="M3 10h18"/>',
  globe: '<circle cx="12" cy="12" r="9"/><ellipse cx="12" cy="12" rx="4" ry="9"/><path d="M3 12h18"/>',
  sliders: '<path d="M4 6h7m4 0h5M4 12h3m4 0h9M4 18h10m4 0h2"/><circle cx="13" cy="6" r="2"/><circle cx="9" cy="12" r="2"/><circle cx="16" cy="18" r="2"/>',
  calendar: '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M16 3v4M8 3v4M3 11h18M8 15h2M14 15h2"/>',
  sparkles: '<path d="m12 3 2.6 6.4L21 12l-6.4 2.6L12 21l-2.6-6.4L3 12l6.4-2.6L12 3ZM20 2v4M18 4h4"/>',
  files: '<path d="M14 2H5v17h14V7l-5-5Z"/><path d="M14 2v5h5M9 11h6M9 15h4M8 22h14V9"/>',
  file: '<path d="M14 2H5v20h14V7l-5-5Z"/><path d="M14 2v5h5M8 12h8M8 16h6"/>',
  image: '<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8" cy="8" r="1.5"/><path d="m21 15-5-5L5 21"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7v1"/>',
  logout: '<path d="M9 4H4v16h5M9 12h12m-4-4 4 4-4 4"/>',
};
const icon = name => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[name] || paths.file}</svg>`;
const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[char]));
function icons(root = document) { $$('[data-icon]', root).forEach(el => el.innerHTML = icon(el.dataset.icon)); }
let state = null, jobs = [], page = 'dialog', authMode = 'login', pollTimer = null, toastTimer = null;
let jobsSignature = '', settingsDirty = false, polling = false;
const names = {dialog: 'Диалог с редакцией', archive: 'Мои материалы', sources: 'Источники новостей', settings: 'Настройки'};

async function api(path, method = 'GET', body) {
  let res;
  try { res = await fetch('/api' + path, {method, credentials: 'same-origin', headers: body ? {'Content-Type': 'application/json'} : {}, body: body ? JSON.stringify(body) : undefined}); }
  catch { throw new Error('Нет связи с сервером. Проверьте, что приложение запущено.'); }
  const data = await res.json();
  if (!res.ok) {
    if (res.status === 401 && !['/login', '/register'].includes(path)) showAuth();
    const detail = Array.isArray(data.detail) ? data.detail.map(d => d.msg.replace('Value error, ', '')).join('\n') : data.detail;
    throw new Error(detail || 'Не удалось выполнить запрос');
  }
  return data;
}
function toast(message, error = false) {
  const el = $('#toast'); el.textContent = message; el.className = 'toast' + (error ? ' error' : ''); el.hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => el.hidden = true, 4500);
}
function showAuth() {
  clearTimeout(pollTimer); state = null; jobs = []; jobsSignature = ''; settingsDirty = false;
  $('#toast').hidden = true;
  $('#app-screen').hidden = true; $('#auth-screen').hidden = false;
}
function changeAuth(mode) {
  authMode = mode;
  const register = mode === 'register';
  $('#name-field').hidden = !register;
  $('#auth-form').elements.name.required = register;
  $('#auth-form').elements.password.autocomplete = register ? 'new-password' : 'current-password';
  $('#auth-title').textContent = register ? 'Своя орбита открытий' : 'Рады видеть вас';
  $('#auth-subtitle').textContent = register ? 'Создайте аккаунт для вашего научного общества.' : 'Войдите, чтобы продолжить работу над постами.';
  $('#auth-submit').innerHTML = (register ? 'Создать аккаунт' : 'Войти в редакцию') + ' <span>↗</span>';
  $$('[data-auth]').forEach(b => b.classList.toggle('selected', b.dataset.auth === mode));
  $('#auth-error').textContent = '';
}
function setPage(next) {
  page = next;
  $$('.page').forEach(el => el.hidden = el.id !== 'page-' + next);
  $$('.nav-item').forEach(el => { el.classList.toggle('active', el.dataset.page === next); if (el.dataset.page === next) el.setAttribute('aria-current', 'page'); else el.removeAttribute('aria-current'); });
  $('#page-crumb').textContent = names[next];
  document.title = `${names[next]} — Орбита`;
  window.scrollTo({top: 0, behavior: 'instant'});
}
function dateLabel(value, year = false) {
  return new Intl.DateTimeFormat('ru-RU', {day: 'numeric', month: 'long', ...(year ? {year: 'numeric'} : {}), timeZone: 'Europe/Moscow'}).format(new Date(value.length === 10 ? value + 'T12:00:00+03:00' : value));
}
function shortDate(value) { return dateLabel(value); }
function setPeriod(days) {
  const end = state.today;
  const start = new Date(end + 'T12:00:00Z'); start.setUTCDate(start.getUTCDate() - days + 1);
  $('#date-from').value = start.toISOString().slice(0, 10); $('#date-to').value = end;
}
function renderState(fill = false) {
  const {user, settings: s} = state;
  $('#user-name').textContent = user.name; $('#user-email').textContent = user.email; $('#user-avatar').textContent = user.name[0].toUpperCase();
  $('#next-run').textContent = s.weekly_enabled && state.next_run ? new Intl.DateTimeFormat('ru-RU', {day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Moscow'}).format(new Date(state.next_run)) : 'Когда вам удобно';
  $('#schedule-caption').textContent = s.weekly_enabled ? 'Раз в неделю · за 7 предыдущих дней · МСК' : 'Расписание на паузе. Создавайте посты по кнопке.';
  $('#schedule-badge').textContent = s.weekly_enabled ? 'По расписанию' : 'На паузе';
  $('#community-title').textContent = s.community_url ? 'Ссылка сохранена' : 'Знакомство ещё впереди';
  $('#community-caption').textContent = s.community_url ? 'Образцы текста и цвет обложки — в настройках.' : 'Добавьте ссылку и образцы постов, когда будете готовы.';
  $('#date-from').max = state.today; $('#date-to').max = state.today;
  const provider = state.ai_provider === 'ollama' ? 'локально через Ollama' : state.ai_provider === 'openai' ? 'через OpenAI API' : 'отключён';
  $('#ai-status').textContent = state.ai_enabled ? `ИИ-редактор: ${state.ai_model} (${provider}). Модель доступна; правила и примеры учитываются при создании текста.` : `Выбран ИИ-редактор ${state.ai_model || provider}, но модель сейчас недоступна. Будет создан обычный дайджест. Проверьте настройки сервера.`;
  $('#sources-list').innerHTML = Object.entries(state.sources).map(([key, src]) => {
    const status = state.collection?.sources[key];
    return `<article class="source-card"><span class="source-symbol">${key === 'naked' ? 'N' : 'э'}</span><h2>${esc(src.name)}</h2><p>${esc(src.description)}</p><p class="source-status">${status ? status.ok ? `● Лента доступна · ${status.count} публикаций в последнем чтении` : '○ Временно недоступен — используем архив' : '○ Ожидает первого чтения'}</p><a href="${esc(src.home)}" target="_blank" rel="noopener noreferrer">Открыть издание ↗</a></article>`;
  }).join('');
  $('#archive-coverage').textContent = state.archive.count ? `В архиве ${state.archive.count} публикаций: с ${dateLabel(state.archive.oldest, true)} по ${dateLabel(state.archive.newest, true)}. ` + (state.collection ? 'Последняя проверка: ' + new Intl.DateTimeFormat('ru-RU', {dateStyle: 'short', timeStyle: 'short', timeZone: 'Europe/Moscow'}).format(new Date(state.collection.at)) + ' МСК.' : '') : 'Архив пока пуст. Первое чтение источников начнётся автоматически.';
  if (fill) {
    const form = $('#settings-form');
    for (const [key, value] of Object.entries(s)) {
      const input = form.elements.namedItem(key);
      if (input) { if (input.type === 'checkbox') input.checked = value; else input.value = value; }
    }
    $('#source-options').innerHTML = Object.entries(state.sources).map(([key, src]) => `<label><input type="checkbox" name="sources" value="${key}" ${s.sources.includes(key) ? 'checked' : ''}>${esc(src.name)}</label>`).join('');
    $('#topic-options').innerHTML = Object.entries(state.topics).map(([key, name]) => `<label><input type="checkbox" name="topics" value="${key}" ${s.topics.includes(key) ? 'checked' : ''}>${esc(name)}</label>`).join('');
    settingsDirty = false;
  }
}
function welcome() {
  return `<article class="message"><div class="message-head"><span class="bot-avatar">✳</span><strong>Орбита <span class="subtle">· ваш научный редактор</span></strong><time>Всегда рядом</time></div><div class="message-body"><h3>Давайте рассказывать о науке вместе 👋</h3><p>Я помогу превратить научные новости в материалы для вашего сообщества. Вот что можно поручить редакции:</p><div class="welcome-steps"><div class="welcome-step"><span>${icon('globe')}</span><span>Найти открытия за выбранный период</span></div><div class="welcome-step"><span>${icon('file')}</span><span>Подготовить текст с ссылками на источники</span></div><div class="welcome-step"><span>${icon('image')}</span><span>Собрать фотографии и обложку в один архив</span></div></div><p>Выберите даты и нажмите <strong>«Создать пост»</strong>. Готовые файлы появятся прямо здесь.</p><p class="chat-hint">${state.ai_enabled ? `ИИ-редактор ${esc(state.ai_model)} готов. Настройте голос сообщества в разделе «Настройки».` : 'Сейчас включён режим дайджеста. Проверьте доступность модели в настройках.'}</p></div></article>`;
}
function jobCard(job, inArchive = false) {
  const period = `${shortDate(job.date_from)} — ${dateLabel(job.date_to, true)}`;
  const time = new Intl.DateTimeFormat('ru-RU', {day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Moscow'}).format(new Date(job.created_at));
  let body = '';
  if (['queued', 'running'].includes(job.status)) body = `<span class="loading-dots">✳</span> <strong>${job.status === 'queued' ? 'Задание в очереди' : 'Готовлю вашу подборку'}</strong><p>Проверяю новости за ${esc(period)}. Файлы появятся автоматически; можно закрыть вкладку.</p>`;
  else if (job.status === 'empty' || job.status === 'error') body = `<h3>${job.status === 'empty' ? 'Пока без открытий' : 'Не удалось завершить подборку'}</h3><p>${esc(job.error || job.body)}</p><button class="text-button" data-retry="${job.id}">Попробовать снова ↗</button>`;
  else body = `<span class="job-tag">${job.kind === 'weekly' ? 'Еженедельная подборка' : 'По вашему запросу'} · ${esc(period)}</span><h3>Материалы для нового поста готовы</h3><p>${job.details.articles?.length || 0} новости · ${job.details.photo_count || 0} фото и обложка · ${job.details.mode === 'ai' ? `ИИ-редактура ${esc(job.details.ai_model || '')}` : 'Дайджест источников'}</p><img class="cover-preview" src="/api/jobs/${job.id}/cover.jpg" alt="Обложка подборки за ${esc(period)}" loading="lazy"><pre class="post-body">${esc(job.body)}</pre><div class="attachments"><a class="attachment" href="/api/jobs/${job.id}/post.txt" download><span>${icon('file')}</span><span><strong>Текст поста</strong><small>TXT · готов к редактированию</small></span><span class="download">↓</span></a><a class="attachment" href="/api/jobs/${job.id}/photos.zip" download><span>${icon('image')}</span><span><strong>Изображения</strong><small>ZIP · фото, обложка, источники</small></span><span class="download">↓</span></a></div><div class="post-actions"><button class="text-button" data-copy="${job.id}">Копировать текст ${icon('files')}</button></div>${(job.details.warnings || []).map(w => `<p class="warning">${esc(w)}</p>`).join('')}<p class="chat-hint">Перед публикацией проверьте факты и права на фотографии. Ссылки и сведения об авторах — внутри архива.</p>`;
  return `${!inArchive && job.kind === 'manual' ? `<div class="user-message">Подготовь пост о научных открытиях: ${esc(period)}.</div>` : ''}<article class="message"><div class="message-head"><span class="bot-avatar">✳</span><strong>Орбита</strong><time>${esc(time)} МСК</time></div><div class="message-body">${body}</div></article>`;
}
function renderJobs() {
  $('#jobs-count').textContent = jobs.filter(j => j.status === 'done').length;
  $('#chat').innerHTML = jobs.length ? [...jobs].reverse().map(j => jobCard(j)).join('') : welcome();
  $('#archive-list').innerHTML = jobs.length ? jobs.map(j => jobCard(j, true)).join('') : `<div class="empty-state"><span>✳</span><h2>Здесь будут ваши открытия</h2><p>Создайте первый пост — текст и изображения сохранятся здесь.</p><button class="button primary" data-page="dialog">К созданию поста ↗</button></div>`;
  const active = jobs.some(j => ['queued', 'running'].includes(j.status));
  $('#generate-button').disabled = active;
  $('#generate-button').innerHTML = active ? '<span class="loading-dots">✳</span>Готовим материалы…' : icon('sparkles') + 'Создать пост<span>↗</span>';
}
async function refreshJobs() {
  const next = await api('/jobs');
  const signature = JSON.stringify(next);
  if (signature !== jobsSignature) {
    const newlyDone = next.some(j => j.status === 'done' && jobs.some(old => old.id === j.id && old.status !== 'done'));
    jobs = next; jobsSignature = signature; renderJobs();
    if (newlyDone) toast('Подборка готова. Оба файла уже в диалоге.');
  }
}
async function poll() {
  if (!state || polling) return;
  polling = true;
  try {
    await refreshJobs();
    const latest = await api('/me');
    if (state) { state = latest; renderState(false); }
    $('#connection-warning')?.remove();
  } catch (err) {
    if (state && !$('#connection-warning')) {
      const warning = document.createElement('div'); warning.id = 'connection-warning'; warning.className = 'network-alert'; warning.setAttribute('role', 'alert'); warning.textContent = err.message + ' Повторяем подключение автоматически.'; $('#main-content').prepend(warning);
    }
  } finally {
    polling = false;
    if (state) pollTimer = setTimeout(poll, jobs.some(j => ['queued', 'running'].includes(j.status)) ? 3000 : 15000);
  }
}
async function loadApp() {
  state = await api('/me');
  $('#auth-screen').hidden = true; $('#app-screen').hidden = false;
  renderState(true); setPeriod(7); renderJobs(); setPage('dialog');
  await refreshJobs(); clearTimeout(pollTimer); pollTimer = setTimeout(poll, 3000);
}
$('#auth-form').addEventListener('submit', async event => {
  event.preventDefault(); const button = $('#auth-submit'); button.disabled = true; $('#auth-error').textContent = '';
  try { await api('/' + authMode, 'POST', Object.fromEntries(new FormData(event.target))); event.target.reset(); await loadApp(); }
  catch (err) { $('#auth-error').textContent = err.message; }
  finally { button.disabled = false; }
});
$('#logout').addEventListener('click', async () => {
  try { await api('/logout', 'POST'); showAuth(); changeAuth('login'); }
  catch (err) { toast(err.message, true); }
});
$('#generate-form').addEventListener('submit', async event => {
  event.preventDefault(); const button = $('#generate-button'); button.disabled = true; $('#generate-error').textContent = '';
  try {
    if ($('#date-from').value > $('#date-to').value) throw new Error('Дата начала должна быть раньше даты окончания.');
    await api('/generate', 'POST', {date_from: $('#date-from').value, date_to: $('#date-to').value});
    await refreshJobs(); toast('Редакция приступила к работе'); clearTimeout(pollTimer); pollTimer = setTimeout(poll, 1500);
    $('#chat').lastElementChild?.scrollIntoView({behavior: 'smooth', block: 'nearest'});
  } catch (err) { $('#generate-error').textContent = err.message; button.disabled = jobs.some(j => ['queued', 'running'].includes(j.status)); }
});
$('#settings-form').addEventListener('input', () => { settingsDirty = true; $('#settings-message').textContent = 'Есть несохранённые изменения'; });
$('#settings-form').addEventListener('submit', async event => {
  event.preventDefault(); const button = $('button[type=submit]', event.target); button.disabled = true;
  const f = new FormData(event.target);
  const settings = Object.fromEntries(f);
  for (const key of ['weekday', 'hour', 'article_count']) settings[key] = Number(settings[key]);
  settings.weekly_enabled = f.has('weekly_enabled'); settings.sources = f.getAll('sources'); settings.topics = f.getAll('topics');
  try {
    if (!settings.sources.length) throw new Error('Выберите хотя бы один источник');
    const result = await api('/settings', 'PUT', settings); state.settings = result.settings; state.next_run = result.next_run; renderState(true);
    $('#settings-message').textContent = 'Настройки сохранены'; toast('Всё сохранено');
  } catch (err) { $('#settings-message').textContent = err.message; toast(err.message, true); }
  finally { button.disabled = false; }
});
document.addEventListener('click', async event => {
  const nav = event.target.closest('[data-page]'); if (nav) setPage(nav.dataset.page);
  const auth = event.target.closest('[data-auth]'); if (auth) changeAuth(auth.dataset.auth);
  const period = event.target.closest('[data-period]');
  if (period) { $$('[data-period]').forEach(b => b.classList.toggle('selected', b === period)); if (period.dataset.period !== 'custom') setPeriod(Number(period.dataset.period)); else $('#date-from').focus(); }
  const copy = event.target.closest('[data-copy]');
  if (copy) { try { await navigator.clipboard.writeText(jobs.find(j => j.id === copy.dataset.copy).body); toast('Текст скопирован'); } catch { toast('Не удалось скопировать. Скачайте текстовый файл.', true); } }
  const retry = event.target.closest('[data-retry]');
  if (retry) { const job = jobs.find(j => j.id === retry.dataset.retry); setPage('dialog'); $('#date-from').value = job.date_from; $('#date-to').value = job.date_to; $$('[data-period]').forEach(b => b.classList.toggle('selected', b.dataset.period === 'custom')); $('#generate-form').requestSubmit(); }
});
for (const id of ['date-from', 'date-to']) $('#' + id).addEventListener('change', () => { $$('[data-period]').forEach(b => b.classList.toggle('selected', b.dataset.period === 'custom')); });
window.addEventListener('beforeunload', event => { if (settingsDirty) { event.preventDefault(); event.returnValue = ''; } });
$('#hour-options').innerHTML = Array.from({length: 24}, (_, i) => `<option value="${i}">${String(i).padStart(2, '0')}:00</option>`).join('');
icons();
loadApp().catch(err => { showAuth(); if (!err.message.includes('Войдите')) $('#auth-error').textContent = err.message; });

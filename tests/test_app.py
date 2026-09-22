"""Run: .venv/bin/python -m pytest -q. No network or API key required."""
import io
import json
import zipfile
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import app as sno


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(sno, 'DATA', tmp_path)
    monkeypatch.setenv('DISABLE_WORKER', '1')
    monkeypatch.setenv('AI_PROVIDER', 'none')
    monkeypatch.delenv('OLLAMA_MODEL', raising=False)
    monkeypatch.delenv('OLLAMA_BASE_URL', raising=False)
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    monkeypatch.delenv('OPENAI_MODEL', raising=False)
    monkeypatch.delenv('OPENAI_REASONING_EFFORT', raising=False)
    monkeypatch.delenv('ALLOWED_EMAILS', raising=False)
    with TestClient(sno.app) as client:
        yield client


def register(client, email='one@example.org'):
    response = client.post('/api/register', json={'name': 'Александр', 'email': email, 'password': 'test-pass-very-long'})
    assert response.status_code == 200, response.text
    return response.json()


def test_installable_pwa_assets(client):
    page = client.get('/')
    assert page.status_code == 200
    assert 'rel="manifest" href="/manifest.webmanifest"' in page.text
    assert 'apple-touch-icon' in page.text
    manifest = client.get('/manifest.webmanifest')
    assert manifest.status_code == 200
    assert manifest.headers['content-type'].startswith('application/manifest+json')
    data = manifest.json()
    assert data['start_url'] == '/' and data['display'] == 'standalone'
    assert {icon['sizes'] for icon in data['icons']} == {'192x192', '512x512'}
    worker = client.get('/service-worker.js')
    assert worker.status_code == 200 and "url.pathname.startsWith('/api/')" in worker.text
    assert worker.headers['cache-control'] == 'no-cache'
    assert client.get('/static/icon-192.png').headers['content-type'] == 'image/png'


def seed_article(date='2026-08-01T21:00:00+00:00', image='https://naked-science.ru/test.jpg'):
    item = ('https://naked-science.ru/article/test', 'naked', 'Физики исследовали квантовые частицы', 'Учёные измерили свойства частиц. Результат получен в лабораторном эксперименте.', date, image, 'physics', 'Research team')
    with sno.db() as con:
        con.execute('INSERT INTO articles VALUES (?,?,?,?,?,?,?,?)', item)
    return item


def finish_job(client, monkeypatch):
    seed_article()
    raw = io.BytesIO()
    Image.new('RGB', (120, 100), '#649175').save(raw, format='JPEG')
    monkeypatch.setattr(sno, 'fetch_public', lambda *a, **kw: raw.getvalue())
    monkeypatch.setattr(sno, 'collect', lambda: {'sources': {key: {'ok': True} for key in sno.SOURCES}})
    response = client.post('/api/generate', json={'date_from': '2026-08-02', 'date_to': '2026-08-02'})
    assert response.status_code == 202
    jid = response.json()['id']
    with sno.db() as con:
        job = dict(con.execute('SELECT * FROM jobs WHERE id=?', (jid,)).fetchone())
    sno.process_job(job)
    return jid


def test_registration_login_sessions_and_private_files(client, monkeypatch):
    assert client.get('/api/me').status_code == 401
    assert client.post('/api/register', json={'name': 'A', 'email': 'a@b.co', 'password': '123'}).status_code == 422
    user = register(client)
    assert 'password' not in user
    assert client.cookies.get('sno_session')
    assert client.get('/api/me').json()['user']['email'] == 'one@example.org'
    jid = finish_job(client, monkeypatch)
    job = client.get('/api/jobs').json()[0]
    assert job['status'] == 'done'
    txt = client.get(f'/api/jobs/{jid}/post.txt')
    assert txt.status_code == 200 and 'Источники:' in txt.content.decode('utf-8-sig')
    assert 'attachment' in txt.headers['content-disposition']
    archive = zipfile.ZipFile(io.BytesIO(client.get(f'/api/jobs/{jid}/photos.zip').content))
    assert set(archive.namelist()) == {'cover.jpg', 'photo-01.jpg', 'sources-and-credits.txt'}
    assert archive.testzip() is None
    assert 'Research team' in archive.read('sources-and-credits.txt').decode()
    client.post('/api/logout')
    assert client.get(f'/api/jobs/{jid}/post.txt').status_code == 401
    register(client, 'two@example.org')
    assert client.get('/api/jobs').json() == []
    assert client.get(f'/api/jobs/{jid}/post.txt').status_code == 404
    assert client.get(f'/api/jobs/{jid}/cover.jpg').status_code == 404
    client.post('/api/logout')
    assert client.post('/api/login', json={'email': 'one@example.org', 'password': 'incorrect-password'}).status_code == 401
    assert client.post('/api/login', json={'email': 'one@example.org', 'password': 'test-pass-very-long'}).status_code == 200
    assert client.get('/api/jobs').json()[0]['id'] == jid
    with sno.db() as con:
        stored = con.execute('SELECT password FROM users WHERE id=?', (user['id'],)).fetchone()[0]
        assert 'test-pass' not in stored
        session = con.execute('SELECT token FROM sessions').fetchone()[0]
        assert session != client.cookies.get('sno_session')


def test_validation_csrf_allowlist_and_duplicate_jobs(client, monkeypatch):
    assert client.post('/api/login', headers={'origin': 'https://evil.test'}, json={}).status_code == 403
    monkeypatch.setenv('ALLOWED_EMAILS', 'invited@example.org')
    assert client.post('/api/register', json={'name': 'A', 'email': 'other@example.org', 'password': 'safe-test-password'}).status_code == 403
    register(client, 'invited@example.org')
    assert client.post('/api/generate', json={'date_from': '2026-08-02', 'date_to': '2026-08-01'}).status_code == 422
    assert client.post('/api/generate', json={'date_from': '2999-01-01', 'date_to': '2999-01-02'}).status_code == 422
    settings = client.get('/api/me').json()['settings']
    assert client.put('/api/settings', json=settings | {'sources': []}).status_code == 422
    assert client.put('/api/settings', json=settings | {'community_url': 'http://127.0.0.1/private'}).status_code == 422
    assert client.put('/api/settings', json=settings | {'sources': ['evil']}).status_code == 422
    assert client.put('/api/settings', json=settings | {'weekly_enabled': False}).json()['next_run'] is None
    payload = {'date_from': '2026-08-01', 'date_to': '2026-08-02'}
    assert client.post('/api/generate', json=payload).status_code == 202
    assert client.post('/api/generate', json=payload).status_code == 409
    with pytest.raises(ValueError):
        sno.fetch_public('http://localhost:8000/api/me')
    with pytest.raises(ValueError):
        sno.fetch_public('https://naked-science.ru.attacker.com/x')


def test_moscow_date_boundary_schedule_and_restart(client):
    user = register(client)
    seed_article()
    settings = sno.DEFAULT_SETTINGS
    assert len(sno.select_articles({'date_from': '2026-08-02', 'date_to': '2026-08-02'}, settings)) == 1
    assert sno.select_articles({'date_from': '2026-08-01', 'date_to': '2026-08-01'}, settings) == []
    assert sno.select_articles({'date_from': '2026-08-02', 'date_to': '2026-08-02'}, settings | {'topics': ['space']} ) == []
    at = datetime(2026, 8, 3, 7, 0, tzinfo=timezone.utc)  # Monday 10:00 Moscow
    assert sno.next_run(settings, at) == '2026-08-10T07:00:00+00:00'
    assert sno.next_run(settings, at - timedelta(seconds=1)) == at.isoformat()
    with sno.db() as con:
        con.execute('UPDATE users SET next_run=? WHERE id=?', ((at - timedelta(days=14)).isoformat(), user['id']))
    sno.enqueue_scheduled(at)
    sno.enqueue_scheduled(at)
    with sno.db() as con:
        jobs = con.execute('SELECT * FROM jobs').fetchall()
        assert len(jobs) == 1
        assert jobs[0]['date_from'] == '2026-07-27' and jobs[0]['date_to'] == '2026-08-02'
        con.execute("UPDATE jobs SET status='running'")
    sno.initialize()
    assert client.get('/api/jobs').json()[0]['status'] == 'queued'


def test_empty_archive_and_failed_images_are_honest(client, monkeypatch):
    register(client)
    monkeypatch.setattr(sno, 'collect', lambda: {'sources': {key: {'ok': False} for key in sno.SOURCES}})
    jid = client.post('/api/generate', json={'date_from': '2026-08-01', 'date_to': '2026-08-02'}).json()['id']
    with sno.db() as con:
        job = dict(con.execute('SELECT * FROM jobs WHERE id=?', (jid,)).fetchone())
    sno.process_job(job)
    result = client.get('/api/jobs').json()[0]
    assert result['status'] == 'empty' and 'недоступны' in result['body']
    assert client.get(f'/api/jobs/{jid}/post.txt').status_code == 404
    seed_article(image='')
    sno.process_job(job)
    result = client.get('/api/jobs').json()[0]
    assert result['status'] == 'done' and result['details']['photo_count'] == 0
    assert any('не фотография' in w for w in result['details']['warnings'])


def test_feed_parser_dates_html_and_images():
    raw = '''<rss xmlns:media="http://search.yahoo.com/mrss/"><channel><item><title>Открытие &amp; наука</title><link>https://naked-science.ru/article/a</link><pubDate>Sun, 02 Aug 2026 01:00:00 +0300</pubDate><description><![CDATA[<p>Учёные изучили <b>клетки</b>.</p>]]></description><media:content type="image/jpeg" url="https://naked-science.ru/a.jpg"/></item><item><title>Без даты</title><link>https://naked-science.ru/no-date</link></item></channel></rss>'''
    parsed = sno.parse_feed(raw, 'naked')
    assert len(parsed) == 1
    assert parsed[0][2] == 'Открытие & наука'
    assert '<b>' not in parsed[0][3]
    assert parsed[0][4] == '2026-08-01T22:00:00+00:00'
    assert parsed[0][5] == 'https://naked-science.ru/a.jpg'


def test_ai_style_and_provider_failure(client, monkeypatch):
    register(client)
    seed_article(image='')
    with sno.db() as con:
        articles = [dict(con.execute('SELECT * FROM articles').fetchone())]
    settings = sno.DEFAULT_SETTINGS | {'examples': 'Наш фирменный пример', 'style_notes': 'Обращаться на вы'}
    job = {'date_from': '2026-08-01', 'date_to': '2026-08-02'}
    requests = []

    def fake_ollama(url, **kwargs):
        requests.append(kwargs['json'])
        return sno.httpx.Response(200, request=sno.httpx.Request('POST', url), json={'done': True, 'done_reason': 'stop', 'message': {'content': 'Проверенный русский пост. ' * 12}})

    monkeypatch.setenv('AI_PROVIDER', 'ollama')
    monkeypatch.setattr(sno.httpx, 'post', fake_ollama)
    text, mode, warning = sno.write_post(articles, settings, job)
    assert mode == 'ai' and not warning and 'Источники:' in text
    assert 'Наш фирменный пример' in requests[0]['messages'][1]['content']
    assert requests[0]['model'] == sno.DEFAULT_OLLAMA_MODEL
    assert requests[0]['think'] is False and requests[0]['stream'] is False
    assert requests[0]['options']['num_ctx'] == 8192

    def fake_openai(url, **kwargs):
        requests.append(kwargs['json'])
        return sno.httpx.Response(200, request=sno.httpx.Request('POST', url), json={'status': 'completed', 'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': 'Проверенный русский пост. ' * 12}]}]})

    monkeypatch.setenv('AI_PROVIDER', 'openai')
    monkeypatch.setenv('OPENAI_API_KEY', 'test-key-never-used-on-network')
    monkeypatch.setattr(sno.httpx, 'post', fake_openai)
    sno.write_post(articles, settings, job)
    assert requests[-1]['model'] == sno.DEFAULT_OPENAI_MODEL
    assert requests[-1]['reasoning'] == {'effort': 'low'}
    assert requests[-1]['max_output_tokens'] == 6000
    monkeypatch.setenv('OPENAI_MODEL', 'gpt-4.1-mini')
    sno.write_post(articles, settings, job)
    assert requests[-1]['model'] == 'gpt-4.1-mini' and 'reasoning' not in requests[-1]
    monkeypatch.setenv('OPENAI_REASONING_EFFORT', '')
    monkeypatch.setenv('OPENAI_MODEL', sno.DEFAULT_OPENAI_MODEL)
    sno.write_post(articles, settings, job)
    assert 'reasoning' not in requests[-1]

    def incomplete(url, **kwargs):
        return sno.httpx.Response(200, request=sno.httpx.Request('POST', url), json={'done': False, 'done_reason': 'length', 'message': {'content': 'Незаконченный текст. ' * 12}})

    monkeypatch.setenv('AI_PROVIDER', 'ollama')
    monkeypatch.setattr(sno.httpx, 'post', incomplete)
    text, mode, warning = sno.write_post(articles, settings, job)
    assert mode == 'digest' and warning and 'Незаконченный текст' not in text

    def fail(*args, **kwargs):
        raise sno.httpx.ConnectError('Provider unavailable')

    monkeypatch.setattr(sno.httpx, 'post', fail)
    text, mode, warning = sno.write_post(articles, settings, job)
    assert mode == 'digest' and 'недоступен' in warning
    assert articles[0]['title'] in text


def test_cover_headline_matches_first_available_photo(client, monkeypatch):
    register(client)
    seed_article(image='')
    with sno.db() as con:
        first = dict(con.execute('SELECT * FROM articles').fetchone())
    second = first | {'title': 'Вторая новость с фотографией', 'image': 'https://naked-science.ru/photo.jpg'}
    raw = io.BytesIO()
    Image.new('RGB', (100, 100), 'green').save(raw, format='JPEG')
    monkeypatch.setattr(sno, 'fetch_public', lambda *a, **kw: raw.getvalue())
    headings = []
    original = sno.draw_wrapped

    def capture(draw, text, *args, **kwargs):
        headings.append(text)
        return original(draw, text, *args, **kwargs)

    monkeypatch.setattr(sno, 'draw_wrapped', capture)
    count, warnings = sno.make_files('cover-test', [first, second], sno.DEFAULT_SETTINGS, {'date_from': '2026-08-01', 'date_to': '2026-08-02'}, 'Тест')
    assert count == 1 and headings == [second['title']]
    assert sno.excerpt('Полное предложение. ' * 100).endswith('.')

"""Opt-in real RSS/browser smoke test; own temporary database, no real accounts."""
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
QA = ROOT / 'data' / 'qa'
QA.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(prefix='sno-browser-') as data:
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    url = f'http://127.0.0.1:{port}'
    env = os.environ | {'DATA_DIR': data, 'OPENAI_API_KEY': '', 'ALLOWED_EMAILS': '', 'COOKIE_SECURE': 'false', 'DISABLE_WORKER': '0'}
    with (QA / 'server.log').open('w') as log:
        proc = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'app:app', '--host', '127.0.0.1', '--port', str(port)], cwd=ROOT, env=env, stdout=log, stderr=log)
        try:
            for _ in range(100):
                try:
                    urllib.request.urlopen(url, timeout=1)
                    break
                except OSError:
                    time.sleep(.2)
            with sync_playwright() as p:
                browser = p.chromium.launch()
                context = browser.new_context(viewport={'width': 1440, 'height': 1100}, device_scale_factor=1, locale='ru-RU')
                page = context.new_page()
                errors = []
                page.on('pageerror', lambda err: errors.append(str(err)))
                page.goto(url)
                page.locator('#auth-screen').wait_for(state='visible')
                page.screenshot(path=QA / '01-login-desktop.png', full_page=True)
                page.get_by_role('button', name='Регистрация', exact=True).click()
                page.get_by_label('Как вас зовут').fill('Тестовый редактор')
                page.get_by_label('Электронная почта').fill('qa@example.org')
                page.get_by_label('Пароль', exact=True).fill('browser-test-password-942')
                page.get_by_role('button', name='Создать аккаунт').click()
                page.locator('#app-screen').wait_for(state='visible')
                page.get_by_text('Давайте рассказывать о науке вместе').wait_for()
                page.screenshot(path=QA / '02-dialog-desktop.png', full_page=True)
                print('Registration and desktop dashboard OK', flush=True)
                page.locator('nav').get_by_role('button', name='Настройки', exact=True).click()
                page.get_by_label('Название общества', exact=True).fill('Научное общество университета')
                page.get_by_label('Ссылка на сообщество ВК').fill('https://vk.com/science_example')
                page.locator('textarea[name=examples]').fill('Наука начинается с вопроса. Обсудим новое исследование вместе!')
                page.get_by_label('Включить еженедельную подборку').uncheck()
                page.get_by_role('button', name='Сохранить настройки').click()
                page.locator('#settings-message').get_by_text('Настройки сохранены').wait_for()
                page.reload()
                page.locator('#app-screen').wait_for(state='visible')
                page.get_by_text('Расписание на паузе.').wait_for()
                page.locator('nav').get_by_role('button', name='Настройки', exact=True).click()
                assert page.get_by_label('Название общества', exact=True).input_value() == 'Научное общество университета'
                assert not page.get_by_label('Включить еженедельную подборку').is_checked()
                page.screenshot(path=QA / '03-settings-desktop.png', full_page=True)
                page.locator('nav').get_by_role('button', name='Диалог с редакцией').click()
                page.get_by_role('button', name='Создать пост', exact=False).click()
                page.get_by_role('heading', name='Материалы для нового поста готовы').wait_for(timeout=180000)
                print('Live generation completed', flush=True)
                page.screenshot(path=QA / '04-generated-desktop.png', full_page=True)
                with page.expect_download() as download:
                    page.get_by_role('link', name='Текст поста').click()
                download.value.save_as(QA / 'post.txt')
                assert 'Источники:' in (QA / 'post.txt').read_text(encoding='utf-8-sig')
                with page.expect_download() as download:
                    page.get_by_role('link', name='Изображения').click()
                download.value.save_as(QA / 'photos.zip')
                with zipfile.ZipFile(QA / 'photos.zip') as archive:
                    assert archive.testzip() is None
                    assert any(n.startswith('photo-') for n in archive.namelist()), archive.namelist()
                    (QA / 'cover.jpg').write_bytes(archive.read('cover.jpg'))
                    print('ZIP validated:', archive.namelist(), flush=True)
                page.locator('nav').get_by_role('button', name='Источники новостей').click()
                page.get_by_role('heading', name='Naked Science').wait_for()
                page.screenshot(path=QA / '05-sources-desktop.png', full_page=True)
                page.locator('nav').get_by_role('button', name='Мои материалы').click()
                page.get_by_role('heading', name='Материалы для нового поста готовы').wait_for()
                page.set_viewport_size({'width': 390, 'height': 844})
                page.locator('nav').get_by_role('button', name='Диалог с редакцией').click()
                page.screenshot(path=QA / '06-dialog-mobile.png', full_page=True)
                assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'Mobile horizontal overflow'
                page.locator('nav').get_by_role('button', name='Настройки', exact=True).click()
                assert page.locator('.nav-item.active').get_attribute('data-page') == 'settings'
                page.screenshot(path=QA / '07-settings-mobile.png', full_page=True)
                assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'Settings mobile overflow'
                page.get_by_role('button', name='Выйти', exact=True).click()
                page.locator('#auth-screen').wait_for(state='visible')
                page.screenshot(path=QA / '08-login-mobile.png', full_page=True)
                page.get_by_label('Электронная почта').fill('qa@example.org')
                page.get_by_label('Пароль', exact=True).fill('browser-test-password-942')
                page.get_by_role('button', name='Войти в редакцию').click()
                page.get_by_role('heading', name='Материалы для нового поста готовы').wait_for()
                assert not errors, errors
                print('Login, history persistence, mobile layouts and JavaScript errors OK', flush=True)
                browser.close()
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()

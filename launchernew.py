import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk
import os
import threading
import requests
import shutil
import pyzipper
import gdown
import re
import urllib.request
import winshell
from win32com.client import Dispatch
from dotenv import load_dotenv
import subprocess
import sys
import io
import json
import ctypes
import time
from pypresence import Presence
import pythoncom

USER_FILE = "user.json"

FIREBASE_URL = "https://corsar-launcher-default-rtdb.firebaseio.com/"

PLAYED_TIME_FILE = "played_time.json"
played_time = {}

discord_app_id = "1388812335719911567"  # ← Вставь свой Discord Application ID
rpc = None

visible_games = []

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

if not is_admin():
    script = os.path.abspath(sys.argv[0])
    params = " ".join([f'"{arg}"' for arg in sys.argv[1:]])
    ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, f'"{script}" {params}', None, 1)
    os._exit(0)

SETTINGS_FILE = "settings.json"
user_settings = {
    "theme": "dark",
    "age_confirmed": False
}

GAMES_DIR = r"C:\Program Files (x86)\CorsarLauncher\Games"
os.makedirs(GAMES_DIR, exist_ok=True)

load_dotenv()
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
LAUNCHER_VERSION = "1.5.2"
GAMES_FILE = "games.json"

current_user = {"name": None}
downloading_game = {"name": None}
age_confirmed = {}
user_versions = {}
theme_mode = {"value": "dark"}
image_cache = {}
active_downloads = 0
download_button_state = {"enabled": True}
current_game = {}
global_age_override = {"value": False}

def show_game_report_window():
    if not current_user.get("name"):
        messagebox.showwarning("Ошибка", "Сначала войдите в аккаунт.")
        return

    win = tk.Toplevel()
    win.title("Пожаловаться на игру")
    win.geometry("400x300")

    tk.Label(win, text="Опишите проблему с этой игрой:", font=("Arial", 12)).pack(pady=10)

    text = tk.Text(win, wrap="word", height=10)
    text.pack(padx=10, pady=5, fill="both", expand=True)

    def send_game_report():
        message = text.get("1.0", tk.END).strip()
        if not message:
            messagebox.showwarning("Пусто", "Введите текст жалобы.")
            return
        content = f"🚨 Жалоба на игру: `{current_game['name']}` от `{current_user['name']}`\n```{message}```"
        if send_discord_feedback(content):
            messagebox.showinfo("Спасибо!", "Жалоба отправлена.")
            win.destroy()
        else:
            messagebox.showerror("Ошибка", "Не удалось отправить жалобу.")

    ttk.Button(win, text="Отправить", command=send_game_report).pack(pady=10)

def show_comments_window():
    if not current_user.get("name"):
        messagebox.showwarning("Ошибка", "Сначала войдите в аккаунт.")
        return

    game_name = current_game["name"]
    win = tk.Toplevel()
    win.title(f"Комментарии — {game_name}")
    win.geometry("500x400")

    comments_box = tk.Text(win, state="disabled", wrap="word")
    comments_box.pack(fill="both", expand=True, padx=10, pady=10)

    entry = tk.Entry(win)
    entry.pack(fill="x", padx=10)

    def refresh_comments():
        comments = get_comments(game_name)
        comments_box.config(state="normal")
        comments_box.delete("1.0", tk.END)
        for ts in sorted(comments, key=int):
            c = comments[ts]
            comments_box.insert(tk.END, f"{c['from']}: {c['text']}\n")
        comments_box.config(state="disabled")

    def send_comment():
        text = entry.get().strip()
        if text:
            post_comment(game_name, current_user["name"], text)
            entry.delete(0, tk.END)
            refresh_comments()

    ttk.Button(win, text="Отправить", command=send_comment).pack(pady=5)
    refresh_comments()

def get_comments(game_name):
    url = f"{FIREBASE_URL}/comments/{game_name}.json"
    response = requests.get(url)
    data = response.json()
    return data or {}

def post_comment(game_name, user_name, comment_text):
    if not comment_text.strip():
        return
    timestamp = str(int(time.time() * 1000))
    url = f"{FIREBASE_URL}/comments/{game_name}/{timestamp}.json"
    payload = {
        "from": user_name,
        "text": comment_text
    }
    requests.put(url, json=payload)

def add_friend(sender, recipient):
    # Проверим, что пользователь не отправляет заявку самому себе
    if sender == recipient:
        return False, "Нельзя добавить самого себя."

    # Проверим, существует ли получатель
    url_check = f"{FIREBASE_URL}/users/{recipient}.json"
    response = requests.get(url_check)
    if response.status_code != 200 or response.json() is None:
        return False, "Пользователь не найден."

    # Отправим заявку в друзья
    url_request = f"{FIREBASE_URL}/users/{recipient}/friend_requests/{sender}.json"
    requests.put(url_request, json=True)
    return True, f"Заявка отправлена {recipient}"

def chat_id(user1, user2):
    return "_".join(sorted([user1, user2]))  # Пример: 'Alice_Bob'

def get_messages(user1, user2):
    url = f"{FIREBASE_URL}/messages/{chat_id(user1, user2)}.json"
    response = requests.get(url)
    data = response.json()
    return data or {}

def send_message(sender, recipient, message):
    if not message.strip():
        print("Пустое сообщение. Не отправлено.")
        return

    timestamp = str(int(time.time() * 1000))  # Миллисекунды — ключ

    chat_path = f"{FIREBASE_URL}/messages/{chat_id(sender, recipient)}/{timestamp}.json"
    payload = {
        "from": sender,
        "message": message
    }

    response = requests.put(chat_path, json=payload)
    if response.status_code == 200:
        print(f"Сообщение от {sender} к {recipient} отправлено.")
    else:
        print(f"Ошибка при отправке сообщения: {response.text}")

def show_account_window():
    win = tk.Toplevel()
    win.title("Аккаунт")
    win.geometry("300x300")

    tk.Label(win, text="Имя пользователя:").pack()
    entry_user = tk.Entry(win)
    entry_user.pack()

    tk.Label(win, text="Пароль:").pack()
    entry_pass = tk.Entry(win, show="*")
    entry_pass.pack()

    status = tk.Label(win, text="", fg="red")
    status.pack()

    def login():
        username = entry_user.get().strip()
        password = entry_pass.get().strip()

        if not username or not password:
            status.config(text="Введите имя и пароль", fg="red")
            return

        ok, msg = login_user(username, password)
        status.config(text=msg, fg="green" if ok else "red")

        if ok:
            current_user["name"] = username
            try:
                with open("user.json", "w", encoding="utf-8") as f:
                    json.dump({"name": username, "password": password}, f)
            except Exception as e:
                print(f"Ошибка сохранения user.json: {e}")
            win.destroy()

    def register():
        username = entry_user.get().strip()
        password = entry_pass.get().strip()

        if not username or not password:
            status.config(text="Введите имя и пароль", fg="red")
            return

        ok, msg = register_user(username, password)
        status.config(text=msg, fg="green" if ok else "red")

    def logout():
        current_user["name"] = None
        if os.path.exists("user.json"):
            os.remove("user.json")
        status.config(text="Вы вышли из аккаунта.", fg="orange")

    # ❗️ ЭТИ КНОПКИ ДОЛЖНЫ БЫТЬ ВНЕ ВНУТРЕННИХ ФУНКЦИЙ
    ttk.Button(win, text="Войти", command=login).pack(pady=5)
    ttk.Button(win, text="Регистрация", command=register).pack(pady=5)
    ttk.Button(win, text="Выйти", command=logout).pack(pady=5)

def get_friend_requests(current_user):
    url = f"{FIREBASE_URL}/users/{current_user}/friend_requests.json"
    response = requests.get(url)
    return response.json() or {}

def show_friends_window():
    if not current_user.get("name"):
        messagebox.showwarning("Ошибка", "Сначала войдите в аккаунт.")
        return

    win = tk.Toplevel()
    win.title("Друзья и чат")
    win.geometry("500x600")

    # ===== Добавить друга =====
    tk.Label(win, text="Добавить друга:").pack(pady=(10, 0))
    entry_friend = tk.Entry(win)
    entry_friend.pack(pady=5)

    def add():
        friend_name = entry_friend.get().strip()
        if not friend_name:
            messagebox.showwarning("Ошибка", "Введите имя друга.")
            return
        ok, msg = add_friend(current_user["name"], friend_name)
        messagebox.showinfo("Результат", msg)
        update_requests()
        update_friends()

    ttk.Button(win, text="Добавить", command=add).pack(pady=(0, 10))

    # ===== Входящие заявки =====
    tk.Label(win, text="Заявки в друзья:").pack()
    request_listbox = tk.Listbox(win, height=5)
    request_listbox.pack(fill="x", pady=5)

    def accept_selected_request():
        if not request_listbox.curselection():
            messagebox.showwarning("Ошибка", "Выберите заявку.")
            return
        selected = request_listbox.get(request_listbox.curselection()[0])
        accept_friend(current_user["name"], selected)
        messagebox.showinfo("Готово", f"{selected} теперь ваш друг!")
        update_requests()
        update_friends()
        update_chat(selected)

    ttk.Button(win, text="Принять заявку", command=accept_selected_request).pack(pady=(0, 10))

    # ===== Список друзей =====
    tk.Label(win, text="Мои друзья:").pack()
    friend_listbox = tk.Listbox(win)
    friend_listbox.pack(fill="both", expand=True, pady=5)

    # ===== Чат =====
    chat_log = tk.Text(win, height=10, state="disabled")
    chat_log.pack(fill="both", padx=5, pady=5)

    chat_entry = tk.Entry(win)
    chat_entry.pack(fill="x", padx=5, pady=(0, 10))

    def update_requests():
        request_listbox.delete(0, tk.END)
        requests_data = get_friend_requests(current_user["name"])
        for name in requests_data:
            request_listbox.insert(tk.END, name)

    def update_friends():
        friend_listbox.delete(0, tk.END)
        friends = get_friends(current_user["name"])
        for name in friends:
            friend_listbox.insert(tk.END, name)

    def get_friends(username):
        url = f"{FIREBASE_URL}/users/{username}/friends.json"
        response = requests.get(url)
        data = response.json()
        if isinstance(data, dict):
            return list(data.keys())
        elif isinstance(data, list):
            return data
        return []

    def get_friend_requests(username):
        url = f"{FIREBASE_URL}/users/{username}/friend_requests.json"
        response = requests.get(url)
        data = response.json()
        if isinstance(data, dict):
            return list(data.keys())
        elif isinstance(data, list):
            return data
        return []

    def accept_friend(current_user_name, friend_username):
        # Добавить друг друга
        requests.put(f"{FIREBASE_URL}/users/{current_user_name}/friends/{friend_username}.json", json=True)
        requests.put(f"{FIREBASE_URL}/users/{friend_username}/friends/{current_user_name}.json", json=True)
        # Удалить заявку
        requests.delete(f"{FIREBASE_URL}/users/{current_user_name}/friend_requests/{friend_username}.json")

    def send():
        msg = chat_entry.get().strip()
        if not msg:
            return
        if not friend_listbox.curselection():
            messagebox.showwarning("Ошибка", "Выберите друга для отправки сообщения.")
            return
        selected = friend_listbox.get(friend_listbox.curselection()[0])
        send_message(current_user["name"], selected, msg)
        chat_entry.delete(0, tk.END)
        update_chat(selected)

    def update_chat(friend=None):
        if friend is None:
            if not friend_listbox.curselection():
                return
            friend = friend_listbox.get(friend_listbox.curselection()[0])
        messages = get_messages(current_user["name"], friend)
        chat_log.configure(state="normal")
        chat_log.delete("1.0", tk.END)
        for ts in sorted(messages, key=int):
            m = messages[ts]
            chat_log.insert(tk.END, f"{m['from']}: {m['message']}\n")
        chat_log.configure(state="disabled")

    def on_friend_select(event):
        if not friend_listbox.curselection():
            return
        selected = friend_listbox.get(friend_listbox.curselection()[0])
        update_chat(selected)

    friend_listbox.bind("<<ListboxSelect>>", on_friend_select)

    ttk.Button(win, text="Отправить", command=send).pack(pady=5)

    # Периодическое обновление чата
    def periodic_chat_update():
        if friend_listbox.curselection():
            selected = friend_listbox.get(friend_listbox.curselection()[0])
            update_chat(selected)
        win.after(3000, periodic_chat_update)  # каждые 3 секунды

    # Начальное обновление списков
    update_requests()
    update_friends()
    periodic_chat_update()  # запустить обновление

def register_user(username, password):
    url = f"{FIREBASE_URL}/users/{username}.json"
    response = requests.get(url)
    if response.json():
        return False, "Пользователь уже существует"
    data = {"password": password, "friends": {}, "messages": {}}
    requests.put(url, json=data)
    return True, "Регистрация успешна"

def login_user(username, password):
    url = f"{FIREBASE_URL}/users/{username}.json"
    response = requests.get(url)
    data = response.json()
    if not data:
        return False, "Пользователь не найден"
    if data.get("password") != password:
        return False, "Неверный пароль"
    return True, "Успешный вход"

def show_feedback_form():
    win = tk.Toplevel()
    win.title("Обратная связь")
    win.geometry("400x300")
    
    tk.Label(win, text="Опишите вашу проблему или пожелание:", font=("Arial", 12)).pack(pady=10)
    
    text = tk.Text(win, wrap="word", height=10)
    text.pack(padx=10, pady=5, fill="both", expand=True)
    
    def send_feedback():
        message = text.get("1.0", tk.END).strip()
        if not message:
            messagebox.showwarning("Пусто", "Пожалуйста, введите сообщение.")
            return
        if send_discord_feedback(message):
            messagebox.showinfo("Спасибо!", "Ваше сообщение отправлено!")
            win.destroy()
        else:
            messagebox.showerror("Ошибка", "Не удалось отправить сообщение.")
    
    ttk.Button(win, text="Отправить", command=send_feedback).pack(pady=10)

def send_discord_feedback(message):
    webhook_url = "https://discord.com/api/webhooks/1388900373053444176/idHqfWKskBWULKZWCJILOF7JZf-933t-eRfcb2uz2NHHIeeoq0VUkPuD5hOQWPJgLbxF"
    data = {
        "content": f"📢 Новый отзыв от пользователя:\n```{message}```"
    }
    try:
        response = requests.post(webhook_url, json=data)
        if response.status_code == 204:
            return True
        else:
            print("Ошибка Discord:", response.text)
            return False
    except Exception as e:
        print("Ошибка отправки:", e)
        return False

def search_games(*args):
    query = search_var.get().lower()
    game_listbox.delete(0, tk.END)
    visible_games.clear()
    for game in games:
        if query in game["name"].lower():
            game_listbox.insert(tk.END, game["name"])
            visible_games.append(game)

def update_games_json():
    url = "https://github.com/Robon99/Gamelaunchertest1/releases/download/Games/games.json"  # замени ссылку на свою
    local_file = GAMES_FILE

    try:
        response = requests.get(url)
        if response.status_code == 200:
            with open(local_file, "w", encoding="utf-8") as f:
                f.write(response.text)
            print("games.json успешно обновлён.")
        else:
            print("Не удалось загрузить games.json:", response.status_code)
    except Exception as e:
        print("Ошибка при обновлении games.json:", e)

def format_time(seconds):
    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    parts = []
    if days > 0:
        parts.append(f"{days}д")
    if hours > 0 or days > 0:  # показываем часы, если есть дни или часы
        parts.append(f"{hours}ч")
    parts.append(f"{minutes}м")
    parts.append(f"{secs}с")
    return " ".join(parts)

def load_played_time():
    global played_time
    if os.path.exists("played_time.json"):
        with open("played_time.json", "r", encoding="utf-8") as f:
            played_time = json.load(f)

def save_played_time():
    with open(PLAYED_TIME_FILE, "w", encoding="utf-8") as f:
        json.dump(played_time, f)

def load_played_time():
    global played_time
    if os.path.exists(PLAYED_TIME_FILE):
        with open(PLAYED_TIME_FILE, "r", encoding="utf-8") as f:
            played_time = json.load(f)

def add_hover_effect(widget):
    def on_enter(e):
        widget.configure(style="Hover.TButton")
    def on_leave(e):
        widget.configure(style="TButton")
    widget.bind("<Enter>", on_enter)
    widget.bind("<Leave>", on_leave)

def update_game_panel(game):
    global current_game
    current_game = game

    clear_game_panel()

    if game.get("adult_only"):
        if not global_age_override["value"]:
            if not messagebox.askyesno("Возраст", "Вам есть 18 лет?"):
                return

    game_title.config(text=game["name"])
    game_description.config(text=game["description"])

    played_sec = played_time.get(game["name"], 0)
    time_text = f"Время игры: {format_time(played_sec)}"
    played_time_label.config(text=time_text)
    played_time_label.pack(pady=5)

    photo = image_cache.get(game["name"])
    if photo:
        game_image_label.configure(image=photo)
        game_image_label.image = photo
    else:
        game_image_label.config(image="", text="[Нет изображения]")

    if is_game_installed(game):
        play_button.pack(pady=10)
        delete_button.pack(pady=10)
        download_button.pack_forget()
        progress_label.config(text="Игра уже установлена ✅")
    else:
        play_button.pack_forget()
        delete_button.pack_forget()
        current_version = user_versions.get(game['name'])
        if current_version == game['version']:
            download_button.pack_forget()
            progress_label.config(text="Игра уже установлена ✅")
        else:
            download_button.pack(pady=10)
            download_button_state["enabled"] = True
            download_button.state(["!disabled"])
            progress_label.config(text="")

    if downloading_game["name"] == game["name"]:
        progress.pack(pady=5)

        installed_ver = user_versions.get(game["name"])
        if installed_ver == game["version"]:
            version_text = f"Версия: {installed_ver} ✅"
        else:
            version_text = f"Установлена: {installed_ver or '—'}, доступна: {game['version']}"
        progress_label.config(text="Загрузка...\n" + version_text)
    else:
        progress.pack_forget()
        installed_ver = user_versions.get(game["name"])
        if installed_ver == game["version"]:
            version_text = f"Версия: {installed_ver} ✅"
        else:
            version_text = f"Установлена: {installed_ver or '—'}, доступна: {game['version']}"
        progress_label.config(text=version_text)

def delete_game(game):
    game_folder = os.path.join(GAMES_DIR, game['name'].replace(" ", "_"))
    zip_path = os.path.join(GAMES_DIR, game['name'].replace(" ", "_") + ".zip")
    if os.path.exists(game_folder) or os.path.exists(zip_path):
        if messagebox.askyesno("Удаление", f"Удалить игру '{game['name']}'?"):
            try:
                if os.path.exists(game_folder):
                    shutil.rmtree(game_folder)
                if os.path.exists(zip_path):
                    os.remove(zip_path)
                messagebox.showinfo("Удалено", f"Игра '{game['name']}' удалена.")
                play_button.pack_forget()
                delete_button.pack_forget()
                progress_label.config(text="Игра удалена ❌")
                update_game_panel(game)
            except Exception as e:
                messagebox.showerror("Ошибка", f"Не удалось удалить игру:\n{e}")
    else:
        messagebox.showwarning("Внимание", "Файлы игры не найдены.")

def launch_game(game):
    game_folder = os.path.join(GAMES_DIR, game['name'].replace(" ", "_"))
    for root_dir, _, files in os.walk(game_folder):
        for file in files:
            if file.lower().endswith(".exe"):
                exe_path = os.path.join(root_dir, file)
                try:
                    # Discord Rich Presence
                    try:
                        global rpc
                        rpc = Presence(discord_app_id)
                        rpc.connect()
                        rpc.update(
                            state="Играет :)",
                            details=game["name"],
                            large_image="icon",  # замените на картинку из Discord Developer
                            start=time.time()
                        )
                    except Exception as e:
                        print(f"Discord RPC error: {e}")

                    start_time = time.time()
                    process = subprocess.Popen(exe_path, cwd=root_dir)

                    def track_play():
                        process.wait()
                        end_time = time.time()
                        duration = int(end_time - start_time)
                        name = game["name"]
                        played_time[name] = played_time.get(name, 0) + duration
                        save_played_time()
                        try:
                            if rpc:
                                rpc.clear()
                        except:
                            pass

                    threading.Thread(target=track_play, daemon=True).start()
                    return
                except Exception as e:
                    messagebox.showerror("Ошибка", f"Не удалось запустить игру:\n{e}")
    messagebox.showwarning("Внимание", f"Файл .exe не найден в: {game_folder}")

def apply_theme():
    theme_mode["value"] = user_settings.get("theme", "dark")
    if theme_mode["value"] == "dark":
        bg, fg, accent, list_bg = "#1c1c1c", "white", "#ff8800", "#2a2a2a"
    else:
        bg, fg, accent, list_bg = "white", "black", "#0066cc", "#e0e0e0"
    root.configure(bg=bg)
    left_panel.configure(bg=bg)
    main_panel.configure(bg=bg)
    left_buttons_frame.configure(bg=bg)
    game_title.config(bg=bg, fg=accent)
    game_description.config(bg=bg, fg=fg)
    game_image_label.config(bg=bg)
    progress_label.config(bg=bg, fg=fg)
    download_status_label.config(bg=bg, fg=accent)
    game_listbox.config(bg=list_bg, fg=accent)
    style.configure("TButton", font=("Arial", 12), padding=6)
    style.map("TButton", background=[("active", accent)])

def get_direct_gdrive_link(url):
    match = re.search(r'/d/([a-zA-Z0-9_-]+)', url)
    if match:
        return f'https://drive.google.com/uc?export=download&id={match.group(1)}'
    # Если уже id?export=download=id — возвращаем как есть
    if 'uc?export=download&id=' in url:
        return url
    return url

def download_and_replace_launcher(url):
    try:
        update_progress("Скачивание обновления...", 0)
        response = requests.get(url)
        new_code = response.text

        current_script = sys.argv[0]

        with open(current_script, "w", encoding="utf-8") as f:
            f.write(new_code)

        messagebox.showinfo("Обновление", "Лаунчер обновлён. Он будет перезапущен.")
        subprocess.Popen([sys.executable, current_script])
        root.destroy()
    except Exception as e:
        messagebox.showerror("Ошибка", f"Ошибка при обновлении: {e}")

def check_launcher_update():
    try:
        # 👇 Сюда вставляешь ссылку на JSON-файл
        url = "https://raw.githubusercontent.com/Robon99/Gamelaunchertest1/main/update_launcher.json"
        response = requests.get(url)
        update_data = response.json()

        if update_data["version"] != LAUNCHER_VERSION:
            if messagebox.askyesno("Обновление", "Доступна новая версия лаунчера. Обновить?"):
                download_and_replace_launcher(update_data["download_url"])
    except Exception as e:
        print("Ошибка при проверке ахуений:", e)

def load_games():
    if os.path.exists(GAMES_FILE):
        with open(GAMES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_games():
    with open(GAMES_FILE, "w", encoding="utf-8") as f:
        json.dump(games, f, indent=2, ensure_ascii=False)

def save_settings():
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(user_settings, f, indent=2)

def load_settings():
    global user_settings
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            user_settings = json.load(f)

games = load_games()

root = tk.Tk()
root.title("Corsar Launcher")
root.geometry("900x550")
root.configure(bg="#1c1c1c")
threading.Thread(target=check_launcher_update, daemon=True).start()

style = ttk.Style()
style.configure("Hover.TButton", font=("Arial", 13, "bold"), padding=8)
style.configure("TButton", font=("Arial", 12), padding=6)
style.map("TButton", background=[("active", "#ff8800")])

left_panel = tk.Frame(root, bg="#1c1c1c", width=200)
left_panel.pack(side="left", fill="y")

search_var = tk.StringVar()

search_entry = tk.Entry(left_panel, textvariable=search_var, font=("Arial", 12))
search_entry.pack(padx=10, pady=5, fill="x")

search_var.trace_add("write", lambda *args: search_games())

game_listbox = tk.Listbox(left_panel, bg="#2a2a2a", fg="#ff8800", font=("Arial", 12))
game_listbox.pack(fill="both", expand=True, padx=10, pady=10)

left_buttons_frame = tk.Frame(left_panel, bg="#1c1c1c")
left_buttons_frame.pack(fill="x")

btn_account = ttk.Button(left_buttons_frame, text="👤 Аккаунт", command=show_account_window)
btn_account.pack(side="left", padx=5, pady=5)
add_hover_effect(btn_account)

btn_friends = ttk.Button(left_buttons_frame, text="👥 Друзья", command=show_friends_window)
btn_friends.pack(side="left", padx=5, pady=5)
add_hover_effect(btn_friends)

main_panel = tk.Frame(root, bg="#1c1c1c")
main_panel.pack(side="right", fill="both", expand=True)

game_title = tk.Label(main_panel, text="", font=("Arial", 20, "bold"), bg="#1c1c1c", fg="#ff8800")
game_title.pack(pady=10)

game_image_label = tk.Label(main_panel, bg="#1c1c1c")
game_image_label.pack()

game_description = tk.Label(main_panel, text="", wraplength=500, justify="left", font=("Arial", 13), bg="#1c1c1c", fg="white")
game_description.pack(pady=10)

played_time_label = tk.Label(main_panel, text="", font=("Arial", 12), bg="#1c1c1c", fg="white")
played_time_label.pack(pady=5)

download_button = ttk.Button(main_panel, text="Скачать игру")
download_button.pack(pady=10)
add_hover_effect(download_button)

play_button = ttk.Button(main_panel, text="Играть")
play_button.pack(pady=10)
add_hover_effect(play_button)
play_button.pack_forget()

play_button.config(command=lambda: launch_game(current_game))

delete_button = ttk.Button(main_panel, text="Удалить")
delete_button.pack(pady=10)
add_hover_effect(delete_button)
delete_button.pack_forget()

delete_button.config(command=lambda: delete_game(current_game))

btn_feedback = ttk.Button(left_buttons_frame, text="📢 Жалоба", command=lambda: show_feedback_form())
btn_feedback.pack(side="left", padx=5, pady=5)
add_hover_effect(btn_feedback)

progress = ttk.Progressbar(main_panel, orient="horizontal", length=400, mode="determinate")
progress.pack(pady=5)

progress_label = tk.Label(main_panel, text="", font=("Arial", 10), bg="#1c1c1c", fg="white")
progress_label.pack()

download_status_label = tk.Label(root, text="", font=("Arial", 10), bg="#1c1c1c", fg="#ff8800")
download_status_label.place(relx=1.0, rely=1.0, anchor="se", x=-10, y=-10)

def update_progress(msg, value=None):
    progress_label.config(text=msg)
    if value is not None:
        progress["value"] = value
    root.update_idletasks()

def update_download_status():
    if active_downloads > 0:
        download_status_label.config(text=f"Загрузка... ({active_downloads} активных)")
    else:
        download_status_label.config(text="")
    root.after(500, update_download_status)

def extract_and_create_shortcut(zip_path, game_name):
    extract_path = os.path.join(GAMES_DIR, game_name.replace(" ", "_"))
    os.makedirs(extract_path, exist_ok=True)
    exe_path = None

    try:
        with pyzipper.AESZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_path)
    except:
        import zipfile
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_path)

    for root_dir, _, files in os.walk(extract_path):
        for file in files:
            if file.lower().endswith(".exe"):
                exe_path = os.path.join(root_dir, file)
                break

    if exe_path:
        try:
            pythoncom.CoInitialize()  # ← важно!
            shortcut_path = os.path.join(winshell.desktop(), f"{game_name}.lnk")
            shell = Dispatch('WScript.Shell')
            shortcut = shell.CreateShortCut(shortcut_path)
            shortcut.TargetPath = exe_path
            shortcut.WorkingDirectory = os.path.dirname(exe_path)
            shortcut.IconLocation = exe_path
            shortcut.save()
        except Exception as e:
            print(f"Не удалось создать ярлык: {e}")

    return exe_path

def threaded_download():
    global active_downloads
    game = current_game
    downloading_game["name"] = game["name"]
    active_downloads += 1
    update_download_status()
    user_versions[game['name']] = game['version']
    download_button.pack_forget()

    url = game.get('download_url')
    google_drive = game.get('google_drive', False)
    dest_path = os.path.join(GAMES_DIR, game['name'].replace(" ", "_") + ".zip")

    try:
        if not url:
            raise Exception("Ссылка на загрузку отсутствует.")

        update_progress("Скачивание...", 0)

        if google_drive:
            print(f"[GDOWN] Загрузка с Google Drive: {url}")
            result = gdown.download(get_direct_gdrive_link(url), dest_path, quiet=False, fuzzy=True)
            if result is None:
                raise Exception("Не удалось скачать файл с Google Drive. Проверьте доступность и формат ссылки.")
        else:
            print(f"[HTTP] Прямая загрузка: {url}")
            r = requests.get(url, stream=True, timeout=30)
            if r.status_code != 200:
                raise Exception(f"HTTP ошибка: {r.status_code}")
            total_length = r.headers.get('content-length')
            with open(dest_path, 'wb') as f:
                if total_length is None:
                    if not r.content:
                        raise Exception("Сервер вернул пустой файл.")
                    f.write(r.content)
                else:
                    dl = 0
                    total_length = int(total_length)
                    for chunk in r.iter_content(chunk_size=4096):
                        if chunk:
                            f.write(chunk)
                            dl += len(chunk)
                            done = int(100 * dl / total_length)
                            update_progress(f"Загрузка... {done}%", done)

        update_progress("Загрузка завершена ✅", 100)
        exe_path = extract_and_create_shortcut(dest_path, game['name'])

        if exe_path:
            update_progress("Игра загружается")
            progress.pack_forget()
        else:
            update_progress("Файл .exe не найден", 0)
            messagebox.showwarning("Внимание", "Файл .exe не найден. Проверьте архив.")

    except Exception as e:
        update_progress("Ошибка загрузки", 0)
        messagebox.showerror("Ошибка", f"Ошибка загрузки: {e}")

    finally:
        active_downloads -= 1
        downloading_game["name"] = None
        update_download_status()
        update_game_panel(game)

def download_game():
    if not download_button_state["enabled"]:
        return
    progress["value"] = 0
    progress_label.config(text="Подготовка...")
    threading.Thread(target=threaded_download, daemon=True).start()

download_button.config(command=download_game)

def is_game_installed(game):
    game_folder = os.path.join(GAMES_DIR, game['name'].replace(" ", "_"))
    if not os.path.exists(game_folder):
        return False
    for root_dir, _, files in os.walk(game_folder):
        if any(f.lower().endswith(".exe") for f in files):
            return True
    return False

def clear_game_panel():
    play_button.pack_forget()
    delete_button.pack_forget()
    download_button.pack_forget()
    game_title.config(text="")
    game_description.config(text="")
    game_image_label.config(image="", text="")
    progress_label.config(text="")
    progress.pack_forget()
    progress["value"] = 0

def on_game_select(event):
    index = game_listbox.curselection()
    if not index or index[0] >= len(visible_games):
        return
    selected_game = visible_games[index[0]]
    update_game_panel(selected_game)

def show_admin_panel():
    def submit():
        if entry.get() == ADMIN_PASSWORD:
            win.destroy()
            show_admin_editor()
        else:
            messagebox.showerror("Ошибка", "Неверный пароль")
    win = tk.Toplevel()
    win.title("Админ вход")
    tk.Label(win, text="Пароль:").pack()
    entry = tk.Entry(win, show="*")
    entry.pack()
    tk.Button(win, text="Войти", command=submit).pack()

def show_admin_editor():
    win = tk.Toplevel()
    win.title("Редактор игр")
    win.geometry("500x400")
    def add_right_click_paste(entry):
        menu = tk.Menu(entry, tearoff=0)
        menu.add_command(label="Вставить", command=lambda: entry.insert(tk.INSERT, root.clipboard_get()))
        entry.bind("<Button-3>", lambda event: menu.tk_popup(event.x_root, event.y_root))
    def add_game():
        new_game = {
            "name": name.get(),
            "description": desc.get(),
            "image_url": img.get(),
            "download_url": url.get(),
            "version": ver.get(),
            "adult_only": adult.get() == 1,
            "google_drive": google_drive.get() == 1
        }
        games.append(new_game)
        save_games()
        game_listbox.insert(tk.END, new_game["name"])
        win.destroy()
    def delete_selected_game():
        index = game_listbox.curselection()
        if not index:
            messagebox.showwarning("Внимание", "Выберите игру для удаления.")
            return
        game_name = game_listbox.get(index)
        if messagebox.askyesno("Удаление", f"Удалить игру '{game_name}'?"):
            for i, g in enumerate(games):
                if g["name"] == game_name:
                    del games[i]
                    break
            save_games()
            game_listbox.delete(index)
            win.destroy()
    name = tk.Entry(win)
    desc = tk.Entry(win)
    img = tk.Entry(win)
    url = tk.Entry(win)
    ver = tk.Entry(win)
    for entry in [name, desc, img, url, ver]:
        add_right_click_paste(entry)
    adult = tk.IntVar()
    google_drive = tk.IntVar()
    for label, widget in zip(["Название", "Описание", "Картинка URL", "Ссылка", "Версия"], [name, desc, img, url, ver]):
        tk.Label(win, text=label).pack()
        widget.pack()
    tk.Checkbutton(win, text="18+", variable=adult).pack()
    tk.Checkbutton(win, text="Google Drive", variable=google_drive).pack()
    tk.Button(win, text="Добавить", command=add_game).pack(pady=5)
    tk.Button(win, text="Удалить выбранную игру", command=delete_selected_game).pack(pady=5)

btn_report = ttk.Button(main_panel, text="🚨 Пожаловаться", command=show_game_report_window)
btn_report.pack(pady=5)
add_hover_effect(btn_report)

btn_comments = ttk.Button(main_panel, text="💬 Комментарии", command=show_comments_window)
btn_comments.pack(pady=5)
add_hover_effect(btn_comments)

btn_library = ttk.Button(left_buttons_frame, text="📚 Библиотека", command=lambda: show_library())
btn_library.pack(side="left", padx=5, pady=5)
add_hover_effect(btn_library)

btn_settings = ttk.Button(left_buttons_frame, text="⚙️ Настройки", command=lambda: show_settings())
btn_settings.pack(side="left", padx=5, pady=5)
add_hover_effect(btn_settings)

btn_admin = ttk.Button(left_buttons_frame, text="🔧 Админ", command=show_admin_panel)
btn_admin.pack(side="right", padx=5, pady=5)
add_hover_effect(btn_admin)

def show_settings():
    win = tk.Toplevel()
    win.title("Настройки")
    win.geometry("300x250")
    tk.Label(win, text="Опции", font=("Arial", 14, "bold")).pack(pady=10)
    var_age = tk.BooleanVar(value=user_settings.get("age_confirmed", False))

    def on_toggle_age():
        global_age_override["value"] = var_age.get()
        user_settings["age_confirmed"] = var_age.get()
        save_settings()

    tk.Checkbutton(win, text="Мне уже есть 18 лет", variable=var_age, command=on_toggle_age).pack()

    tk.Label(win, text="Тема", font=("Arial", 12, "bold")).pack(pady=10)
    ttk.Button(win, text="🌙 Тёмная тема", command=lambda: set_theme("dark")).pack(pady=5)
    ttk.Button(win, text="☀️ Светлая тема", command=lambda: set_theme("light")).pack(pady=5)

def set_theme(new_theme):
    theme_mode["value"] = new_theme
    user_settings["theme"] = new_theme
    save_settings()
    apply_theme()

def show_all_games():
    game_listbox.delete(0, tk.END)
    visible_games.clear()
    for g in games:
        game_listbox.insert(tk.END, g["name"])
        visible_games.append(g)

    if hasattr(show_library, "back_button"):
        show_library.back_button.destroy()
        del show_library.back_button

def show_library():
    game_listbox.delete(0, tk.END)
    visible_games.clear()
    for g in games:
        if is_game_installed(g):
            game_listbox.insert(tk.END, g["name"])
            visible_games.append(g)

    if not hasattr(show_library, "back_button"):
        show_library.back_button = ttk.Button(left_buttons_frame, text="⬅️ Назад", command=show_all_games)
        show_library.back_button.pack(side="left", padx=5, pady=5)

def load_images():
    for game in games:
        try:
            raw = urllib.request.urlopen(game["image_url"]).read()
            image = Image.open(io.BytesIO(raw))
            image.thumbnail((400, 200))
            photo = ImageTk.PhotoImage(image)
            image_cache[game["name"]] = photo
        except:
            image_cache[game["name"]] = None

def load_saved_user():
    if os.path.exists("user.json"):
        try:
            with open("user.json", "r", encoding="utf-8") as f:
                data = json.load(f)
                name = data.get("name")
                password = data.get("password")
                if name and password:
                    ok, _ = login_user(name, password)
                    if ok:
                        current_user["name"] = name
        except Exception as e:
            print(f"Ошибка при автологине: {e}")

load_saved_user()

threading.Thread(target=load_images, daemon=True).start()
root.withdraw()
loading_screen = tk.Toplevel()
loading_screen.geometry("300x150")
loading_screen.title("Загрузка...")
loading_screen.configure(bg="black")
loading_label = tk.Label(loading_screen, text="Загрузка данных...", font=("Arial", 14), bg="black", fg="orange")
loading_label.pack(expand=True)

def finish_loading():
    load_settings()
    load_played_time()
    global_age_override["value"] = user_settings.get("age_confirmed", False)
    update_games_json()  # обновить файл
    games.clear()
    games.extend(load_games())  # загрузить игры после обновления
    visible_games.clear()
    game_listbox.delete(0, tk.END)
    for game in games:
        game_listbox.insert(tk.END, game["name"])
        visible_games.append(game)
    load_images()
    update_download_status()
    loading_screen.destroy()
    root.deiconify()
    apply_theme()

game_listbox.bind("<<ListboxSelect>>", on_game_select)
threading.Thread(target=finish_loading, daemon=True).start()
root.mainloop()

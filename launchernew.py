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
LAUNCHER_VERSION = "1.3.4"
GAMES_FILE = "games.json"

downloading_game = {"name": None}
age_confirmed = {}
user_versions = {}
theme_mode = {"value": "dark"}
image_cache = {}
active_downloads = 0
download_button_state = {"enabled": True}
current_game = {}
global_age_override = {"value": False}

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
    url = game['download_url']
    google_drive = game.get('google_drive', False)
    dest_path = os.path.join(GAMES_DIR, game['name'].replace(" ", "_") + ".zip")

    try:
        update_progress("Скачивание...", 0)

        if google_drive:
            gdown.download(get_direct_gdrive_link(url), dest_path, quiet=False)
        else:
            with requests.get(url, stream=True) as r:
                r.raise_for_status()
                total_length = r.headers.get('content-length')
                with open(dest_path, 'wb') as f:
                    if total_length is None:
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

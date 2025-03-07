import os
import requests
from flask import Flask, request, Response
import json
from git import Repo
import shutil

app = Flask(__name__)

# Конфигурация
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "your bot token")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "YourChatID")
REPO_PATH = "/tmp/repo"  # Временная папка для клонирования

# Функция отправки сообщения в Telegram
def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    response = requests.post(url, json=payload)
    return response.status_code == 200

# Очистка временной папки
def clean_repo():
    if os.path.exists(REPO_PATH):
        shutil.rmtree(REPO_PATH)

# Обработка вебхука от GitLab
@app.route("/webhook", methods=["POST"])
def handle_webhook():
    data = request.json
    event_type = request.headers.get("X-Gitlab-Event")

    if event_type == "Pipeline Hook":
        pipeline_status = data["object_attributes"]["status"]
        pipeline_url = data["object_attributes"]["url"]
        commit_msg = data["commit"]["message"]
        repo_url_base = data["project"]["git_http_url"] 
        gitlab_token = os.getenv("GITLAB_TOKEN", "YourTokenGitlab")  
        repo_url = repo_url_base.replace("https://", f"https://oauth2:{gitlab_token}@")
        commit_sha = data["commit"]["id"]

        # Клонируем репозиторий с токеном
        clean_repo()
        repo = Repo.clone_from(repo_url, REPO_PATH)

        # Переключаемся на конкретный коммит
        repo.git.checkout(commit_sha)

        # Получаем статистику изменений
        try:
            diff_stat = repo.git.diff("--stat", f"{commit_sha}^", commit_sha)
            added_lines = 0
            removed_lines = 0
            for line in diff_stat.splitlines():
                if "insertion" in line or "deletion" in line:
                    parts = line.split(",")
                    for part in parts:
                        if "insertion" in part:
                            added_lines = int(part.split()[0])
                        elif "deletion" in part:
                            removed_lines = int(part.split()[0])
        except Exception as e:
            added_lines = removed_lines = 0  # Если diff не удалось получить

        # Список новых и удалённых файлов
        try:
            diff_status = repo.git.diff("--name-status", f"{commit_sha}^", commit_sha).splitlines()
            new_files = [line.split()[1] for line in diff_status if line.startswith("A")]
            deleted_files = [line.split()[1] for line in diff_status if line.startswith("D")]
        except Exception:
            new_files = []
            deleted_files = []

        # Формируем сообщение
        message = (
            f"*Pipeline*: {pipeline_url}\n"
            f"*Статус*: {pipeline_status}\n"
            f"*Коммит*: {commit_msg}\n"
            f"*Добавлено строк*: {added_lines}\n"
            f"*Удалено строк*: {removed_lines}\n"
            f"*Новые файлы*: {', '.join(new_files) or 'Нет'}\n"
            f"*Удалённые файлы*: {', '.join(deleted_files) or 'Нет'}"
        )

        # Отправляем уведомление
        if send_telegram_message(message):
            clean_repo()
            return Response("Notification sent", status=200)
        else:
            clean_repo()
            return Response("Failed to send notification", status=500)

    return Response("Event not handled", status=200)
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

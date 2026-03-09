from __future__ import annotations

import random
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import tomllib

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)


def load_settings() -> dict:
    """setting.tomlを読み込み、なければデフォルト値を使う。"""
    default = {
        "app": {"idle_seconds": 20, "sakura_probability": 0.45},
        "ollama": {
            "model": "gemma3:4b",
            "endpoint": "http://127.0.0.1:11434/api/generate",
            "temperature": 0.9,
        },
        "prompt": {
            "praise": (
                "あなたは超ハイテンションなアイデア応援AIです。\n"
                "以下のアイデアを日本語で全力で褒めてください。\n"
                "タイトル: {title}\n"
                "ユーザーのアイデア: {idea}"
            ),
            "suggest": (
                "あなたは優秀な発想パートナーです。\n"
                "タイトルと既存アイデアを踏まえ、次の一歩になる新しい案を1つ提案してください。\n"
                "タイトル: {title}\n"
                "既存アイデア:\n{ideas}"
            ),
        },
    }

    settings_path = BASE_DIR / "setting.toml"
    if not settings_path.exists():
        return default

    with settings_path.open("rb") as f:
        loaded = tomllib.load(f)

    # デフォルト値とマージして、設定漏れでも動作させる
    for section, values in default.items():
        loaded.setdefault(section, {})
        for key, value in values.items():
            loaded[section].setdefault(key, value)
    return loaded


SETTINGS = load_settings()
app = FastAPI(title="idea-turbo")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# セッションID(=ログファイル名)ごとの入力履歴をメモリで持つ
SESSION_STATE: Dict[str, List[str]] = {}
# セッションID(=ログファイル名)とファイルパスの対応
SESSION_FILES: Dict[str, Path] = {}


def sanitize_title(title: str) -> str:
    """ファイル名に使えない文字を置換して安全にする。"""
    normalized = title.strip()
    if not normalized:
        raise ValueError("タイトルが空です")
    return re.sub(r"[\\/:*?\"<>|]", "_", normalized)


def build_session_id(title: str) -> str:
    """`{YYYYMMDD_HHMM}-{title}.txt` のファイル名を作る。"""
    safe_title = sanitize_title(title)
    base = f"{datetime.now().strftime('%Y%m%d_%H%M')}-{safe_title}"
    candidate = DATA_DIR / f"{base}.txt"
    serial = 1
    while candidate.exists():
        serial += 1
        candidate = DATA_DIR / f"{base}-{serial}.txt"
    return candidate.name


def session_file_path(session_id: str) -> Path:
    """セッションIDからログファイルパスを引く。"""
    if session_id in SESSION_FILES:
        return SESSION_FILES[session_id]
    path = DATA_DIR / session_id
    if not path.resolve().is_file() or path.parent.resolve() != DATA_DIR.resolve():
        raise HTTPException(status_code=404, detail="セッションが見つかりません")
    SESSION_FILES[session_id] = path
    return path


def title_from_session_id(session_id: str) -> str:
    """`YYYYMMDD_HHMM-title.txt` から表示用タイトルを取り出す。"""
    stem = Path(session_id).stem
    matched = re.match(r"^\d{8}_\d{4}-(.+)$", stem)
    if matched:
        return matched.group(1)
    return stem


def find_latest_session_id_by_title(title: str) -> str | None:
    """旧フロント互換: タイトルに一致する最新セッションIDを返す。"""
    safe_title = sanitize_title(title)
    pattern = re.compile(rf"^\d{{8}}_\d{{4}}-{re.escape(safe_title)}(?:-\d+)?\.txt$")
    matched = [p for p in DATA_DIR.glob("*.txt") if pattern.match(p.name)]
    if not matched:
        return None
    latest = max(matched, key=lambda p: p.stat().st_mtime)
    return latest.name


def resolve_session_id(payload: dict, *, require_idea: bool = False) -> str:
    """session_id優先で解決し、なければタイトル指定を後方互換で受け付ける。"""
    session_id = (payload.get("session_id") or "").strip()
    if session_id:
        session_file_path(session_id)
        return session_id

    # 旧クライアント互換: titleだけ送る形式も許容する
    title = (payload.get("title") or "").strip()
    if title:
        found = find_latest_session_id_by_title(title)
        if found:
            session_file_path(found)
            return found

    if require_idea:
        raise HTTPException(status_code=400, detail="session_idとアイデアが必要です")
    raise HTTPException(status_code=400, detail="session_idが必要です")


def append_log(session_id: str, speaker: str, message: str) -> None:
    """会話を`data/{タイトル}.txt`へ追記する。"""
    path = session_file_path(session_id)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with path.open("a", encoding="utf-8") as f:
        f.write(f"[{now}] {speaker}: {message}\n")


def parse_log_messages(path: Path) -> List[Dict[str, str]]:
    """保存済みログをUI表示用メッセージ配列へ変換する。"""
    messages: List[Dict[str, str]] = []
    pattern = re.compile(r"^\[(?P<ts>[^\]]+)\]\s+(?P<speaker>[^:]+):\s*(?P<msg>.*)$")
    with path.open("r", encoding="utf-8") as f:
        for raw in f:
            line = raw.rstrip("\n")
            matched = pattern.match(line)
            if not matched:
                continue

            speaker = matched.group("speaker")
            message = matched.group("msg")
            if speaker == "USER":
                kind = "user"
                text = f"あなた: {message}"
            elif speaker in {"AI", "AI-SUGGEST"}:
                kind = "ai" if speaker == "AI" else "suggest"
                prefix = "AI: " if speaker == "AI" else "AIの提案: "
                text = f"{prefix}{message}"
            else:
                continue

            messages.append({"kind": kind, "text": text})
    return messages


def parse_user_ideas(path: Path) -> List[str]:
    """ログからユーザー入力だけを抽出する。"""
    ideas: List[str] = []
    pattern = re.compile(r"^\[[^\]]+\]\s+USER:\s*(.*)$")
    with path.open("r", encoding="utf-8") as f:
        for raw in f:
            line = raw.rstrip("\n")
            matched = pattern.match(line)
            if matched:
                ideas.append(matched.group(1))
    return ideas


async def generate_with_ollama(prompt: str) -> str:
    """Ollama APIを呼び出してテキストを生成する。"""
    payload = {
        "model": SETTINGS["ollama"]["model"],
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": SETTINGS["ollama"]["temperature"],
        },
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(SETTINGS["ollama"]["endpoint"], json=payload)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:  # noqa: BLE001
        # ローカルLLM未起動でもUIが止まらないように、代替メッセージを返す
        return f"Ollamaに接続できませんでした。起動後に再実行してください。詳細: {exc}"

    return data.get("response", "応答を取得できませんでした。")


@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "idle_seconds": SETTINGS["app"]["idle_seconds"],
            "model_name": SETTINGS["ollama"]["model"],
        },
    )


@app.post("/start")
async def start_session(request: Request):
    payload = await request.json()
    title = (payload.get("title") or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="タイトルは必須です")

    session_id = build_session_id(title)
    path = DATA_DIR / session_id
    path.touch(exist_ok=False)
    SESSION_FILES[session_id] = path
    SESSION_STATE[session_id] = []
    append_log(session_id, "SYSTEM", f"セッション開始: {title}")
    return JSONResponse({"ok": True, "title": sanitize_title(title), "session_id": session_id})


@app.get("/sessions")
async def list_sessions():
    sessions = []
    for path in sorted(DATA_DIR.glob("*.txt"), key=lambda p: p.stat().st_mtime, reverse=True):
        sessions.append(
            {
                "session_id": path.name,
                "title": title_from_session_id(path.name),
                "updated_at": datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
    return JSONResponse({"sessions": sessions})


@app.post("/continue")
async def continue_session(request: Request):
    payload = await request.json()
    session_id = (payload.get("session_id") or "").strip()
    if not session_id:
        raise HTTPException(status_code=400, detail="session_idが必要です")

    path = session_file_path(session_id)
    ideas = parse_user_ideas(path)
    SESSION_STATE[session_id] = ideas
    messages = parse_log_messages(path)
    return JSONResponse(
        {
            "ok": True,
            "session_id": session_id,
            "title": title_from_session_id(session_id),
            "messages": messages,
        }
    )


@app.post("/idea")
async def submit_idea(request: Request):
    payload = await request.json()
    session_id = resolve_session_id(payload, require_idea=True)
    idea = (payload.get("idea") or "").strip()
    if not idea:
        raise HTTPException(status_code=400, detail="session_idとアイデアが必要です")

    safe_title = title_from_session_id(session_id)
    SESSION_STATE.setdefault(session_id, []).append(idea)

    append_log(session_id, "USER", idea)

    prompt = SETTINGS["prompt"]["praise"].format(title=safe_title, idea=idea)
    ai_message = await generate_with_ollama(prompt)
    append_log(session_id, "AI", ai_message)

    sakura = random.random() < float(SETTINGS["app"]["sakura_probability"])
    return JSONResponse({"message": ai_message, "sakura": sakura})


@app.post("/suggest")
async def suggest_idea(request: Request):
    payload = await request.json()
    session_id = resolve_session_id(payload, require_idea=False)

    safe_title = title_from_session_id(session_id)
    ideas = SESSION_STATE.get(session_id, [])

    if ideas:
        ideas_text = "\n".join(f"- {i}" for i in ideas[-10:])
    else:
        ideas_text = "- まだ入力なし"

    prompt = SETTINGS["prompt"]["suggest"].format(title=safe_title, ideas=ideas_text)
    ai_message = await generate_with_ollama(prompt)
    append_log(session_id, "AI-SUGGEST", ai_message)

    return JSONResponse({"message": ai_message})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)

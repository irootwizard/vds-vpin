#!/usr/bin/env python3
"""Export Cursor chats for the vPIN-main workspace (agent transcripts + composer bubbles)."""

from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


WORKSPACE_FOLDER = r"d:\WorkStation\pythoncode\experiment-reproduction\vPIN-main"
WORKSPACE_STORAGE_ID = "697d22d8dad7fe982e042959cd551ec6"
PROJECT_SLUG = "d-WorkStation-pythoncode-experiment-reproduction-vPIN-main"

# Cursor bubble types (observed): 1=user, 2=assistant
BUBBLE_TYPE = {1: "user", 2: "assistant"}


def safe_name(text: str, max_len: int = 80) -> str:
    text = re.sub(r"\s+", " ", (text or "").strip())
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", text)
    return (text[:max_len] or "untitled").rstrip(" ._")


def as_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return str(value)


def load_json_blob(value):
    if value is None:
        return None
    s = as_text(value)
    if not s:
        return None
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        return None


def open_db(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)


def ms_to_iso(ms) -> str | None:
    if not ms:
        return None
    try:
        return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).isoformat()
    except Exception:
        return None


def clean_user_text(text: str) -> str:
    text = re.sub(r"<timestamp>.*?</timestamp>\s*", "", text, flags=re.S)
    text = re.sub(r"<user_query>\s*", "", text)
    text = re.sub(r"\s*</user_query>", "", text)
    return text.strip()


def extract_text_from_transcript_message(message: dict | None) -> str:
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "text" and "text" in item:
                    parts.append(str(item["text"]))
                elif "text" in item:
                    parts.append(str(item["text"]))
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(parts)
    return ""


def read_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                rows.append({"_raw": line})
    return rows


def first_user_title_from_rows(rows: list[dict]) -> str:
    for row in rows:
        if row.get("role") == "user":
            t = clean_user_text(extract_text_from_transcript_message(row.get("message")))
            if t:
                return t.splitlines()[0][:80]
    return "untitled"


def transcript_to_markdown(chat_id: str, rows: list[dict], meta: dict | None = None) -> str:
    title = first_user_title_from_rows(rows)
    lines = [f"# {title}", "", f"- id: `{chat_id}`"]
    if meta:
        for k, v in meta.items():
            if v not in (None, ""):
                lines.append(f"- {k}: {v}")
    lines += ["", "---", ""]
    for row in rows:
        role = row.get("role") or "unknown"
        if role == "user":
            body = clean_user_text(extract_text_from_transcript_message(row.get("message")))
            if not body:
                continue
            lines += ["## User", "", body, ""]
        elif role == "assistant":
            msg = row.get("message") or {}
            content = msg.get("content")
            texts, tools = [], []
            if isinstance(content, list):
                for item in content:
                    if not isinstance(item, dict):
                        continue
                    if item.get("type") == "text" and item.get("text"):
                        t = str(item["text"]).strip()
                        if t and t != "[REDACTED]":
                            texts.append(t)
                    elif item.get("type") == "tool_use":
                        tools.append(f"- tool: `{item.get('name', 'tool')}`")
            elif isinstance(content, str) and content.strip():
                texts.append(content.strip())
            if not texts and not tools:
                continue
            lines += ["## Assistant", ""]
            if texts:
                lines += ["\n\n".join(texts), ""]
            if tools:
                lines += [
                    "<details><summary>Tools used</summary>",
                    "",
                    *tools[:50],
                    *( [f"- ... and {len(tools)-50} more"] if len(tools) > 50 else [] ),
                    "",
                    "</details>",
                    "",
                ]
    return "\n".join(lines).rstrip() + "\n"


def belongs_to_workspace(composer: dict) -> bool:
    wi = composer.get("workspaceIdentifier")
    if isinstance(wi, dict):
        wid = wi.get("id")
        if wid == WORKSPACE_STORAGE_ID:
            return True
        if wid:
            # Belongs to another workspace.
            return False
        uri = wi.get("uri") or {}
        if isinstance(uri, dict):
            blob = json.dumps(uri, ensure_ascii=False).lower()
            return "vpin-main" in blob
    # Older chats: path may only appear in context attachments
    ctx = composer.get("context") or {}
    blob = json.dumps(
        {
            "folderSelections": ctx.get("folderSelections"),
            "fileSelections": ctx.get("fileSelections"),
            "name": composer.get("name"),
            "subtitle": composer.get("subtitle"),
        },
        ensure_ascii=False,
    ).lower()
    return "vpin-main" in blob


def export_transcripts(transcripts_root: Path, out_md: Path, out_raw: Path) -> list[dict]:
    out_md.mkdir(parents=True, exist_ok=True)
    out_raw.mkdir(parents=True, exist_ok=True)
    index = []
    files = sorted(transcripts_root.rglob("*.jsonl"))
    for i, path in enumerate(files, 1):
        chat_id = path.stem
        rows = read_jsonl(path)
        title = first_user_title_from_rows(rows)
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()
        md_name = f"{i:03d}_{safe_name(title)}_{chat_id[:8]}.md"
        (out_md / md_name).write_text(
            transcript_to_markdown(
                chat_id,
                rows,
                {"source": "agent-transcript", "mtime_utc": mtime, "messages": len(rows)},
            ),
            encoding="utf-8",
        )
        dest = out_raw / f"{chat_id}.jsonl"
        shutil.copy2(path, dest)
        index.append(
            {
                "id": chat_id,
                "title": title,
                "messages": len(rows),
                "mtime_utc": mtime,
                "markdown": md_name,
                "raw": dest.name,
            }
        )
    return index


def fetch_bubbles(cur, composer_id: str, headers: list) -> list[dict]:
    messages = []
    for h in headers:
        if isinstance(h, dict):
            bubble_id = h.get("bubbleId") or h.get("id")
        else:
            bubble_id = str(h)
        if not bubble_id:
            continue
        key = f"bubbleId:{composer_id}:{bubble_id}"
        row = cur.execute("SELECT value FROM cursorDiskKV WHERE key=?", (key,)).fetchone()
        if not row:
            continue
        bubble = load_json_blob(row[0])
        if not bubble:
            continue
        btype = bubble.get("type")
        role = BUBBLE_TYPE.get(btype, f"type-{btype}")
        text = (bubble.get("text") or "").strip()
        # skip empty tool-only bubbles without text
        tool_results = bubble.get("toolResults") or []
        if not text and not tool_results:
            # still keep thinking blocks if any
            thinking = bubble.get("allThinkingBlocks") or []
            if not thinking:
                continue
        messages.append(
            {
                "bubbleId": bubble_id,
                "role": role,
                "type": btype,
                "text": text,
                "createdAt": bubble.get("createdAt"),
                "toolResultsCount": len(tool_results) if isinstance(tool_results, list) else 0,
                "model": (bubble.get("modelInfo") or {}).get("modelName")
                if isinstance(bubble.get("modelInfo"), dict)
                else None,
            }
        )
    return messages


def composer_to_markdown(meta: dict, messages: list[dict]) -> str:
    title = meta.get("name") or (messages[0]["text"].splitlines()[0][:80] if messages else "untitled")
    lines = [
        f"# {title}",
        "",
        f"- composerId: `{meta.get('composerId')}`",
        f"- mode: {meta.get('unifiedMode')}",
        f"- created_utc: {ms_to_iso(meta.get('createdAt'))}",
        f"- updated_utc: {ms_to_iso(meta.get('lastUpdatedAt'))}",
        f"- messages: {len(messages)}",
        f"- source: composer/cursorDiskKV",
        "",
        "---",
        "",
    ]
    for m in messages:
        role = m["role"]
        heading = "User" if role == "user" else ("Assistant" if role == "assistant" else role)
        body = clean_user_text(m["text"]) if role == "user" else m["text"]
        if not body:
            if m.get("toolResultsCount"):
                body = f"_(tool results: {m['toolResultsCount']})_"
            else:
                continue
        lines += [f"## {heading}", ""]
        if m.get("createdAt"):
            lines.append(f"- time: {ms_to_iso(m['createdAt'])}")
            lines.append("")
        lines += [body, ""]
    return "\n".join(lines).rstrip() + "\n"


def export_composers(global_db: Path, out_md: Path, out_json: Path) -> list[dict]:
    out_md.mkdir(parents=True, exist_ok=True)
    out_json.mkdir(parents=True, exist_ok=True)
    con = open_db(global_db)
    cur = con.cursor()

    headers_row = cur.execute(
        "SELECT value FROM ItemTable WHERE key=?", ("composer.composerHeaders",)
    ).fetchone()
    headers = load_json_blob(headers_row[0]) if headers_row else {}
    all_headers = (headers or {}).get("allComposers") or []

    # Index headers by id for name/timestamps fallback
    header_by_id = {
        h.get("composerId"): h for h in all_headers if isinstance(h, dict) and h.get("composerId")
    }

    # Materialize first — nested cur.execute() would reset this iterator.
    composer_rows = cur.execute(
        "SELECT key, value FROM cursorDiskKV WHERE key LIKE 'composerData:%'"
    ).fetchall()
    bubble_cur = con.cursor()

    index = []
    matched = 0
    for key, value in composer_rows:
        data = load_json_blob(value)
        if not data or not isinstance(data, dict):
            continue
        if not belongs_to_workspace(data):
            continue
        matched += 1
        cid = data.get("composerId") or key.split(":", 1)[-1]
        hdr = header_by_id.get(cid) or {}
        name = data.get("name") or hdr.get("name") or "untitled"
        headers_only = data.get("fullConversationHeadersOnly") or []
        messages = fetch_bubbles(bubble_cur, cid, headers_only)

        meta = {
            "composerId": cid,
            "name": name,
            "unifiedMode": data.get("unifiedMode") or hdr.get("unifiedMode"),
            "createdAt": data.get("createdAt") or hdr.get("createdAt"),
            "lastUpdatedAt": data.get("lastUpdatedAt") or hdr.get("lastUpdatedAt"),
            "subtitle": data.get("subtitle") or hdr.get("subtitle"),
            "bubbleHeaders": len(headers_only),
            "messagesExported": len(messages),
        }
        # raw json (compact meta + messages; not full bubble dumps to save space)
        raw_path = out_json / f"{cid}.json"
        raw_path.write_text(
            json.dumps({"meta": meta, "messages": messages}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        md_name = f"{matched:03d}_{safe_name(name)}_{cid[:8]}.md"
        (out_md / md_name).write_text(composer_to_markdown(meta, messages), encoding="utf-8")
        index.append({**meta, "markdown": md_name, "json": raw_path.name})

    # also dump headers filtered
    filtered_headers = [
        h
        for h in all_headers
        if isinstance(h, dict) and h.get("composerId") in {i["composerId"] for i in index}
    ]
    (out_json / "_composer_headers_workspace.json").write_text(
        json.dumps(filtered_headers, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    con.close()
    # sort by updated desc
    index.sort(key=lambda x: x.get("lastUpdatedAt") or 0, reverse=True)
    return index


def main() -> None:
    home = Path.home()
    appdata = Path(os.environ["APPDATA"])
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_root = Path(r"D:\WorkStation\exports") / f"cursor-chats-export-vPIN-main-{stamp}"
    out_root.mkdir(parents=True, exist_ok=True)

    transcripts = home / ".cursor" / "projects" / PROJECT_SLUG / "agent-transcripts"
    ws_db = (
        appdata
        / "Cursor"
        / "User"
        / "workspaceStorage"
        / WORKSPACE_STORAGE_ID
        / "state.vscdb"
    )
    global_db = appdata / "Cursor" / "User" / "globalStorage" / "state.vscdb"

    print("OUT", out_root)
    print("transcripts", transcripts.exists())
    print("ws_db", ws_db.exists())
    print("global_db", global_db.exists())

    t_index = []
    if transcripts.exists():
        t_index = export_transcripts(
            transcripts, out_root / "agent-transcripts" / "markdown", out_root / "agent-transcripts" / "raw-jsonl"
        )
        print("agent transcripts", len(t_index))

    c_index = []
    if global_db.exists():
        print("exporting composers from cursorDiskKV (may take 1-3 minutes)...")
        c_index = export_composers(
            global_db,
            out_root / "composer-chats" / "markdown",
            out_root / "composer-chats" / "json",
        )
        print("composer chats", len(c_index))

    if ws_db.exists():
        ws_dir = out_root / "workspace-db"
        ws_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ws_db, ws_dir / "state.vscdb")

    readme = f"""# Cursor 对话导出（vPIN-main）

导出时间: {datetime.now().isoformat(timespec='seconds')}
工作区: `{WORKSPACE_FOLDER}`

## 目录

- `agent-transcripts/` — Agent 运行 transcript（JSONL + Markdown），共 **{len(t_index)}** 个
- `composer-chats/` — 本工作区 Composer/Agent 完整会话（按 bubble 还原），共 **{len(c_index)}** 个
- `workspace-db/` — 工作区 state.vscdb 备份
- `index.json` / `CATALOG.md` — 索引

## 迁移到 VS Code Copilot 的现实情况

GitHub Copilot Chat **没有官方导入 Cursor 历史的功能**。
本导出用于：

1. 完整归档项目讨论与决策
2. 在 Copilot 中按需粘贴关键片段
3. 把长期有效的约定写进 `.github/copilot-instructions.md` 或仓库文档

建议：打开 `CATALOG.md` → 选会话 → 复制需要延续的结论到 Copilot。
"""
    (out_root / "README.md").write_text(readme, encoding="utf-8")

    catalog = ["# 会话目录", "", "## Composer / Agent 会话", ""]
    for item in c_index:
        catalog.append(
            f"- [{item.get('name') or 'untitled'}](composer-chats/markdown/{item['markdown']}) "
            f"({item.get('messagesExported', 0)} msgs, mode={item.get('unifiedMode')}, "
            f"{(ms_to_iso(item.get('lastUpdatedAt')) or '')[:10]})"
        )
    catalog += ["", "## Agent transcripts", ""]
    for item in t_index:
        catalog.append(
            f"- [{item['title']}](agent-transcripts/markdown/{item['markdown']}) "
            f"({item['messages']} msgs, {item['mtime_utc'][:10]})"
        )
    (out_root / "CATALOG.md").write_text("\n".join(catalog) + "\n", encoding="utf-8")

    (out_root / "index.json").write_text(
        json.dumps(
            {
                "exported_at": datetime.now().isoformat(timespec="seconds"),
                "workspace": WORKSPACE_FOLDER,
                "workspace_storage_id": WORKSPACE_STORAGE_ID,
                "agent_transcript_count": len(t_index),
                "composer_chat_count": len(c_index),
                "agent_transcripts": t_index,
                "composer_chats": c_index,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print("DONE", out_root)


if __name__ == "__main__":
    main()

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from typing import Dict, Set
import json

app = FastAPI()

# DELETE THE NEXT TWO LINES

# Codes you allow (OTP-like). Add/remove as you want.
# ALLOWED_CODES = {"100", "200", "999"}

# code -> set of active websockets
rooms: Dict[str, Set[WebSocket]] = {}
# websocket -> name
names: Dict[WebSocket, str] = {}

@app.get("/", response_class=HTMLResponse)
def index():
    with open("static/index.html", "r", encoding="utf-8") as f:
        return f.read()

@app.get("/host", response_class=HTMLResponse)
def host_page():
    with open("static/host.html", "r", encoding="utf-8") as f:
        return f.read()

app.mount("/static", StaticFiles(directory="static"), name="static")


async def broadcast(code: str, payload: dict):
    msg = json.dumps(payload)
    for ws in list(rooms.get(code, set())):
        try:
            await ws.send_text(msg)
        except Exception:
            # Ignore send failures; disconnect cleanup happens elsewhere
            pass


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await websocket.accept()

    try:
        # First message must be: {"type":"join","code":"100","name":"Alice"}
        raw = await websocket.receive_text()
        data = json.loads(raw)

        if data.get("type") != "join":
            await websocket.close(code=1008)
            return

        code = str(data.get("code", "")).strip()
        name = str(data.get("name", "")).strip()[:24] or "Anonymous"

        # Allow any alphanumeric OTP of length 1–10
        if not (code.isalnum() and 1 <= len(code) <= 10):
            await websocket.send_text(json.dumps({
                "type": "error",
                "message": "Invalid code (use letters/numbers, length 1–10)"
            }))
            await websocket.close(code=1008)
            return

        rooms.setdefault(code, set()).add(websocket)
        names[websocket] = name

        await broadcast(code, {"type": "system", "message": f"{name} joined", "code": code})

        # Chat loop
        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)

            if msg.get("type") == "chat":
                text = str(msg.get("text", "")).strip()
                if not text:
                    continue
                await broadcast(code, {"type": "chat", "name": name, "text": text})

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        # Cleanup
        left_name = names.get(websocket, "Someone")
        # Remove from any room
        for c, wss in list(rooms.items()):
            if websocket in wss:
                wss.remove(websocket)
                if not wss:
                    rooms.pop(c, None)
                else:
                    await broadcast(c, {"type": "system", "message": f"{left_name} left", "code": c})
        names.pop(websocket, None)
        try:
            await websocket.close()
        except Exception:
            pass

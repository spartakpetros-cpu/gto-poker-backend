import json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# Разрешаем подключение с вашего хостинга Hostinger
app.add_middleware(
    CORSMiddleware, 
    allow_origins=["*"], 
    allow_credentials=True, 
    allow_methods=["*"], 
    allow_headers=["*"]
)

class ConnectionManager:
    def __init__(self):
        self.active = []
        
    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)
        
    def disconnect(self, ws: WebSocket):
        if ws in self.active:
            self.active.remove(ws)
            
    async def broadcast(self, msg: str):
        for connection in self.active:
            await connection.send_text(msg)

manager = ConnectionManager()

@app.get("/")
async def root():
    return {"status": "GTO Poker Server is running!"}

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await manager.connect(ws)
    try:
        while True:
            data = await ws.receive_text()
            action = json.loads(data)
            await manager.broadcast(f"Игрок нажал: {action['button']}")
    except WebSocketDisconnect:
        manager.disconnect(ws)

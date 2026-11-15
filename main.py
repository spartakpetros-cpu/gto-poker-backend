from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import json

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ваши настройки приватной комнаты
ROOM_PASSWORD = "12345qwerty"
MAX_PLAYERS = 9

class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[WebSocket, str] = {}

    def add_player(self, websocket: WebSocket, name: str):
        self.active_connections[websocket] = name

    def remove_player(self, websocket: WebSocket):
        if websocket in self.active_connections:
            del self.active_connections[websocket]

    async def broadcast(self, message: str):
        # Рассылаем сообщение всем игрокам за столом
        for connection in list(self.active_connections.keys()):
            try:
                await connection.send_text(message)
            except:
                pass

manager = ConnectionManager()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    player_name = "Неизвестный"
    
    try:
        # 1. Ждем попытку входа (Имя + Пароль)
        data = await websocket.receive_text()
        auth = json.loads(data)
        
        # 2. Проверяем пароль
        if auth.get("password") != ROOM_PASSWORD:
            await websocket.send_text(json.dumps({"error": "Неверный пароль"}))
            await websocket.close()
            return
            
        # 3. Проверяем наличие свободных мест
        if len(manager.active_connections) >= MAX_PLAYERS:
            await websocket.send_text(json.dumps({"error": "Стол заполнен (9/9)"}))
            await websocket.close()
            return
            
        # 4. Успешный вход: сажаем за стол
        player_name = auth.get("name", "Аноним")
        manager.add_player(websocket, player_name)
        
        # Даем отмашку фронтенду, что пустили, и оповещаем всех
        await websocket.send_text(json.dumps({"status": "auth_ok"}))
        await manager.broadcast(json.dumps({"log": f"👋 {player_name} сел за стол ({len(manager.active_connections)}/{MAX_PLAYERS})."}))
        
        # 5. Основной игровой цикл (Слушаем ходы)
        while True:
            data = await websocket.receive_text()
            action_data = json.loads(data)
            
            if "button" in action_data:
                action = action_data["button"]
                # Оповещаем всех за столом о действии игрока
                await manager.broadcast(json.dumps({"log": f"🃏 {player_name}: {action}"}))
                
    except WebSocketDisconnect:
        # Игрок закрыл вкладку или пропал интернет
        manager.remove_player(websocket)
        await manager.broadcast(json.dumps({"log": f"🚪 {player_name} покинул стол ({len(manager.active_connections)}/{MAX_PLAYERS})."}))

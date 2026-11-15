from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import json
import random

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ROOM_PASSWORD = "12345qwerty"
MAX_PLAYERS = 9

RANKS = ['2', '3', '4', '5', '6', '7', '8', '9', 'T', 'J', 'Q', 'K', 'A']
SUITS = ['♠', '♥', '♦', '♣']
POSITIONS = ['SB', 'BB', 'UTG', 'EP', 'MP', 'LJ', 'HJ', 'CO', 'BTN']

def get_deck():
    deck = [f"{r}{s}" for r in RANKS for s in SUITS]
    random.shuffle(deck)
    return deck

class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[WebSocket, str] = {}
        self.turn_index = 0
        self.game_in_progress = False

    def add_player(self, websocket: WebSocket, name: str):
        self.active_connections[websocket] = name

    def remove_player(self, websocket: WebSocket):
        if websocket in self.active_connections:
            del self.active_connections[websocket]
        self.game_in_progress = False # Защита

    async def broadcast(self, message: str):
        for connection in list(self.active_connections.keys()):
            try: await connection.send_text(message)
            except: pass
                
    async def send_personal_message(self, message: str, websocket: WebSocket):
        try: await websocket.send_text(message)
        except: pass

    def get_current_turn_name(self):
        if not self.active_connections: return None
        players = list(self.active_connections.values())
        if self.turn_index >= len(players): self.turn_index = 0
        return players[self.turn_index]

    def advance_turn(self):
        self.turn_index += 1
        if self.turn_index >= len(self.active_connections):
            self.turn_index = 0

    # НОВЫЙ МЕТОД: Рассылка точного состояния стола всем
    async def broadcast_state(self):
        # Оставляем только уникальные имена, сохраняя порядок посадки
        players_list = []
        for name in self.active_connections.values():
            if name not in players_list:
                players_list.append(name)
                
        await self.broadcast(json.dumps({
            "players_update": players_list, 
            "active_turn": self.get_current_turn_name() if self.game_in_progress else None
        }))

manager = ConnectionManager()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    player_name = "Неизвестный"
    
    try:
        data = await websocket.receive_text()
        auth = json.loads(data)
        
        if auth.get("password") != ROOM_PASSWORD:
            await websocket.send_text(json.dumps({"error": "Неверный пароль"}))
            await websocket.close()
            return
            
        if len(manager.active_connections) >= MAX_PLAYERS:
            await websocket.send_text(json.dumps({"error": "Стол заполнен"}))
            await websocket.close()
            return
            
        player_name = auth.get("name", "Аноним")
        manager.add_player(websocket, player_name)
        
        await websocket.send_text(json.dumps({"status": "auth_ok"}))
        await manager.broadcast(json.dumps({"log": f"👋 {player_name} сел за стол."}))
        await manager.broadcast_state() # Жесткая синхронизация при входе
        
        while True:
            data = await websocket.receive_text()
            action_data = json.loads(data)
            
            if "button" in action_data:
                action = action_data["button"]
                
                if action == "Deal":
                    manager.game_in_progress = True
                    manager.turn_index = 0
                    players = list(manager.active_connections.items())
                    deck = get_deck()
                    
                    await manager.broadcast(json.dumps({"log": f"🎲 {player_name} раздает карты...", "event": "new_hand"}))
                    
                    for i, (ws_conn, p_name) in enumerate(players):
                        pos = POSITIONS[i % len(POSITIONS)]
                        hand_msg = f"Раздача! Позиция: {pos} | Карты: {deck.pop()} {deck.pop()}"
                        await manager.send_personal_message(json.dumps({"log": hand_msg}), ws_conn)
                    
                    await manager.broadcast_state() # Синхронизация очереди
                    
                elif manager.game_in_progress:
                    if player_name == manager.get_current_turn_name():
                        await manager.broadcast(json.dumps({"log": f"🃏 {player_name}: {action}"}))
                        manager.advance_turn()
                        await manager.broadcast_state() # Передача хода
                    else:
                        await websocket.send_text(json.dumps({"log": "⚠️ Сейчас не ваш ход!"}))
                    
    except WebSocketDisconnect:
        manager.remove_player(websocket)
        await manager.broadcast(json.dumps({"log": f"🚪 {player_name} покинул стол.", "event": "player_left"}))
        await manager.broadcast_state() # Жесткая синхронизация при выходе

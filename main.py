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

    def add_player(self, websocket: WebSocket, name: str):
        self.active_connections[websocket] = name

    def remove_player(self, websocket: WebSocket):
        if websocket in self.active_connections:
            del self.active_connections[websocket]

    async def broadcast(self, message: str):
        for connection in list(self.active_connections.keys()):
            try:
                await connection.send_text(message)
            except:
                pass
                
    async def send_personal_message(self, message: str, websocket: WebSocket):
        try:
            await websocket.send_text(message)
        except:
            pass

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
            await websocket.send_text(json.dumps({"error": "Стол заполнен (9/9)"}))
            await websocket.close()
            return
            
        player_name = auth.get("name", "Аноним")
        manager.add_player(websocket, player_name)
        
        # ИСПРАВЛЕНИЕ: Отправляем новому игроку текущий список всех сидящих
        current_players = list(manager.active_connections.values())
        await websocket.send_text(json.dumps({
            "status": "auth_ok", 
            "players": current_players
        }))
        
        await manager.broadcast(json.dumps({"log": f"👋 {player_name} сел за стол ({len(manager.active_connections)}/{MAX_PLAYERS})."}))
        
        while True:
            data = await websocket.receive_text()
            action_data = json.loads(data)
            
            if "button" in action_data:
                action = action_data["button"]
                
                if action == "Deal":
                    players = list(manager.active_connections.items())
                    deck = get_deck()
                    
                    await manager.broadcast(json.dumps({"log": f"🎲 {player_name} раздает карты..."}))
                    
                    for i, (ws_conn, p_name) in enumerate(players):
                        pos = POSITIONS[i % len(POSITIONS)]
                        card1 = deck.pop()
                        card2 = deck.pop()
                        hand_msg = f"Раздача! Позиция: {pos} | Карты: {card1} {card2}"
                        await manager.send_personal_message(json.dumps({"log": hand_msg}), ws_conn)
                else:
                    await manager.broadcast(json.dumps({"log": f"🃏 {player_name}: {action}"}))
                    
    except WebSocketDisconnect:
        manager.remove_player(websocket)
        await manager.broadcast(json.dumps({"log": f"🚪 {player_name} покинул стол ({len(manager.active_connections)}/{MAX_PLAYERS})."}))

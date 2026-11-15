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
STARTING_STACK = 10000

RANKS = ['2', '3', '4', '5', '6', '7', '8', '9', 'T', 'J', 'Q', 'K', 'A']
SUITS = ['♠', '♥', '♦', '♣']
POSITIONS = ['SB', 'BB', 'UTG', 'EP', 'MP', 'LJ', 'HJ', 'CO', 'BTN']

def get_deck():
    deck = [f"{r}{s}" for r in RANKS for s in SUITS]
    random.shuffle(deck)
    return deck

class ConnectionManager:
    def __init__(self):
        self.players = {} 
        self.turn_order = [] 
        self.turn_index = 0
        self.game_in_progress = False
        self.deck = []

    async def connect(self, websocket: WebSocket, name: str):
        if name in self.players:
            # Если сокет еще жив — это реальный дубликат, не пускаем
            if self.players[name]["ws"] is not None:
                return "busy"
            # Если сокет мертв (вы сделали F5) — разрешаем переподключение
            self.players[name]["ws"] = websocket
            return "ok"
            
        if len(self.players) >= MAX_PLAYERS:
            return "full"
            
        self.players[name] = {"ws": websocket, "stack": STARTING_STACK, "cards": [], "pos": ""}
        self.turn_order.append(name)
        return "ok"

    def disconnect(self, name: str):
        if name in self.players:
            self.players[name]["ws"] = None

    async def broadcast(self, message: str):
        for data in self.players.values():
            if data["ws"]:
                try: await data["ws"].send_text(message)
                except: pass
                
    async def send_personal(self, name: str, message: str):
        ws = self.players.get(name, {}).get("ws")
        if ws:
            try: await ws.send_text(message)
            except: pass

    def get_current_turn_name(self):
        if not self.turn_order: return None
        if self.turn_index >= len(self.turn_order): self.turn_index = 0
        return self.turn_order[self.turn_index]

    def advance_turn(self):
        self.turn_index += 1
        if self.turn_index >= len(self.turn_order):
            self.turn_index = 0

    async def broadcast_state(self):
        players_info = [{"name": p, "stack": self.players[p]["stack"]} for p in self.turn_order]
        await self.broadcast(json.dumps({
            "players_update": players_info, 
            "active_turn": self.get_current_turn_name() if self.game_in_progress else None,
            "game_in_progress": self.game_in_progress
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
            
        player_name = auth.get("name", "Аноним").strip()
        
        result = await manager.connect(websocket, player_name)
        if result == "busy":
            await websocket.send_text(json.dumps({"error": "Это имя уже занято за столом!"}))
            await websocket.close()
            return
        elif result == "full":
            await websocket.send_text(json.dumps({"error": "Стол заполнен (9/9)"}))
            await websocket.close()
            return
            
        await websocket.send_text(json.dumps({"status": "auth_ok"}))
        await manager.broadcast(json.dumps({"log": f"👋 {player_name} в сети."}))
        await manager.broadcast_state()
        
        if manager.game_in_progress and manager.players[player_name]["cards"]:
            cards = manager.players[player_name]["cards"]
            pos = manager.players[player_name]["pos"]
            await manager.send_personal(player_name, json.dumps({
                "log": f"🔄 Возврат в игру! Позиция: {pos} | Карты: {cards[0]} {cards[1]}"
            }))
        
        while True:
            data = await websocket.receive_text()
            action_data = json.loads(data)
            
            if "button" in action_data:
                action = action_data["button"]
                
                if action == "Deal":
                    manager.game_in_progress = True
                    manager.turn_index = 0
                    manager.deck = get_deck()
                    
                    await manager.broadcast(json.dumps({"log": f"🎲 {player_name} раздает карты...", "event": "new_hand"}))
                    
                    for i, p_name in enumerate(manager.turn_order):
                        pos = POSITIONS[i % len(POSITIONS)]
                        card1 = manager.deck.pop()
                        card2 = manager.deck.pop()
                        
                        manager.players[p_name]["cards"] = [card1, card2]
                        manager.players[p_name]["pos"] = pos
                        
                        hand_msg = f"Раздача! Позиция: {pos} | Карты: {card1} {card2}"
                        await manager.send_personal(p_name, json.dumps({"log": hand_msg}))
                    
                    await manager.broadcast_state()
                    
                elif manager.game_in_progress:
                    if player_name == manager.get_current_turn_name():
                        await manager.broadcast(json.dumps({"log": f"🃏 {player_name}: {action}"}))
                        manager.advance_turn()
                        await manager.broadcast_state()
                    else:
                        await websocket.send_text(json.dumps({"log": "⚠️ Сейчас не ваш ход!"}))
                    
    except WebSocketDisconnect:
        manager.disconnect(player_name)
        await manager.broadcast(json.dumps({"log": f"📡 {player_name} временно отключился."}))
        await manager.broadcast_state()

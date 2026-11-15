from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import random
import json

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Колода и позиции
RANKS = ['2', '3', '4', '5', '6', '7', '8', '9', 'T', 'J', 'Q', 'K', 'A']
SUITS = ['♠', '♥', '♦', '♣']
POSITIONS = ['UTG', 'MP', 'CO', 'BTN', 'SB', 'BB']

def generate_hand():
    card1 = f"{random.choice(RANKS)}{random.choice(SUITS)}"
    card2 = f"{random.choice(RANKS)}{random.choice(SUITS)}"
    # Проверка, чтобы не раздать две одинаковые карты
    while card1 == card2:
        card2 = f"{random.choice(RANKS)}{random.choice(SUITS)}"
    return card1, card2, random.choice(POSITIONS)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            # 1. Генерируем новую раздачу
            card1, card2, pos = generate_hand()
            
            # 2. Отправляем игроку вопрос
            await websocket.send_text(f"🎲 Раздача! Позиция: {pos} | Карты: {card1} {card2}")
            
            # 3. Ждем нажатия кнопки от фронтенда
            data = await websocket.receive_text()
            action = json.loads(data).get("button")
            
            # 4. Базовая заглушка оценки (пока без привязки к реальным чартам)
            if action == "Fold":
                feedback = "✅ Пас принят (Безопасное решение)."
            elif action == "Raise":
                feedback = "🔥 Рейз! (Агрессивно. Проверим по чарту позже)."
            else:
                feedback = "🤔 Колл (Требует осторожности)."
                
            # 5. Отправляем результат и черту-разделитель
            await websocket.send_text(f"👉 Ваш ход: {action}. {feedback}")
            await websocket.send_text("—" * 20)
            
    except WebSocketDisconnect:
        print("Клиент отключился")

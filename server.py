import os
import random
import uuid
from typing import Dict, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="Wordle API Server")

# 目前 client 是桌面程式，不受瀏覽器 CORS 限制。若日後改成網頁，
# 再把 allow_origins 限定為實際前端網址。
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
WORD_BANK = [
    "APPLE", "TRAIN", "HOUSE", "PLANT", "SMART", "WORLD", "LIGHT", "BRAIN", "CLOUD", "WATER",
    "ABOUT", "ABOVE", "ACTOR", "ACUTE", "ADMIT", "ADOPT", "ADULT", "AFTER", "AGAIN", "AGENT",
    "AGREE", "AHEAD", "ALARM", "ALBUM", "ALERT", "ALIEN", "ALIKE", "ALIVE", "ALLOW", "ALONE",
    "ALONG", "ALTER", "AMONG", "ANGER", "ANGLE", "ANGRY", "APART", "APPLY", "ARGUE", "ARISE",
    "ARRAY", "ARROW", "ASIDE", "ASSET", "AUDIO", "AUDIT", "AVOID", "AWAKE", "AWARE", "BADGE",
    "BAKER", "BASIC", "BASIS", "BEACH", "BEGIN", "BEING", "BELOW", "BENCH", "BLACK", "BLAME",
    "BLANK", "BLAST", "BLEED", "BLEND", "BLOCK", "BLOOD", "BOARD", "BOAST", "BONUS", "BOOST",
    "BOUND", "BREAD", "BREAK", "BRICK", "BRIEF", "BRING", "BROAD", "BROWN", "BRUSH", "BUILD",
    "BUNCH", "BUYER", "CABLE", "CANDY", "CARGO", "CARRY", "CATCH", "CAUSE", "CHAIN", "CHAIR",
    "CHALK", "CHARM", "CHART", "CHASE", "CHEAP", "CHECK", "CHEST", "CHIEF", "CHILD", "CHOSE",
    "CIVIL", "CLAIM", "CLASS", "CLEAN", "CLEAR", "CLIMB", "CLOCK", "CLOSE", "COACH", "COAST",
    "COUNT", "COURT", "COVER", "CRASH", "CREAM", "CRIME", "CROSS", "CROWD", "CROWN", "CURVE",
    "CYCLE", "DAILY", "DANCE", "DEATH", "DELAY", "DEPTH", "DRAFT", "DRAMA", "DREAM", "DRIVE",
    "EAGLE", "EARLY", "EARTH", "EIGHT", "EMPTY", "ENEMY", "ENJOY", "ENTER", "EQUAL", "ERROR",
    "EVENT", "EVERY", "EXACT", "EXIST", "FAITH", "FALSE", "FAULT", "FIELD", "FIGHT", "FINAL",
    "FIRST", "FLAME", "FLASH", "FLOAT", "FLOOR", "FLOUR", "FLUID", "FOCUS", "FORCE", "FORTH",
    "FORTY", "FORUM", "FRAME", "FRESH", "FRONT", "FRUIT", "GIANT", "GLASS", "GLOBE", "GRACE",
    "GRADE", "GRAND", "GRANT", "GRASS", "GREAT", "GREEN", "GROUP", "GUARD", "GUESS", "GUIDE",
    "HAPPY", "HEART", "HEAVY", "HOTEL", "HUMAN", "IMAGE", "INDEX", "INPUT", "ISSUE", "JUDGE",
    "KNIFE", "LAYER", "LEMON", "LEVEL", "LIMIT", "LUNCH", "MAGIC", "MAJOR", "MARCH", "MATCH",
    "MEDAL", "MONEY", "MONTH", "MUSIC", "NIGHT", "NOVEL", "NURSE", "OCEAN", "OFFER", "ORDER"
]

MAX_ATTEMPTS = 6

# 記憶體儲存遊戲狀態：
# {game_id: {"target": "APPLE", "status": "PLAYING", "attempts": 0,
#            "hard_mode": False, "greens": {0: "A"}}}
games_db: Dict[str, dict] = {}

# 任務三：全域戰績統計（一局結束時才計入：猜中或用完 6 次）
stats = {"total_games": 0, "wins": 0}


class NewGameRequest(BaseModel):
    # 任務四：是否開啟硬核模式，預設 False
    hard_mode: bool = False


class GuessRequest(BaseModel):
    game_id: str
    guess: str


def get_stats_data():
    """ 計算目前的總局數、勝場與勝率（百分比，取到小數第一位） """
    total = stats["total_games"]
    wins = stats["wins"]
    win_rate = round(wins / total * 100, 1) if total > 0 else 0.0
    return {"total_games": total, "wins": wins, "win_rate": win_rate}


@app.post("/api/new-game")
def start_new_game(req: Optional[NewGameRequest] = None):
    """ 建立新一局遊戲，回傳 game_id（可選擇是否開啟 Hard Mode） """
    hard_mode = req.hard_mode if req else False
    game_id = str(uuid.uuid4())
    target_word = random.choice(WORD_BANK)
    games_db[game_id] = {
        "target": target_word,
        "status": "PLAYING",
        "attempts": 0,
        "hard_mode": hard_mode,
        "greens": {}  # 已確認的綠色位置 {位置: 字母}
    }
    return {"game_id": game_id, "hard_mode": hard_mode, "message": "New game started!"}


@app.get("/api/stats")
def get_stats():
    """ 任務三：回傳總遊玩局數、獲勝局數與勝率 """
    return get_stats_data()


@app.post("/api/guess")
def process_guess(req: GuessRequest):
    """ 接收玩家猜測，比對答案並回傳顏色結果 """
    game_id = req.game_id
    guess = req.guess.upper()

    if game_id not in games_db:
        raise HTTPException(status_code=404, detail="Game session not found.")

    game = games_db[game_id]

    if game["status"] != "PLAYING":
        raise HTTPException(status_code=400, detail="Game is already over. Start a new game.")

    if len(guess) != 5 or not guess.isalpha():
        raise HTTPException(status_code=400, detail="Word must be 5 letters.")

    # 任務二：字典檢查（在計算次數之前，不合法的字不消耗次數）
    if guess not in WORD_BANK:
        raise HTTPException(status_code=400, detail="Word not in dictionary")

    # 任務四：Hard Mode 驗證，已確認的綠色字母必須留在原位置
    if game["hard_mode"]:
        for pos, letter in game["greens"].items():
            if guess[pos] != letter:
                raise HTTPException(
                    status_code=400,
                    detail="Hard Mode: Must use revealed hint at green position"
                )

    target = game["target"]
    feedback = ["absent"] * 5  # 預設灰色 absent
    target_letter_counts = {}

    # 1. 先計算目標單字的各字母數量
    for char in target:
        target_letter_counts[char] = target_letter_counts.get(char, 0) + 1

    # 2. 標記綠色 correct
    for i in range(5):
        if guess[i] == target[i]:
            feedback[i] = "correct"
            target_letter_counts[guess[i]] -= 1

    # 3. 標記黃色 present
    for i in range(5):
        if feedback[i] != "correct" and guess[i] in target:
            if target_letter_counts[guess[i]] > 0:
                feedback[i] = "present"
                target_letter_counts[guess[i]] -= 1

    # 通過所有檢查，才算一次有效猜測
    game["attempts"] += 1

    # 記錄新出現的綠色位置（給 Hard Mode 使用）
    for i in range(5):
        if feedback[i] == "correct":
            game["greens"][i] = guess[i]

    # 檢查是否過關 / 是否用完次數
    is_correct = (guess == target)
    if is_correct:
        game["status"] = "WON"
        stats["total_games"] += 1
        stats["wins"] += 1
    elif game["attempts"] >= MAX_ATTEMPTS:
        game["status"] = "LOST"
        stats["total_games"] += 1

    game_over = game["status"] != "PLAYING"

    return {
        "guess": guess,
        "feedback": feedback,  # 例如: ["correct", "present", "absent", "absent", "correct"]
        "is_correct": is_correct,
        "game_over": game_over,
        "attempts": game["attempts"],
        "remaining": MAX_ATTEMPTS - game["attempts"],
        # 任務一：遊戲結束（猜中或第 6 次猜錯）才揭曉答案，否則為 None
        "target_word": target if game_over else None,
        "stats": get_stats_data()
    }


if __name__ == "__main__":
    import uvicorn
    # Render 會透過 PORT 環境變數指定服務埠；本機則預設使用 8000。
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)

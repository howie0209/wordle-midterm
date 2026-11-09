import sys
import os
import pygame
import requests

# 桌面 client 在本機執行，透過這個網址呼叫雲端 FastAPI server。
# 本機測試用 127.0.0.1；部署到 Render 後改成下面那行（任務五）。
API_BASE_URL = "https://wordle-midterm.onrender.com"
#API_BASE_URL = "http://127.0.0.1:8000"

# 顏色定義
COLOR_BG = (18, 18, 19)
COLOR_TEXT = (255, 255, 255)
COLOR_EMPTY = (58, 58, 60)
COLOR_CORRECT = (83, 141, 78)   # 綠色
COLOR_PRESENT = (181, 159, 59)  # 黃色
COLOR_ABSENT = (58, 58, 60)     # 灰色
COLOR_DIVIDER = (90, 90, 90)    # 側邊欄分隔線
COLOR_HARD = (230, 90, 90)      # Hard Mode 文字顏色

MAX_ATTEMPTS = 6

pygame.init()
# 任務三：視窗寬度 500 -> 700，左側 0~500 為遊戲區，右側 500~700 為歷史紀錄側邊欄
WIDTH, HEIGHT = 700, 650
GRID_AREA_WIDTH = 500
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Pygame Wordle + FastAPI Client")
font = pygame.font.SysFont("Arial", 36, bold=True)
small_font = pygame.font.SysFont("Arial", 18)
mini_font = pygame.font.SysFont("Arial", 16, bold=True)

NETWORK_ERRORS = (requests.exceptions.RequestException, ValueError, KeyError, IndexError, TypeError)


class WordleGame:
    def __init__(self):
        self.game_id = None
        self.hard_mode = False
        self.stats = {"total_games": 0, "wins": 0, "win_rate": 0.0}
        self.reset_board()
        self.message = "ENTER: submit | R: restart | H: hard mode"
        self.start_new_game()

    def reset_board(self):
        """ 清空棋盤與本局歷史紀錄 """
        self.grid = [["" for _ in range(5)] for _ in range(6)]
        self.colors = [[COLOR_EMPTY for _ in range(5)] for _ in range(6)]
        self.history = []  # 任務三：本局猜過的單字 [(word, [color x5]), ...]
        self.row = 0
        self.col = 0
        self.game_over = False

    def start_new_game(self):
        """ 向 FastAPI 伺服器請求建立新的一局 """
        try:
            # Render 免費服務休眠後，第一次請求可能需要較久才會喚醒。
            payload = {"hard_mode": self.hard_mode}
            res = requests.post(f"{API_BASE_URL}/api/new-game", json=payload, timeout=60)
            if res.status_code == 200:
                self.game_id = res.json()["game_id"]
                self.reset_board()
                mode_text = "HARD" if self.hard_mode else "Normal"
                self.message = f"New game started! ({mode_text} mode)"
                self.fetch_stats()
            else:
                self.message = "Server error starting new game."
        except NETWORK_ERRORS:
            self.message = "Cannot connect to FastAPI server!"

    def fetch_stats(self):
        """ 任務三：向後端取得戰績統計 """
        try:
            res = requests.get(f"{API_BASE_URL}/api/stats", timeout=60)
            if res.status_code == 200:
                self.stats = res.json()
        except NETWORK_ERRORS:
            pass  # 統計抓不到不影響遊戲進行

    @staticmethod
    def get_error_detail(res):
        """ 安全地取出後端錯誤訊息，避免非 JSON 回應造成崩潰 """
        try:
            detail = res.json().get("detail")
        except (ValueError, AttributeError):
            detail = None
        if isinstance(detail, str):
            return detail
        return f"Error processing guess (HTTP {res.status_code})"

    def submit_guess(self):
        """ 將當前行單字發送至 FastAPI 驗證 """
        if self.game_id is None:
            self.message = "No game session. Press R to retry."
            return

        if self.col < 5:
            self.message = "Not enough letters!"
            return

        guess_word = "".join(self.grid[self.row])
        try:
            payload = {"game_id": self.game_id, "guess": guess_word}
            res = requests.post(f"{API_BASE_URL}/api/guess", json=payload, timeout=60)

            if res.status_code == 200:
                data = res.json()
                feedback = data["feedback"]

                # 依據後端回傳更新格子顏色
                for i in range(5):
                    if feedback[i] == "correct":
                        self.colors[self.row][i] = COLOR_CORRECT
                    elif feedback[i] == "present":
                        self.colors[self.row][i] = COLOR_PRESENT
                    else:
                        self.colors[self.row][i] = COLOR_ABSENT

                # 任務三：加入側邊欄歷史紀錄
                self.history.append((guess_word, list(self.colors[self.row])))

                if isinstance(data.get("stats"), dict):
                    self.stats = data["stats"]

                if data["is_correct"]:
                    self.message = "Congratulations! You won! Press R to restart."
                    self.game_over = True
                else:
                    self.row += 1
                    self.col = 0
                    if data.get("game_over") or self.row >= MAX_ATTEMPTS:
                        # 任務一：顯示後端揭曉的正確答案
                        target = data.get("target_word") or "?????"
                        self.message = f"Game Over! The word was {target}. Press R to restart."
                        self.game_over = True
                    else:
                        # 任務一：剩餘次數提示
                        tries_left = MAX_ATTEMPTS - self.row
                        self.message = f"Keep guessing! ({tries_left} tries left)"
            elif res.status_code == 400:
                detail = self.get_error_detail(res)
                if detail == "Word not in dictionary":
                    # 任務二：不在字典中
                    self.message = "Not in word list!"
                else:
                    # 例如 Hard Mode 違規訊息
                    self.message = detail
                # 不增加 self.row、不清除字母，玩家可用 Backspace 修改
            else:
                self.message = self.get_error_detail(res)
        except NETWORK_ERRORS:
            self.message = "Network error during guess!"

    def handle_keydown(self, event):
        # R / H 在「遊戲結束」或「這一行還沒輸入字母」時當指令用；
        # 正在輸入單字時則當成字母（例如 TRAIN、WORLD）。按住 Shift 一定是輸入字母。
        is_command_key = (
            event.key in (pygame.K_r, pygame.K_h)
            and not (event.mod & pygame.KMOD_SHIFT)
            and (self.game_over or self.col == 0)
        )
        if is_command_key:
            if event.key == pygame.K_h:
                # 任務四：切換硬核模式並重新開始一局
                self.hard_mode = not self.hard_mode
            self.start_new_game()
            return

        if self.game_over:
            return

        if event.key == pygame.K_BACKSPACE:
            if self.col > 0:
                self.col -= 1
                self.grid[self.row][self.col] = ""
        elif event.key == pygame.K_RETURN:
            self.submit_guess()
        elif event.unicode.isalpha() and len(event.unicode) == 1:
            if self.col < 5:
                self.grid[self.row][self.col] = event.unicode.upper()
                self.col += 1

    def draw_sidebar(self, surface):
        """ 任務三：右側歷史紀錄側邊欄 """
        pygame.draw.line(surface, COLOR_DIVIDER, (GRID_AREA_WIDTH, 60), (GRID_AREA_WIDTH, HEIGHT), 2)

        title_surface = small_font.render("History", True, COLOR_TEXT)
        surface.blit(title_surface, (GRID_AREA_WIDTH + 20, 75))

        box_size = 26
        gap = 4
        row_width = 5 * box_size + 4 * gap
        start_x = GRID_AREA_WIDTH + (WIDTH - GRID_AREA_WIDTH - row_width) // 2

        for idx, (word, row_colors) in enumerate(self.history):
            y = 110 + idx * (box_size + 10)
            for c in range(5):
                x = start_x + c * (box_size + gap)
                rect = pygame.Rect(x, y, box_size, box_size)
                pygame.draw.rect(surface, row_colors[c], rect, border_radius=3)
                letter_surface = mini_font.render(word[c], True, COLOR_TEXT)
                surface.blit(letter_surface, letter_surface.get_rect(center=rect.center))

    def draw_status(self, surface):
        """ 右上角：戰績統計（任務三）與目前模式（任務四） """
        total = self.stats.get("total_games", 0)
        wins = self.stats.get("wins", 0)
        rate = self.stats.get("win_rate", 0)
        stats_text = f"Total: {total} | Wins: {wins} | Win Rate: {rate:g}%"
        stats_surface = small_font.render(stats_text, True, COLOR_TEXT)
        surface.blit(stats_surface, stats_surface.get_rect(topright=(WIDTH - 10, 8)))

        if self.hard_mode:
            mode_surface = small_font.render("Mode: HARD", True, COLOR_HARD)
        else:
            mode_surface = small_font.render("Mode: Normal", True, COLOR_TEXT)
        surface.blit(mode_surface, mode_surface.get_rect(topright=(WIDTH - 10, 30)))

    def draw(self, surface):
        surface.fill(COLOR_BG)
        # 繪製 6x5 網格
        margin_x, margin_y = 75, 50
        box_size = 60
        gap = 10

        for r in range(6):
            for c in range(5):
                x = margin_x + c * (box_size + gap)
                y = margin_y + r * (box_size + gap)
                rect = pygame.Rect(x, y, box_size, box_size)

                # 畫背景框
                pygame.draw.rect(surface, self.colors[r][c], rect, border_radius=4)
                if self.colors[r][c] == COLOR_EMPTY:
                    pygame.draw.rect(surface, (80, 80, 80), rect, width=2, border_radius=4)

                # 畫字母
                char = self.grid[r][c]
                if char:
                    text_surface = font.render(char, True, COLOR_TEXT)
                    text_rect = text_surface.get_rect(center=rect.center)
                    surface.blit(text_surface, text_rect)

        self.draw_sidebar(surface)
        self.draw_status(surface)

        # 畫底部提示訊息（置中於左側遊戲區）
        msg_surface = small_font.render(self.message, True, COLOR_TEXT)
        msg_rect = msg_surface.get_rect(center=(GRID_AREA_WIDTH // 2, HEIGHT - 40))
        surface.blit(msg_surface, msg_rect)


def main():
    clock = pygame.time.Clock()
    game = WordleGame()

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            elif event.type == pygame.KEYDOWN:
                game.handle_keydown(event)

        game.draw(screen)
        pygame.display.flip()
        clock.tick(30)

if __name__ == "__main__":
    main()

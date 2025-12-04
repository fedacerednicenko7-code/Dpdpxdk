# meta developer: @YourNick
# meta banner: https://i.imgur.com/7RFlWvC.png

from .. import loader, utils
import asyncio, json, random, math, time
from telethon import Button

# ============================================================
#                       DATA STRUCTURES
# ============================================================

class Piece:
    __slots__ = ("color", "king")

    def __init__(self, color, king=False):
        self.color = color
        self.king = king

    def copy(self):
        return Piece(self.color, self.king)

    def __repr__(self):
        return f"{self.color.upper() if self.king else self.color}"


class Move:
    __slots__ = ("src", "dst", "capture")

    def __init__(self, src, dst, capture=None):
        self.src = src
        self.dst = dst
        self.capture = capture

    def __repr__(self):
        return f"{self.src}->{self.dst}" + (f"x{self.capture}" if self.capture else "")


# ============================================================
#                   CHECKERS GAME LOGIC ENGINE
# ============================================================

class CheckersGame:
    def __init__(self):
        self.board = self.make_board()
        self.turn = "w"
        self.history = []
        self.must_capture = False
        self.wins = None
        self.multi_capture_path = None

    def make_board(self):
        board = {}
        for y in range(8):
            for x in range(8):
                cell = chr(97+x) + str(8-y)
                if (x+y) % 2 == 1:
                    if y < 3:
                        board[cell] = Piece("b")
                    elif y > 4:
                        board[cell] = Piece("w")
                    else:
                        board[cell] = None
                else:
                    board[cell] = None
        return board

    def inside(self, x, y): return 0 <= x < 8 and 1 <= y <= 8
    def get(self, coord): return self.board.get(coord)

    def moves_for_piece(self, coord):
        p = self.get(coord)
        if not p:
            return []
        dirs = []
        if p.king:
            dirs = [(1,1),(1,-1),(-1,1),(-1,-1)]
        else:
            dirs = [(1,1),(-1,1)] if p.color=="b" else [(1,-1),(-1,-1)]

        x = ord(coord[0])-97
        y = int(coord[1])
        moves = []
        captures = []

        for dx,dy in dirs:
            nx, ny = x+dx, y+dy
            if self.inside(nx,ny):
                c = chr(97+nx)+str(ny)
                if self.get(c) is None:
                    moves.append(Move(coord,c))
                else:
                    if self.get(c).color != p.color:
                        nx2,ny2 = nx+dx, ny+dy
                        if self.inside(nx2,ny2):
                            d = chr(97+nx2)+str(ny2)
                            if self.get(d) is None:
                                captures.append(Move(coord,d,capture=c))

        return captures if captures else moves

    def all_moves(self):
        moves = []
        caps = []
        for cell,p in self.board.items():
            if p and p.color == self.turn:
                m = self.moves_for_piece(cell)
                for mv in m:
                    if mv.capture:
                        caps.append(mv)
                    else:
                        moves.append(mv)
        return caps if caps else moves

    def apply(self, mv):
        p = self.board[mv.src]
        self.board[mv.src] = None
        self.board[mv.dst] = p

        if mv.capture:
            self.board[mv.capture] = None

        if not p.king:
            if p.color == "w" and mv.dst.endswith("1"):
                p.king = True
            if p.color == "b" and mv.dst.endswith("8"):
                p.king = True

        self.history.append(mv)

    def move(self, src, dst):
        if self.wins: return False, "Игра завершена."
        allm = self.all_moves()
        for mv in allm:
            if mv.src == src and mv.dst == dst:
                self.apply(mv)

                if mv.capture:
                    next_caps = [m for m in self.moves_for_piece(dst) if m.capture]
                    if next_caps:
                        return True, "multi"

                self.turn = "b" if self.turn=="w" else "w"

                if not self.all_moves():
                    self.wins = self.turn
                    return True, "win"

                return True, "ok"

        return False, "Недопустимый ход."

    def ascii_board(self):
        s = "   a b c d e f g h\n"
        for y in range(8):
            row = str(8-y)+"  "
            for x in range(8):
                c = chr(97+x)+str(8-y)
                p = self.board[c]
                if not p:
                    row += "· "
                else:
                    if p.color=="w":
                        row += ("W " if p.king else "○ ")
                    else:
                        row += ("B " if p.king else "● ")
            s += row+"\n"
        return s


# ============================================================
#                   INLINE BOARD RENDERING
# ============================================================

class InlineBoard:
    def __init__(self, game: CheckersGame):
        self.game = game
        self.selected = None
        self.moves = []

    def set_selected(self, cell):
        self.selected = cell
        if cell:
            self.moves = self.game.moves_for_piece(cell)
        else:
            self.moves = []

    def render(self):
        rows = []
        for y in range(8):
            row = []
            for x in range(8):
                c = chr(97+x)+str(8-y)
                p = self.game.get(c)
                text = "⬛" if (x+y)%2 else "⬜"

                if p:
                    if p.color=="w":
                        text = "♔" if p.king else "⚪"
                    else:
                        text = "♚" if p.king else "⚫"

                if self.selected == c:
                    text = "🟦"

                for mv in self.moves:
                    if mv.dst == c:
                        text = "🟩"

                row.append(Button.inline(text, data=("mv:"+c).encode()))
            rows.append(row)

        turn = "⚪ белые" if self.game.turn=="w" else "⚫ чёрные"
        rows.append([Button.inline(f"Ход: {turn}", data=b"noop")])
        rows.append([Button.inline("Отмена хода", data=b"undo")])
        rows.append([Button.inline("Сдаться", data=b"resign")])
        return rows


# ============================================================
#                     MAIN MODULE CLASS
# ============================================================

class CheckersMod(loader.Module):
    strings = {"name": "CheckersPro"}

    def __init__(self):
        self.games = {}
        self.inline_states = {}
        self.ratings = {}
        self.config = loader.ModuleConfig(
            loader.ConfigValue("autosave", True)
        )

    # STORAGE
    def save_all(self):
        if not self.config["autosave"]:
            return
        try:
            data = {"ratings": self.ratings}
            with open("checkers_data.json","w",encoding="utf8") as f:
                json.dump(data,f)
        except:
            pass

    def load_all(self):
        try:
            with open("checkers_data.json","r",encoding="utf8") as f:
                data = json.load(f)
            self.ratings = data.get("ratings",{})
        except:
            pass

    async def client_ready(self, client, db):
        self.client = client
        self.load_all()

    # INLINE INIT
    async def inline__start_game(self, call, chat_id):
        g = CheckersGame()
        self.games[chat_id] = g
        ui = InlineBoard(g)
        self.inline_states[chat_id] = ui
        await call.edit(g.ascii_board(), buttons=ui.render())

    @loader.inline_handler()
    async def inline_handler(self, query):
        return {
            "title": "Шашки",
            "description": "Начать игру",
            "content": self.inline_init,
        }

    async def inline_init(self, call):
        chat_id = call.from_id
        return await self.inline__start_game(call, chat_id)

    # INLINE CALLBACKS
    @loader.raw_handler()
    async def raw_handler(self, update, *args):
        if not hasattr(update, "data"):
            return

        d = update.data
        if d == b"noop":
            return
        if d == b"undo":
            return await self.cb_undo(update)
        if d == b"resign":
            return await self.cb_resign(update)
        if d == b"new":
            return await self.raw_newgame(update)
        if d.startswith(b"mv:"):
            c = d.decode().split(":")[1]
            return await self.cb_click_cell(update, c)

    async def cb_click_cell(self, call, cell):
        chat = call.peer_id.user_id
        g = self.games.get(chat)
        if not g:
            return

        ui = self.inline_states[chat]

        if ui.selected is None:
            p = g.get(cell)
            if p and p.color == g.turn:
                ui.set_selected(cell)
                return await call.edit(g.ascii_board(), buttons=ui.render())
            return await call.answer("Не твоя шашка")

        src = ui.selected
        ok, st = g.move(src, cell)
        if not ok:
            return await call.answer("Неверный ход.")

        if st == "multi":
            ui.set_selected(cell)
        else:
            ui.set_selected(None)

        if st == "win":
            w = "⚪ белые" if g.wins=="w" else "⚫ чёрные"
            return await call.edit(
                f"🏁 Победа: {w}\n\n{g.ascii_board()}",
                buttons=[[Button.inline("Новая игра", data=b"new")]]
            )

        await call.edit(g.ascii_board(), buttons=ui.render())

    async def cb_undo(self, call):
        chat = call.peer_id.user_id
        g = self.games.get(chat)
        if not g or not g.history:
            return await call.answer("Нет ходов.")

        mv = g.history.pop()
        p = g.get(mv.dst)
        g.board[mv.dst] = None
        g.board[mv.src] = p

        if mv.capture:
            opp = "w" if p.color=="b" else "b"
            g.board[mv.capture] = Piece(opp)

        g.turn = "b" if g.turn=="w" else "w"
        self.inline_states[chat].set_selected(None)
        await call.edit(g.ascii_board(), buttons=self.inline_states[chat].render())

    async def cb_resign(self, call):
        chat = call.peer_id.user_id
        g = self.games.get(chat)
        if not g:
            return

        loser = g.turn
        winner = "b" if loser=="w" else "w"
        g.wins = winner

        wtxt = "⚪ белые" if winner=="w" else "⚫ чёрные"
        await call.edit(
            f"Игрок сдался!\nПобедили: {wtxt}\n\n{g.ascii_board()}",
            buttons=[[Button.inline("Новая игра", data=b"new")]]
        )

    # NEW GAME
    async def raw_newgame(self, call):
        chat = call.peer_id.user_id
        g = CheckersGame()
        self.games[chat] = g
        ui = InlineBoard(g)
        self.inline_states[chat] = ui
        await call.edit(g.ascii_board(), buttons=ui.render())

    # FINAL STORAGE
    async def on_unload(self):
        self.save_all()
    async def on_restart(self):
        self.save_all()
    async def on_shutdown(self):
        self.save_all()


# END
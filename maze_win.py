"""迷宫小游戏 — Windows 风格桌面版（pygame 自绘界面）

浅色系统风：菜单栏 / 工具栏 / 白底画布 / 状态栏，自绘 Windows 控件外观。
引擎复用 maze_game.py 的生成、BFS 校验与移动逻辑；不依赖其暗色渲染。
所有界面尺寸与字号按系统 DPI 等比缩放，1:1 物理像素绘制，不糊。
用法：python maze_win.py
"""

import os
import random
import sys

os.environ.setdefault("SDL_WINDOWS_DPI_SCALING", "0")   # 关闭 SDL 缩放，自己按 DPI 排布
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import maze_game as engine

# ---- 配色（浅色系统风）------------------------------------------------

APP_BG = (243, 243, 243)
MENU_BG = (245, 245, 245)
MENU_LINE = (220, 220, 220)
MENU_TEXT = (31, 31, 31)
MENU_HOVER = (229, 241, 251)
MENU_SELECTED = (204, 232, 255)

TOOL_BG = (249, 249, 249)
BTN_BG = (253, 253, 253)
BTN_BORDER = (173, 173, 173)
BTN_HOVER = (229, 241, 251)
BTN_TEXT = (31, 31, 31)

ACCENT = (26, 115, 232)
ACCENT_TEXT = (255, 255, 255)

CANVAS_BG = (255, 255, 255)
GROUND_LINE = (218, 220, 224)
TRAIL_C = (232, 240, 254)
WALL_C = (74, 74, 74)
START_C = (30, 142, 62)
EXIT_C = (217, 48, 37)
PLAYER_C = (26, 115, 232)

STATUS_BG = (240, 240, 240)
STATUS_LINE = (208, 208, 208)
STATUS_TEXT = (51, 51, 51)
HINT_TEXT = (95, 99, 104)
SHORTCUT_TEXT = (118, 118, 118)
PANEL_TEXT = (60, 64, 67)
PANEL_TITLE = (31, 31, 31)

# ---- 设计基准尺寸（逻辑像素，运行时按 DPI 乘系数）----------------------

BASE_MENU_H = 30
BASE_TOOL_H = 52
BASE_STATUS_H = 28
BASE_W = 760
BASE_H = 820

TITLE = "迷宫小游戏"
COPYRIGHT = "© 2026 小虫　保留所有权利"

KEY_DIRS = {
    "up": 0, "w": 0,
    "right": 1, "d": 1,
    "down": 2, "s": 2,
    "left": 3, "a": 3,
}
LEVEL_KEYS = {"1": 1, "2": 2, "3": 3}

_FONTS = {}
_TEXTS = {}


def dpi_scale() -> float:
    """系统 DPI 相对 96 的倍率；拿不到时按 1.0 处理。"""
    try:
        from ctypes import windll
        return max(1.0, min(3.0, windll.user32.GetDpiForSystem() / 96.0))
    except Exception:
        return 1.0


def work_area():
    """桌面可用区域（扣除任务栏），用于限制初始窗口不超出屏幕。"""
    try:
        from ctypes import byref, windll, wintypes
        r = wintypes.RECT()
        windll.user32.SystemParametersInfoW(0x0030, 0, byref(r), 0)
        return max(640, r.right - r.left), max(480, r.bottom - r.top)
    except Exception:
        return 1536, 864


def resource_path(name: str) -> str:
    """打包后资源在 _MEIPASS，开发时在脚本目录。"""
    base = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, name)


def font(size: int, bold: bool = False):
    """按字号与粗细缓存字体，直接加载系统字体文件以拿到中文字形。"""
    key = (size, bold)
    cached = _FONTS.get(key)
    if cached is not None:
        return cached
    result = None
    for path in engine._font_file_candidates():
        if not os.path.exists(path):
            continue
        try:
            f = pygame.font.Font(path, size)
            f.set_bold(bold)
            result = f
            break
        except Exception:
            continue
    if result is None:
        result = pygame.font.Font(None, size)
        result.set_bold(bold)
    _FONTS[key] = result
    return result


def text(txt: str, size: int, color, bold: bool = False):
    """渲染文字并缓存，同一文案每帧复用同一张 Surface。"""
    key = (txt, size, color, bold)
    cached = _TEXTS.get(key)
    if cached is None:
        cached = font(size, bold).render(txt, True, color)
        _TEXTS[key] = cached
    return cached


class MazeWin:
    def __init__(self):
        pygame.init()

        self.s = dpi_scale()
        self.menu_h = int(BASE_MENU_H * self.s)
        self.tool_h = int(BASE_TOOL_H * self.s)
        self.status_h = int(BASE_STATUS_H * self.s)

        area_w, area_h = work_area()
        win_w = min(int(BASE_W * self.s), area_w - int(24 * self.s))
        win_h = min(int(BASE_H * self.s), area_h - int(48 * self.s))
        self.screen = pygame.display.set_mode((win_w, win_h), pygame.RESIZABLE)
        self.min_w = int(560 * self.s)
        self.min_h = int(620 * self.s)

        icon = resource_path("maze_icon.png")
        if os.path.exists(icon):
            try:
                pygame.display.set_icon(pygame.image.load(icon))
            except Exception:
                pass

        self.clock = pygame.time.Clock()
        self.rng = random.Random()
        self.level = engine.DEFAULT_DIFF_LEVEL
        self.walls = None
        self.player = [0, 0]
        self.won = False
        self.visited = set()
        self.overlay = None            # None | "win" | "help" | "about"
        self.open_menu = None          # None | "file" | "difficulty" | "help"
        self.hover = None
        self.overlay_buttons = []
        self.cell = 24
        self.wall_w = 3
        self.ox = self.oy = 0
        self.static = None
        self.menu_rects = {}
        self.tool_rects = {}
        self.dropdown_rect = None
        self.dropdown_items = []

        self._apply_caption()
        self.new_game()
        if os.environ.get("MAZE_DEMO") == "win":   # 仅自测：启动即进胜利态，验证面板
            self.player = [engine.EXIT[0], engine.EXIT[1]]
            self.won = True
            self.overlay = "win"

    # ---- 尺寸与文字工具 -------------------------------------------------

    def px(self, value: float) -> int:
        """设计像素 → 物理像素。"""
        return int(round(value * self.s))

    def fs(self, value: float) -> int:
        """设计字号 → 物理字号（不小于 9，避免高 DPI 下过小）。"""
        return max(9, int(round(value * self.s)))

    # ---- 状态 -----------------------------------------------------------

    def _level_name(self) -> str:
        return engine.DIFFICULTIES[self.level][0]

    def _level_ratio(self) -> float:
        return engine.DIFFICULTIES[self.level][1]

    def _apply_caption(self) -> None:
        pygame.display.set_caption(f"{TITLE} — {self._level_name()}")

    def set_level(self, lv: int) -> None:
        if lv in engine.DIFFICULTIES:
            self.level = lv
            self._apply_caption()
            self.new_game()

    def new_game(self) -> None:
        self.walls = engine.generate_maze(engine.COLS, engine.ROWS,
                                          self.rng, self._level_ratio())
        self.player = [engine.START[0], engine.START[1]]
        self.won = False
        self.overlay = None
        self.visited = {engine.START[0] * engine.COLS + engine.START[1]}
        self.rebuild_static()

    # ---- 布局 -----------------------------------------------------------

    def canvas_rect(self):
        h = self.screen.get_height()
        top = self.menu_h + self.tool_h
        return pygame.Rect(0, top, self.screen.get_width(),
                           max(1, h - top - self.status_h))

    def rebuild_static(self) -> None:
        """把墙 + 起终点 + 地面边框预渲染成一张透明 Surface。

        透明层叠在轨迹之上：一次 blit 就能同时压住轨迹又保留墙面，
        不必每帧重画几百条墙线。仅换局或改窗口尺寸时重建。
        """
        area = self.canvas_rect()
        cols, rows = engine.COLS, engine.ROWS
        margin = self.px(14)
        self.cell = max(10, min((area.w - 2 * margin) // cols,
                                (area.h - 2 * margin) // rows))
        self.wall_w = max(2, int(round(self.cell * 0.10)))
        half = self.wall_w // 2
        maze_w, maze_h = self.cell * cols, self.cell * rows
        self.ox = area.x + (area.w - maze_w) // 2 + half
        self.oy = area.y + (area.h - maze_h) // 2 + half
        self.ground_rect = pygame.Rect(self.ox - half, self.oy - half,
                                       maze_w + 2 * half, maze_h + 2 * half)
        self.rebuild_ver = getattr(self, "rebuild_ver", 0) + 1

        surf = pygame.Surface((area.w, area.h), pygame.SRCALPHA)
        pygame.draw.rect(surf, GROUND_LINE,
                         self.ground_rect.move(-area.x, -area.y), width=1)

        for i, w in enumerate(self.walls):
            r, c = divmod(i, cols)
            x = self.ox - area.x + c * self.cell
            y = self.oy - area.y + r * self.cell
            x2, y2 = x + self.cell, y + self.cell
            if w[0]:
                pygame.draw.line(surf, WALL_C, (x, y), (x2, y), self.wall_w)
            if w[1]:
                pygame.draw.line(surf, WALL_C, (x2, y), (x2, y2), self.wall_w)
            if w[2]:
                pygame.draw.line(surf, WALL_C, (x, y2), (x2, y2), self.wall_w)
            if w[3]:
                pygame.draw.line(surf, WALL_C, (x, y), (x, y2), self.wall_w)

        pad = self.cell * 0.20
        for (mr, mc), color in (((0, 0), START_C),
                                ((rows - 1, cols - 1), EXIT_C)):
            pygame.draw.rect(surf, color,
                             (self.ox - area.x + mc * self.cell + pad,
                              self.oy - area.y + mr * self.cell + pad,
                              self.cell - 2 * pad, self.cell - 2 * pad))
        self.static = surf

    # ---- 绘制 -----------------------------------------------------------

    def draw(self) -> None:
        self.screen.fill(APP_BG)
        self.draw_canvas()
        self.draw_toolbar()
        self.draw_menubar()
        self.draw_statusbar()
        if self.open_menu is not None:
            self.draw_dropdown()
        if self.overlay is not None:
            self.draw_overlay()
        pygame.display.flip()

    def draw_canvas(self) -> None:
        area = self.canvas_rect()
        pygame.draw.rect(self.screen, CANVAS_BG, area)
        cols = engine.COLS
        inset = 1
        for idx in self.visited:                       # 轨迹垫在墙层之下
            r, c = divmod(idx, cols)
            pygame.draw.rect(
                self.screen, TRAIL_C,
                (self.ox + c * self.cell + inset, self.oy + r * self.cell + inset,
                 self.cell - 2 * inset, self.cell - 2 * inset))
        if self.static is not None:
            self.screen.blit(self.static, area.topleft)

        cx = self.ox + (self.player[1] + 0.5) * self.cell
        cy = self.oy + (self.player[0] + 0.5) * self.cell
        pygame.draw.circle(self.screen, PLAYER_C, (int(cx), int(cy)),
                           int(self.cell * 0.26))

    def draw_menubar(self) -> None:
        w = self.screen.get_width()
        pygame.draw.rect(self.screen, MENU_BG, (0, 0, w, self.menu_h))
        pygame.draw.line(self.screen, MENU_LINE, (0, self.menu_h - 1),
                         (w, self.menu_h - 1))
        self.menu_rects = {}
        x = self.px(16)
        size = self.fs(15)
        for key, label in (("file", "文件"), ("difficulty", "难度"), ("help", "帮助")):
            tw = text(label, size, MENU_TEXT).get_width()
            rect = pygame.Rect(x - self.px(10), self.px(2),
                               tw + self.px(20), self.menu_h - self.px(6))
            if self.open_menu == key:
                pygame.draw.rect(self.screen, MENU_SELECTED, rect)
            elif self.hover == ("menu", key):
                pygame.draw.rect(self.screen, MENU_HOVER, rect)
            blit = text(label, size, MENU_TEXT).get_rect(center=rect.center)
            self.screen.blit(text(label, size, MENU_TEXT), blit)
            self.menu_rects[key] = rect
            x = rect.right + self.px(6)

    def menu_items(self, key: str):
        """菜单项：(标签, 快捷键提示, 是否当前项, 动作)"""
        if key == "file":
            return [("新建游戏", "Ctrl+N", False, ("new", None)),
                    ("退出", "Esc", False, ("quit", None))]
        if key == "difficulty":
            out = []
            for lv, (name, ratio) in sorted(engine.DIFFICULTIES.items()):
                out.append((f"{name} · 打通 {int(ratio * 100)}% 死胡同", None,
                            lv == self.level, ("level", lv)))
            return out
        return [("玩法说明", None, False, ("help", None)),
                ("关于", None, False, ("about", None))]

    def draw_dropdown(self) -> None:
        key = self.open_menu
        if key is None or key not in self.menu_rects:
            return
        items = self.menu_items(key)
        size = self.fs(15)
        row_h = self.px(26)
        pad = self.px(4)
        width = (max(text(it[0], size, MENU_TEXT).get_width() for it in items)
                 + self.px(56))
        x = self.menu_rects[key].x + self.px(8)
        y = self.menu_h - self.px(2)
        panel = pygame.Rect(x, y, width, row_h * len(items) + pad * 2)
        pygame.draw.rect(self.screen, (214, 214, 214), panel.move(self.px(3), self.px(3)))
        pygame.draw.rect(self.screen, (255, 255, 255), panel)
        pygame.draw.rect(self.screen, (185, 185, 185), panel, width=1)

        self.dropdown_items = []
        for i, (label, shortcut, selected, action) in enumerate(items):
            row = pygame.Rect(panel.x + pad, panel.y + pad + i * row_h,
                              panel.w - 2 * pad, row_h)
            if self.hover == ("item", key, i):
                pygame.draw.rect(self.screen, MENU_HOVER, row)
            if selected:                       # 当前档位：左侧蓝色对勾
                cx, cy = row.x + self.px(10), row.centery
                k = self.px(5)
                pygame.draw.lines(self.screen, ACCENT, False,
                                  [(cx - k, cy), (cx - k // 3, cy + k),
                                   (cx + k, cy - k)], max(2, self.px(2)))
            tx = row.x + (self.px(22) if selected else self.px(10))
            ty = row.y + (row.h - text(label, size, MENU_TEXT).get_height()) // 2
            self.screen.blit(text(label, size, MENU_TEXT), (tx, ty))
            if shortcut:
                sc_size = self.fs(13)
                sc = text(shortcut, sc_size, SHORTCUT_TEXT)
                self.screen.blit(sc, (row.right - sc.get_width() - self.px(8),
                                      row.y + (row.h - sc.get_height()) // 2))
            self.dropdown_items.append((row, action))
        self.dropdown_rect = panel

    def draw_toolbar(self) -> None:
        w = self.screen.get_width()
        y = self.menu_h
        pygame.draw.rect(self.screen, TOOL_BG, (0, y, w, self.tool_h))
        pygame.draw.line(self.screen, MENU_LINE, (0, y + self.tool_h - 1),
                         (w, y + self.tool_h - 1))
        self.tool_rects = {}

        size = self.fs(15)
        label_h = text("难度", size, MENU_TEXT).get_height()
        self.screen.blit(text("难度", size, MENU_TEXT),
                         (self.px(14), y + (self.tool_h - label_h) // 2))
        btn_h = self.px(30)
        btn_y = y + (self.tool_h - btn_h) // 2
        x = self.px(52)
        for lv, (name, _ratio) in sorted(engine.DIFFICULTIES.items()):
            label = f"{lv} {name}"
            tw = text(label, size, BTN_TEXT).get_width()
            rect = pygame.Rect(x, btn_y, tw + self.px(26), btn_h)
            if lv == self.level:
                pygame.draw.rect(self.screen, ACCENT, rect,
                                 border_radius=self.px(4))
                surf = text(label, size, ACCENT_TEXT)
            else:
                bg = BTN_HOVER if self.hover == ("btn", lv) else BTN_BG
                pygame.draw.rect(self.screen, bg, rect,
                                 border_radius=self.px(4))
                pygame.draw.rect(self.screen, BTN_BORDER, rect, width=1,
                                 border_radius=self.px(4))
                surf = text(label, size, BTN_TEXT)
            self.screen.blit(surf, surf.get_rect(center=rect.center))
            self.tool_rects[lv] = rect
            x = rect.right + self.px(8)

        new_label = "新局 (Ctrl+N)"
        nw = text(new_label, size, BTN_TEXT).get_width() + self.px(24)
        new_rect = pygame.Rect(x + self.px(16), btn_y, nw, btn_h)
        bg = BTN_HOVER if self.hover == ("btn", "new") else BTN_BG
        pygame.draw.rect(self.screen, bg, new_rect, border_radius=self.px(4))
        pygame.draw.rect(self.screen, BTN_BORDER, new_rect, width=1,
                         border_radius=self.px(4))
        surf = text(new_label, size, BTN_TEXT)
        self.screen.blit(surf, surf.get_rect(center=new_rect.center))
        self.tool_rects["new"] = new_rect

        hint = "方向键 / WASD 移动  ·  R 重开"
        hint_size = self.fs(13)
        hs = text(hint, hint_size, HINT_TEXT)
        if new_rect.right + self.px(20) + hs.get_width() < w:
            self.screen.blit(hs, (w - hs.get_width() - self.px(16),
                                  y + (self.tool_h - hs.get_height()) // 2))

    def draw_statusbar(self) -> None:
        h = self.screen.get_height()
        w = self.screen.get_width()
        y = h - self.status_h
        pygame.draw.rect(self.screen, STATUS_BG, (0, y, w, self.status_h))
        pygame.draw.line(self.screen, STATUS_LINE, (0, y), (w, y))
        size = self.fs(13)
        left = (f"难度：{self._level_name()}（打通 "
                f"{int(self._level_ratio() * 100)}% 死胡同）")
        ls = text(left, size, STATUS_TEXT)
        self.screen.blit(ls, (self.px(12), y + (self.status_h - ls.get_height()) // 2))
        right = f"尺寸 {engine.COLS} × {engine.ROWS}"
        rs = text(right, size, STATUS_TEXT)
        self.screen.blit(rs, (w - rs.get_width() - self.px(12),
                              y + (self.status_h - rs.get_height()) // 2))

    # ---- 覆盖面板（胜利 / 帮助 / 关于）--------------------------------

    def overlay_content(self):
        if self.overlay == "win":
            return ("胜 利", "绿色起点 → 红色终点，已到达。\n按任意键直接开新局。",
                    [("再来一局", "again"), ("关闭", "close")])
        if self.overlay == "help":
            return ("玩法说明",
                    "从左上角绿色起点走到右下角红色终点。\n"
                    "移动：方向键或 WASD，撞墙不移动。\n"
                    "难度：工具栏、菜单「难度」或按 1 / 2 / 3 切换。\n"
                    "重开：R 或 Ctrl+N；退出：Esc。\n"
                    "胜利后按任意键即刷新迷宫继续。",
                    [("知道了", "close")])
        return ("关于",
                f"{TITLE}\n\n"
                f"迷宫尺寸：{engine.COLS} × {engine.ROWS}\n"
                "生成：深度优先回溯（迭代）+ 可调环路密度\n"
                "界面：pygame 自绘，浅色系统风\n\n"
                f"版权：{COPYRIGHT}",
                [("关闭", "close")])

    def draw_overlay(self) -> None:
        w, h = self.screen.get_size()
        veil = pygame.Surface((w, h), pygame.SRCALPHA)
        veil.fill((246, 247, 249, 158))
        self.screen.blit(veil, (0, 0))

        title, body, buttons = self.overlay_content()
        lines = body.split("\n")
        title_size = self.fs(26)
        body_size = self.fs(15)
        line_h = self.px(22)
        text_w = max([text(title, title_size, PANEL_TITLE, True).get_width()]
                     + [text(ln, body_size, PANEL_TEXT).get_width() for ln in lines])
        panel_w = min(w - self.px(64), max(self.px(380), text_w + self.px(72)))
        panel_h = (self.px(62) + line_h * len(lines) + self.px(72))
        panel = pygame.Rect(0, 0, panel_w, panel_h)
        panel.center = (w // 2, h // 2)

        pygame.draw.rect(self.screen, (206, 206, 206), panel.move(self.px(4), self.px(4)))
        pygame.draw.rect(self.screen, (255, 255, 255), panel)
        pygame.draw.rect(self.screen, ACCENT, panel, width=self.px(2))

        ts = text(title, title_size, PANEL_TITLE, True)
        self.screen.blit(ts, ts.get_rect(midtop=(panel.centerx,
                                                 panel.y + self.px(22))))
        y = panel.y + self.px(62)
        for ln in lines:
            ls = text(ln, body_size, PANEL_TEXT)
            self.screen.blit(ls, ls.get_rect(midtop=(panel.centerx, y)))
            y += line_h

        self.overlay_buttons = []
        btn_w = self.px(104)
        btn_h = self.px(30)
        gap = self.px(12)
        total = btn_w * len(buttons) + gap * (len(buttons) - 1)
        bx = panel.centerx - total // 2
        by = panel.bottom - self.px(44)
        for label, act in buttons:
            rect = pygame.Rect(bx, by, btn_w, btn_h)
            if act == "again":
                pygame.draw.rect(self.screen, ACCENT, rect, border_radius=self.px(4))
                surf = text(label, body_size, ACCENT_TEXT)
            else:
                bg = BTN_HOVER if self.hover == ("obtn", label) else BTN_BG
                pygame.draw.rect(self.screen, bg, rect, border_radius=self.px(4))
                pygame.draw.rect(self.screen, BTN_BORDER, rect, width=1,
                                 border_radius=self.px(4))
                surf = text(label, body_size, BTN_TEXT)
            self.screen.blit(surf, surf.get_rect(center=rect.center))
            self.overlay_buttons.append((rect, act))
            bx += btn_w + gap

    # ---- 交互 -----------------------------------------------------------

    def hit_menu(self, pos):
        for key, rect in self.menu_rects.items():
            if rect.collidepoint(pos):
                return ("menu", key)
        return None

    def hit_dropdown(self, pos):
        if self.open_menu is None:
            return None
        for i, (row, _action) in enumerate(self.dropdown_items):
            if row.collidepoint(pos):
                return ("item", self.open_menu, i)
        return None

    def hit_toolbar(self, pos):
        for key, rect in self.tool_rects.items():
            if rect.collidepoint(pos):
                return ("btn", key)
        return None

    def hit_overlay_button(self, pos):
        for rect, act in self.overlay_buttons:
            if rect.collidepoint(pos):
                return ("obtn", act)
        return None

    def run_action(self, action) -> None:
        kind, arg = action
        if kind == "new":
            self.new_game()
        elif kind == "quit":
            pygame.event.post(pygame.event.Event(pygame.QUIT))
        elif kind == "level":
            self.set_level(arg)
        elif kind == "help":
            self.overlay = "help"
        elif kind == "about":
            self.overlay = "about"

    def on_click(self, pos) -> None:
        if self.overlay is not None:
            hit = self.hit_overlay_button(pos)
            if hit:
                if hit[1] == "again":
                    self.new_game()
                else:
                    self.overlay = None
            return

        hit = self.hit_dropdown(pos)
        if hit:
            items = self.menu_items(self.open_menu)
            self.run_action(items[hit[2]][3])
            self.open_menu = None
            return

        hit = self.hit_menu(pos)
        if hit:
            key = hit[1]
            self.open_menu = None if self.open_menu == key else key
            return
        self.open_menu = None

        hit = self.hit_toolbar(pos)
        if hit:
            target = hit[1]
            if target == "new":
                self.new_game()
            else:
                self.set_level(target)

    def on_key(self, event) -> None:
        ks = (pygame.key.name(event.key) or "").lower()
        mods = pygame.key.get_mods()
        if ks == "n" and (mods & pygame.KMOD_CTRL):
            self.new_game()
            return
        if ks == "escape":
            if self.overlay is not None:
                self.overlay = None
            else:
                pygame.event.post(pygame.event.Event(pygame.QUIT))
            return
        if ks in LEVEL_KEYS:
            self.set_level(LEVEL_KEYS[ks])
            return
        if self.overlay is not None:
            if self.overlay == "win":
                self.new_game()            # 胜利后任意键刷新图继续
            return
        if ks == "r":
            self.new_game()
            return
        d = KEY_DIRS.get(ks)
        if d is None:
            return
        before = (self.player[0], self.player[1])
        engine.try_move(self.walls, self.player, d)
        if before != (self.player[0], self.player[1]):
            self.visited.add(self.player[0] * engine.COLS + self.player[1])
            if tuple(self.player) == engine.EXIT:
                self.won = True
                self.overlay = "win"

    def loop(self) -> int:
        while True:
            pos = pygame.mouse.get_pos()
            if self.overlay is not None:
                self.hover = self.hit_overlay_button(pos)
            else:
                self.hover = (self.hit_menu(pos) or self.hit_dropdown(pos)
                              or self.hit_toolbar(pos))

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    return 0
                if event.type == pygame.VIDEORESIZE:
                    width = max(self.min_w, event.w)
                    height = max(self.min_h, event.h)
                    self.screen = pygame.display.set_mode((width, height),
                                                         pygame.RESIZABLE)
                    self.rebuild_static()
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    self.on_click(event.pos)
                elif event.type == pygame.KEYDOWN:
                    self.on_key(event)
            self.draw()
            self.clock.tick(60)


def main() -> int:
    try:
        from ctypes import windll
        windll.user32.SetProcessDPIAware()     # 先让进程 DPI 感知，再取 DPI 排布
    except Exception:
        pass
    return MazeWin().loop()


if __name__ == "__main__":
    sys.exit(main())

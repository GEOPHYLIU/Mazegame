"""迷宫小游戏 — M2 + M3 实现。

数据口径见同目录 SPEC.md §3：通道式迷宫（格子 + 格间墙），
递归回溯用栈迭代实现；START=(0,0)，EXIT=(cols-1, rows-1)。

用法：
    python maze_game.py --selftest      # A1 + A6 自检，通过则退出码 0
    python maze_game.py                 # pygame 游戏主程序（A2–A5）
    python -m pytest test_maze_game.py -q   # 自动化验收（A1–A6）
"""

import sys
import os
import random
from collections import deque

# ---- 参数口径（SPEC.md §3，D05/D07）--------------------------------------

COLS = 21          # 迷宫列数（奇数，>=5）
ROWS = 21          # 迷宫行数（奇数，>=5）
CELL_PX = 28       # 每格边长（像素），窗口尺寸 = COLS*CELL_PX x ROWS*CELL_PX

START = (0, 0)                     # 左上格
EXIT = (COLS - 1, ROWS - 1)        # 右下格

# 难度档位（D10）：档位号 -> (档位名, braid 死胡同打通比例)
# 档位号与键盘数字键的对应在 build_diff_keys() 内用 pygame.K_* 常量构建，
# 不在此处硬编码键值（与 D09 同一教训：键码随 pygame 版本/布局而变）。
DIFFICULTIES = {
    1: ("\u5bbd\u677e", 0.0),      # 宽松 0%
    2: ("\u6807\u51c6", 0.25),     # 标准 25%（默认）
    3: ("\u5bc6\u96c6", 0.5),      # 密集 50%
}
DEFAULT_DIFF_LEVEL = 2

# 难度菜单的显示文本：档位号 -> (档位名, 效果说明, 无中文字体时的英文回退)
MENU_TEXT = {
    1: ("\u5bbd\u677e", "\u6b7b\u80e1\u540c\u5168\u4fdd\u7559", "Loose"),
    2: ("\u6807\u51c6", "\u6253\u901a 25% \u6b7b\u80e1\u540c\uff08\u9ed8\u8ba4\uff09",
        "Standard"),
    3: ("\u5bc6\u96c6", "\u6253\u901a 50% \u6b7b\u80e1\u540c", "Dense"),
}

# 四个方向：dr, dc 与该格墙位索引。墙位索引约定 0=上 1=右 2=下 3=左。
DIRS = (
    (-1, 0, 0, 2),   # 上：本格墙0，对面格墙2
    (0, 1, 1, 3),    # 右：本格墙1，对面格墙3
    (1, 0, 2, 0),    # 下：本格墙2，对面格墙0
    (0, -1, 3, 1),   # 左：本格墙3，对面格墙1
)


# ---- 迷宫数据结构与生成（M1）--------------------------------------------

def new_maze(cols: int, rows: int) -> list:
    """建一个四周全封墙的迷宫：每格 [上, 右, 下, 左] 四个布尔墙位。"""
    return [[True, True, True, True] for _ in range(cols * rows)]


def dead_end_count(walls: list) -> int:
    """死胡同格数量：恰有 3 面墙的格。"""
    return sum(1 for w in walls if w.count(True) == 3)


def braid(walls: list, cols: int, rows: int, ratio: float,
          rng: random.Random) -> list:
    """按 ratio 比例打通死胡同的墙，形成环路（D10 难度口径）。

    死胡同 = 恰有 3 面墙的格。对随机抽到的前 ratio 比例死胡同，随机打开
    一面"朝向格内邻居"的墙（边界墙绝不开，保持迷宫外形完整）。
    """
    if ratio <= 0.0:
        return walls
    dead_ends = [i for i, w in enumerate(walls)
                 if w.count(True) == 3]
    rng.shuffle(dead_ends)
    n = int(round(len(dead_ends) * ratio))
    for i in dead_ends[:n]:
        r, c = divmod(i, cols)
        # 可打的墙：该方向有墙，且穿过去是格内邻居（界外方向永不入选）
        candidates = []
        for dr, dc, wall_here, _ in DIRS:
            nr, nc = r + dr, c + dc
            if walls[i][wall_here] and 0 <= nr < rows and 0 <= nc < cols:
                candidates.append(wall_here)
        if candidates:
            wall_here = rng.choice(candidates)
            walls[i][wall_here] = False
            nxt = (r + DIRS[wall_here][0]) * cols + (c + DIRS[wall_here][1])
            walls[nxt][(wall_here + 2) % 4] = False
    return walls


def generate_maze(cols: int, rows: int, rng: random.Random,
                  braid_ratio: float = 0.0) -> list:
    """递归回溯生成完美迷宫（栈迭代，避免深迷宫爆栈），可选 braid 增环。

    返回长度 cols*rows 的墙位表；braid_ratio=0 时任意两格间恰有一条路径，
    >0 时存在环路但 START 到 EXIT 仍必可达（打洞只增边、不减连通性）。
    """
    walls = new_maze(cols, rows)
    visited = [False] * (cols * rows)
    stack = [0]                      # 从格 0 = (row 0, col 0) 起挖
    visited[0] = True

    while stack:
        cur = stack[-1]
        r, c = divmod(cur, cols)
        # 收集未访问的相邻格
        neighbors = []
        for dr, dc, wall_here, _wall_there in DIRS:
            nr, nc = r + dr, c + dc
            if 0 <= nr < rows and 0 <= nc < cols:
                nxt = nr * cols + nc
                if not visited[nxt]:
                    neighbors.append((nxt, nr, nc, wall_here))

        if neighbors:
            nxt, nr, nc, wall_here = rng.choice(neighbors)
            # 打通两格间对应的墙（本格与对面格成对删除）
            walls[cur][wall_here] = False
            walls[nxt][(wall_here + 2) % 4] = False
            visited[nxt] = True
            stack.append(nxt)
        else:
            stack.pop()

    if braid_ratio > 0.0:            # D10：难度档位真正作用于迷宫拓扑
        braid(walls, cols, rows, braid_ratio, rng)
    return walls


def solvable(walls: list, cols: int, rows: int,
             start: tuple = START, exit_rc: tuple = EXIT) -> bool:
    """BFS 验证从 start 到 exit_rc 可达（验收 A1 的判据）。"""
    sr, sc = start
    er, ec = exit_rc
    start_i, exit_i = sr * cols + sc, er * cols + ec
    seen = {start_i}
    queue = deque([start_i])
    while queue:
        cur = queue.popleft()
        if cur == exit_i:
            return True
        r, c = divmod(cur, cols)
        for dr, dc, wall_here, _ in DIRS:
            if walls[cur][wall_here]:        # 有墙，不通
                continue
            nr, nc = r + dr, c + dc
            if 0 <= nr < rows and 0 <= nc < cols:
                nxt = nr * cols + nc
                if nxt not in seen:
                    seen.add(nxt)
                    queue.append(nxt)
    return False


def run_selftest() -> int:
    """自检：A1（100 个 39x39 全可达）+ A6（braid 0%/50% 各 100 个 21x21）。"""
    # ---- A1 -------------------------------------------------------------
    n, size = 100, 39
    rng = random.Random(20261110)        # 固定种子，验收可复现
    for i in range(1, n + 1):
        walls = generate_maze(size, size, rng)
        if not solvable(walls, size, size, (0, 0), (size - 1, size - 1)):
            print(f"[FAIL] A1 第 {i} 个迷宫不可达")
            return 1
    print(f"[OK] A1 {n} 个 {size}x{size} 迷宫全部从(0,0)可达"
          f"({size-1},{size-1})")

    # ---- A6：两档各 100 个 21x21，可达 + 密集档死胡同占比降至宽松档一半以下
    n6, size6 = 100, 21
    loose_dead = dense_dead = 0
    for s in range(n6):
        w_loose = generate_maze(size6, size6, random.Random(5000 + s), 0.0)
        if not solvable(w_loose, size6, size6, (0, 0), (size6 - 1, size6 - 1)):
            print(f"[FAIL] A6 braid=0% 第 {s + 1} 个迷宫不可达")
            return 1
        loose_dead += dead_end_count(w_loose)

        w_dense = generate_maze(size6, size6, random.Random(5000 + s), 0.5)
        if not solvable(w_dense, size6, size6, (0, 0), (size6 - 1, size6 - 1)):
            print(f"[FAIL] A6 braid=50% 第 {s + 1} 个迷宫不可达")
            return 1
        dense_dead += dead_end_count(w_dense)

    if not dense_dead * 2 < loose_dead:
        print(f"[FAIL] A6 密集档死胡同 {dense_dead} 未降到宽松档 "
              f"{loose_dead} 的一半以下")
        return 1
    print(f"[OK] A6 braid 0%/50% 各 {n6} 个 {size6}x{size6} 迷宫全部可达；"
          f"死胡同 {loose_dead} -> {dense_dead}（< 一半）")
    return 0


# ---- pygame 游戏主程序（M2：A2 渲染 / A3 操作 / A4 胜利 / A5 依赖）--------

BG      = (20, 24, 31)      # 背景/路面 #14181f（D06）
WALL_C  = (232, 230, 227)   # 墙 #e8e6e3
START_C = (61, 220, 132)    # 起点 青绿
EXIT_C  = (255, 109, 58)    # 终点 橙红
PLAYER_C = (255, 214, 10)   # 玩家 亮黄
TEXT_C  = (255, 255, 255)   # 文字 白

# 键位映射（D07）在 run_game() 内构建：箭头方向键的键值随 pygame 版本
# 不同，必须用 pygame.K_* 常量，不能硬编码键码。

_FONT_CACHE = {}            # size_px -> (font, has_cjk)
_TEXT_CACHE = {}            # (size_px, text) -> 渲染好的 Surface


def build_key_dirs() -> dict:
    """pygame 键常数 -> 方向索引（DIRS 的下标）。需在 import pygame 之后调用。"""
    import pygame
    return {
        pygame.K_UP: 0, pygame.K_w: 0,       # 上箭头 / W
        pygame.K_RIGHT: 1, pygame.K_d: 1,    # 右箭头 / D
        pygame.K_DOWN: 2, pygame.K_s: 2,     # 下箭头 / S
        pygame.K_LEFT: 3, pygame.K_a: 3,     # 左箭头 / A
    }


def build_diff_keys() -> dict:
    """pygame 键常数 -> 难度档位号（1/2/3，含小键盘）。需在 import pygame 后调用。"""
    import pygame
    return {
        pygame.K_1: 1, pygame.K_KP1: 1,
        pygame.K_2: 2, pygame.K_KP2: 2,
        pygame.K_3: 3, pygame.K_KP3: 3,
    }


def step_level(level: int, delta: int) -> int:
    """菜单里上/下移动选中档位，超出 1–3 范围则夹紧在边界。"""
    lo, hi = min(DIFFICULTIES), max(DIFFICULTIES)
    return max(lo, min(hi, level + delta))


def try_move(walls: list, player: list, dir_idx: int,
             cols: int = COLS, rows: int = ROWS) -> None:
    """请求一次移动：无墙且不出界则更新 player=[r, c]，否则原地不动。

    尺寸默认取模块级 COLS/ROWS（游戏内即此口径），显式传入可用于其它尺寸。
    """
    dr, dc, wall_here, _ = DIRS[dir_idx]
    r, c = player
    if walls[r * cols + c][wall_here]:
        return                          # 撞墙：不动、无惩罚
    nr, nc = r + dr, c + dc
    if 0 <= nr < rows and 0 <= nc < cols:
        player[0], player[1] = nr, nc


def _font_file_candidates() -> list:
    """Windows 系统字体文件路径（含中文字形的首选字体）。"""
    base = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
    return [os.path.join(base, name) for name in
            ("msyh.ttc", "msyhbd.ttc", "simhei.ttf", "simsun.ttc", "Deng.ttf")]


def load_font(size_px: int):
    """加载含中文字形的字体，结果按字号缓存。

    优先直接加载系统字体文件：pygame 2.6 + Python 3.13 在 Windows 上
    pygame.font.get_fonts() / SysFont() 会因注册表值类型抛 TypeError
    （sysfont.py: splitext(font) 收到 int），按名字查字体一律失败，
    只能靠 Font(路径) 绕开系统字体扫描。
    """
    import pygame
    cached = _FONT_CACHE.get(size_px)
    if cached is not None:
        return cached

    result = None
    for path in _font_file_candidates():
        if not os.path.exists(path):
            continue
        try:
            f = pygame.font.Font(path, size_px)
            f.set_bold(True)                 # Font 不自动加粗，显式设置
            result = (f, True)               # 这些字体都含中文字形
            break
        except Exception:
            continue

    if result is None:                       # 退路：按名字扫描（部分平台可用）
        for name in ("microsoftyahei", "msyh", "simhei", "simsun", "dengxian"):
            try:
                f = pygame.font.SysFont(name, size_px, bold=True)
                m = f.metrics("\u80dc\u5229")
                if m and m[0][0] is not None:
                    result = (f, True)
                    break
            except Exception:
                continue

    if result is None:
        result = (pygame.font.Font(None, size_px), False)

    _FONT_CACHE[size_px] = result
    return result


def render_text(text: str, size_px: int, color: tuple = TEXT_C):
    """渲染文字并按 (字号, 文本, 颜色) 缓存；菜单/提示每帧多次调用也只 render 一次。"""
    key = (size_px, text, color)
    surf = _TEXT_CACHE.get(key)
    if surf is None:
        font, _has_cjk = load_font(size_px)
        surf = font.render(text, True, color)
        _TEXT_CACHE[key] = surf
    return surf


def draw_win_text(screen, cell_px: float):
    """胜利画面：主文字 + 续玩提示，共用一块半透明深色背板（压在墙线上也可读）。"""
    import pygame
    size_px = max(18, int(cell_px * 1.4))
    cjk = has_cjk_font(size_px)
    text = "胜利" if cjk else "YOU WIN"
    hint = ("按任意键开新局 · M 换难度 · Esc 退出" if cjk
            else "Any key: new maze . M: menu . Esc: quit")

    label = render_text(text, size_px)
    hint_label = render_text(hint, max(13, int(cell_px * 0.62)), WALL_C)

    gap = int(cell_px * 0.30)
    block_h = label.get_height() + gap + hint_label.get_height()
    cx, cy = screen.get_width() // 2, screen.get_height() // 2
    top = cy - block_h // 2

    pad_x, pad_y = int(cell_px * 0.55), int(cell_px * 0.32)
    plate = pygame.Surface((max(label.get_width(), hint_label.get_width())
                            + 2 * pad_x, block_h + 2 * pad_y), pygame.SRCALPHA)
    plate.fill(BG + (216,))
    screen.blit(plate, plate.get_rect(center=(cx, cy)))

    screen.blit(label, label.get_rect(midtop=(cx, top)))
    screen.blit(hint_label, hint_label.get_rect(
        midtop=(cx, top + label.get_height() + gap)))


def has_cjk_font(size_px: int) -> bool:
    """当前字号用的字体是否含中文字形。"""
    return load_font(size_px)[1]


def draw_menu(screen, selected: int, cell_px: float):
    """难度选择菜单：标题 + 三个档位项（选中项加亮框）+ 底部按键提示。"""
    import pygame
    screen.fill(BG)
    w, h = screen.get_size()

    title_size = max(28, int(cell_px * 1.7))
    item_size = max(18, int(cell_px * 1.0))
    note_size = max(13, int(cell_px * 0.66))
    cjk_title = has_cjk_font(title_size)

    title = render_text("\u8ff7\u5bab" if cjk_title else "MAZE", title_size)
    screen.blit(title, title.get_rect(center=(w // 2, int(h * 0.20))))

    box_w, box_h = int(w * 0.72), int(cell_px * 1.35)
    x0 = (w - box_w) // 2
    y0 = int(h * 0.34)

    for idx, level in enumerate(sorted(DIFFICULTIES)):
        cjk_name, cjk_note, en_name = MENU_TEXT[level]
        name = cjk_name if cjk_title else en_name
        note = cjk_note if cjk_title else ""
        rect = pygame.Rect(x0, y0 + idx * (box_h + int(cell_px * 0.35)),
                           box_w, box_h)
        chosen = level == selected

        if chosen:                          # 选中项：亮黄底框 + 实心指示
            pygame.draw.rect(screen, PLAYER_C, rect, width=max(2, int(cell_px * 0.1)))
            pygame.draw.rect(screen, PLAYER_C,
                             (rect.x + int(cell_px * 0.18), rect.y + int(cell_px * 0.22),
                              int(cell_px * 0.16), int(cell_px * 0.16)))

        label = render_text(f"{level}  {name}", item_size)
        screen.blit(label, label.get_rect(
            midleft=(rect.x + int(cell_px * 0.62), rect.centery)))

        if note:
            note_label = render_text(note, note_size)
            screen.blit(note_label, note_label.get_rect(
                midright=(rect.right - int(cell_px * 0.2), rect.centery)))

    hint = ("\u2191\u2193 \u9009\u62e9 \u00b7 Enter \u5f00\u59cb \u00b7 "
            "1/2/3 \u76f4\u9009 \u00b7 Esc \u9000\u51fa") if cjk_title else \
           "Up/Down select . Enter start . 1/2/3 pick . Esc quit"
    hint_label = render_text(hint, note_size)
    screen.blit(hint_label, hint_label.get_rect(
        center=(w // 2, int(h * 0.86))))


def _wall_width(cell_px: float) -> int:
    return max(2, round(cell_px * 0.09))


def _clamped_line(surface, color, p1, p2, wt: int) -> None:
    """画墙线段并把端点收进画布内，避免最外框线被窗口边缘裁掉一半。"""
    import pygame
    w, h = surface.get_size()
    hx = max(0, min(wt // 2, (w - 1) // 2))
    hy = max(0, min(wt // 2, (h - 1) // 2))
    hi_x, hi_y = max(hx, w - 1 - hx), max(hy, h - 1 - hy)

    def _clamp(pt):
        return (min(max(pt[0], hx), hi_x), min(max(pt[1], hy), hi_y))

    pygame.draw.line(surface, color, _clamp(p1), _clamp(p2), wt)


def render_static_layer(walls: list, cols: int, rows: int, cell_px: float,
                        size: tuple = None):
    """把迷宫静态部分（背景 + 全部墙 + 起点/终点标记）预渲染成一张 Surface。

    玩家圆点与胜利文字属于每帧变化的图层，不计入此处。窗口尺寸变化或
    迷宫重建时需要重新调用一次；此后每帧只需一次 blit。
    """
    import pygame
    if size is None:
        size = (max(1, int(cols * cell_px)), max(1, int(rows * cell_px)))
    surf = pygame.Surface(size)
    surf.fill(BG)

    wt = _wall_width(cell_px)
    for i, w in enumerate(walls):
        r, c = divmod(i, cols)
        x, y = c * cell_px, r * cell_px
        if w[0]:    # 上
            _clamped_line(surf, WALL_C, (x, y), (x + cell_px, y), wt)
        if w[1]:    # 右
            _clamped_line(surf, WALL_C, (x + cell_px, y),
                          (x + cell_px, y + cell_px), wt)
        if w[2]:    # 下
            _clamped_line(surf, WALL_C, (x, y + cell_px),
                          (x + cell_px, y + cell_px), wt)
        if w[3]:    # 左
            _clamped_line(surf, WALL_C, (x, y), (x, y + cell_px), wt)

    pad = cell_px * 0.30                    # 起点/终点标记
    for (mr, mc), color in (((0, 0), START_C), ((rows - 1, cols - 1), EXIT_C)):
        pygame.draw.rect(surf, color,
                         (mc * cell_px + pad, mr * cell_px + pad,
                          cell_px - 2 * pad, cell_px - 2 * pad))

    return surf


def draw_player(surface, player: list, cell_px: float) -> None:
    """画玩家圆点（每帧变化的图层）。"""
    import pygame
    radius = cell_px * 0.32
    center = ((player[1] + 0.5) * cell_px, (player[0] + 0.5) * cell_px)
    pygame.draw.circle(surface, PLAYER_C, center, int(radius))


def draw(screen, walls: list, player: list, won: bool, cell_px: float,
         cols: int = COLS, rows: int = ROWS, static=None) -> None:
    """渲染一帧。传入 static（render_static_layer 的结果）可省去逐格重画墙。"""
    import pygame
    if static is None:
        static = render_static_layer(walls, cols, rows, cell_px,
                                     screen.get_size())
    screen.blit(static, (0, 0))
    draw_player(screen, player, cell_px)
    if won:
        draw_win_text(screen, cell_px)


def run_game() -> int:
    """主循环：生成迷宫 -> 绘制 -> 处理按键（A2–A4、A6 切档）。"""
    try:
        import pygame
    except ImportError:
        print("未检测到 pygame，请先安装后再运行：")
        print("    pip install pygame")
        return 1                            # A5：不抛裸 traceback

    pygame.init()
    try:
        # 窗口尺寸 = 格数 x 格宽，是派生量（SPEC 注2）；超屏则整体缩放
        win_w, win_h = COLS * CELL_PX, ROWS * CELL_PX
        info = pygame.display.Info()
        scale = min(1.0, info.current_w * 0.9 / win_w,
                    info.current_h * 0.9 / win_h)
        cell_px = CELL_PX * scale
        screen = pygame.display.set_mode(
            (int(win_w * scale), int(win_h * scale)))

        clock = pygame.time.Clock()
        key_dirs = build_key_dirs()
        diff_keys = build_diff_keys()
        rng = random.Random()               # 每局新种子
        static = None                       # 静态层缓存，仅迷宫/尺寸变化时重建

        def start_round(level: int):
            """按指定档位开新局，同时刷新静态层与窗口标题。"""
            nonlocal static
            name, ratio = DIFFICULTIES[level]
            walls = generate_maze(COLS, ROWS, rng, ratio)
            player = [START[0], START[1]]
            static = render_static_layer(walls, COLS, ROWS, cell_px,
                                         screen.get_size())
            pygame.display.set_caption(f"迷宫 · {name}")
            return walls, player, False

        # ---- 难度菜单：启动即出现，选完才开局 ----
        in_menu = True
        selected = DEFAULT_DIFF_LEVEL       # 菜单里当前高亮的档位
        level = DEFAULT_DIFF_LEVEL          # 本局实际使用的档位
        walls, player, won = None, None, False
        pygame.display.set_caption("迷宫 · 选择难度")

        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return 0
                if event.type != pygame.KEYDOWN:
                    continue
                key = event.key
                if key == pygame.K_ESCAPE:
                    return 0

                if in_menu:
                    if key in (pygame.K_UP, pygame.K_w,
                               pygame.K_LEFT, pygame.K_a):
                        selected = step_level(selected, -1)
                        continue
                    if key in (pygame.K_DOWN, pygame.K_s,
                               pygame.K_RIGHT, pygame.K_d):
                        selected = step_level(selected, 1)
                        continue
                    lvl = diff_keys.get(key)     # 1/2/3 直达并开局
                    if lvl is None and key in (pygame.K_RETURN,
                                               pygame.K_KP_ENTER,
                                               pygame.K_SPACE):
                        lvl = selected           # Enter/空格：用当前高亮档
                    if lvl is None:
                        continue
                    selected = level = lvl
                    walls, player, won = start_round(level)
                    in_menu = False
                    continue

                # ---- 游戏中 ----
                lvl = diff_keys.get(key)         # A6：1/2/3 切档并重开新局
                if lvl is not None:
                    selected = level = lvl
                    walls, player, won = start_round(level)
                    continue
                if key == pygame.K_m:            # 回难度菜单另选
                    in_menu = True
                    pygame.display.set_caption("迷宫 · 选择难度")
                    continue
                if won:                     # 胜利后：任意非 Esc 键开新局
                    walls, player, won = start_round(level)
                    continue
                if key == pygame.K_r:  # D07：R 重开新局
                    walls, player, won = start_round(level)
                    continue
                d = key_dirs.get(key)
                if d is not None:
                    try_move(walls, player, d)
                    if (player[0], player[1]) == EXIT:
                        won = True          # A4：到终点即胜

            if in_menu:
                draw_menu(screen, selected, cell_px)
            else:
                draw(screen, walls, player, won, cell_px, COLS, ROWS, static)
            pygame.display.flip()
            clock.tick(60)
    finally:
        pygame.quit()


# ---- 入口 ---------------------------------------------------------------

def main() -> int:
    if "--selftest" in sys.argv:
        return run_selftest()
    return run_game()


if __name__ == "__main__":
    sys.exit(main())

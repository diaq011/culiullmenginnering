import json
import os
import random
from dataclasses import dataclass
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import HTTPCookieProcessor, Request, build_opener

from flask import Flask, jsonify, render_template, request


app = Flask(__name__)

COACH_BASE_URL = os.getenv("COACH_BASE_URL", "http://127.0.0.1:5000")
DEFAULT_CREDENTIALS = {
    "player1": "a",
    "player2": "b",
    "player3": "c",
}
GAME_DATA_PATH = (
    Path(__file__).resolve().parent.parent / "game_coach_game" / "game_data.json"
)


@dataclass
class Candidate:
    row: int
    col: int
    value: str
    priority: float
    profile: Optional[Dict[str, Any]] = None


class CoachClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.cookie_jar = CookieJar()
        self.opener = build_opener(HTTPCookieProcessor(self.cookie_jar))

    def _request(
        self, method: str, path: str, payload: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        data = None
        headers = {}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request_obj = Request(
            url=f"{self.base_url}{path}",
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with self.opener.open(request_obj, timeout=10) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="ignore")
            try:
                body = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                body = {"success": False, "message": raw or f"HTTP {exc.code}"}
            if "success" not in body:
                body["success"] = False
            return body
        except URLError as exc:
            return {"success": False, "message": f"网络错误: {exc.reason}"}

    def login(self, username: str, password: str) -> Dict[str, Any]:
        return self._request(
            "POST",
            "/api/login",
            {"username": username, "password": password},
        )

    def get_snapshot(self, room_code: str) -> Dict[str, Any]:
        return self._request("GET", f"/api/coach/snapshot/{room_code}")

    def evaluate_move(
        self, room_code: str, row: int, col: int, value: str
    ) -> Dict[str, Any]:
        return self._request(
            "POST",
            "/api/coach/evaluate_move",
            {
                "roomCode": room_code,
                "row": row,
                "col": col,
                "value": value,
            },
        )


def load_credentials() -> Dict[str, str]:
    credentials = dict(DEFAULT_CREDENTIALS)
    if not GAME_DATA_PATH.exists():
        return credentials
    try:
        content = json.loads(GAME_DATA_PATH.read_text(encoding="utf-8"))
        users = content.get("users", {})
        for username, info in users.items():
            password = info.get("password")
            if isinstance(password, str) and password:
                credentials[username] = password
    except (OSError, json.JSONDecodeError):
        pass
    return credentials


def pick_snapshot_client(
    room_code: str, credentials: Dict[str, str]
) -> Tuple[Optional[CoachClient], Optional[Dict[str, Any]], str]:
    for username, password in credentials.items():
        client = CoachClient(COACH_BASE_URL)
        login_resp = client.login(username, password)
        if not login_resp.get("success"):
            continue
        snapshot_resp = client.get_snapshot(room_code)
        if snapshot_resp.get("success"):
            return client, snapshot_resp.get("snapshot"), username
    return None, None, ""


def get_turn_username(snapshot: Dict[str, Any]) -> Optional[str]:
    turn = snapshot.get("currentTurn")
    if turn == "player1":
        return snapshot.get("player1")
    if turn == "player2":
        return snapshot.get("player2")
    return None


def numeric_exists_in_row(grid: List[List[Any]], row: int, value: str) -> bool:
    for cell in grid[row]:
        if cell and str(cell.get("value")) == value:
            return True
    return False


def numeric_exists_in_col(grid: List[List[Any]], col: int, value: str) -> bool:
    for line in grid:
        cell = line[col]
        if cell and str(cell.get("value")) == value:
            return True
    return False


def is_locally_valid(
    grid: List[List[Any]], row: int, col: int, value: str
) -> bool:
    if grid[row][col] is not None:
        return False
    if value.upper() == "X":
        return True
    return (not numeric_exists_in_row(grid, row, value)) and (
        not numeric_exists_in_col(grid, col, value)
    )


def other_turn(turn: str) -> str:
    return "player2" if turn == "player1" else "player1"


def line_key_set(raw: Any) -> set:
    if not isinstance(raw, dict):
        return set()
    keys = set()
    for key in raw.keys():
        try:
            keys.add(int(key))
        except (TypeError, ValueError):
            continue
    return keys


def row_values(grid: List[List[Any]], row: int) -> List[str]:
    values = []
    for cell in grid[row]:
        if cell is None:
            continue
        values.append(str(cell.get("value")).upper())
    return values


def col_values(grid: List[List[Any]], col: int) -> List[str]:
    values = []
    for line in grid:
        cell = line[col]
        if cell is None:
            continue
        values.append(str(cell.get("value")).upper())
    return values


def owned_values_in_line(line: List[Any], player_turn: str) -> set:
    owned = set()
    for cell in line:
        if cell is None:
            continue
        if cell.get("turn") != player_turn:
            continue
        val = str(cell.get("value")).upper()
        if val != "X":
            owned.add(val)
    return owned


def line_future_score(line: List[Any]) -> Tuple[int, int]:
    non_x = [cell for cell in line if cell and str(cell.get("value")).upper() != "X"]
    n = len(non_x)
    if n <= 0:
        return 0, 0
    p1 = 0
    p2 = 0
    for cell in line:
        if cell is None:
            continue
        if str(cell.get("value")).upper() != str(n):
            continue
        if cell.get("turn") == "player1":
            p1 = n
        elif cell.get("turn") == "player2":
            p2 = n
    return p1, p2


def apply_move_local(
    state: Dict[str, Any], row: int, col: int, value: str, turn: str
) -> Tuple[Dict[str, Any], Dict[str, int]]:
    new_state = {
        "grid": [[None if cell is None else dict(cell) for cell in line] for line in state["grid"]],
        "row_scored": set(state["row_scored"]),
        "col_scored": set(state["col_scored"]),
        "turn": other_turn(turn),
    }
    new_state["grid"][row][col] = {"value": value, "turn": turn, "color": "sim"}

    gained = {"player1": 0, "player2": 0}
    rows = len(new_state["grid"])
    cols = len(new_state["grid"][0])

    if row not in new_state["row_scored"]:
        line = new_state["grid"][row]
        if all(cell is not None for cell in line):
            s1, s2 = line_future_score(line)
            gained["player1"] += s1
            gained["player2"] += s2
            new_state["row_scored"].add(row)

    if col not in new_state["col_scored"]:
        line = [new_state["grid"][r][col] for r in range(rows)]
        if all(cell is not None for cell in line):
            s1, s2 = line_future_score(line)
            gained["player1"] += s1
            gained["player2"] += s2
            new_state["col_scored"].add(col)

    return new_state, gained


def enumerate_legal_moves(state: Dict[str, Any], turn: str) -> List[Tuple[int, int, str]]:
    grid = state["grid"]
    rows = len(grid)
    cols = len(grid[0])
    max_num = max(rows, cols)
    moves: List[Tuple[int, int, str]] = []

    for r in range(rows):
        for c in range(cols):
            if grid[r][c] is not None:
                continue

            rv = row_values(grid, r)
            cv = col_values(grid, c)
            row_non_x = sum(1 for val in rv if val != "X")
            col_non_x = sum(1 for val in cv if val != "X")

            preferred = [
                str(row_non_x + 1),
                str(col_non_x + 1),
                str(max(row_non_x, col_non_x) + 1),
                "X",
            ]
            preferred.extend(str(i) for i in range(1, max_num + 1))

            used = set()
            for value in preferred:
                v = value.upper()
                if v in used:
                    continue
                used.add(v)
                value_norm = "X" if v == "X" else value
                if is_locally_valid(grid, r, c, value_norm):
                    moves.append((r, c, value_norm))
    return moves


def pair_progress_score(line: List[Any], turn: str, is_first_player: bool) -> float:
    non_x = [cell for cell in line if cell and str(cell.get("value")).upper() != "X"]
    n = len(non_x)
    if n <= 1:
        return 0.0

    mine = owned_values_in_line(line, turn)
    opp = owned_values_in_line(line, other_turn(turn))

    mine_bonus = 0.0
    opp_risk = 0.0
    if is_first_player:
        need_a = str(n)
        need_b = str(n - 1)
        if need_a in mine and need_b in mine:
            mine_bonus += 2.6
        if need_a in opp and need_b in opp:
            opp_risk += 2.2
    else:
        need_a = str(n)
        need_b = str(max(1, n - 2))
        if need_a in mine and need_b in mine:
            mine_bonus += 2.6
        if need_a in opp and need_b in opp:
            opp_risk += 2.2

    return mine_bonus - opp_risk


def two_empty_trap_score(line: List[Any], my_turn: str) -> float:
    empties = sum(1 for cell in line if cell is None)
    if empties != 1:
        return 0.0
    n = len([cell for cell in line if cell and str(cell.get("value")).upper() != "X"])
    if n <= 0:
        return 0.0
    mine = owned_values_in_line(line, my_turn)
    opp = owned_values_in_line(line, other_turn(my_turn))
    if str(n) in opp and str(n) not in mine:
        return -1.8
    if str(n) in mine and str(n) not in opp:
        return 1.4
    return -0.4


def evaluate_board_heuristic(state: Dict[str, Any], root_turn: str) -> float:
    grid = state["grid"]
    rows = len(grid)
    cols = len(grid[0])

    total = 0.0
    root_is_first = root_turn == "player1"

    for r in range(rows):
        if r in state["row_scored"]:
            continue
        line = grid[r]
        total += pair_progress_score(line, root_turn, root_is_first)
        total += two_empty_trap_score(line, root_turn)

    for c in range(cols):
        if c in state["col_scored"]:
            continue
        line = [grid[r][c] for r in range(rows)]
        total += pair_progress_score(line, root_turn, root_is_first)
        total += two_empty_trap_score(line, root_turn)

    return total


def select_top_moves(
    state: Dict[str, Any], turn: str, top_k: int = 12
) -> List[Tuple[int, int, str, float]]:
    scored_moves: List[Tuple[int, int, str, float]] = []
    for r, c, v in enumerate_legal_moves(state, turn):
        next_state, gained = apply_move_local(state, r, c, v, turn)
        immediate = gained[turn] - gained[other_turn(turn)]
        heuristic = evaluate_board_heuristic(next_state, turn)
        x_penalty = -0.45 if str(v).upper() == "X" else 0.0
        score = immediate * 2.8 + heuristic + x_penalty
        scored_moves.append((r, c, v, score))
    scored_moves.sort(key=lambda item: item[3], reverse=True)
    return scored_moves[:top_k]


def forecast_score(state: Dict[str, Any], root_turn: str, depth: int, actor: str) -> float:
    if depth <= 0:
        return evaluate_board_heuristic(state, root_turn)

    top_moves = select_top_moves(state, actor, top_k=10 if depth >= 2 else 8)
    if not top_moves:
        return evaluate_board_heuristic(state, root_turn)

    if actor == root_turn:
        best = -10**9
        for r, c, v, pre_score in top_moves:
            next_state, gained = apply_move_local(state, r, c, v, actor)
            immediate = gained[root_turn] - gained[other_turn(root_turn)]
            value = immediate * 2.5 + pre_score + forecast_score(
                next_state, root_turn, depth - 1, other_turn(actor)
            )
            if value > best:
                best = value
        return best

    worst = 10**9
    for r, c, v, pre_score in top_moves:
        next_state, gained = apply_move_local(state, r, c, v, actor)
        immediate = gained[root_turn] - gained[other_turn(root_turn)]
        value = immediate * 2.5 - pre_score + forecast_score(
            next_state, root_turn, depth - 1, other_turn(actor)
        )
        if value < worst:
            worst = value
    return worst


def build_state_from_snapshot(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    grid = snapshot.get("grid", [])
    return {
        "grid": grid,
        "row_scored": line_key_set(snapshot.get("rowScores", {})),
        "col_scored": line_key_set(snapshot.get("colScores", {})),
        "turn": snapshot.get("currentTurn"),
    }


def strategic_profile(snapshot: Dict[str, Any], candidate: Candidate) -> Dict[str, Any]:
    base_state = build_state_from_snapshot(snapshot)
    root_turn = snapshot.get("currentTurn")
    if not root_turn:
        return {"lookaheadScore": -999.0, "style": "fallback"}

    sim_state, gained = apply_move_local(
        base_state, candidate.row, candidate.col, candidate.value, root_turn
    )
    immediate_diff = gained[root_turn] - gained[other_turn(root_turn)]
    outlook = forecast_score(
        sim_state, root_turn=root_turn, depth=2, actor=other_turn(root_turn)
    )
    total = immediate_diff * 2.3 + outlook

    row_line = sim_state["grid"][candidate.row]
    col_line = [sim_state["grid"][r][candidate.col] for r in range(len(sim_state["grid"]))]
    trap_risk = two_empty_trap_score(row_line, root_turn) + two_empty_trap_score(
        col_line, root_turn
    )
    pair_hint = pair_progress_score(
        row_line, root_turn, root_turn == "player1"
    ) + pair_progress_score(col_line, root_turn, root_turn == "player1")

    style = "balanced"
    if str(candidate.value).upper() == "X":
        style = "defensive"
    elif immediate_diff > 0:
        style = "conversion"
    elif pair_hint > 1.5:
        style = "setup"

    return {
        "lookaheadScore": total,
        "immediateDiff": immediate_diff,
        "trapRisk": trap_risk,
        "pairHint": pair_hint,
        "style": style,
    }


def build_candidates(snapshot: Dict[str, Any]) -> List[Candidate]:
    grid = snapshot.get("grid", [])
    if not grid:
        return []
    rows = len(grid)
    cols = len(grid[0])
    max_num = max(rows, cols)
    candidates: List[Candidate] = []

    for r in range(rows):
        for c in range(cols):
            if grid[r][c] is not None:
                continue

            row_non_empty = sum(1 for cell in grid[r] if cell is not None)
            col_non_empty = sum(1 for i in range(rows) if grid[i][c] is not None)
            row_non_x = sum(
                1
                for cell in grid[r]
                if cell is not None and str(cell.get("value")).upper() != "X"
            )
            col_non_x = sum(
                1
                for i in range(rows)
                if grid[i][c] is not None
                and str(grid[i][c].get("value")).upper() != "X"
            )

            preferred_values = [
                str(row_non_x + 1),
                str(col_non_x + 1),
                str(max(row_non_x, col_non_x) + 1),
                str(max(1, row_non_x)),
                str(max(1, col_non_x)),
            ]
            preferred_values.extend(str(i) for i in range(1, max_num + 1))
            preferred_values.extend(["X", "X"])

            unique_values: List[str] = []
            seen = set()
            for value in preferred_values:
                value_norm = value.upper()
                if value_norm in seen:
                    continue
                seen.add(value_norm)
                unique_values.append("X" if value_norm == "X" else value)

            completion_bonus = 0.0
            if row_non_empty == cols - 1:
                completion_bonus += 2.0
            if col_non_empty == rows - 1:
                completion_bonus += 2.0
            if row_non_empty == cols - 2:
                completion_bonus -= 0.3
            if col_non_empty == rows - 2:
                completion_bonus -= 0.3

            for idx, value in enumerate(unique_values):
                if not is_locally_valid(grid, r, c, value):
                    continue
                x_bias = -0.25 if value.upper() == "X" else 0.0
                priority = completion_bonus + (1.5 / (idx + 1)) + x_bias
                candidates.append(
                    Candidate(row=r, col=c, value=value, priority=priority)
                )

    random.shuffle(candidates)
    ranked: List[Candidate] = []
    coarse_top = sorted(candidates, key=lambda item: item.priority, reverse=True)[:40]
    for candidate in coarse_top:
        profile = strategic_profile(snapshot, candidate)
        candidate.profile = profile
        candidate.priority = candidate.priority + profile.get("lookaheadScore", -999.0)
        ranked.append(candidate)

    ranked.sort(key=lambda item: item.priority, reverse=True)
    return ranked


def build_snapshot_brief(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    grid = snapshot.get("grid", [])
    occupied = []
    for r, line in enumerate(grid):
        for c, cell in enumerate(line):
            if cell is None:
                continue
            occupied.append(
                {
                    "row": r,
                    "col": c,
                    "value": str(cell.get("value")),
                    "owner": cell.get("turn"),
                }
            )
    return {
        "roomCode": snapshot.get("roomCode"),
        "currentTurn": snapshot.get("currentTurn"),
        "scores": {
            "player1": snapshot.get("player1Score", 0),
            "player2": snapshot.get("player2Score", 0),
        },
        "occupiedCells": occupied,
    }


def build_reason_and_risk(
    snapshot: Dict[str, Any],
    candidate: Candidate,
    evaluation: Dict[str, Any],
) -> Tuple[str, str, str]:
    turn = snapshot.get("currentTurn")
    profile = candidate.profile or {}
    lookahead_score = float(profile.get("lookaheadScore", 0.0))
    trap_risk = float(profile.get("trapRisk", 0.0))
    style = profile.get("style", "balanced")

    if lookahead_score >= 4.0 and trap_risk > -0.8:
        confidence = "high"
    elif lookahead_score >= 1.2:
        confidence = "medium"
    else:
        confidence = "low"

    if style == "setup":
        reason = (
            f"推荐在({candidate.row}, {candidate.col})填入 {candidate.value}。"
            "这一步优先建立后续得分组合，不追求立刻得分，目标是让下一轮可在关键行/列形成连贯配合。"
        )
    elif style == "defensive":
        reason = (
            f"推荐在({candidate.row}, {candidate.col})填入 X。"
            "该步用于降低对手在关键线上的收官机会，先稳住局面，再为后续数字点位预留空间。"
        )
    elif turn == "player1":
        reason = (
            f"推荐在({candidate.row}, {candidate.col})填入 {candidate.value}。"
            "作为先手，这一步更偏向围绕 n 与 n-1 的组合去铺设线路，避免把收分点直接让给对手。"
        )
    else:
        reason = (
            f"推荐在({candidate.row}, {candidate.col})填入 {candidate.value}。"
            "作为后手，这一步更偏向围绕 n 与 n-2 的组合去组织下一轮反制空间。"
        )

    if trap_risk <= -1.4:
        risk = "该方案存在“剩两格抢手”风险，若对手应对准确，可能把最后得分点拿走。"
    elif candidate.value.upper() == "X":
        risk = "X 不参与数字得分结构，若后续衔接不足，可能出现控场有效但得分偏慢。"
    else:
        risk = "该步偏向中期布局，若对手改走另一条线，原定配合路线可能需要临时调整。"

    return reason, risk, confidence


def generate_suggestion(room_code: str) -> Dict[str, Any]:
    credentials = load_credentials()
    snapshot_client, snapshot, login_user = pick_snapshot_client(room_code, credentials)
    if not snapshot_client or not snapshot:
        return {
            "success": False,
            "message": "无法获取对局快照。请确认 game_coach_game 已启动，且房间号有效。",
        }

    turn_username = get_turn_username(snapshot)
    if not turn_username:
        return {"success": False, "message": "快照中缺少当前回合玩家信息。"}

    password = credentials.get(turn_username)
    if not password:
        return {
            "success": False,
            "message": f"找不到当前回合玩家 {turn_username} 的密码，无法调用 evaluate_move。",
        }

    eval_client = CoachClient(COACH_BASE_URL)
    login_resp = eval_client.login(turn_username, password)
    if not login_resp.get("success"):
        return {"success": False, "message": f"回合玩家登录失败: {turn_username}"}

    candidates = build_candidates(snapshot)
    if not candidates:
        return {"success": False, "message": "当前棋盘没有可用落子位置。"}

    attempts: List[Dict[str, Any]] = []
    selected = None
    selected_eval = None

    for candidate in candidates[:80]:
        eval_resp = eval_client.evaluate_move(
            room_code=room_code,
            row=candidate.row,
            col=candidate.col,
            value=candidate.value,
        )
        evaluation = eval_resp.get("evaluation")
        if not eval_resp.get("success") or not isinstance(evaluation, dict):
            attempts.append(
                {
                    "candidate": {
                        "row": candidate.row,
                        "col": candidate.col,
                        "value": candidate.value,
                    },
                    "status": "error",
                    "message": eval_resp.get("message", "evaluate_move 请求失败"),
                }
            )
            continue

        is_legal = bool(evaluation.get("isLegal"))
        attempts.append(
            {
                "candidate": {
                    "row": candidate.row,
                    "col": candidate.col,
                    "value": candidate.value,
                },
                "status": "legal" if is_legal else "illegal",
                "reason": evaluation.get("reason"),
                "reasonCode": evaluation.get("reasonCode"),
            }
        )

        if is_legal:
            selected = candidate
            selected_eval = evaluation
            break

    if not selected or not selected_eval:
        return {
            "success": False,
            "message": "已尝试多组候选方案，但都不合法。",
            "snapshot": build_snapshot_brief(snapshot),
            "attempts": attempts,
            "snapshotLoginUser": login_user,
            "evaluateLoginUser": turn_username,
        }

    reason, risk, confidence = build_reason_and_risk(snapshot, selected, selected_eval)
    suggestion = {
        "position": {"row": selected.row, "col": selected.col},
        "value": selected.value,
        "reason": reason,
        "confidence": confidence,
        "risk": risk,
    }
    return {
        "success": True,
        "snapshot": build_snapshot_brief(snapshot),
        "suggestion": suggestion,
        "evaluation": selected_eval,
        "attemptCount": len(attempts),
        "snapshotLoginUser": login_user,
        "evaluateLoginUser": turn_username,
        "attempts": attempts,
    }


@app.route("/")
def index() -> str:
    return render_template("index.html")


@app.route("/api/suggest", methods=["POST"])
def suggest() -> Any:
    payload = request.get_json(silent=True) or {}
    room_code = str(payload.get("roomCode", "")).strip()
    if not room_code:
        return jsonify({"success": False, "message": "roomCode 不能为空。"}), 400
    result = generate_suggestion(room_code)
    return jsonify(result), (200 if result.get("success") else 400)


if __name__ == "__main__":
    app.run(debug=True, port=5050)

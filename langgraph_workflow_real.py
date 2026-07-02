"""
多智能體協作工作流（真實 API 版本）

架構與 langgraph_workflow.py（骨架版）完全相同，差別只在於：
- search_node  改為真正呼叫 Gemini API
- planner_node 改為真正呼叫 Claude API（claude-opus-4-8，開啟 adaptive thinking）
- coder_node   改為真正呼叫 Claude API
- reviewer_node 改為「靜態檢查（語法 / 執行期錯誤）+ Claude 結構化審查」的組合

執行前請確認環境變數已設定：
    ANTHROPIC_API_KEY
    GEMINI_API_KEY
"""

import json
import os
import re
from typing import TypedDict, Literal

import anthropic
from google import genai
from langgraph.graph import StateGraph, END


# ---------------------------------------------------------------------------
# 全域設定與 Client 初始化
# ---------------------------------------------------------------------------
CLAUDE_MODEL = "claude-opus-4-8"
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
MAX_REVISIONS = 3

claude_client = anthropic.Anthropic()   # 讀取 ANTHROPIC_API_KEY
gemini_client = genai.Client()          # 讀取 GEMINI_API_KEY


# ---------------------------------------------------------------------------
# 狀態定義（Shared State）—— 與骨架版完全相同
# ---------------------------------------------------------------------------
class AgentState(TypedDict):
    user_request: str      # 原始需求
    search_context: str    # Gemini 找來的參考資料
    spec_draft: str        # Claude 產出的規格書
    generated_code: str    # Claude 產出的程式碼
    error_log: str         # 驗證失敗時的錯誤訊息
    revision_count: int    # 重試次數，上限為 3 次


# ---------------------------------------------------------------------------
# 小工具函式
# ---------------------------------------------------------------------------
def extract_text(response) -> str:
    """從 Claude 回應中取出第一個 text 區塊（跳過 thinking 區塊）。"""
    for block in response.content:
        if block.type == "text":
            return block.text
    return ""


def extract_code_block(text: str) -> str:
    """把 Claude 回應中的 ```python ... ``` 區塊抽出來；沒有標記就整段回傳。"""
    match = re.search(r"```(?:python)?\s*\n(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text.strip()


# ---------------------------------------------------------------------------
# 節點 1：search_node（真正呼叫 Gemini）
# ---------------------------------------------------------------------------
def search_node(state: AgentState) -> AgentState:
    print(f"\n[search_node / Gemini] 正在針對需求進行資料搜尋：{state['user_request']!r}")

    prompt = (
        "針對以下開發需求，整理一份精簡的技術背景資料，內容包含：\n"
        "1. 建議使用的 Python 版本與相關函式庫\n"
        "2. 實作時常見的陷阱或邊界條件\n"
        "3. 效能或安全性上需要注意的地方\n"
        "不要撰寫程式碼，只要條列式的背景資訊。用繁體中文回答。\n\n"
        f"需求：{state['user_request']}"
    )

    response = gemini_client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
    )
    search_context = response.text or ""

    print("[search_node / Gemini] 搜尋完成，已產出參考資料。")
    return {"search_context": search_context}


# ---------------------------------------------------------------------------
# 節點 2：planner_node（真正呼叫 Claude —— 大腦，邏輯推演）
# ---------------------------------------------------------------------------
def planner_node(state: AgentState) -> AgentState:
    print("\n[planner_node / Claude] 讀取需求與搜尋結果，開始規劃系統規格...")

    user_message = (
        f"原始需求：\n{state['user_request']}\n\n"
        f"技術參考資料（來自前置搜尋）：\n{state['search_context']}\n\n"
        "請根據以上內容，產出一份明確、可直接交給工程師實作的系統規格書，須包含：\n"
        "- 函式 / 類別簽名（含型別標註）\n"
        "- 輸入與輸出格式\n"
        "- 需要處理的邊界條件與例外狀況\n"
        "- 驗收標準\n"
        "用繁體中文撰寫。"
    )

    response = claude_client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=4096,
        thinking={"type": "adaptive"},
        output_config={"effort": "high"},
        messages=[{"role": "user", "content": user_message}],
    )

    spec_draft = extract_text(response)
    print("[planner_node / Claude] 規格書產出完成。")
    return {"spec_draft": spec_draft}


# ---------------------------------------------------------------------------
# 節點 3：coder_node（真正呼叫 Claude —— 依規格撰寫程式碼）
# ---------------------------------------------------------------------------
def coder_node(state: AgentState) -> AgentState:
    current_count = state["revision_count"]
    print(f"\n[coder_node / Claude] 開始撰寫程式碼（第 {current_count + 1} 次嘗試）...")

    revision_note = ""
    if state.get("error_log"):
        print(f"[coder_node / Claude] 收到上一輪錯誤訊息，將據此修正：{state['error_log']}")
        revision_note = (
            f"\n\n上一版程式碼未通過驗證，錯誤如下：\n{state['error_log']}\n\n"
            f"上一版程式碼：\n{state['generated_code']}\n\n"
            "請修正上述問題後重新產出完整程式碼。"
        )

    user_message = (
        f"請根據以下系統規格書撰寫 Python 程式碼：\n\n{state['spec_draft']}{revision_note}\n\n"
        "只回傳完整可執行的程式碼（放在 ```python``` 區塊內），不要額外說明文字。"
    )

    response = claude_client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=4096,
        thinking={"type": "adaptive"},
        output_config={"effort": "high"},
        messages=[{"role": "user", "content": user_message}],
    )

    raw_text = extract_text(response)
    code = extract_code_block(raw_text)

    print("[coder_node / Claude] 程式碼產出完成。")
    return {
        "generated_code": code,
        "revision_count": current_count + 1,
    }


# ---------------------------------------------------------------------------
# 節點 4：reviewer_node（靜態檢查 + Claude 結構化審查）
# ---------------------------------------------------------------------------
REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "passed": {"type": "boolean", "description": "程式碼是否完全符合規格書要求"},
        "issues": {
            "type": "string",
            "description": "若 passed 為 false，說明具體問題；若為 true，可留空字串",
        },
    },
    "required": ["passed", "issues"],
    "additionalProperties": False,
}


def reviewer_node(state: AgentState) -> AgentState:
    print("\n[reviewer_node] 正在驗證程式碼...")
    code = state["generated_code"]

    # 第一階段：靜態語法檢查
    try:
        compile(code, "<generated_code>", "exec")
    except SyntaxError as exc:
        error_message = f"語法錯誤：{exc}"
        print(f"[reviewer_node] [FAIL] {error_message}")
        return {"error_log": error_message}

    # 第二階段：載入期錯誤檢查（import 錯誤、NameError 等）
    try:
        namespace: dict = {}
        exec(code, namespace)
    except Exception as exc:
        error_message = f"載入程式碼時發生錯誤：{type(exc).__name__}: {exc}"
        print(f"[reviewer_node] [FAIL] {error_message}")
        return {"error_log": error_message}

    # 第三階段：交給 Claude 對照規格書做語意層級的審查
    review_prompt = (
        f"系統規格書：\n{state['spec_draft']}\n\n"
        f"實際程式碼：\n{code}\n\n"
        "請檢查這段程式碼是否完整符合規格書的所有要求，特別注意邊界條件與例外處理是否遺漏。"
    )

    response = claude_client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1024,
        output_config={
            "effort": "medium",
            "format": {"type": "json_schema", "schema": REVIEW_SCHEMA},
        },
        messages=[{"role": "user", "content": review_prompt}],
    )

    result_text = extract_text(response)
    result = json.loads(result_text)

    if not result["passed"]:
        error_message = f"語意審查未通過：{result['issues']}"
        print(f"[reviewer_node] [FAIL] {error_message}")
        return {"error_log": error_message}

    print("[reviewer_node] [PASS] 程式碼驗證通過，沒有發現問題。")
    return {"error_log": ""}


# ---------------------------------------------------------------------------
# 條件路由（Conditional Edge）—— 與骨架版邏輯相同
# ---------------------------------------------------------------------------
def route_after_review(state: AgentState) -> Literal["retry", "end"]:
    has_error = bool(state["error_log"])
    revision_count = state["revision_count"]

    if has_error and revision_count < MAX_REVISIONS:
        print(
            f"[route_after_review] 發現錯誤，且重試次數 {revision_count} < 上限 {MAX_REVISIONS}，"
            "退回 coder_node 重寫。"
        )
        return "retry"

    if has_error:
        print(
            f"[route_after_review] 已達重試上限（{MAX_REVISIONS} 次），"
            "即使仍有錯誤也結束流程。"
        )
    else:
        print("[route_after_review] 驗證通過，流程結束。")

    return "end"


# ---------------------------------------------------------------------------
# 建立 StateGraph
# ---------------------------------------------------------------------------
def build_graph():
    builder = StateGraph(AgentState)

    builder.add_node("search_node", search_node)
    builder.add_node("planner_node", planner_node)
    builder.add_node("coder_node", coder_node)
    builder.add_node("reviewer_node", reviewer_node)

    builder.set_entry_point("search_node")
    builder.add_edge("search_node", "planner_node")
    builder.add_edge("planner_node", "coder_node")
    builder.add_edge("coder_node", "reviewer_node")

    builder.add_conditional_edges(
        "reviewer_node",
        route_after_review,
        {
            "retry": "coder_node",
            "end": END,
        },
    )

    return builder.compile()


# ---------------------------------------------------------------------------
# 主程式
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    task = " ".join(sys.argv[1:]) or "寫一個計算整數列表總和與平均值的函式"

    graph = build_graph()

    initial_state: AgentState = {
        "user_request": task,
        "search_context": "",
        "spec_draft": "",
        "generated_code": "",
        "error_log": "",
        "revision_count": 0,
    }

    print("=" * 70)
    print("開始執行多智能體協作工作流（真實 API）")
    print("=" * 70)

    final_state = graph.invoke(initial_state)

    print("\n" + "=" * 70)
    print("流程結束，最終狀態：")
    print("=" * 70)
    print(f"重試次數（revision_count）: {final_state['revision_count']}")
    print(f"最終錯誤訊息（error_log）: {final_state['error_log'] or '(無)'}")
    print("\n最終程式碼（generated_code）:\n")
    print(final_state["generated_code"])

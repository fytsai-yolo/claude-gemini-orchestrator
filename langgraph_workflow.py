"""
多智能體協作工作流骨架（LangGraph StateGraph）

目的：先驗證 Graph 的連線（Edges）、狀態更新（State Mutation）、
條件路由（Conditional Routing）是否正確運作。
所有節點目前都用 print + 假資料模擬 LLM 輸出，尚未串接真實的
Google GenAI / Anthropic API。
"""

from typing import TypedDict, Literal

from langgraph.graph import StateGraph, END


# ---------------------------------------------------------------------------
# 狀態定義（Shared State）
# ---------------------------------------------------------------------------
# 所有節點共用同一份狀態，每個節點回傳的 dict 會被 LangGraph 合併進整體狀態。
class AgentState(TypedDict):
    user_request: str      # 原始需求（使用者輸入）
    search_context: str    # Gemini 找來的參考資料
    spec_draft: str        # Claude 產出的規格書
    generated_code: str    # Claude 產出的程式碼
    error_log: str         # 驗證失敗時的錯誤訊息（空字串代表沒有錯誤）
    revision_count: int    # 重試次數，上限為 3 次


MAX_REVISIONS = 3


# ---------------------------------------------------------------------------
# 節點 1：search_node（Gemini 負責 —— 前線資料搜尋）
# ---------------------------------------------------------------------------
def search_node(state: AgentState) -> AgentState:
    """
    讀取使用者的初步需求，模擬 Gemini 進行資料搜尋 / 技術盤點，
    輸出「環境與技術參考資料」。
    """
    print(f"\n[search_node / Gemini] 正在針對需求進行資料搜尋：{state['user_request']!r}")

    # --- 這裡未來會換成真實的 Gemini API 呼叫 ---
    mock_search_result = (
        "【模擬技術盤點結果】\n"
        "- 建議使用 Python 3.11+\n"
        "- 相關函式庫：pandas, requests\n"
        "- 常見陷阱：型別轉換錯誤、None 處理"
    )

    print("[search_node / Gemini] 搜尋完成，已產出參考資料。")
    return {"search_context": mock_search_result}


# ---------------------------------------------------------------------------
# 節點 2：planner_node（Claude 負責 —— 大腦，邏輯推演）
# ---------------------------------------------------------------------------
def planner_node(state: AgentState) -> AgentState:
    """
    讀取原始需求與 Gemini 的參考資料，模擬 Claude 進行嚴謹的
    邏輯推演，產出明確的「系統規格書（Spec）」。
    """
    print("\n[planner_node / Claude] 讀取需求與搜尋結果，開始規劃系統規格...")
    print(f"[planner_node / Claude] 參考資料摘要：{state['search_context'][:40]}...")

    # --- 這裡未來會換成真實的 Claude API 呼叫 ---
    mock_spec = (
        "【模擬系統規格書】\n"
        f"需求：{state['user_request']}\n"
        "函式簽名：def process(data: list[int]) -> dict\n"
        "輸入：整數列表\n"
        "輸出：包含 sum / avg 的 dict\n"
        "邊界條件：空列表需回傳 sum=0, avg=0"
    )

    print("[planner_node / Claude] 規格書產出完成。")
    return {"spec_draft": mock_spec}


# ---------------------------------------------------------------------------
# 節點 3：coder_node（Claude 負責 —— 依規格撰寫程式碼）
# ---------------------------------------------------------------------------
def coder_node(state: AgentState) -> AgentState:
    """
    根據 Planner 的 Spec（以及上一輪 reviewer 的錯誤訊息，如果有的話）
    模擬 Claude 撰寫 / 修正 Python 程式碼。

    為了讓這個骨架能實際演練「reviewer 退回 -> coder 重寫」的迴圈，
    這裡刻意讓前兩次產出「有瑕疵」的程式碼，第三次（revision_count >= 2）
    才產出「正確」的程式碼，藉此驗證條件路由是否正常運作。
    """
    current_count = state["revision_count"]
    print(f"\n[coder_node / Claude] 開始撰寫程式碼（第 {current_count + 1} 次嘗試）...")

    if state.get("error_log"):
        print(f"[coder_node / Claude] 收到上一輪錯誤訊息，將據此修正：{state['error_log']}")

    # --- 這裡未來會換成真實的 Claude API 呼叫 ---
    if current_count < 2:
        # 模擬前兩次故意留下瑕疵（缺少空列表防呆），觸發 reviewer 退回
        mock_code = (
            "def process(data: list[int]) -> dict:\n"
            "    # TODO_BUG: 沒有處理空列表，除以零會噴錯\n"
            "    total = sum(data)\n"
            "    avg = total / len(data)\n"
            "    return {'sum': total, 'avg': avg}\n"
        )
    else:
        # 第三次（第三輪嘗試）修正完成
        mock_code = (
            "def process(data: list[int]) -> dict:\n"
            "    total = sum(data)\n"
            "    avg = total / len(data) if data else 0\n"
            "    return {'sum': total, 'avg': avg}\n"
        )

    print("[coder_node / Claude] 程式碼產出完成。")
    return {
        "generated_code": mock_code,
        "revision_count": current_count + 1,
    }


# ---------------------------------------------------------------------------
# 節點 4：reviewer_node（驗證節點）
# ---------------------------------------------------------------------------
def reviewer_node(state: AgentState) -> AgentState:
    """
    檢查 coder_node 產出的程式碼是否符合基本規範或報錯。
    這裡用一個簡單的字串標記（TODO_BUG）來模擬「靜態檢查發現問題」。
    未來可以換成真的 lint / 單元測試 / 執行驗證。
    """
    print("\n[reviewer_node] 正在驗證程式碼...")
    code = state["generated_code"]

    if "TODO_BUG" in code:
        error_message = "驗證失敗：偵測到未處理的邊界條件（空列表除以零風險）"
        print(f"[reviewer_node] [FAIL] {error_message}")
        return {"error_log": error_message}

    print("[reviewer_node] [PASS] 程式碼驗證通過，沒有發現問題。")
    return {"error_log": ""}  # 清空錯誤訊息，代表這一輪驗證通過


# ---------------------------------------------------------------------------
# 條件路由（Conditional Edge）：決定 reviewer 之後要去哪裡
# ---------------------------------------------------------------------------
def route_after_review(state: AgentState) -> Literal["retry", "end"]:
    """
    路由邏輯：
    - 如果 reviewer 發現錯誤，且重試次數還沒到上限 -> 退回 coder_node 重寫
    - 如果驗證通過，或重試次數已達上限 -> 結束流程（END）
    """
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
# 建立 StateGraph：把節點與邊組裝起來
# ---------------------------------------------------------------------------
def build_graph():
    builder = StateGraph(AgentState)

    # 註冊四個節點
    builder.add_node("search_node", search_node)
    builder.add_node("planner_node", planner_node)
    builder.add_node("coder_node", coder_node)
    builder.add_node("reviewer_node", reviewer_node)

    # 設定進入點：流程一律從 search_node 開始
    builder.set_entry_point("search_node")

    # 線性流程：search -> planner -> coder -> reviewer
    builder.add_edge("search_node", "planner_node")
    builder.add_edge("planner_node", "coder_node")
    builder.add_edge("coder_node", "reviewer_node")

    # 條件路由：reviewer_node 之後根據 route_after_review 的回傳值分岔
    #   "retry" -> 退回 coder_node 重寫
    #   "end"   -> 進入 END，流程結束
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
# 主程式：實際執行一次完整流程
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    graph = build_graph()

    # 初始狀態：只有 user_request 有值，其餘欄位先給預設值
    initial_state: AgentState = {
        "user_request": "寫一個計算整數列表總和與平均值的函式",
        "search_context": "",
        "spec_draft": "",
        "generated_code": "",
        "error_log": "",
        "revision_count": 0,
    }

    print("=" * 70)
    print("開始執行多智能體協作工作流")
    print("=" * 70)

    final_state = graph.invoke(initial_state)

    print("\n" + "=" * 70)
    print("流程結束，最終狀態：")
    print("=" * 70)
    print(f"重試次數（revision_count）: {final_state['revision_count']}")
    print(f"最終錯誤訊息（error_log）: {final_state['error_log'] or '(無)'}")
    print("最終程式碼（generated_code）:")
    print(final_state["generated_code"])

# CLAUDE.md

給 Claude Code 在這個專案目錄工作時的預設行為準則。

## 專案是什麼

這個 repo 探索「Claude 當大腦、Gemini 當寫手」的協作模式，有兩種實作方式：

1. **獨立腳本版**（`orchestrator.py`、`langgraph_workflow.py`、`langgraph_workflow_real.py`）
   用 LangGraph StateGraph 寫成的獨立程式，會呼叫 Anthropic API + Gemini API。
   **保留作為參考**，但這會產生額外的 Anthropic API 費用（跟 Claude Code 本身的
   Pro/Max 訂閱是分開計費的）。除非使用者明確要求跑這些檔案或要做成可獨立部署 /
   排程執行的服務，否則不要主動執行它們。

2. **互動式協作模式**（`gemini_call.py`）—— **這是預設、優先使用的模式**。
   Claude Code（也就是你）本身直接扮演「大腦」，不需要額外的 Anthropic API 呼叫。
   需要寫程式碼時，透過 Bash 呼叫 `gemini_call.py` 把工作委派給 Gemini，
   自己審查、驗證、必要時要求 Gemini 重寫。

## 預設工作流程（互動式協作模式）

當使用者要求「寫程式碼」、「幫我實作 XXX」這類任務時，依以下步驟進行：

1. **規劃 spec**：把需求轉換成明確的規格 —— 函式/類別簽名、輸入輸出、邊界條件、
   驗收標準。規格要完整到 Gemini 不需要額外猜測就能寫出正確程式碼。

2. **委派給 Gemini**：透過 Bash 呼叫

   ```bash
   python gemini_call.py "<完整的 spec>"
   ```

   spec 太長時先寫進暫存檔案，改用 `python gemini_call.py --file spec.txt`。

3. **審查 + 實測**：不要只用眼睛看程式碼就相信它是對的。
   - 讀程式碼，對照 spec 檢查邏輯、邊界條件、型別
   - 實際寫測試案例並用 Bash 執行，特別是邊界情況（空輸入、極端值、錯誤輸入）
   - 有語法錯誤或執行期錯誤，一定要先抓出來

4. **不滿意就重來**：如果程式碼有問題，把具體錯誤訊息或不符合規格之處寫進新的 spec，
   再呼叫一次 `gemini_call.py`。不要無限重試 —— 大約 2-3 次修正後仍不理想，
   就自己動手修正或如實告知使用者哪裡有困難。

5. **交付**：確認測試通過後，把最終程式碼交給使用者，簡短說明做了什麼、
   驗證過哪些案例。不需要展示中間失敗的版本，除非使用者要求。

## 模型與成本注意事項

- **`GEMINI_API_KEY`**：`gemini_call.py` 預設用 `gemini-2.5-flash`（免費層有額度）。
  **不要**改用 `gemini-2.5-pro`，除非使用者確認自己有付費方案 ——
  免費層對 `gemini-2.5-pro` 的配額是 0，會直接 429 報錯。
- 不需要 `ANTHROPIC_API_KEY` 就能完成上述互動式工作流，因為「大腦」的推理
  已經包含在 Claude Code 的 Pro/Max 訂閱裡。只有要跑獨立腳本版
  （`orchestrator.py` / `langgraph_workflow_real.py`）時才需要它。

## 環境備忘

- Windows 環境跑 Python 印中文/emoji 容易遇到 `cp950` 編碼錯誤，
  執行有中文輸出的腳本時記得帶上：
  ```bash
  PYTHONUTF8=1 PYTHONIOENCODING=utf-8 python <script>.py
  ```
- 套件安裝到系統 Python 目錄（`C:\Python311`）常因權限問題失敗，
  改用 `pip install --user <package>`。
- git 的 credential helper 是 `gh auth git-credential`（已透過
  `gh auth setup-git` 設定），push 使用帳號 `fytsai-yolo`。

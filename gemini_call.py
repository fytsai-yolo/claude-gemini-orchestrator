"""
輕量 Gemini 呼叫工具 —— 給 Claude Code 直接透過 Bash 呼叫用。

設計理念：
Claude Code（也就是你正在對話的這個工具）本身跑在你的 Pro/Max 訂閱裡，
不需要另外付 Anthropic API 的錢。所以「大腦」的角色直接由 Claude Code
扮演即可，不需要再寫一個獨立的 Python 程式去呼叫 Claude API。

這支腳本純粹只負責一件事：把 spec 丟給 Gemini，印出它的回覆。
沒有任何 Claude / Anthropic 相關的程式碼。

用法：
    python gemini_call.py "你的 spec 或問題內容"

    # 或從檔案讀取較長的 spec：
    python gemini_call.py --file spec.txt

    # 指定模型（預設 gemini-2.5-flash，免費層額度足夠；
    # gemini-2.5-pro 目前免費層配額為 0，需要付費方案才能用）：
    python gemini_call.py "..." --model gemini-2.5-pro
"""

import argparse
import os
import sys

from google import genai


def main() -> None:
    parser = argparse.ArgumentParser(description="呼叫 Gemini API 並印出回覆文字")
    parser.add_argument("spec", nargs="?", help="要傳給 Gemini 的內容（spec / prompt）")
    parser.add_argument("--file", "-f", help="從檔案讀取 spec 內容（會覆蓋 spec 參數）")
    parser.add_argument(
        "--model",
        "-m",
        default=os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"),
        help="要使用的 Gemini 模型（預設 gemini-2.5-flash）",
    )
    args = parser.parse_args()

    if args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            spec = f.read()
    elif args.spec:
        spec = args.spec
    else:
        parser.error("請提供 spec 內容，或用 --file 指定檔案")
        return

    client = genai.Client()  # 讀取 GEMINI_API_KEY 環境變數

    try:
        response = client.models.generate_content(model=args.model, contents=spec)
    except Exception as exc:  # noqa: BLE001 -- 讓呼叫端（Claude Code）看得懂錯誤原因
        print(f"[gemini_call error] {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)

    print(response.text or "")


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""Phase 1: Text -> Gloss. API key from apiKey.txt in same dir."""

import json
import os
import re

import openai

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_API_KEY_PATH = os.path.join(_SCRIPT_DIR, "apiKey.txt")

SYSTEM_PROMPT = """你是一个中国手语(CSL)的语序转换专家。任务：把用户输入的中文句子转成「手语词(Gloss)序列」。

规则：
1. 手语有独立语序，不是字对字翻译。常见规律：时间词常前移(明天/今天/昨天先打)；疑问词或重点后置；主语+话题+谓语顺序与中文可能不同。
2. 输出只能是 Gloss 序列：用中文词表示每个手语动作单元，词与词之间用逗号分隔，整体用 JSON 数组格式，不要解释、不要标点句号问号在词内。
3. 每个词对应一个手语手势，保持词粒度为「手语词」而非单字拆碎（如「看病」保持为一个词，「北京」保持为一个词，除非该手语习惯拆成两个手势）。
4. 若句子含疑问，不在词列表里加「吗」「呢」，用语序和后续表情表示疑问。

只输出一个 JSON 数组，例如：["明天","我","去","北京","看病"]"""

FEW_SHOT_USER = """请将以下中文转为中国手语 Gloss 序列，只输出 JSON 数组。

示例：
- 输入：我明天去北京看病 → 输出：["明天","我","去","北京","看病"]
- 输入：你叫什么名字 → 输出：["你","名字","什么"]
- 输入：今天天气很好 → 输出：["今天","天气","很","好"]
- 输入：他昨天去了医院 → 输出：["昨天","他","去","了","医院"]

请对下面句子输出 Gloss：
"""


def _load_api_key():
    with open(_API_KEY_PATH, "r", encoding="utf-8") as f:
        return f.read().strip()


def _call_llm(api_key: str, user_text: str, api_base: str = "https://chat.d.run/v1") -> str:
    openai.api_key = api_key
    openai.api_base = api_base
    response = openai.ChatCompletion.create(
        model="public/deepseek-v3",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": FEW_SHOT_USER + user_text},
        ],
        temperature=0.2,
    )
    return response.choices[0].message["content"].strip()


def _parse_gloss_list(raw: str) -> list[str]:
    raw = raw.strip()
    s = re.search(r"\[[\s\S]*?\]", raw)
    if not s:
        raise ValueError("no JSON array in response")
    return json.loads(s.group())


MOCK_GLOSS = ["明天", "我", "去", "北京", "看病"]


def _mock_gloss(_text: str) -> list[str]:
    return MOCK_GLOSS.copy()


def text_to_gloss(text: str, api_base: str = "https://chat.d.run/v1", use_mock: bool = None) -> list[str]:
    if use_mock is None:
        use_mock = os.environ.get("TEXT_TO_GLOSS_MOCK", "").lower() in ("1", "true", "yes")
    if use_mock:
        return _mock_gloss(text)
    try:
        api_key = _load_api_key()
        reply = _call_llm(api_key, text, api_base)
        return _parse_gloss_list(reply)
    except (openai.error.APIError, openai.error.PermissionError, openai.error.AuthenticationError):
        return _mock_gloss(text)


if __name__ == "__main__":
    t = "我明天去北京看病"
    gloss = text_to_gloss(t, use_mock=True)
    print(t, "->", gloss)

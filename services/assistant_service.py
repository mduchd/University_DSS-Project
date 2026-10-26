"""Grounded admission-advice chat backed by DeepSeek."""

from __future__ import annotations

import os
import re
import json
from typing import Any, Iterator

import pandas as pd
import requests

from services.data_repository import data_repo

DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
MAX_MESSAGE_LENGTH = 1_000
MAX_HISTORY_MESSAGES = 6


class AssistantError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _text(value: Any) -> str:
    return str(value or "").strip()


def _profile_context(profile: object) -> tuple[str, str | None, float | None]:
    if not isinstance(profile, dict):
        return "Chưa có hồ sơ điểm hoặc sở thích.", None, None
    combination = _text(profile.get("combination")).upper()
    scores = profile.get("scores") if isinstance(profile.get("scores"), dict) else {}
    interests = profile.get("interests") if isinstance(profile.get("interests"), list) else []
    values: list[float] = []
    for value in scores.values():
        try:
            number = float(value)
            if 0 <= number <= 10:
                values.append(number)
        except (TypeError, ValueError):
            continue
    total = round(sum(values), 2) if len(values) == 3 else None
    parts = [f"Tổ hợp: {combination or 'chưa chọn'}."]
    if total is not None:
        parts.append(f"Tổng điểm 3 môn: {total:.2f}/30.")
    if interests:
        parts.append("Sở thích: " + "; ".join(_text(item) for item in interests[:2] if _text(item)) + ".")
    return " ".join(parts), combination or None, total


def _admission_context(question: str, combination: str | None, score: float | None) -> list[dict[str, str]]:
    dataframe = data_repo.get_master_data()
    if dataframe.empty:
        return []
    filtered = dataframe.copy()
    if combination and "subject_combination" in filtered:
        filtered = filtered[filtered["subject_combination"].astype(str).str.upper() == combination]

    searchable = filtered[[column for column in ("university_name", "major_name", "major_group_name") if column in filtered]].fillna("").astype(str).agg(" ".join, axis=1)
    tokens = [token for token in re.findall(r"[\wÀ-ỹ]{3,}", question.casefold()) if token not in {"nganh", "truong", "diem", "minh", "ban", "cho", "voi"}]
    if tokens:
        mask = pd.Series(False, index=filtered.index)
        normalized = searchable.str.casefold()
        for token in tokens[:5]:
            mask |= normalized.str.contains(token, regex=False, na=False)
        if mask.any():
            filtered = filtered[mask]

    cutoff_column = "cutoff_score_30" if "cutoff_score_30" in filtered else "cutoff_score"
    if cutoff_column in filtered:
        filtered[cutoff_column] = pd.to_numeric(filtered[cutoff_column], errors="coerce")
        filtered = filtered.dropna(subset=[cutoff_column])
        if score is not None:
            filtered = filtered.assign(_distance=(filtered[cutoff_column] - score).abs()).sort_values("_distance")
        else:
            filtered = filtered.sort_values(cutoff_column, ascending=False)

    fields = ["university_name", "major_name", "subject_combination", cutoff_column, "year"]
    available = [field for field in fields if field in filtered]
    return [
        {field: _text(row.get(field)) for field in available}
        for row in filtered.head(8).to_dict(orient="records")
    ]


def _job_context() -> list[dict[str, str]]:
    dataframe = data_repo.get_job_market_data()
    if dataframe.empty:
        return []
    return [
        {column: _text(row.get(column)) for column in dataframe.columns[:5]}
        for row in dataframe.head(5).to_dict(orient="records")
    ]


def _history_messages(history: object) -> list[dict[str, str]]:
    if not isinstance(history, list):
        return []
    messages = []
    for item in history[-MAX_HISTORY_MESSAGES:]:
        if not isinstance(item, dict) or item.get("role") not in {"user", "assistant"}:
            continue
        content = _text(item.get("content"))[:MAX_MESSAGE_LENGTH]
        if content:
            messages.append({"role": item["role"], "content": content})
    return messages


def _prepare_request(message: object, profile: object, history: object) -> tuple[list[dict[str, str]], list[dict[str, str]], str]:
    question = _text(message)
    if not question or len(question) > MAX_MESSAGE_LENGTH:
        raise AssistantError(f"Câu hỏi cần có từ 1 đến {MAX_MESSAGE_LENGTH} ký tự.")
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        raise AssistantError("Trợ lý AI chưa được cấu hình.", 503)

    profile_summary, combination, score = _profile_context(profile)
    admissions = _admission_context(question, combination, score)
    system_prompt = """Bạn là trợ lý hướng nghiệp của La bàn Đại học. Trả lời bằng tiếng Việt, ngắn gọn và thực tế.
Chỉ dùng dữ liệu ngữ cảnh được cung cấp cho các số liệu, trường, ngành và điểm chuẩn. Nếu ngữ cảnh không đủ, nói rõ là chưa đủ dữ liệu; không bịa nguồn, điểm chuẩn hoặc chính sách tuyển sinh.
Không được cam kết đỗ đại học. Luôn nhắc rằng đây là tham khảo và người dùng cần kiểm tra đề án tuyển sinh chính thức.
Không yêu cầu số báo danh, số điện thoại, địa chỉ hoặc thông tin nhạy cảm."""
    context_prompt = {
        "profile": profile_summary,
        "admission_records": admissions,
        "job_market_records": _job_context(),
    }
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(_history_messages(history))
    messages.append({"role": "user", "content": f"Ngữ cảnh DSS đã lọc:\n{context_prompt}\n\nCâu hỏi: {question}"})
    return messages, admissions, api_key


def _request_body(messages: list[dict[str, str]], *, stream: bool) -> dict:
    return {
        "model": os.environ.get("DEEPSEEK_MODEL", "deepseek-flash"),
        "messages": messages,
        "max_tokens": 700,
        "thinking": {"type": "disabled"},
        "stream": stream,
    }


def answer_question(message: object, profile: object, history: object) -> dict:
    """Keep the original JSON endpoint available for existing clients."""
    messages, admissions, api_key = _prepare_request(message, profile, history)

    try:
        response = requests.post(
            DEEPSEEK_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=_request_body(messages, stream=False),
            timeout=30,
        )
    except requests.RequestException as error:
        raise AssistantError("Không thể kết nối DeepSeek lúc này.", 503) from error
    if not response.ok:
        raise AssistantError("DeepSeek chưa thể xử lý yêu cầu. Vui lòng thử lại sau.", 503)

    try:
        payload = response.json()
        content = _text(payload["choices"][0]["message"]["content"])
    except (KeyError, IndexError, TypeError, ValueError) as error:
        raise AssistantError("DeepSeek trả về phản hồi không hợp lệ.", 503) from error
    if not content:
        raise AssistantError("DeepSeek chưa tạo được câu trả lời.", 503)
    return {"answer": content, "sources": admissions, "model": payload.get("model", "deepseek-flash")}


def _sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def stream_answer(message: object, profile: object, history: object) -> Iterator[str]:
    """Proxy DeepSeek's SSE deltas without exposing its API key to the browser."""
    messages, admissions, api_key = _prepare_request(message, profile, history)
    try:
        upstream = requests.post(
            DEEPSEEK_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=_request_body(messages, stream=True),
            stream=True,
            timeout=(10, 60),
        )
    except requests.RequestException as error:
        raise AssistantError("Không thể kết nối DeepSeek lúc này.", 503) from error
    if not upstream.ok:
        upstream.close()
        raise AssistantError("DeepSeek chưa thể xử lý yêu cầu. Vui lòng thử lại sau.", 503)

    def generate() -> Iterator[str]:
        received_text = False
        finished = False
        model = os.environ.get("DEEPSEEK_MODEL", "deepseek-flash")
        try:
            yield _sse_event("ready", {})
            for line in upstream.iter_lines(chunk_size=1):
                if isinstance(line, bytes):
                    line = line.decode("utf-8", errors="replace")
                if not line.startswith("data:"):
                    continue  # DeepSeek also sends SSE keep-alive comments.
                data = line[5:].strip()
                if data == "[DONE]":
                    finished = True
                    break
                try:
                    chunk = json.loads(data)
                    model = chunk.get("model") or model
                    delta = chunk.get("choices", [{}])[0].get("delta", {}).get("content")
                except (ValueError, KeyError, IndexError, TypeError, AttributeError):
                    continue
                if isinstance(delta, str) and delta:
                    received_text = True
                    yield _sse_event("delta", {"text": delta})
            if finished and received_text:
                yield _sse_event("done", {"model": model, "sources": admissions})
            elif received_text:
                yield _sse_event("error", {"message": "Kết nối tới DeepSeek bị ngắt trước khi trả lời xong."})
            else:
                yield _sse_event("error", {"message": "DeepSeek chưa tạo được câu trả lời."})
        except requests.RequestException:
            yield _sse_event("error", {"message": "Kết nối tới DeepSeek bị gián đoạn."})
        finally:
            upstream.close()

    return generate()

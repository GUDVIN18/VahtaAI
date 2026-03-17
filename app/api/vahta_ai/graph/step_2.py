from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from app.api.vahta_ai.resources.redis_client import RedisClient
from app.api.vahta_ai.RAG.service import FAQSearchService
from app.api.vaxtarekrut.service import find_jobs
from app.include.config import config

log = logging.getLogger("vahta_ai.step_2")

faq_service = FAQSearchService()

# ─── States ──────────────────────────────────────────────────────────────────

STATE_STEP_2 = "step_2"
STATE_STEP_2_AWAITING_REJECTION = "step_2_awaiting_rejection"
STATE_STEP_2_AWAITING_PASSPORT = "step_2_awaiting_passport"
STATE_STEP_2_DONE = "step_2_done"

# ─── Schema ──────────────────────────────────────────────────────────────────


class Step2Result(BaseModel):
    reply: str
    funnel_state: str
    completed: bool = False
    ready_for_next_step: bool = False


# ─── Prompt ──────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """
Ты - рекрутер Яна. Помогаешь кандидату подобрать вахту и оформить заявку.

ЭТАПЫ:
1. Первое сообщение кандидата = его пожелания. Сразу предложи вакансию.
2. Предлагай по одной вакансии.
3. Не подошла - предложи следующую из списка.
4. Согласен - попроси фото паспорта ОДИН РАЗ.

КАК ПРЕДЛАГАТЬ ВАКАНСИЮ:
Пиши живо, как подруга, которая нашла крутой вариант. НЕ копируй описание - перескажи своими словами.

Структура:
1. Эмоциональный крючок под пожелания кандидата
   Пример: "Смотрите, нашла то, что просили - без ТСД и почти 4000 фикса!"
2. 2-3 конкретных плюса: зарплата, условия труда, проживание/питание, легкость работы
3. Завершение: "Подойдет?" или "Как вам?"

ЕСЛИ ПРОСЯТ ПОДРОБНОСТИ:
Кандидат пишет "расскажи подробнее", "что за работа", "расскажи про неё" и т.п. -
дай ПОЛНОЕ описание: название, ставка, условия труда, проживание, питание, график,
требования по возрасту/полу, особенности объекта. Используй ВСЮ информацию из "Текущая вакансия".
Пиши живо и структурированно.

ПРОЧИЕ ПРАВИЛА:
- Не благодари, не повторяй вопросы
- НИКОГДА не пиши фразы вроде "если нужно больше деталей - дай знать", "если есть вопросы - спрашивай", "готова ответить на вопросы" и подобные. Просто заверши ответ.
- Вопрос по условиям - сначала ответь по FAQ, затем предложи вакансию
- Вакансии закончились - "По этим пожеланиям варианты закончились. Подскажите, что именно изменить в подборе?"

ПРИ СОГЛАСИИ - СТРОГО ДОСЛОВНО:
Для создания заявки мне нужно фото вашего паспорта. Сейчас забронирую место, чтобы точно зафиксировать место за вами.

Пожалуйста, пришлите сразу, т.к. я вижу, что осталось всего три места!
""".strip()

MAIN_PROMPT = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_PROMPT),
    ("human", """
Данные кандидата: {candidate}

Пожелания кандидата: {desired_conditions}

Причины отказа от предыдущих вакансий (ОБЯЗАТЕЛЬНО учитывай при выборе и презентации следующей):
{rejection_reasons}

Текущая вакансия (используй для предложения и подробного описания):
{current_job}

Все доступные вакансии (краткий список для навигации):
{jobs_summary}

FAQ-контекст (используй если кандидат задаёт вопрос по условиям):
{rag_context}

История диалога:
{history}

Новое сообщение от кандидата: {message}
"""),
])


# ─── Candidate → find_jobs kwargs ────────────────────────────────────────────

_CITIZENSHIP_MAP = {
    "рф": "РФ", "россия": "РФ", "беларусь": "Беларусь",
    "казахстан": "Казахстан", "узбекистан": "Узбекистан",
    "таджикистан": "Таджикистан", "киргизия": "Киргизия",
    "армения": "Армения", "азербайджан": "Азербайджан",
    "молдова": "Молдова", "украина": "Украина",
}


def _candidate_to_find_jobs_kwargs(candidate: dict) -> dict:
    """Собирает kwargs для find_jobs из данных кандидата."""
    kwargs: dict = {}
    city = str(candidate.get("city") or "").strip()
    kwargs["region"] = city or "Москва"
    return kwargs


# ─── Service ─────────────────────────────────────────────────────────────────


class Step2Service:
    llm = ChatOpenAI(
        api_key=config.YANDEX_API_KEY,
        model=f"gpt://{config.FOLDER_LLM_YANDEX_ID}/yandexgpt-5-pro/latest",
        base_url="https://ai.api.cloud.yandex.net/v1",
        temperature=0.4,
        top_p=0.9,
    )

    FAQ_TRIGGERS = (
        "?", "аванс", "зарплат", "оплат", "прожив", "общеж", "питани",
        "график", "паспорт", "документ", "самозан", "мед", "договор",
        "штраф", "транспорт", "дорога", "билет", "ночн", "дневн",
    )

    NEXT_JOB_TRIGGERS = ("не подходит", "другую", "ещё", "еще", "следующ", "иной", "другой")

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.redis = RedisClient(session_id=session_id)
        self._state_key = f"ai_step_2_state:{session_id}"
        self._data_key = f"ai_step_2_data:{session_id}"
        self._candidate_key = f"ai_candidate:{session_id}"

    # ── Redis ─────────────────────────────────────────────────────────────────

    def _load(self, key: str) -> dict[str, Any]:
        raw = self.redis.client.get(key)
        if not raw:
            return {}
        try:
            data = json.loads(raw if isinstance(raw, str) else raw.decode())
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _save(self, key: str, data: dict[str, Any]) -> None:
        self.redis.client.setex(key, self.redis.ttl, json.dumps(data, ensure_ascii=False))

    def _get_state(self) -> str | None:
        raw = self.redis.client.get(self._state_key)
        if raw is None:
            return None
        return raw.decode() if isinstance(raw, bytes) else str(raw)

    def _set_state(self, state: str) -> None:
        self.redis.client.setex(self._state_key, self.redis.ttl, state)

    # ── RAG ──────────────────────────────────────────────────────────────────

    def _get_rag_context(self, query: str) -> str:
        if not any(t in query.lower() for t in self.FAQ_TRIGGERS):
            return "Нет релевантного FAQ."
        try:
            results = faq_service.search(query=query, top_k=6)
        except Exception as e:
            log.warning("RAG search failed: %s", e)
            return "Нет релевантного FAQ."

        parts = [
            f"В: {(item.question or '').strip()}\nО: {(item.answer or '').strip()}"
            for item in results
            if float(item.score) >= 0.72 and (item.question or item.answer)
        ]
        return "\n\n".join(parts) or "Нет релевантного FAQ."

    # ── Jobs ─────────────────────────────────────────────────────────────────

    def _fetch_jobs(self, candidate: dict) -> list[dict]:
        kwargs = _candidate_to_find_jobs_kwargs(candidate)
        log.info("find_jobs kwargs: %s", kwargs)
        try:
            jobs = list(asyncio.run(find_jobs(**kwargs)))[:10]
            log.info("find_jobs returned %d jobs", len(jobs))
            return jobs
        except Exception as e:
            log.exception("find_jobs failed: %s", e)
            return []

    @staticmethod
    def _job_to_text(job: dict) -> str:
        if not job:
            return "Вакансия не найдена."
        fields = {
            "Название": job.get("name"),
            "Ставка": f"{job.get('salary_min', '?')}-{job.get('salary_max', '?')} руб.",
            "Нужны мужчины": job.get("men_needed"),
            "Нужны женщины": job.get("women_needed"),
            "Возраст": f"{job.get('age_min', '?')}-{job.get('age_max', '?')} лет",
            "Описание": str(job.get("description") or "")[:1200],
        }
        return "\n".join(f"{k}: {v}" for k, v in fields.items() if v not in (None, "", "?-? лет"))

    @staticmethod
    def _jobs_summary(jobs: list[dict]) -> str:
        if not jobs:
            return "Вакансий нет."
        return "\n".join(
            f"{i+1}. {j.get('name', '?')} | {j.get('salary_min')}-{j.get('salary_max')} руб."
            for i, j in enumerate(jobs)
        )

    # ── Passport ─────────────────────────────────────────────────────────────

    @staticmethod
    def _is_passport(attachment_type: str | None) -> bool:
        return (attachment_type or "").lower() in {"photo", "file"}

    # ── Main ─────────────────────────────────────────────────────────────────

    def run(self, message: str, attachment_type: str | None = None) -> Step2Result:
        candidate = self._load(self._candidate_key)
        data = self._load(self._data_key) or {
            "desired_conditions": None,
            "jobs": [],
            "current_job_index": 0,
            "passport_received": False,
            "rejection_reasons": [],
        }

        # Паспорт - завершаем этап
        if self._is_passport(attachment_type) and not data.get("passport_received"):
            data["passport_received"] = True
            self._save(self._data_key, data)
            self._set_state(STATE_STEP_2_DONE)
            reply = "Отлично, фото получила! Сейчас забронирую место..."
            self.redis.add_message(role="user", message=message)
            self.redis.add_message(role="ai", message=reply)
            return Step2Result(reply=reply, funnel_state=STATE_STEP_2_DONE, completed=True, ready_for_next_step=True)

        # Сохраняем пожелания из первого сообщения (если ещё не сохранены)
        if not data.get("desired_conditions"):
            data["desired_conditions"] = message

        # Загружаем вакансии если их нет — всегда повторяем если jobs пустой
        if not data["jobs"]:
            log.info("Fetching jobs for candidate: %s", candidate)
            data["jobs"] = self._fetch_jobs(candidate)
            data["current_job_index"] = 0
            log.info("Fetched %d jobs", len(data["jobs"]))
            self._save(self._data_key, data)

        jobs: list[dict] = data["jobs"]
        idx: int = data["current_job_index"]
        current_state = self._get_state() or STATE_STEP_2

        # Ждём причину отказа — сохраняем и переключаем вакансию
        if current_state == STATE_STEP_2_AWAITING_REJECTION:
            data.setdefault("rejection_reasons", []).append(message)
            idx = min(idx + 1, len(jobs) - 1)
            data["current_job_index"] = idx
            self._save(self._data_key, data)

        # Явный отказ без причины — спрашиваем что не устроило
        elif any(w in message.lower() for w in self.NEXT_JOB_TRIGGERS) and jobs:
            reply = "Да, конечно, сейчас ещё предложу! Но мне, чтобы понять что предлагать — что именно в этой не подошло?"
            self.redis.add_message(role="user", message=message)
            self.redis.add_message(role="ai", message=reply)
            self._set_state(STATE_STEP_2_AWAITING_REJECTION)
            return Step2Result(reply=reply, funnel_state=STATE_STEP_2_AWAITING_REJECTION)

        current_job = jobs[idx] if 0 <= idx < len(jobs) else {}

        history = "\n".join(
            f"{'Кандидат' if m.type == 'human' else 'Яна'}: {m.content}"
            for m in (self.redis.get_session_history_v2() or [])[-10:]
        )

        reply = self._generate_reply(
            message=message,
            candidate=candidate,
            desired_conditions=data.get("desired_conditions") or "",
            rejection_reasons=data.get("rejection_reasons") or [],
            current_job_text=self._job_to_text(current_job),
            jobs_summary=self._jobs_summary(jobs),
            rag_context=self._get_rag_context(message),
            history=history,
        )

        funnel_state = STATE_STEP_2_AWAITING_PASSPORT if "фото вашего паспорта" in reply else STATE_STEP_2
        self.redis.add_message(role="user", message=message)
        self.redis.add_message(role="ai", message=reply)
        self._set_state(funnel_state)

        return Step2Result(reply=reply, funnel_state=funnel_state)

    def _generate_reply(
        self,
        message: str,
        candidate: dict,
        desired_conditions: str,
        rejection_reasons: list,
        current_job_text: str,
        jobs_summary: str,
        rag_context: str,
        history: str,
    ) -> str:
        rejection_text = (
            "\n".join(f"- {r}" for r in rejection_reasons)
            if rejection_reasons else "Нет."
        )
        try:
            result = (MAIN_PROMPT | self.llm).invoke({
                "candidate": json.dumps(candidate, ensure_ascii=False),
                "desired_conditions": desired_conditions,
                "rejection_reasons": rejection_text,
                "current_job": current_job_text,
                "jobs_summary": jobs_summary,
                "rag_context": rag_context,
                "history": history,
                "message": message,
            })
            return (result.content if hasattr(result, "content") else str(result)).strip()
        except Exception as e:
            log.exception("LLM reply failed: %s", e)
            return f"Смотрите, такой вариант:\n\n{current_job_text}\n\nПодойдет?"


# ─── Public API ───────────────────────────────────────────────────────────────


def run_step_2(session_id: str, message: str, attachment_type: str | None = None) -> Step2Result:
    return Step2Service(session_id=session_id).run(message=message, attachment_type=attachment_type)


if __name__ == "__main__":
    result = run_step_2(session_id="123", message="Без ТСД и от 4000 ставка")
    print(result.model_dump())
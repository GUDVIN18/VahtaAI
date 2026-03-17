from __future__ import annotations

import json
import logging
from typing import Any, Optional

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from openai import ContentFilterFinishReasonError
from pydantic import BaseModel, Field

from app.api.vahta_ai.RAG.service import FAQSearchService
from app.api.vahta_ai.resources.redis_client import RedisClient
from app.include.config import config

log = logging.getLogger("vahta_ai.step_1")

faq_service = FAQSearchService()

# ─── States ──────────────────────────────────────────────────────────────────

STATE_NEW = "new"
STATE_AWAITING_RELEVANCE = "awaiting_relevance"
STATE_COLLECTING = "collecting"
STATE_AWAITING_SELECTION_CONSENT = "awaiting_selection_consent"
STATE_STEP_1_DONE = "step_1_done"
STATE_CLOSED = "closed"

# ─── Static texts (base templates, slightly varied per user via LLM) ───────────

GREETING_TEXT = (
    "Здравствуйте!🤝😊 Вы оставляли отклик на вакансию вахта,\n"
    "на Авито.\n"
    "Работа для Вас еще актуальна?"
)

INTRO_TEXT = (
    "Меня зовут Яна, я - ваш менеджер,\n"
    "так как у нас МНОГО ОБЪЕКТОВ, ответьте, пожалуйста на несколько вопросов, "
    "чтобы подобрать максимально подходящий вам\n\n"
    "Ваше ФИО?"
)

STEP_2_TRANSITION = "А что бы вы хотели? Что вообще рассматриваете?"

VARY_PROMPT = ChatPromptTemplate.from_template(
    "Слегка перефразируй сообщение рекрутера — измени 1-2 слова или порядок слов, "
    "сохрани смысл, тон и все эмодзи. Верни ТОЛЬКО текст сообщения без кавычек и пояснений.\n\n"
    "Сообщение: {text}"
)

# ─── Keyword sets ─────────────────────────────────────────────────────────────

POSITIVE_TRIGGERS = {"да", "актуал", "интерес", "хочу", "готов", "конечно", "подходит"}
NEGATIVE_TRIGGERS = {"нет", "не актуал", "не интерес", "не ищу", "не подходит"}
CONSENT_TRIGGERS = {"давайте", "подберите", "подбирайте", "согласен", "согласна", "хорошо", "можно", "давай", "ок", "окей"}

FAQ_TRIGGERS = (
    "?", "аванс", "зарплат", "оплат", "прожив", "общеж", "питани", "график",
    "договор", "самозан", "медк", "медком", "паспорт", "документ",
    "смен", "вахт", "бригад", "форма", "дорог", "билет", "транспорт",
    "штраф", "выходн", "ночн", "дневн", "регистрац", "судим",
)

# ─── Candidate schema ─────────────────────────────────────────────────────────

FIELD_LABELS: dict[str, str] = {
    "full_name": "ФИО",
    "age": "возраст",
    "citizenship": "гражданство",
    "city": "город",
    "start_date": "дата выезда",
    "experience": "опыт работы",
    "previous_job": "предыдущее место работы",
    "reason_for_change": "причина смены работы",
}

EMPTY_MARKERS = {None, "", "не заполнено", "не указано", "unknown", "null", "-"}


class CandidateSchema(BaseModel):
    full_name: Optional[str] = Field(None)
    age: Optional[int] = Field(None)
    citizenship: Optional[str] = Field(None)
    city: Optional[str] = Field(None)
    start_date: Optional[str] = Field(None)
    experience: Optional[str] = Field(None)
    previous_job: Optional[str] = Field(None)
    reason_for_change: Optional[str] = Field(None)


class Step1Response(BaseModel):
    candidate: CandidateSchema
    reply: str


class Step1Result(BaseModel):
    candidate: dict[str, Any]
    missing_fields: list[str]
    reply: str
    completed: bool
    funnel_state: str
    ready_for_next_step: bool = False


# ─── Prompts ──────────────────────────────────────────────────────────────────

DIALOG_PROMPT = ChatPromptTemplate.from_template("""
Ты рекрутер Яна. Ведешь первичный диалог с кандидатом на вахтовую работу.

ЖЕСТКИЕ ПРАВИЛА:
- Одно сообщение = один короткий ответ + один вопрос.
- Не благодари. Никогда не пиши: "спасибо", "благодарю".
- Не используй: "Понятно", "Хорошо", "Отлично", "Ясно", "Поняла".
- Не обращайся по имени в каждом сообщении.
- Не добавляй вводных фраз перед вопросом — только вопрос.
- Не повторяй уже заполненные поля.
- Незаполненное поле = null, не пиши "не заполнено" или "unknown".
- Пока есть пустые поля — задавай следующий вопрос строго по порядку.
- Не закрывай диалог самостоятельно.
- Если пользователь ответил на причину смены работы — не переспрашивай и не осуждай.
- НИКОГДА не пиши "спасибо", "есть ли у вас вопросы", "готова ответить на вопросы" и подобное.
- НИКОГДА не завершай диалог фразой об окончании — это делает система, не ты.

ПРАВИЛА RAG:
- Если пользователь задал вопрос по условиям — ответь по FAQ-контексту, затем продолжи сбор анкеты.
- Не выдумывай факты, которых нет в FAQ.
- Если FAQ нерелевантен — игнорируй его.

ПОРЯДОК ПОЛЕЙ (строго):
full_name → age → citizenship → city → start_date → experience → previous_job → reason_for_change

Уже собранные данные:
{candidate_snapshot}

Незаполненные поля:
{missing_fields}

История диалога:
{history}

FAQ-контекст:
{rag_context}

Новое сообщение:
{message}

Верни:
- candidate: актуальные данные кандидата
- reply: короткий ответ + один следующий вопрос
""")

FINAL_REASON_PROMPT = ChatPromptTemplate.from_template("""
Ты рекрутер Яна. Кандидат только что рассказал, что его не устроило на прошлой работе.
Это последнее поле анкеты.

Напиши ОДНО короткое сообщение:
- Начни с "Да, КОНЕЧНО ПОНИМАЮ ВАС!" 
- Затем ДОСЛОВНО перечисли проблемы из ответа кандидата (не перефразируй, говори именно то, что он написал)
- Скажи что это неприятно / понятно
- Предложи найти объект который понравится, упомяни что есть выбор
- В конце напиши просто: "Давайте?"

Запрещено:
- "спасибо", "благодарю"
- обращение по имени
- уточняющие вопросы о прошлой работе
- шаблонные фразы

Пример (если кандидат написал "бригадир дебил, платят мало, общага плохая"):
Да, КОНЕЧНО ПОНИМАЮ ВАС! Бригадир дебил, низкие выплаты, плохое общежитие — это конечно неприятно, поэтому давайте найдем объект, который вам понравится! У нас действительно есть выбор.
Давайте?

Причина смены работы: {reason_for_change}

Верни только текст сообщения.
""")


# ─── Service ──────────────────────────────────────────────────────────────────


class Step1Service:
    llm = ChatOpenAI(
        api_key=config.YANDEX_API_KEY,
        model=f"gpt://{config.FOLDER_LLM_YANDEX_ID}/yandexgpt-5-pro/latest",
        base_url="https://ai.api.cloud.yandex.net/v1",
        temperature=0.2,
        top_p=0.9,
    )
    structured_llm = llm.with_structured_output(Step1Response)

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.redis = RedisClient(session_id=session_id)
        self._state_key = f"ai_funnel_state:{session_id}"
        self._candidate_key = f"ai_candidate:{session_id}"

    # ── Redis ─────────────────────────────────────────────────────────────────

    def _get_state(self) -> str | None:
        raw = self.redis.client.get(self._state_key)
        if raw is None:
            return None
        return raw.decode() if isinstance(raw, bytes) else str(raw)

    def _set_state(self, state: str) -> None:
        self.redis.client.setex(self._state_key, self.redis.ttl, state)

    def _load_candidate(self) -> dict[str, Any]:
        raw = self.redis.client.get(self._candidate_key)
        if not raw:
            return {}
        try:
            data = json.loads(raw.decode() if isinstance(raw, bytes) else raw)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _save_candidate(self, candidate: dict[str, Any]) -> None:
        self.redis.client.setex(
            self._candidate_key, self.redis.ttl,
            json.dumps(candidate, ensure_ascii=False),
        )

    # ── Candidate helpers ─────────────────────────────────────────────────────

    def _is_empty(self, value: Any) -> bool:
        if value in EMPTY_MARKERS:
            return True
        return isinstance(value, str) and value.strip().lower() in EMPTY_MARKERS

    def _sanitize(self, candidate: dict[str, Any]) -> dict[str, Any]:
        return {
            k: v.strip() if isinstance(v, str) else v
            for k, v in candidate.items()
            if not self._is_empty(v)
        }

    def _missing_fields(self, candidate: dict[str, Any]) -> list[str]:
        return [f for f in CandidateSchema.model_fields if self._is_empty(candidate.get(f))]

    def _merge(self, old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
        merged = dict(old)
        for k, v in self._sanitize(new).items():
            if not self._is_empty(v):
                merged[k] = v
        return self._sanitize(merged)

    def _candidate_snapshot(self, candidate: dict[str, Any]) -> str:
        if not candidate:
            return "Данные ещё не собраны."
        lines = [
            f"{FIELD_LABELS.get(k, k)}: {candidate.get(k) or 'не заполнено'}"
            for k in CandidateSchema.model_fields
        ]
        return "\n".join(lines)

    def _missing_human(self, missing: list[str]) -> str:
        return ", ".join(FIELD_LABELS.get(f, f) for f in missing) or "Пустых полей нет."

    # ── Intent detection ──────────────────────────────────────────────────────

    def _is_positive(self, message: str) -> bool:
        text = message.strip().lower()
        return any(t in text for t in POSITIVE_TRIGGERS)

    def _is_negative(self, message: str) -> bool:
        text = message.strip().lower()
        return any(t in text for t in NEGATIVE_TRIGGERS)

    def _is_consent(self, message: str) -> bool:
        text = message.strip().lower()
        return any(t in text for t in CONSENT_TRIGGERS)

    # ── RAG ───────────────────────────────────────────────────────────────────

    def _get_rag_context(self, query: str) -> str:
        if not any(t in query.lower() for t in FAQ_TRIGGERS):
            return "FAQ-контекст не найден."
        try:
            results = faq_service.search(query=query, top_k=8)
        except Exception as e:
            log.warning("RAG search failed: %s", e)
            return "FAQ-контекст не найден."

        parts = []
        for i, item in enumerate(results, 1):
            q = (item.question or "").strip()
            a = (item.answer or "").strip()
            if q or a:
                block = f"[FAQ {i}]"
                if getattr(item, "block", None):
                    block += f" {item.block.strip()}"
                parts.append(f"{block}\n{'В: ' + q + chr(10) if q else ''}{'О: ' + a if a else ''}")

        return "\n\n".join(parts) or "FAQ-контекст не найден."

    # ── History ───────────────────────────────────────────────────────────────

    def _history_text(self, history: list) -> str:
        if not history:
            return "История пуста."
        lines = [
            f"{'Пользователь' if isinstance(m, HumanMessage) else 'AI'}: {m.content}"
            for m in history
        ]
        return "\n".join(lines)

    # ── LLM calls ─────────────────────────────────────────────────────────────

    def _collect(self, history: list, message: str) -> Step1Result:
        candidate = self._sanitize(self._load_candidate())
        missing_before = self._missing_fields(candidate)
        rag_context = self._get_rag_context(message)

        invoke_kwargs = {
            "candidate_snapshot": self._candidate_snapshot(candidate),
            "missing_fields": self._missing_human(missing_before),
            "history": self._history_text(history),
            "rag_context": rag_context,
            "message": message,
        }

        try:
            response: Step1Response = (DIALOG_PROMPT | self.structured_llm).invoke(invoke_kwargs)
        except ContentFilterFinishReasonError:
            log.warning("Content filter triggered for message: %s", message)
            response = Step1Response(
                candidate=CandidateSchema(**candidate),
                reply="Поняла. Какой ещё опыт работы у вас был?" if "сво" in message.lower()
                      else self._fallback_reply(invoke_kwargs, candidate),
            )
        except Exception:
            log.exception("LLM invoke failed")
            response = Step1Response(
                candidate=CandidateSchema(**candidate),
                reply="Не поняла ваш ответ, уточните, пожалуйста.",
            )

        new_candidate = response.candidate.model_dump(exclude_none=True)
        merged = self._merge(candidate, new_candidate)
        missing_after = self._missing_fields(merged)

        # Последнее поле заполнено — генерируем переходное сообщение
        if (
            "reason_for_change" in missing_before
            and "reason_for_change" not in missing_after
            and not missing_after
        ):
            reply = self._final_reason_reply(str(merged.get("reason_for_change", "")))
            next_state = STATE_AWAITING_SELECTION_CONSENT
        else:
            reply = response.reply.strip()
            next_state = STATE_COLLECTING

        self.redis.add_message(role="user", message=message)
        self.redis.add_message(role="ai", message=reply)
        self._save_candidate(merged)
        self._set_state(next_state)

        return Step1Result(
            candidate=merged,
            missing_fields=missing_after,
            reply=reply,
            completed=not missing_after,
            funnel_state=next_state,
        )

    def _fallback_reply(self, invoke_kwargs: dict, candidate: dict) -> str:
        try:
            raw = (DIALOG_PROMPT | self.llm).invoke(invoke_kwargs)
            return (raw.content if hasattr(raw, "content") else str(raw)).strip()
        except Exception:
            return "Не поняла ваш ответ, уточните, пожалуйста."

    def _final_reason_reply(self, reason: str) -> str:
        try:
            raw = (FINAL_REASON_PROMPT | self.llm).invoke({"reason_for_change": reason})
            content = (raw.content if hasattr(raw, "content") else str(raw)).strip()
            return content or "Понимаю. Могу подобрать для вас более подходящие варианты."
        except Exception:
            return "Понимаю. Могу подобрать для вас более подходящие варианты."

    def _vary(self, text: str) -> str:
        """Return slightly rephrased version of a static template."""
        try:
            raw = (VARY_PROMPT | self.llm).invoke({"text": text})
            result = (raw.content if hasattr(raw, "content") else str(raw)).strip()
            return result or text
        except Exception:
            return text

    # ── Result builder ────────────────────────────────────────────────────────

    def _build_result(self, reply: str, funnel_state: str, ready_for_next_step: bool = False) -> Step1Result:
        candidate = self._sanitize(self._load_candidate())
        missing = self._missing_fields(candidate)
        return Step1Result(
            candidate=candidate,
            missing_fields=missing,
            reply=reply,
            completed=not missing,
            funnel_state=funnel_state,
            ready_for_next_step=ready_for_next_step,
        )

    # ── Main ──────────────────────────────────────────────────────────────────

    def run(self, message: str) -> Step1Result:
        history = self.redis.get_session_history_v2()
        state = self._get_state() or (STATE_NEW if not history else STATE_COLLECTING)

        log.info("step_1 | state=%s | session=%s | msg=%s", state, self.session_id, message)

        if state == STATE_NEW:
            greeting = self._vary(GREETING_TEXT)
            self.redis.add_message(role="ai", message=greeting)
            self._set_state(STATE_AWAITING_RELEVANCE)
            return Step1Result(
                candidate={},
                missing_fields=list(CandidateSchema.model_fields.keys()),
                reply=greeting,
                completed=False,
                funnel_state=STATE_AWAITING_RELEVANCE,
            )

        if state == STATE_AWAITING_RELEVANCE:
            self.redis.add_message(role="user", message=message)

            if self._is_negative(message):
                reply = "Поняла вас. Если позже снова станет актуально — напишите, подберу подходящие варианты."
                self.redis.add_message(role="ai", message=reply)
                self._set_state(STATE_CLOSED)
                return self._build_result(reply=reply, funnel_state=STATE_CLOSED)

            if self._is_positive(message):
                intro = self._vary(INTRO_TEXT)
                self.redis.add_message(role="ai", message=intro)
                self._set_state(STATE_COLLECTING)
                return self._build_result(reply=intro, funnel_state=STATE_COLLECTING)

            # Непонятный ответ
            reply = "Подскажите, работа ещё актуальна? Ответьте, пожалуйста: да или нет."
            self.redis.add_message(role="ai", message=reply)
            return self._build_result(reply=reply, funnel_state=STATE_AWAITING_RELEVANCE)

        if state == STATE_AWAITING_SELECTION_CONSENT:
            self.redis.add_message(role="user", message=message)

            if self._is_consent(message):
                self.redis.add_message(role="ai", message=STEP_2_TRANSITION)
                self._set_state(STATE_STEP_1_DONE)
                return self._build_result(
                    reply=STEP_2_TRANSITION,
                    funnel_state=STATE_STEP_1_DONE,
                    ready_for_next_step=True,
                )

            reply = "Если готовы, напишите: давайте, и начнём подбор."
            self.redis.add_message(role="ai", message=reply)
            return self._build_result(reply=reply, funnel_state=STATE_AWAITING_SELECTION_CONSENT)

        if state == STATE_CLOSED:
            return self._build_result(reply="Диалог уже завершён.", funnel_state=STATE_CLOSED)

        # STATE_COLLECTING
        return self._collect(history=history, message=message)


# ─── Public API ───────────────────────────────────────────────────────────────


def run_step_1(session_id: str, message: str) -> Step1Result:
    return Step1Service(session_id=session_id).run(message=message)


if __name__ == "__main__":
    result = run_step_1(session_id="188015181", message="Привет")
    print(result.model_dump())
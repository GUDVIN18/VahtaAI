from __future__ import annotations

import json
import logging
from typing import Optional, Any

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from app.api.vahta_ai.resources.redis_client import RedisClient
from app.include.config import config
from app.api.vahta_ai.RAG.service import FAQSearchService
from openai import ContentFilterFinishReasonError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
log = logging.getLogger("vahta_ai.step_1")

service = FAQSearchService()

GREETING_TEXT = (
    "Здравствуйте!🤝😊 Вы оставляли отклик на вакансию вахта,\n"
    "на Авито.\n"
    "Работа для вас еще актуальна?"
)

INTRO_TEXT = (
    "Меня зовут Яна, я ваш менеджер.\n"
    "Так как у нас много объектов, ответьте, пожалуйста, на несколько вопросов, "
    "чтобы я могла подобрать максимально подходящий вариант.\n\n"
    "Подскажите, пожалуйста, ваше ФИО."
)

STATE_NEW = "new"
STATE_AWAITING_RELEVANCE = "awaiting_relevance"
STATE_COLLECTING = "collecting"
STATE_AWAITING_SELECTION_CONSENT = "awaiting_selection_consent"
STATE_STEP_1_DONE = "step_1_done"
STATE_CLOSED = "closed"

POSITIVE_ANSWERS = {
    "да",
    "да.",
    "да!",
    "конечно",
    "актуально",
    "интересно",
    "подходит",
    "хочу",
    "готов",
    "готова",
}

NEGATIVE_ANSWERS = {
    "нет",
    "нет.",
    "нет!",
    "не актуально",
    "неинтересно",
    "не интересно",
    "не подходит",
    "уже не ищу",
    "не ищу",
}

SELECTION_CONSENT_ANSWERS = {
    "давайте",
    "да",
    "ок",
    "окей",
    "хорошо",
    "согласен",
    "согласна",
    "подбирайте",
    "подберите",
    "да, давайте",
    "давай",
}

EMPTY_MARKERS = {
    None,
    "",
    "не заполнено",
    "не указано",
    "unknown",
    "null",
    "-",
}

FIELD_LABELS = {
    "full_name": "ФИО",
    "age": "возраст",
    "citizenship": "гражданство",
    "city": "город",
    "start_date": "дата выезда",
    "experience": "опыт работы",
    "previous_job": "предыдущее место работы",
    "reason_for_change": "причина смены работы",
}


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


class Step1Service:
    llm = ChatOpenAI(
        api_key=config.YANDEX_API_KEY,
        model=f"gpt://{config.FOLDER_LLM_YANDEX_ID}/yandexgpt-5-pro/latest",
        base_url="https://ai.api.cloud.yandex.net/v1",
        temperature=0.2,
        top_p=0.9,
    )

    structured_llm = llm.with_structured_output(Step1Response)

    dialog_prompt = ChatPromptTemplate.from_template(
        """
Ты рекрутер Яна. Ты ведешь первичный диалог с кандидатом на вахтовую работу.

ЖЕСТКИЕ ПРАВИЛА:
- Отвечай коротко, естественно и по-человечески, как живой менеджер.
- Одно сообщение = один ответ и один вопрос.
- Не благодари пользователя.
- Никогда не используй слова: "спасибо", "благодарю", "благодарим".
- Не обращайся к пользователю по имени в каждом сообщении.
- Запрещено использовать фразы вроде: "Понятно", "Хорошо", "Отлично", "Ясно", "Поняла" и тд.
- Запрещено использовать фразы вроде: Укажите пожалуйста и тд ТОЛЬКО ВОПРОС!! Без лишенго.
- Не добавляй лишние вводные фразы перед вопросом. Только вопрос!
- Не повторяй уже заполненные вопросы.
- Не пиши "не заполнено", "не указано", "unknown", "-" ни в candidate, ни в reply.
- Если поле не удалось извлечь, оставь его null.
- Если пользователь просто ответил на предыдущий вопрос, зафиксируй ответ и сразу задай следующий вопрос.
- Ответ должен звучать как обычное сообщение живого менеджера.
- Не закрывай диалог сам.
- Не делай вывод, что анкета заполнена, если еще остались пустые поля.
- Пока есть хотя бы одно пустое поле, обязательно задай следующий вопрос.
- Не меняй порядок полей.
- Если пользователь ответил на вопрос о причине смены работы, не спорь, не осуждай и не проси дополнительных объяснений, если ответ уже понятен по смыслу.

ПРАВИЛА РАБОТЫ С FAQ / RAG:
- Ниже тебе будет передан FAQ-контекст с найденными ответами по базе знаний.
- Если пользователь задал вопрос по условиям работы, оплате, проживанию, авансам, документам, графику, медкнижке, питанию, общежитию и т.д. — используй FAQ-контекст.
- Отвечай только по тем фактам, которые есть в FAQ-контексте.
- Не выдумывай факты, которых нет в FAQ.
- Если FAQ-контекст релевантен, сначала коротко ответь на вопрос пользователя, а потом продолжи сбор анкеты.
- Если пользователь не дал ответ на текущий анкетный вопрос, после ответа по FAQ вернись к тому же ближайшему незаполненному полю.
- Если FAQ-контекст пустой или нерелевантный, игнорируй его.

Твоя задача:
1. Извлечь новые данные кандидата из сообщения.
2. Обновить уже собранные данные.
3. Если пользователь задал вопрос по вакансии — коротко ответить по FAQ.
4. После этого задать ОДИН следующий вопрос по ближайшему незаполненному полю.
5. Если пользователь прислал некорректные данные — коротко попроси уточнить это же поле.

Поля кандидата в строгом порядке:
- full_name
- age
- citizenship
- city
- start_date
- experience
- previous_job
- reason_for_change

Названия полей:
- full_name = ФИО
- age = возраст
- citizenship = гражданство
- city = город
- start_date = дата выезда
- experience = опыт работы
- previous_job = предыдущее место работы
- reason_for_change = причина смены работы

Уже собранные данные:
{candidate_snapshot}

Какие поля еще пустые:
{missing_fields}

История диалога:
{history}

FAQ-контекст:
{rag_context}

Новое сообщение пользователя:
{message}

Верни:
- candidate: только актуальные данные кандидата
- reply: короткий ответ и только один следующий вопрос
"""
    )

    final_reason_prompt = ChatPromptTemplate.from_template(
        """
Ты рекрутер Яна. Пользователь только что ответил, что именно его не устроило на прошлой работе.
Это последнее поле анкеты. Анкета уже заполнена.

Нужно написать ОДНО короткое человеческое сообщение:
- с эмпатией
- без шаблонной благодарности
- без обращения по имени
- без канцелярита
- без уточняющих вопросов о проблеме
- без осуждения
- без повторения дословно всей жалобы пользователя
- с мягким переходом к тому, что ты можешь подобрать подходящий объект
- в конце естественно подведи к тому, что пользователь может согласиться на подбор

ЖЕСТКИЕ ПРАВИЛА:
- Не используй слова: "спасибо", "благодарю", "благодарим".
- Не задавай новых вопросов про прошлую работу.
- Не пиши одинаково шаблонно.
- Сообщение должно быть 1-2 предложения.

Причина смены работы:
{reason_for_change}

Верни только текст сообщения.
"""
    )

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.redis = RedisClient(session_id=session_id)
        self.state_key = f"ai_funnel_state:{session_id}"
        self.candidate_key = f"ai_candidate:{session_id}"

    def _set_state(self, state: str) -> None:
        self.redis.client.setex(self.state_key, self.redis.ttl, state)

    def _get_state(self) -> str | None:
        state = self.redis.client.get(self.state_key)
        if state is None:
            return None
        if isinstance(state, bytes):
            return state.decode("utf-8")
        return str(state)

    def _save_candidate(self, candidate: dict[str, Any]) -> None:
        self.redis.client.setex(
            self.candidate_key,
            self.redis.ttl,
            json.dumps(candidate, ensure_ascii=False),
        )

    def _load_candidate(self) -> dict[str, Any]:
        raw = self.redis.client.get(self.candidate_key)
        if not raw:
            return {}

        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")

        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _history_to_prompt(self, history: list[Any]) -> str:
        if not history:
            return "История пуста."

        lines: list[str] = []
        for item in history:
            if isinstance(item, HumanMessage):
                lines.append(f"Пользователь: {item.content}")
            elif isinstance(item, AIMessage):
                lines.append(f"AI: {item.content}")

        return "\n".join(lines) if lines else "История пуста."

    def _is_empty_value(self, value: Any) -> bool:
        if value in EMPTY_MARKERS:
            return True
        if isinstance(value, str) and value.strip().lower() in EMPTY_MARKERS:
            return True
        return False

    def _sanitize_candidate(self, candidate: dict[str, Any]) -> dict[str, Any]:
        cleaned: dict[str, Any] = {}
        for key, value in candidate.items():
            if self._is_empty_value(value):
                continue
            if isinstance(value, str):
                value = value.strip()
            cleaned[key] = value
        return cleaned

    def _get_missing_fields(self, candidate: dict[str, Any]) -> list[str]:
        missing_fields: list[str] = []
        for field_name in CandidateSchema.model_fields:
            value = candidate.get(field_name)
            if self._is_empty_value(value):
                missing_fields.append(field_name)
        return missing_fields

    def _missing_fields_human(self, missing_fields: list[str]) -> str:
        if not missing_fields:
            return "Пустых полей нет."
        return ", ".join(FIELD_LABELS.get(field, field) for field in missing_fields)

    def _candidate_snapshot_to_prompt(self, candidate: dict[str, Any]) -> str:
        if not candidate:
            return "Данные кандидата пока не собраны."

        lines: list[str] = []
        for key in CandidateSchema.model_fields:
            value = candidate.get(key)
            label = FIELD_LABELS.get(key, key)
            lines.append(f"{label}: {value if not self._is_empty_value(value) else 'не заполнено'}")
        return "\n".join(lines)

    def _merge_candidate_data(
        self,
        old_candidate: dict[str, Any],
        new_candidate: dict[str, Any],
    ) -> dict[str, Any]:
        merged = dict(old_candidate)
        new_candidate = self._sanitize_candidate(new_candidate)

        for key, value in new_candidate.items():
            if not self._is_empty_value(value):
                merged[key] = value

        return self._sanitize_candidate(merged)

    def _resolve_state(self, history: list[Any]) -> str:
        saved_state = self._get_state()
        if saved_state:
            return saved_state

        if not history:
            return STATE_NEW

        ai_messages = [msg for msg in history if isinstance(msg, AIMessage)]
        user_messages = [msg for msg in history if isinstance(msg, HumanMessage)]

        if ai_messages and ai_messages[0].content.strip() == GREETING_TEXT.strip():
            if not user_messages or len(ai_messages) == 1:
                return STATE_AWAITING_RELEVANCE

        candidate = self._load_candidate()
        if candidate and not self._get_missing_fields(candidate):
            return STATE_AWAITING_SELECTION_CONSENT

        return STATE_COLLECTING

    def _is_positive_answer(self, message: str) -> bool:
        normalized = message.strip().lower()
        if normalized in POSITIVE_ANSWERS:
            return True
        return any(word in normalized for word in {"да", "актуал", "интерес", "хочу", "готов"})

    def _is_negative_answer(self, message: str) -> bool:
        normalized = message.strip().lower()
        if normalized in NEGATIVE_ANSWERS:
            return True
        return any(word in normalized for word in {"нет", "не актуал", "не интерес", "не ищу"})

    def _is_selection_consent(self, message: str) -> bool:
        normalized = message.strip().lower()
        if normalized in SELECTION_CONSENT_ANSWERS:
            return True

        triggers = {
            "давайте",
            "подберите",
            "подбирайте",
            "согласен",
            "согласна",
            "хорошо",
            "можно",
            "да, давайте",
            "давай",
        }
        return any(trigger in normalized for trigger in triggers)

    def _is_reason_for_change_completion(
        self,
        missing_before: list[str],
        missing_after: list[str],
        new_candidate: dict[str, Any],
    ) -> bool:
        return (
            "reason_for_change" in missing_before
            and "reason_for_change" not in missing_after
            and len(missing_after) == 0
            and not self._is_empty_value(new_candidate.get("reason_for_change"))
        )

    def _generate_final_reason_reply(self, reason_for_change: str) -> str:
        chain = self.final_reason_prompt | self.llm
        response = chain.invoke({"reason_for_change": reason_for_change})
        content = getattr(response, "content", None)
        if isinstance(content, str) and content.strip():
            return content.strip()
        return "Понимаю вас. Могу подобрать для вас более подходящие варианты."

    def _should_use_rag(self, message: str) -> bool:
        normalized = message.strip().lower()
        if not normalized:
            return False

        faq_triggers = (
            "?", "аванс", "зарплат", "оплат", "прожив", "общеж", "питани", "график",
            "договор", "самозан", "медк", "медком", "паспорт", "документ",
            "смен", "вахт", "бригад", "форма", "дорог", "билет", "транспорт",
            "штраф", "выходн", "ночн", "дневн", "регистрац", "сб", "судим",
        )
        return any(trigger in normalized for trigger in faq_triggers)

    def _build_rag_context(self, query: str, top_k: int = 6) -> str:
        if not self._should_use_rag(query):
            print("Раг контекст не найден")
            return "FAQ-контекст не найден."

        try:
            results = service.search(query=query, top_k=top_k)
        except Exception as e:
            log.exception("RAG search failed: %s", e)
            return "FAQ-контекст не найден."

        if not results:
            return "FAQ-контекст не найден."

        lines: list[str] = []
        for idx, item in enumerate(results, start=1):
            question = (item.question or "").strip()
            answer = (item.answer or "").strip()
            block = (item.block or "").strip()

            if not question and not answer:
                continue

            lines.append(f"[FAQ {idx}]")
            if block:
                lines.append(f"Блок: {block}")
            if question:
                lines.append(f"Вопрос: {question}")
            if answer:
                lines.append(f"Ответ: {answer}")
            lines.append("")

        return "\n".join(lines).strip() or "FAQ-контекст не найден."

    def _collect_candidate_data(self, history: list[Any], message: str) -> Step1Result:
        stored_candidate = self._sanitize_candidate(self._load_candidate())
        missing_before = self._get_missing_fields(stored_candidate)
        rag_context = self._build_rag_context(query=message, top_k=8)

        chain = self.dialog_prompt | self.structured_llm

        try:
            response: Step1Response = chain.invoke(
                {
                    "candidate_snapshot": self._candidate_snapshot_to_prompt(stored_candidate),
                    "missing_fields": self._missing_fields_human(missing_before),
                    "history": self._history_to_prompt(history),
                    "rag_context": rag_context,
                    "message": message,
                }
            )

        except ContentFilterFinishReasonError:
            log.warning("Content filter triggered")

            # второй вызов без structured_output
            if "сво" in message.lower():
                response = Step1Response(
                    candidate=CandidateSchema(**stored_candidate),
                    reply="Поняла. Какой еще у вас опыт работы был?"
                )
            else:
                fallback_chain = self.dialog_prompt | self.llm
                raw = fallback_chain.invoke(
                    {
                        "candidate_snapshot": self._candidate_snapshot_to_prompt(stored_candidate),
                        "missing_fields": self._missing_fields_human(missing_before),
                        "history": self._history_to_prompt(history),
                        "rag_context": rag_context,
                        "message": message,
                    }
                )

                text = raw.content if hasattr(raw, "content") else str(raw)

                response = Step1Response(
                    candidate=CandidateSchema(**stored_candidate),
                    reply=text.strip(),
                )

        except Exception:
            log.exception("LLM invoke failed")

            response = Step1Response(
                candidate=CandidateSchema(**stored_candidate),
                reply="Не поняла Ваш ответ...",
            )
        new_candidate = response.candidate.model_dump(exclude_none=True)
        merged_candidate = self._merge_candidate_data(stored_candidate, new_candidate)
        missing_after = self._get_missing_fields(merged_candidate)

        if self._is_reason_for_change_completion(
            missing_before=missing_before,
            missing_after=missing_after,
            new_candidate=new_candidate,
        ):
            reply = self._generate_final_reason_reply(
                str(merged_candidate.get("reason_for_change", ""))
            )
            next_state = STATE_AWAITING_SELECTION_CONSENT
        else:
            reply = response.reply.strip()
            next_state = STATE_CLOSED if not missing_after else STATE_COLLECTING

        self.redis.add_message(role="user", message=message)
        self.redis.add_message(role="ai", message=reply)
        self._save_candidate(merged_candidate)

        completed = not missing_after

        return Step1Result(
            candidate=merged_candidate,
            missing_fields=missing_after,
            reply=reply,
            completed=completed,
            funnel_state=next_state,
            ready_for_next_step=False,
        )

    def _build_result(
        self,
        reply: str,
        funnel_state: str,
        ready_for_next_step: bool,
    ) -> Step1Result:
        candidate = self._sanitize_candidate(self._load_candidate())
        missing_fields = self._get_missing_fields(candidate)

        return Step1Result(
            candidate=candidate,
            missing_fields=missing_fields,
            reply=reply,
            completed=not missing_fields,
            funnel_state=funnel_state,
            ready_for_next_step=ready_for_next_step,
        )

    def run(self, message: str) -> Step1Result:
        history = self.redis.get_session_history_v2()
        state = self._resolve_state(history)

        log.info("step_1 state=%s session_id=%s message=%s", state, self.session_id, message)

        if state == STATE_NEW:
            self.redis.add_message(role="ai", message=GREETING_TEXT)
            self._set_state(STATE_AWAITING_RELEVANCE)

            return Step1Result(
                candidate=self._load_candidate(),
                missing_fields=list(CandidateSchema.model_fields.keys()),
                reply=GREETING_TEXT,
                completed=False,
                funnel_state=STATE_AWAITING_RELEVANCE,
                ready_for_next_step=False,
            )

        if state == STATE_AWAITING_RELEVANCE:
            if self._is_negative_answer(message):
                self.redis.add_message(role="user", message=message)
                reply = (
                    "Поняла вас. Если позже снова станет актуально, напишите мне, "
                    "и я подберу подходящие варианты."
                )
                self.redis.add_message(role="ai", message=reply)
                self._set_state(STATE_CLOSED)
                return self._build_result(
                    reply=reply,
                    funnel_state=STATE_CLOSED,
                    ready_for_next_step=False,
                )

            if not self._is_positive_answer(message):
                self.redis.add_message(role="user", message=message)
                reply = "Подскажите, работа еще актуальна для вас? Ответьте, пожалуйста: да или нет."
                self.redis.add_message(role="ai", message=reply)
                self._set_state(STATE_AWAITING_RELEVANCE)

                candidate = self._load_candidate()
                missing_fields = self._get_missing_fields(candidate) or list(CandidateSchema.model_fields.keys())

                return Step1Result(
                    candidate=candidate,
                    missing_fields=missing_fields,
                    reply=reply,
                    completed=False,
                    funnel_state=STATE_AWAITING_RELEVANCE,
                    ready_for_next_step=False,
                )

            self.redis.add_message(role="user", message=message)
            self.redis.add_message(role="ai", message=INTRO_TEXT)
            self._set_state(STATE_COLLECTING)

            candidate = self._load_candidate()
            missing_fields = self._get_missing_fields(candidate) or list(CandidateSchema.model_fields.keys())

            return Step1Result(
                candidate=candidate,
                missing_fields=missing_fields,
                reply=INTRO_TEXT,
                completed=False,
                funnel_state=STATE_COLLECTING,
                ready_for_next_step=False,
            )

        if state == STATE_AWAITING_SELECTION_CONSENT:
            self.redis.add_message(role="user", message=message)

            if self._is_selection_consent(message):
                reply = "А что бы вы хотели? Что вообще рассматриваете?"
                self.redis.add_message(role="ai", message=reply)
                self._set_state(STATE_STEP_1_DONE)

                result = self._build_result(
                    reply=reply,
                    funnel_state=STATE_STEP_1_DONE,
                    ready_for_next_step=True,
                )
                log.info("step_1 handoff result: %s", result.model_dump())
                return result

            reply = "Если готовы, напишите: давайте, и мы начнем подбор."
            self.redis.add_message(role="ai", message=reply)
            self._set_state(STATE_AWAITING_SELECTION_CONSENT)

            result = self._build_result(
                reply=reply,
                funnel_state=STATE_AWAITING_SELECTION_CONSENT,
                ready_for_next_step=False,
            )
            log.info("step_1 waiting consent result: %s", result.model_dump())
            return result

        if state == STATE_CLOSED:
            return self._build_result(
                reply="Диалог уже завершен.",
                funnel_state=STATE_CLOSED,
                ready_for_next_step=False,
            )

        result = self._collect_candidate_data(history=history, message=message)

        if result.funnel_state == STATE_AWAITING_SELECTION_CONSENT:
            self._set_state(STATE_AWAITING_SELECTION_CONSENT)
        elif result.completed:
            self._set_state(STATE_CLOSED)
            result.funnel_state = STATE_CLOSED
        else:
            self._set_state(STATE_COLLECTING)
            result.funnel_state = STATE_COLLECTING

        log.info("step_1 result: %s", result.model_dump())
        return result


def run_step_1(session_id: str, message: str) -> Step1Result:
    return Step1Service(session_id=session_id).run(message=message)


if __name__ == "__main__":
    result = run_step_1(session_id="6", message="Привет")
    print(result.model_dump())
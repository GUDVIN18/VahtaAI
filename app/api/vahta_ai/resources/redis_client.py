import json
import redis
import datetime
from langchain_community.chat_message_histories import RedisChatMessageHistory
from langchain_classic.schema import BaseChatMessageHistory
from langchain_core.messages import HumanMessage, AIMessage
from app.include.logging_config import logger as log
from app.include.config import config


class RedisClient:
    def __init__(
            self,
            session_id: str,
            url:str = "redis://:hUvput-vujfow-ganma3@193.35.17.66:6379/0",
            key_prefix: str = "ai_history:"
        ):
        self.session_id=session_id
        self.url=url
        self.key_prefix=key_prefix
        self.client=redis.from_url(url, decode_responses=True)
        self.key=f"{key_prefix}{session_id}"
        self.ttl=int(datetime.timedelta(days=365 * 2).total_seconds())

    def get_session_history_v2(
            self,
        ) -> list[BaseChatMessageHistory]:

        history = self.client.lrange(self.key, 0, -1)
        lc_messages = []
        for msg_str in history:
            data = json.loads(msg_str)
            if data['role'] == 'user':
                lc_messages.append(HumanMessage(content=data['content']))
            if data['role'] == 'ai':
                lc_messages.append(AIMessage(content=data['content']))

        return lc_messages



    def add_message(self, role: str, message: str):
        try:
            message_data = json.dumps({
                "role": role,
                "content": message
            }, ensure_ascii=False)
            # Добавляем в конец списка (RPUSH)
            self.client.rpush(self.key, message_data)
        
            self.client.expire(self.key, self.ttl)
            
            log.info(f"Message added to Redis. Key: {self.key}, TTL.")
        except Exception as e:
            log.error(f"Redis add_message error: {e}")

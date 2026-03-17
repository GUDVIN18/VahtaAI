from typing import List

from pydantic import BaseModel
from qdrant_client import QdrantClient
from yandex_cloud_ml_sdk import YCloudML

from app.include.config import config


COLLECTION_NAME = "vahta_faq"


class FAQSearchResult(BaseModel):
    id: str
    score: float
    block: str | None = None
    question: str | None = None
    answer: str | None = None


class FAQSearchService:

    def __init__(self):

        sdk = YCloudML(
            folder_id=config.FOLDER_LLM_YANDEX_ID,
            auth=config.YANDEX_API_KEY,
        )

        self.model = sdk.models.text_embeddings("text-embeddings-1.0")

        self.client = QdrantClient(
            url="http://localhost:6333"
        )

    def _embed_query(self, query: str) -> List[float]:

        query = query.strip()

        if not query:
            raise ValueError("Пустой поисковый запрос")

        embedding = self.model.run(query).embedding

        return list(embedding)

    def search(
        self,
        query: str,
        top_k: int = 10,
    ) -> List[FAQSearchResult]:

        vector = self._embed_query(query)

        search_result = self.client.query_points(
            collection_name=COLLECTION_NAME,
            query=vector,
            limit=top_k,
            with_payload=True,
        )

        items: List[FAQSearchResult] = []

        for point in search_result.points:

            payload = point.payload or {}

            items.append(
                FAQSearchResult(
                    id=str(point.id),
                    score=float(point.score),
                    block=payload.get("block"),
                    question=payload.get("question"),
                    answer=payload.get("answer"),
                )
            )

        return items


if __name__ == "__main__":
    service = FAQSearchService()
    query = "Если я участник сво"
    results = service.search(query=query, top_k=12)
    print(results)
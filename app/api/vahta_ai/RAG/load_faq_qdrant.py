import uuid
import pandas as pd
import time
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

from yandex_cloud_ml_sdk import YCloudML
from app.include.config import config


COLLECTION_NAME = "vahta_faq"


class FAQIndexer:
    def __init__(self):
        sdk = YCloudML(
            folder_id=config.FOLDER_LLM_YANDEX_ID,
            auth=config.YANDEX_API_KEY,
        )

        self.model = sdk.models.text_embeddings("text-embeddings-1.0")

        self.client = QdrantClient(
            url="http://localhost:6333"
        )

    def recreate_collection(self):
        if self.client.collection_exists(COLLECTION_NAME):
            self.client.delete_collection(COLLECTION_NAME)

        self.client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(
                size=1536,
                distance=Distance.COSINE,
            ),
        )

    def load_excel(self, file_path: str):
        excel = pd.ExcelFile(file_path)
        points = []

        for sheet_name in excel.sheet_names:
            df = excel.parse(sheet_name)
            print(sheet_name)
            df.columns = df.columns.str.strip()
            for _, row in df.iterrows():

                question = str(row.get("СОИСКАТЕЛЬ", "")).strip()
                answer = str(row.get("ОПЕРАТОР", "")).strip()
                if not question or not answer or question == "nan" or answer == "nan":
                    continue

                # text = f"""Тема: {sheet_name}\nВопрос: {question}\nОтвет: {answer}"""
                text = f"{question}\n{answer}"
                # print(text)

                vector = self.model.run(text).embedding

                points.append(
                    PointStruct(
                        id=str(uuid.uuid4()),
                        vector=vector,
                        payload={
                            "block": sheet_name,
                            "question": question,
                            "answer": answer,
                        },
                    )
                )
                # time.sleep(0.05)
            self.client.upsert(
                collection_name=COLLECTION_NAME,
                points=points,
            )
            print(sheet_name, "успешно загружена")


if __name__ == "__main__":

    indexer = FAQIndexer()
    indexer.recreate_collection()
    print("Пересоздали коллекцию")

    indexer.load_excel(
        "/VahtaAI/files/Дмитрий.Возраженияпотемам.xlsx"
    )
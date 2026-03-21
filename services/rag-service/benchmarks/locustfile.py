import time
from locust import HttpUser, task, between

class RAGUser(HttpUser):
    wait_time = between(1, 4)
    
    @task(3)
    def search_normal(self):
        payload = {
            "query": "Quy định về BIM trong Nghị định 15/2021",
            "use_hyde": False,
            "use_cache": True
        }
        self.client.post("/search", json=payload, timeout=60)

    @task(1)
    def search_hyde(self):
        payload = {
            "query": "Các giai đoạn áp dụng BIM theo lộ trình của Chính phủ",
            "use_hyde": True,
            "use_cache": False
        }
        self.client.post("/search", json=payload, timeout=90)

    @task(2)
    def health_check(self):
        self.client.get("/health")

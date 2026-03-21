from locust import HttpUser, task, between
import random

class RAGUser(HttpUser):
    wait_time = between(1, 5)

    @task
    def complex_query(self):
        queries = [
            "Điều 123 Luật Xây dựng hiện hành sau tất cả các sửa đổi là gì?",
            "Bản vẽ BIM số DWG-2023-A1 của dự án ABC có còn hiệu lực không?",
            "Quy trình cấp phép xây dựng theo Nghị định 15/2021 là gì?",
            "So sánh Luật Xây dựng 2014 và Luật Xây dựng 2024 về phần cấp phép.",
            "Các văn bản hướng dẫn mới nhất cho Luật Đất đai 2024?"
        ]
        self.client.post("/search", json={
            "query": random.choice(queries),
            "limit": 5,
            "use_reranker": True
        })

    @task(3)
    def simple_query(self):
        self.client.post("/search", json={
            "query": "Số hiệu Nghị định 15/2021",
            "limit": 3,
            "use_reranker": False
        })

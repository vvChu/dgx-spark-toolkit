from locust import HttpUser, task, between
import random

class RAGUser(HttpUser):
    wait_time = between(1, 3)
    
    questions = [
        "EIR là gì?",
        "BEP cần những gì?",
        "ISO 19650 là gì?",
        "Nghị định 15/2021 có nội dung gì chính?",
        "Quy trình quản lý dự án BIM?",
        "CDE hoạt động như thế nào?",
        "LOD 300 và LOD 400 khác nhau thế nào?",
        "Ai phê duyệt dự toán công trình?",
        "Hợp đồng trọn gói là gì?",
        "Xử lý vi phạm trật tự xây dựng thế nào?"
    ]

    @task
    def query_rag(self):
        question = random.choice(self.questions)
        with self.client.post(
            "/chat",
            json={"query": question, "context_limit": 5},
            catch_response=True
        ) as response:
            if response.status_code == 200:
                data = response.json()
                if "answer" in data:
                    response.success()
                else:
                    response.failure("Response missing 'answer' field")
            else:
                response.failure(f"Status code {response.status_code}")

    @task(3)
    def check_health(self):
        self.client.get("/health")

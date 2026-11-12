import re
import uuid

from locust import HttpUser, between, task


def extract_csrf_token(html_text: str) -> str:
    match = re.search(
        r'name=["\']csrfmiddlewaretoken["\']\s+value=["\']([^"\']+)["\']',
        html_text,
    )
    return match.group(1) if match else ""


class PublicTicketReaderUser(HttpUser):
    wait_time = between(0.5, 1.5)
    weight = 3

    @task(3)
    def view_public_ticket_dh1(self):
        with self.client.get(
            "/view/?ticket=DH-1&email=helpdesk@example.com",
            name="C1: GET /view/ (Ticket Válido)",
            catch_response=True,
        ) as response:
            if response.status_code == 200 and "DH-1" in response.text:
                response.success()
            else:
                response.failure(
                    f"Falha ao abrir ticket DH-1: HTTP {response.status_code}"
                )

    @task(1)
    def view_public_search_form(self):
        with self.client.get(
            "/view/",
            name="C1: GET /view/ (Formulário de Busca)",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(
                    f"Falha no formulário /view/: HTTP {response.status_code}"
                )


class PublicTicketSubmitterUser(HttpUser):
    wait_time = between(0.5, 1.5)
    weight = 2

    @task
    def submit_public_ticket(self):
        with self.client.get(
            "/tickets/submit/",
            name="C2: GET /tickets/submit/ (CSRF)",
            catch_response=True,
        ) as get_resp:
            if get_resp.status_code != 200:
                get_resp.failure(
                    f"Erro ao obter formulário: HTTP {get_resp.status_code}"
                )
                return
            csrf_token = extract_csrf_token(get_resp.text)
            if not csrf_token:
                get_resp.failure("Token CSRF não encontrado no HTML")
                return

        unique_id = uuid.uuid4().hex[:8]
        payload = {
            "csrfmiddlewaretoken": csrf_token,
            "queue": "1",
            "title": f"Incidente #{unique_id}",
            "body": "Chamado de teste de carga.",
            "priority": "3",
            "submitter_email": "helpdesk@example.com",
        }
        headers = {"Referer": f"{self.host}/tickets/submit/"}

        with self.client.post(
            "/tickets/submit/",
            data=payload,
            headers=headers,
            name="C2: POST /tickets/submit/ (Criar Ticket)",
            allow_redirects=False,
            catch_response=True,
        ) as post_resp:
            if post_resp.status_code in (302, 303):
                post_resp.success()
            elif post_resp.status_code == 200:
                post_resp.failure("HTTP 200: Formulário rejeitado")
            else:
                post_resp.failure(f"Erro na escrita: HTTP {post_resp.status_code}")


class StaffTicketListUser(HttpUser):
    wait_time = between(0.5, 1.5)
    weight = 2
    urlsafe_query = None

    def on_start(self):
        for _ in range(3):
            login_page = self.client.get("/login/", name="C3: GET /login/ (Auth)")
            csrf_token = extract_csrf_token(login_page.text)
            post_resp = self.client.post(
                "/login/",
                data={
                    "csrfmiddlewaretoken": csrf_token,
                    "username": "admin",
                    "password": "Pa33w0rd",
                    "next": "/tickets/",
                },
                headers={"Referer": f"{self.host}/login/"},
                allow_redirects=False,
                name="C3: POST /login/ (Auth)",
            )
            set_cookie_header = post_resp.headers.get("Set-Cookie", "")
            match_sid = re.search(r"sessionid=([^;,\s]+)", set_cookie_header)
            if match_sid:
                self.client.cookies.set("sessionid", match_sid.group(1))
            if "sessionid" in self.client.cookies:
                break

    @task(2)
    def list_tickets_page(self):
        with self.client.get(
            "/tickets/",
            name="C3: GET /tickets/ (Página Staff)",
            catch_response=True,
        ) as response:
            if response.status_code == 200 and "ticketTable" in response.text:
                match = re.search(
                    r"/datatables_ticket_list/([A-Za-z0-9+/=]+)", response.text
                )
                if match:
                    self.urlsafe_query = match.group(1)
                response.success()
            else:
                response.failure(
                    f"Falha ao carregar /tickets/: HTTP {response.status_code}"
                )

    @task(2)
    def fetch_datatables_json(self):
        if not self.urlsafe_query:
            self.list_tickets_page()
            if not self.urlsafe_query:
                return

        with self.client.get(
            f"/datatables_ticket_list/{self.urlsafe_query}?draw=1&start=0&length=25",
            name="C3: GET /datatables_ticket_list/ (JSON)",
            catch_response=True,
        ) as response:
            if response.status_code == 200 and "recordsTotal" in response.text:
                response.success()
            else:
                response.failure(
                    f"Falha no DataTables JSON: HTTP {response.status_code}"
                )

    @task(1)
    def filter_tickets_search(self):
        with self.client.get(
            "/tickets/?q=Problem&status=1&queue=1&sort=created",
            name="C3: GET /tickets/?q=... (Busca Filtrada)",
            catch_response=True,
        ) as response:
            if response.status_code == 200 and "ticketTable" in response.text:
                response.success()
            else:
                response.failure(
                    f"Falha na busca filtrada: HTTP {response.status_code}"
                )

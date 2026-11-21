import logging
import os
import shutil
import sys
import tempfile
import time
from contextlib import contextmanager

import django
from django.conf import settings

PASTA_SCRIPT = os.path.dirname(os.path.abspath(__file__))
ARQUIVO_LOG = os.path.join(PASTA_SCRIPT, "resultado_exploracao.txt")


class _Duplicar:
    """Escreve na tela e no arquivo de log ao mesmo tempo."""

    def __init__(self, *fluxos):
        self.fluxos = fluxos

    def write(self, dados):
        for fluxo in self.fluxos:
            fluxo.write(dados)

    def flush(self):
        for fluxo in self.fluxos:
            fluxo.flush()


sys.stdout.reconfigure(encoding="utf-8")
sys.stdout = _Duplicar(sys.stdout, open(ARQUIVO_LOG, "w", encoding="utf-8"))  # noqa: SIM115

RAIZ = os.path.dirname(PASTA_SCRIPT)
sys.path.insert(0, RAIZ)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "demodesk.config.settings")

PASTA_TMP = tempfile.mkdtemp()
COPIA_BANCO = os.path.join(PASTA_TMP, "base_exploracao.sqlite3")  # nunca alterada
BANCO_TRABALHO = os.path.join(PASTA_TMP, "trabalho.sqlite3")  # refeita a cada cenário
shutil.copy(settings.DATABASES["default"]["NAME"], COPIA_BANCO)
shutil.copy(COPIA_BANCO, BANCO_TRABALHO)
settings.DATABASES["default"]["NAME"] = BANCO_TRABALHO
settings.MEDIA_ROOT = os.path.join(PASTA_TMP, "media")
django.setup()

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.signals import got_request_exception
from django.db import connections
from django.test import Client
from django.test.utils import setup_test_environment

from helpdesk.models import FollowUp, Ticket, TicketDependency

setup_test_environment()  # e-mails vão para mail.outbox, sem rede

User = get_user_model()
ADMIN = User.objects.get(username="admin")


logging.getLogger("django").setLevel(logging.CRITICAL)
EXCECOES = []


def _registra_excecao(sender, request=None, **kwargs):
    EXCECOES.append(sys.exc_info()[1])


got_request_exception.connect(_registra_excecao)


@contextmanager
def isolado():
    """Entrega um banco novo (cópia da base) para o cenário."""
    connections.close_all()
    shutil.copy(COPIA_BANCO, BANCO_TRABALHO)
    EXCECOES.clear()
    mail.outbox.clear()
    yield
    connections.close_all()


def cliente(usuario=None, csrf=False):
    c = Client(enforce_csrf_checks=csrf, raise_request_exception=False)
    if usuario is not None:
        c.force_login(usuario)
    return c


def atualizar(ticket, dados=None, arquivos=None, c=None, url=None):
    """Envia o mesmo formulário que a tela do atendente envia."""
    c = c or cliente(ADMIN)
    corpo = {
        "title": ticket.title,
        "priority": ticket.priority,
        "queue": ticket.queue_id,
        "public": "1",
    }
    corpo.update(dados or {})
    if arquivos is not None:
        corpo["attachment"] = arquivos
    return c.post(url or f"/tickets/{ticket.id}/update/", corpo)


def titulo(texto):
    print("\n" + "=" * 78 + f"\n{texto}\n" + "=" * 78)


def desfecho(resp):
    if resp.status_code == 302:
        return "302 (salvou e redirecionou)"
    if resp.status_code >= 500 and EXCECOES:
        e = EXCECOES[-1]
        return f"{resp.status_code} {type(e).__name__}: {str(e)[:55]}"
    return str(resp.status_code)


NOMES = {1: "Open", 2: "Reopened", 3: "Resolved", 4: "Closed", 5: "Duplicate"}

# ---------------------------------------------------------------------------
titulo("S1 - Caminho feliz: comentário público + Resolved + 01:30 de tempo gasto")
with isolado():
    t = Ticket.objects.get(id=1)
    r = atualizar(
        t, {"new_status": "3", "comment": "Resolvido.", "time_spent": "01:30"}
    )
    t.refresh_from_db()
    f = FollowUp.objects.filter(ticket=t).latest("id")
    print(f"resposta={desfecho(r)} destino={r.headers.get('Location')}")
    print(
        f"status={NOMES.get(t.status, t.status)} follow-up: público={f.public} "
        f"tempo={f.time_spent} título={f.title!r} e-mails enviados={len(mail.outbox)}"
    )

# ---------------------------------------------------------------------------
titulo("S2 - Transição de Estados: o que a TELA oferece x o que o SERVIDOR aceita")
print("(status: 1=Open 2=Reopened 3=Resolved 4=Closed 5=Duplicate)")
for origem in (1, 2, 3, 4, 5):
    with isolado():
        t = Ticket.objects.get(id=1)
        t.status = origem
        t.save()
        oferecidos = [s for s, _ in t.get_allowed_status_flow]
    aceitos, rejeitados, erros = [], [], []
    for destino in (1, 2, 3, 4, 5):
        if destino == origem:
            continue
        with isolado():
            t = Ticket.objects.get(id=1)
            t.status = origem
            t.save()
            r = atualizar(t, {"new_status": str(destino)})
            t.refresh_from_db()
            if r.status_code >= 500:
                erros.append(destino)
            elif t.status == destino:
                aceitos.append(destino)
            else:
                rejeitados.append(destino)
    fora_da_tela = [d for d in aceitos if d not in oferecidos]
    print(
        f"de {origem}-{NOMES[origem]:9s} | tela oferece {oferecidos} | servidor aceitou {aceitos}"
        f" | aceitou SEM a tela oferecer {fora_da_tela} | rejeitou {rejeitados} | erro 500 {erros}"
    )

print(
    "\nValores fora do domínio enviados em new_status (ticket DH-1, status inicial 1):"
)
for valor in ("0", "6", "9", "-1", "99", " 3 ", "3.0", "abc", "", "٣", "9" * 30):
    with isolado():
        t = Ticket.objects.get(id=1)
        r = atualizar(t, {"new_status": valor})
        t.refresh_from_db()
        mostra = valor if len(valor) < 12 else valor[:8] + "..."
        extra = ""
        if r.status_code == 302 and t.status != 1:
            extra = (
                f" -> status gravado={t.status!r} exibido={t.get_status_display()!r}"
            )
        print(f"new_status={mostra!r:14s} -> {desfecho(r)}{extra}")

# ---------------------------------------------------------------------------
titulo("S3 - Valor Limite: campo 'Tempo gasto' (time_spent, formato HH:MM)")
for valor in (
    "",
    "0:00",
    "00:01",
    "1:30",
    "23:59",
    "24:00",
    "100:00",
    "99999:59",
    "1:60",
    "1:99",
    "-1:30",
    "1:-30",
    "1.5",
    "1",
    "1:30:00",
    "abc",
    ":",
    "٠١:٣٠",
    "999999999999:00",
):
    with isolado():
        t = Ticket.objects.get(id=1)
        r = atualizar(t, {"comment": "tempo", "time_spent": valor})
        gravado = ""
        if r.status_code == 302:
            f = FollowUp.objects.filter(ticket=t).latest("id")
            gravado = f" -> gravado={f.time_spent!r}"
        print(f"time_spent={valor!r:18s} -> {desfecho(r)}{gravado}")

# ---------------------------------------------------------------------------
titulo("S4 - Dono do chamado (owner): valores de borda e inválidos")


def criar_usuarios():
    comum = User.objects.create_user("comum", "comum@example.com", "x")
    inativo = User.objects.create_user(
        "inativo", "inativo@example.com", "x", is_active=False
    )
    equipe = User.objects.create_user(
        "atendente2", "a2@example.com", "x", is_staff=True
    )
    return comum, inativo, equipe


for rotulo in (
    "0 (desatribuir)",
    "-1 (sem mudança)",
    "admin (staff)",
    "atendente2 (staff)",
    "comum (NÃO é staff)",
    "inativo (conta desativada)",
    "9999 (inexistente)",
    "abc",
    "'' (vazio)",
):
    with isolado():
        comum, inativo, equipe = criar_usuarios()
        valor = {
            "0 (desatribuir)": "0",
            "-1 (sem mudança)": "-1",
            "admin (staff)": str(ADMIN.id),
            "atendente2 (staff)": str(equipe.id),
            "comum (NÃO é staff)": str(comum.id),
            "inativo (conta desativada)": str(inativo.id),
            "9999 (inexistente)": "9999",
            "abc": "abc",
            "'' (vazio)": "",
        }[rotulo]
        t = Ticket.objects.get(id=1)
        r = atualizar(t, {"owner": valor, "comment": "dono"})
        t.refresh_from_db()
        dono = t.assigned_to.username if t.assigned_to else None
        print(f"owner={rotulo:28s} -> {desfecho(r)} | dono gravado={dono}")

# ---------------------------------------------------------------------------
titulo("S5 - Comentário: sintaxe de template, HTML e limites de tamanho")
chave = Ticket.objects.get(id=1).secret_key
for rotulo, texto in {
    "variável de template {{ ticket.title }}": "Titulo: {{ ticket.title }}",
    "{{ ticket.submitter_email }} e {{ queue.email_address }}": "{{ ticket.submitter_email }} | {{ queue.email_address }}",
    "'{{' sem fechar": "texto com {{ aberto",
    "'{% load static %}'": "{% load static %} ok",
    "<script>alert(1)</script>": "<script>alert(1)</script>",
}.items():
    with isolado():
        t = Ticket.objects.get(id=1)
        r = atualizar(t, {"comment": texto})
        if r.status_code == 302:
            f = FollowUp.objects.filter(ticket=t).latest("id")
            pagina = cliente().get(
                f"/view/?ticket=DH-1&email={t.submitter_email}&key={chave}"
            )
            cru = texto in pagina.content.decode() if "<script>" in texto else None
            extra = f" | script CRU na página pública={cru}" if cru is not None else ""
            print(f"{rotulo:52s} -> {desfecho(r)} | gravado={f.comment[:55]!r}{extra}")
        else:
            print(f"{rotulo:52s} -> {desfecho(r)}")

print(
    "\nTamanho do comentário (limite padrão do Django para campos de texto: 2.621.440 bytes):"
)
for n in (0, 1, 100_000, 2_600_000, 2_700_000):
    with isolado():
        t = Ticket.objects.get(id=1)
        ini = time.time()
        r = atualizar(t, {"comment": "a" * n})
        dur = time.time() - ini
        existe = (
            FollowUp.objects.filter(
                ticket=t, comment__startswith="a" * min(n, 5)
            ).exists()
            if n
            else None
        )
        print(
            f"comentário de {n:>9,} caracteres -> {desfecho(r)} em {dur:4.1f}s | follow-up criado={existe}"
        )
with isolado():
    t = Ticket.objects.get(id=1)
    r = atualizar(t, {"comment": "   "})
    print(
        f"comentário só com espaços            -> {desfecho(r)} | follow-ups={FollowUp.objects.filter(ticket=t).count()}"
    )

# ---------------------------------------------------------------------------
titulo(
    "S6 - Tabela de Decisão: público x comentário x Resolved -> follow-up, visibilidade e e-mail"
)
print(
    "regra | público | comentário | muda p/ Resolved | follow-up criado | texto aparece em /view/ | e-mails (destinatários)"
)
n = 0
for publico in (True, False):
    for comentario in (True, False):
        for resolve in (False, True):
            n += 1
            with isolado():
                t = Ticket.objects.get(id=1)
                # No demo o solicitante e o admin têm o MESMO e-mail, e o sistema nunca
                # notifica quem fez a atualização. Usamos um solicitante diferente.
                t.submitter_email = "cliente@example.com"
                t.save()
                antes = FollowUp.objects.filter(ticket=t).count()
                mail.outbox.clear()
                dados = {"public": "1"} if publico else {}
                corpo = {"title": t.title, "priority": t.priority, "queue": t.queue_id}
                corpo.update(dados)
                if comentario:
                    corpo["comment"] = "Mensagem para o cliente"
                if resolve:
                    corpo["new_status"] = "3"
                r = cliente(ADMIN).post(f"/tickets/{t.id}/update/", corpo)
                depois = FollowUp.objects.filter(ticket=t).count()
                criou = depois > antes
                t.refresh_from_db()
                pagina = (
                    cliente()
                    .get(
                        f"/view/?ticket=DH-1&email={t.submitter_email}&key={t.secret_key}"
                    )
                    .content.decode()
                )
                aparece = "Mensagem para o cliente" in pagina if comentario else "-"
                dest = sorted({d for m in mail.outbox for d in m.to})
                print(
                    f"TD-{n:02d}  | {'sim' if publico else 'não':7s} | {'sim' if comentario else 'não':10s} | "
                    f"{'sim' if resolve else 'não':16s} | {'sim' if criou else 'não':16s} | "
                    f"{aparece!s:17s} | {dest}"
                )

# ---------------------------------------------------------------------------
titulo("S7 - Autorização, CSRF e chamado inexistente")
with isolado():
    t = Ticket.objects.get(id=1)
    comum = User.objects.create_user("comum", "comum@example.com", "x")
    r = atualizar(t, {"comment": "x"}, c=cliente())
    print(
        f"anônimo envia atualização                 -> {desfecho(r)} {r.headers.get('Location', '')}"
    )
    r = atualizar(t, {"comment": "x"}, c=cliente(comum))
    print(
        f"usuário comum (não staff) envia           -> {desfecho(r)} {r.headers.get('Location', '')}"
    )
    r = atualizar(t, {"comment": "x"}, c=cliente(ADMIN, csrf=True))
    print(f"staff SEM token CSRF                      -> {desfecho(r)}")
    r = atualizar(t, {"comment": "x"}, url="/tickets/99999/update/")
    print(f"POST em chamado inexistente (id 99999)    -> {desfecho(r)}")
    r = cliente(ADMIN).get("/tickets/99999/")
    print(f"GET  página de chamado inexistente        -> {desfecho(r)}")
    r = cliente(ADMIN).get("/tickets/1/update/")
    print(f"GET  na rota de update (sem POST)         -> {desfecho(r)}")

# ---------------------------------------------------------------------------
titulo("S8 - Anexos na atualização (e atomicidade quando o anexo é inválido)")
for rotulo, nome, conteudo in (
    ("arquivo .txt válido", "nota.txt", b"ola"),
    ("arquivo .exe", "programa.exe", b"MZ" + b"0" * 10),
    ("arquivo .html", "pagina.html", b"<script>alert(1)</script>"),
    ("arquivo vazio (0 bytes)", "vazio.txt", b""),
    ("nome com ../../", "../../fora.txt", b"x"),
    ("nome com 300 caracteres", "a" * 296 + ".txt", b"x"),
):
    with isolado():
        t = Ticket.objects.get(id=1)
        r = atualizar(
            t, {"comment": "com anexo"}, arquivos=SimpleUploadedFile(nome, conteudo)
        )
        t.refresh_from_db()
        print(
            f"{rotulo:28s} -> {desfecho(r)} | anexos gravados="
            f"{sum(f.followupattachment_set.count() for f in t.followup_set.all())}"
        )
with isolado():
    t = Ticket.objects.get(id=1)
    r = atualizar(
        t,
        {"comment": "fechando", "new_status": "4"},
        arquivos=SimpleUploadedFile("programa.exe", b"MZ0000"),
    )
    t.refresh_from_db()
    print(
        f"\nFechar chamado COM anexo inválido (.exe) -> {desfecho(r)} | "
        f"status do chamado depois={NOMES.get(t.status)} | follow-ups criados="
        f"{FollowUp.objects.filter(ticket=t).count()}"
    )

# ---------------------------------------------------------------------------
titulo("S9 - Repetição da operação (duplo clique em 'Update This Ticket')")
with isolado():
    t = Ticket.objects.get(id=1)
    antes = FollowUp.objects.filter(ticket=t).count()
    for _ in range(2):
        atualizar(t, {"comment": "mesma mensagem"})
    print(
        f"2 envios idênticos -> follow-ups novos={FollowUp.objects.filter(ticket=t).count() - antes}"
        f" | e-mails enviados={len(mail.outbox)}"
    )

# ---------------------------------------------------------------------------
titulo("S10 - Dependência: a tela bloqueia resolver, o servidor bloqueia?")
with isolado():
    t1 = Ticket.objects.get(id=1)
    t2 = Ticket.objects.get(id=2)
    TicketDependency.objects.create(ticket=t1, depends_on=t2)
    print(f"DH-1 depende de SP-2 (aberto): can_be_resolved={t1.can_be_resolved}")
    r = atualizar(t1, {"new_status": "3", "comment": "tentando"})
    t1.refresh_from_db()
    print(
        f"POST new_status=3 -> {desfecho(r)} | status do DH-1 depois={NOMES.get(t1.status)}"
    )

# ---------------------------------------------------------------------------
titulo("S11 - Título e prioridade: limites e valores inválidos")
for n in (0, 1, 200, 201, 1000):
    with isolado():
        t = Ticket.objects.get(id=1)
        r = atualizar(t, {"title": "T" * n, "comment": "x"})
        t.refresh_from_db()
        print(
            f"título com {n:4d} caracteres -> {desfecho(r)} | título gravado tem {len(t.title)} caracteres"
        )
for valor in ("0", "1", "5", "6", "abc", ""):
    with isolado():
        t = Ticket.objects.get(id=1)
        r = atualizar(t, {"priority": valor, "comment": "x"})
        t.refresh_from_db()
        print(
            f"priority={valor!r:6s} -> {desfecho(r)} | prioridade gravada={t.priority}"
        )

# ---------------------------------------------------------------------------
titulo("S12 - Efeito de um status inválido (9) nas outras telas")
import re

with isolado():
    t = Ticket.objects.get(id=1)
    atualizar(t, {"new_status": "9"})
    t.refresh_from_db()
    c = cliente(ADMIN)
    chave = t.secret_key
    r1 = c.get("/tickets/1/")
    r2 = cliente().get(f"/view/?ticket=DH-1&email={t.submitter_email}&key={chave}")
    pagina = c.get("/tickets/").content.decode()
    consulta = re.search(r'name="query_encoded" value="([^"]+)"', pagina).group(1)
    lista = c.get(
        f"/datatables_ticket_list/{consulta}", {"draw": 1, "start": 0, "length": 25}
    ).json()
    ids = [linha["id"] for linha in lista["data"]]
    print(
        f"status gravado={t.status} | status em OPEN_STATUSES={t.status in Ticket.OPEN_STATUSES}"
    )
    print(
        f"GET /tickets/1/ (staff) -> {r1.status_code} | GET /view/ (público) -> {r2.status_code}"
    )
    print(
        f"fila padrão do atendente: total={lista['recordsTotal']} | DH-1 aparece na fila={1 in ids}"
    )
    print(
        f"opções de status oferecidas agora pela tela: {[s for s, _ in t.get_allowed_status_flow]}"
    )

# ---------------------------------------------------------------------------
titulo("S13 - Tempo gasto negativo ou absurdo: como o sistema exibe e soma")
for valor in ("-1:30", "99999:59"):
    with isolado():
        t = Ticket.objects.get(id=1)
        r = atualizar(t, {"comment": "tempo", "time_spent": valor})
        f = FollowUp.objects.filter(ticket=t).latest("id")
        pagina = cliente(ADMIN).get("/tickets/1/").content.decode()
        print(
            f"time_spent={valor!r:11s} -> {desfecho(r)} | exibido pelo sistema={f.time_spent_formated!r} "
            f"| tempo total do chamado={t.time_spent!r}"
        )

# ---------------------------------------------------------------------------
titulo(
    "S14 - Resolução: reabrir e resolver de novo SEM comentário apaga a solução anterior?"
)
with isolado():
    t = Ticket.objects.get(id=1)
    atualizar(
        t, {"new_status": "3", "comment": "Solução correta: reiniciar o serviço."}
    )
    t.refresh_from_db()
    print(f"1) Resolved com comentário -> resolução={t.resolution!r}")
    atualizar(t, {"new_status": "2", "comment": "Cliente reabriu."})
    t.refresh_from_db()
    print(
        f"2) Reopened               -> status={NOMES[t.status]} resolução={t.resolution!r}"
    )
    atualizar(t, {"new_status": "3"})
    t.refresh_from_db()
    print(
        f"3) Resolved SEM comentário -> status={NOMES[t.status]} resolução={t.resolution!r}"
    )

# ---------------------------------------------------------------------------
titulo(
    "S15 - Privacidade: o comentário PRIVADO (só da equipe) chega por e-mail a quem está em cópia?"
)
with isolado():
    t = Ticket.objects.get(id=1)
    t.submitter_email = "cliente@example.com"
    t.save()
    mail.outbox.clear()
    segredo = "SEGREDO-INTERNO-123"
    corpo = {
        "title": t.title,
        "priority": t.priority,
        "queue": t.queue_id,
        "comment": f"Nota interna: {segredo}",
    }  # sem 'public' = atualização privada
    cliente(ADMIN).post("/tickets/1/update/", corpo)
    f = FollowUp.objects.filter(ticket=t).latest("id")
    print(f"follow-up público={f.public}")
    for m in mail.outbox:
        texto = m.body + "".join(a[0] for a in getattr(m, "alternatives", []))
        print(f"e-mail para {m.to}: contém o texto privado={segredo in texto}")
    cc = t.ticketcc_set.all()
    print(
        "observadores (TicketCC) do chamado:",
        [(c.email_address, c.user_id) for c in cc],
    )

# ---------------------------------------------------------------------------
titulo(
    "S16 - Privacidade: comentário PRIVADO + mudar para Resolved aparece para o solicitante?"
)
for rotulo, extra in (
    ("privado, SEM mudar o status", {}),
    ("privado, mudando para Resolved", {"new_status": "3"}),
):
    with isolado():
        t = Ticket.objects.get(id=1)
        t.submitter_email = "cliente@example.com"
        t.save()
        corpo = {
            "title": t.title,
            "priority": t.priority,
            "queue": t.queue_id,
            "comment": "NOTA-INTERNA-XYZ",
            **extra,
        }  # sem 'public' = privado
        cliente(ADMIN).post("/tickets/1/update/", corpo)
        f = FollowUp.objects.filter(ticket=t).latest("id")
        t.refresh_from_db()
        pagina = (
            cliente()
            .get(f"/view/?ticket=DH-1&email=cliente@example.com&key={t.secret_key}")
            .content.decode()
        )
        print(
            f"{rotulo:34s} -> follow-up público={f.public} | campo Resolução={t.resolution!r} "
            f"| nota aparece na página pública={'NOTA-INTERNA-XYZ' in pagina}"
        )

print("\nFim da exploração. Banco original intacto; cópia temporária:", COPIA_BANCO)

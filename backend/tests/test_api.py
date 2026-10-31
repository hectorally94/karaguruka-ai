"""End-to-end checks against a real Postgres test database (see conftest.py)."""
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.engine import monthly_payment, parse_amount, parse_months
from app.intents import classify
from app.main import app
from app.privacy import mask_sensitive
from app.settings import ADMIN_PASSWORD, AGENT_PASSWORD


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def say(client, conversation_id, message):
    response = client.post("/api/chat", json={"conversation_id": conversation_id, "message": message})
    assert response.status_code == 200, response.text
    return response.json()


def new_chat(client, message):
    body = say(client, None, message)
    return body["conversation_id"], body


@pytest.mark.parametrize(
    "raw,hidden",
    [
        ("Ma carte 4970 1234 5678 9012 est bloquée", "4970 1234"),
        ("mon code est 1234", "1234"),
        ("mon mot de passe est secret123", "secret123"),
        ("IBAN FR76 3000 6000 0112 3456 7890 189", "3000 6000"),
    ],
)
def test_secrets_are_masked(raw, hidden):
    text, masked = mask_sensitive(raw)
    assert hidden not in text
    assert masked


def test_phone_number_is_not_masked():
    assert mask_sensitive("06 12 34 56 78")[0] == "06 12 34 56 78"


@pytest.mark.parametrize(
    "text,route",
    [
        ("Ma carte est bloquée", "card"),
        ("on m'a volé ma carte", "stolen"),
        ("J'ai perdu ma CB", "stolen"),
        ("je ne reconnais pas ce paiement", "fraud"),
        ("Je veux déposer une réclamation", "complaint"),
        ("Je veux simuler un crédit", "credit_sim"),
        ("Passez-moi un conseiller", "human"),
        ("Quelles cartes proposez-vous ?", "question"),
        ("Quels sont vos horaires ?", "question"),
    ],
)
def test_routes(text, route):
    assert classify(text) == route


def test_credit_math_and_parsing():
    assert parse_amount("15 000 €") == 15000
    assert parse_amount("20k") == 20000
    assert parse_months("4 ans") == 48
    assert round(monthly_payment(15000, 5.2, 48), 2) == 346.8


@pytest.mark.parametrize(
    "question,expected,title",
    [
        ("Quelles pièces pour ouvrir un compte ?", "justificatif de domicile", "ouverture"),
        ("Quels sont les horaires de l'agence Gare ?", "9 h à 18 h", "Agences"),
        ("Quel est le plafond de retrait de la Visa Gold ?", "1 500", "Produits"),
        ("Quel est le taux du crédit immobilier ?", "3,6", "crédit"),
    ],
)
def test_questions_are_answered_from_documents_with_a_source(client, question, expected, title):
    _, body = new_chat(client, question)
    assert expected in body["reply"]
    assert any(title.lower() in s["title"].lower() for s in body["sources"])


def test_unknown_question_is_not_invented_and_is_logged(client):
    question = f"Proposez-vous une assurance pour chevaux de course {uuid4().hex[:6]} ?"
    _, body = new_chat(client, question)
    assert body["intent"] == "sans_reponse"
    client.post("/api/login", json={"password": ADMIN_PASSWORD})
    assert any(q["question"] == question for q in client.get("/api/admin/unanswered").json())


def test_customers_never_receive_internal_documents(client):
    _, body = new_chat(client, "Quel est le code interne CF-27 de la cellule fraude et le barème interne ?")
    assert "CF-27" not in body["reply"]
    assert not any("interne" in s["title"].lower() for s in body["sources"])


def test_stolen_card_goes_straight_to_urgent_agent(client):
    conversation_id, body = new_chat(client, "On m'a volé ma carte")
    assert body["intent"] == "carte_perdue"
    body = say(client, conversation_id, "4821")
    assert body["transferred"] and body["ticket_ref"]
    client.post("/api/login", json={"password": AGENT_PASSWORD})
    ticket = next(t for t in client.get("/api/tickets").json() if t["ref"] == body["ticket_ref"])
    assert ticket["priority"] == "P1" and ticket["department"] == "Urgence cartes" and "4821" in ticket["summary"]


def test_full_card_number_is_never_stored(client):
    conversation_id, _ = new_chat(client, "Ma carte 4970 1234 5678 9012 est bloquée")
    messages = client.get(f"/api/conversations/{conversation_id}/messages").json()["messages"]
    assert not any("4970" in m["content"] for m in messages)


def test_complaint_flow_creates_ticket_and_frustration_raises_priority(client):
    conversation_id, _ = new_chat(client, "Je veux faire une réclamation")
    say(client, conversation_id, "Frais ou facturation")
    # The word "conseiller" in a description must not interrupt the flow.
    body = say(client, conversation_id, "Le conseiller m'a facturé 40 € deux fois, c'est inadmissible !")
    assert body["intent"] == "reclamation" and not body["transferred"]
    body = say(client, conversation_id, "06 12 34 56 78")
    assert body["ticket_ref"]
    client.post("/api/login", json={"password": AGENT_PASSWORD})
    ticket = next(t for t in client.get("/api/tickets").json() if t["ref"] == body["ticket_ref"])
    assert ticket["priority"] == "P1" and ticket["contact"] == "0612345678"


def test_credit_flow(client):
    conversation_id, _ = new_chat(client, "Je veux simuler un crédit")
    say(client, conversation_id, "Crédit auto")
    assert "Indiquez un montant" in say(client, conversation_id, "100")["reply"]
    say(client, conversation_id, "15 000")
    assert "346,80 €" in say(client, conversation_id, "48 mois")["reply"]


def test_agent_handoff_round_trip(client):
    conversation_id, body = new_chat(client, "Je voudrais parler à un conseiller")
    assert body["transferred"]
    # While an agent holds the conversation, the assistant stays silent.
    assert say(client, conversation_id, "Vous êtes là ?")["reply"] == ""
    client.post("/api/login", json={"password": AGENT_PASSWORD})
    ticket = next(t for t in client.get("/api/tickets").json() if t["ref"] == body["ticket_ref"])
    assert "Vous êtes là" in str(client.get(f"/api/tickets/{ticket['id']}").json()["messages"])
    assert client.post(f"/api/tickets/{ticket['id']}/take").status_code == 200
    assert client.post(f"/api/tickets/{ticket['id']}/take").status_code == 409
    assert client.post(f"/api/tickets/{ticket['id']}/reply", json={"message": "Bonjour, je vous écoute."}).status_code == 200
    messages = client.get(f"/api/conversations/{conversation_id}/messages").json()["messages"]
    assert messages[-1]["role"] == "agent"
    assert client.post(f"/api/tickets/{ticket['id']}/resolve").status_code == 200
    assert say(client, conversation_id, "Bonjour")["intent"] == "accueil"


def test_access_control(client):
    assert client.get("/api/documents").status_code == 401
    assert client.get("/api/tickets").status_code == 401
    assert client.post("/api/login", json={"password": "faux"}).status_code == 401
    client.post("/api/login", json={"password": AGENT_PASSWORD})
    assert client.get("/api/tickets").status_code == 200
    assert client.get("/api/documents").status_code == 403
    assert client.get("/api/admin/stats").status_code == 403


def wait_ready(client, document_id):
    # TestClient runs background tasks before returning, so processing has finished here.
    return next(d for d in client.get("/api/documents").json() if d["id"] == document_id)


def test_upload_replace_disable_delete(client):
    client.post("/api/login", json={"password": ADMIN_PASSWORD})
    code = uuid4().hex[:8]
    first = client.post("/api/documents", files={"file": ("test.txt", f"Le tarif zebrafrais{code} coûte 11 euros.".encode())}, data={"title": "Test tarif", "audience": "public"})
    assert first.status_code == 201
    document_id = first.json()["id"]
    assert wait_ready(client, document_id)["status"] == "ready"
    question = f"Quel est le tarif zebrafrais{code} ?"
    assert "11 euros" in client.post("/api/admin/ask", json={"question": question}).json()["answer"]

    # The old value disappears once the file is replaced.
    replaced = client.post(f"/api/documents/{document_id}/replace", files={"file": ("test.txt", f"Le tarif zebrafrais{code} coûte 22 euros.".encode())})
    assert replaced.status_code == 200 and replaced.json()["version"] == 2
    answer = client.post("/api/admin/ask", json={"question": question}).json()["answer"]
    assert "22 euros" in answer and "11 euros" not in answer

    assert client.patch(f"/api/documents/{document_id}", json={"active": False}).status_code == 200
    assert not client.post("/api/admin/ask", json={"question": question}).json()["found"]
    assert client.patch(f"/api/documents/{document_id}", json={"active": True, "expires_at": "2020-01-01"}).status_code == 200
    assert not client.post("/api/admin/ask", json={"question": question}).json()["found"]

    assert client.delete(f"/api/documents/{document_id}").status_code == 200
    assert not any(d["id"] == document_id for d in client.get("/api/documents").json())


def test_upload_rejects_bad_files_and_reports_unreadable_ones(client):
    client.post("/api/login", json={"password": ADMIN_PASSWORD})
    assert client.post("/api/documents", files={"file": ("virus.exe", b"MZ")}).status_code == 400
    assert client.post("/api/documents", files={"file": ("vide.txt", b"")}).status_code == 400
    bad = client.post("/api/documents", files={"file": ("casse.pdf", b"ceci n'est pas un pdf")})
    document = wait_ready(client, bad.json()["id"])
    assert document["status"] == "failed" and document["error"]
    client.delete(f"/api/documents/{document['id']}")


def test_stats(client):
    client.post("/api/login", json={"password": ADMIN_PASSWORD})
    stats = client.get("/api/admin/stats").json()
    assert stats["conversations"] >= stats["handled_by_ai"] >= 1
    assert stats["minutes_saved"] == stats["handled_by_ai"] * stats["handle_minutes"]
    assert len(stats["by_day"]) == 7

import re
from dataclasses import dataclass, field
from typing import Any

from psycopg.types.json import Jsonb

from .db import one, query
from .intents import classify, detect_sentiment, normalize
from .llm import answer_customer, summarize
from .privacy import mask_sensitive
from .rag import extractive_answer, is_confident, search, to_sources
from .settings import BANK_NAME, CREDIT_PRODUCTS, CURRENCY, RATE_LABEL, URGENT_CONTACT

MENU = ["Carte bloquée", "Ouvrir un compte", "Informations crédit", "Faire une réclamation", "Horaires des agences", "Parler à un agent"]
CREDIT_CHIPS = [p["label"] for p in CREDIT_PRODUCTS.values()]
KEEP_INTENT = {"accueil", "remerciement", "annulation", "securite", "relance"}


@dataclass
class Step:
    reply: str
    intent: str
    chips: list[str] = field(default_factory=list)
    flow: dict[str, Any] | None = None
    sources: list[dict] = field(default_factory=list)
    ticket_ref: str | None = None
    transferred: bool = False


def money(value: float) -> str:
    # Currencies with no cents in everyday use, such as the Burundian franc, are rounded to whole units.
    text = f"{value:,.2f}".replace(",", " ").replace(".", ",") if CURRENCY == "€" else f"{round(value):,}".replace(",", " ")
    return f"{text.removesuffix(',00')} {CURRENCY}"


def monthly_payment(amount: float, annual_rate_pct: float, months: int) -> float:
    r = annual_rate_pct / 100 / 12
    return amount * r / (1 - (1 + r) ** -months)


def parse_amount(text: str) -> float | None:
    match = re.search(r"(\d[\d\s.]*)(?:\s*(k|mille|millions?))?", normalize(text))
    if not match:
        return None
    digits = re.sub(r"[\s.]", "", match.group(1))
    if not digits:
        return None
    unit = match.group(2) or ""
    return float(digits) * (1_000_000 if unit.startswith("million") else 1000 if unit else 1)


def find_credit_product(normalized_text: str) -> str | None:
    for key, product in CREDIT_PRODUCTS.items():
        keywords = product.get("keywords") or [normalize(product["label"]).split()[-1]]
        if any(word in normalized_text for word in keywords):
            return key
    return None


def parse_months(text: str) -> int | None:
    match = re.search(r"(\d+)\s*(ans?|annees?|mois)?", normalize(text))
    if not match:
        return None
    return int(match.group(1)) * (12 if (match.group(2) or "").startswith("an") else 1)


def parse_phone(text: str) -> str | None:
    digits = re.sub(r"\D", "", text)
    return re.sub(r"[^\d+]", "", text) if 8 <= len(digits) <= 15 else None


def is_skip(text: str) -> bool:
    return bool(re.search(r"(passer|pas de numero|non merci|^non$)", normalize(text).strip()))


def transcript_of(conversation_id: str) -> str:
    rows = query("SELECT role, content FROM messages WHERE conversation_id = %s ORDER BY id DESC LIMIT 16", (conversation_id,))
    names = {"user": "Client", "assistant": "Assistant", "agent": "Conseiller"}
    # One line per message, so a customer cannot fake a line from the agent by typing a line break.
    return "\n".join(f"{names[m['role']]} : {' '.join(m['content'].split())}" for m in reversed(rows))


def create_ticket(conversation_id: str, kind: str, department: str, priority: str, summary: str, contact: str | None = None, data: dict | None = None) -> str:
    row = one(
        "INSERT INTO tickets (conversation_id, kind, department, priority, summary, contact, data) VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING ref",
        (conversation_id, kind, department, priority, summary, contact, Jsonb(data or {})),
    )
    return row["ref"]


def transfer(conversation_id: str, reason: str, priority: str, department: str, kind: str, data: dict | None = None) -> Step:
    transcript = transcript_of(conversation_id)
    last = next((l.removeprefix("Client : ") for l in reversed(transcript.split("\n")) if l.startswith("Client : ")), "non précisé")
    summary = summarize(transcript) or f"{reason}. Dernier message du client : {last}"
    summary = f"{reason}. {summary}" if not summary.startswith(reason) else summary
    ref = create_ticket(conversation_id, kind, department, priority, summary, data=data)
    query("UPDATE conversations SET status = 'transferred' WHERE id = %s", (conversation_id,))
    ahead = one("SELECT count(*)::int AS n FROM tickets WHERE status = 'open' AND priority <= %s", (priority,))["n"]
    return Step(
        reply=f"Je transmets votre demande au service {department} avec le résumé de notre échange, vous n'aurez pas à répéter. Dossier {ref}, {ahead} dossier(s) dans la file. Un conseiller va vous répondre ici.",
        intent=kind,
        ticket_ref=ref,
        transferred=True,
    )


def start_flow(route: str) -> Step:
    if route == "card":
        return Step(
            "Je m'occupe de votre carte. Que s'est-il passé ? Ne me communiquez jamais votre numéro complet ni votre code.",
            "carte",
            ["Code erroné plusieurs fois", "Carte perdue ou volée", "Paiement ou retrait refusé", "Opération que je ne reconnais pas"],
            {"type": "card_reason"},
        )
    if route == "complaint":
        return Step("Je vais enregistrer votre réclamation. Quel est le sujet ?", "reclamation", ["Frais ou facturation", "Opération contestée", "Qualité de service", "Autre sujet"], {"type": "complaint_category"})
    return Step("Je peux estimer votre mensualité. Quel type de crédit vous intéresse ?", "credit", CREDIT_CHIPS, {"type": "credit_product"})


def urgent_card(reason: str) -> Step:
    return Step(
        f"C'est une urgence, je vous mets en priorité. Si vous ne pouvez pas attendre, {URGENT_CONTACT}. Pour aider le conseiller, si une carte est concernée, donnez-moi uniquement ses 4 derniers chiffres. Sinon, répondez « je ne sais pas ».",
        "fraude" if reason == "fraud" else "carte_perdue",
        ["Je ne sais pas"],
        {"type": "card_last4", "reason": reason},
    )


def advance_flow(conversation_id: str, flow: dict, text: str, sentiment: str) -> Step:
    n = normalize(text)
    kind = flow["type"]

    if kind == "card_reason":
        if re.search(r"(perdu|vol)", n):
            return urgent_card("stolen")
        if re.search(r"(reconnais|fraud|pirat)", n):
            return urgent_card("fraud")
        topic = "paiement refusé plafond" if re.search(r"(refus|retrait|paiement)", n) else "code erroné"
        passages = search(f"carte bloquée {topic}", ["public"], 3)
        best = next((p for p in passages if is_confident(p)), passages[0] if passages else None)
        if not best:
            return Step("Je n'ai pas de procédure pour ce cas dans mes documents. Voulez-vous parler à un conseiller ?", "carte", ["Parler à un agent"], {"type": "card_followup"})
        return Step(f"{extractive_answer(best, topic)}\n\nEst-ce que cela résout votre problème ?", "carte", ["Oui, c'est réglé", "Parler à un agent"], {"type": "card_followup"}, to_sources([best]))

    if kind == "card_followup":
        if re.search(r"(agent|conseiller|\bnon\b)", n):
            return transfer(conversation_id, "Problème de carte non résolu", "P2", "Cartes", "carte")
        return Step("Parfait. Puis-je vous aider sur autre chose ?", "carte", MENU)

    if kind == "card_last4":
        match = re.search(r"\b\d{4}\b", text)
        if not match and not re.search(r"(sais pas|aucune idee|\bnon\b)", n):
            return Step("Il me faut seulement 4 chiffres, ou répondez « je ne sais pas ».", "carte_perdue", ["Je ne sais pas"], flow)
        last4 = match.group(0) if match else None
        label = "Suspicion de fraude" if flow["reason"] == "fraud" else "Carte perdue ou volée"
        suffix = f", carte finissant par {last4}" if last4 else ""
        return transfer(conversation_id, f"{label}{suffix}. Opposition à confirmer par le conseiller", "P1", "Urgence cartes", "fraude" if flow["reason"] == "fraud" else "carte_perdue", {"last4": last4})

    if kind == "complaint_category":
        return Step("Décrivez ce qui s'est passé, avec les dates et les montants si vous les avez.", "reclamation", flow={"type": "complaint_detail", "category": text[:80]})

    if kind == "complaint_detail":
        return Step("Merci. Sur quel numéro pouvons-nous vous rappeler ?", "reclamation", ["Passer"], {"type": "complaint_phone", "category": flow["category"], "detail": text})

    if kind == "complaint_phone":
        phone = parse_phone(text)
        if not phone and not is_skip(text):
            return Step("Ce numéro ne semble pas valide. Réessayez, ou choisissez « Passer ».", "reclamation", ["Passer"], flow)
        ref = create_ticket(conversation_id, "reclamation", "Réclamations", "P1" if sentiment == "frustré" else "P2", f"Réclamation ({flow['category']}) : {flow['detail']}", phone, {"category": flow["category"]})
        return Step(f"Votre réclamation est enregistrée sous la référence {ref}. Le service Réclamations va la traiter. Puis-je vous aider sur autre chose ?", "reclamation", MENU, ticket_ref=ref)

    if kind == "credit_product":
        product = find_credit_product(n)
        if not product:
            return Step("Choisissez un type de crédit.", "credit", CREDIT_CHIPS, flow)
        p = CREDIT_PRODUCTS[product]
        return Step(f"Quel montant souhaitez-vous emprunter ? Entre {money(p['min_amount'])} et {money(p['max_amount'])}.", "credit", flow={"type": "credit_amount", "product": product})

    if kind == "credit_amount":
        p = CREDIT_PRODUCTS[flow["product"]]
        amount = parse_amount(text)
        if not amount or not p["min_amount"] <= amount <= p["max_amount"]:
            return Step(f"Indiquez un montant entre {money(p['min_amount'])} et {money(p['max_amount'])}.", "credit", flow=flow)
        return Step(f"Sur quelle durée ? Entre {p['min_months']} et {p['max_months']} mois.", "credit", flow={"type": "credit_months", "product": flow["product"], "amount": amount})

    if kind == "credit_months":
        p = CREDIT_PRODUCTS[flow["product"]]
        months = parse_months(text)
        if not months or not p["min_months"] <= months <= p["max_months"]:
            return Step(f"Indiquez une durée entre {p['min_months']} et {p['max_months']} mois.", "credit", flow=flow)
        monthly = monthly_payment(flow["amount"], p["rate"], months)
        interest = monthly * months - flow["amount"]
        return Step(
            f"Estimation pour un {p['label'].lower()} de {money(flow['amount'])} sur {months} mois, au taux {RATE_LABEL} de {str(p['rate']).replace('.', ',')} % : environ {money(monthly)} par mois, soit {money(interest)} d'intérêts. Cette estimation n'est pas une offre de prêt. Voulez-vous qu'un conseiller vous rappelle ?",
            "credit",
            ["Être rappelé", "Non merci"],
            {"type": "credit_followup", "product": flow["product"], "amount": flow["amount"], "months": months, "monthly": monthly},
        )

    if kind == "credit_followup":
        if re.search(r"(rappel|\boui\b|conseiller)", n):
            return Step("Sur quel numéro pouvons-nous vous rappeler ?", "credit", flow={**flow, "type": "credit_phone"})
        return Step("Très bien. Puis-je vous aider sur autre chose ?", "credit", MENU)

    if kind == "credit_phone":
        phone = parse_phone(text)
        if not phone:
            return Step("Ce numéro ne semble pas valide. Pouvez-vous le redonner ?", "credit", flow=flow)
        p = CREDIT_PRODUCTS[flow["product"]]
        ref = create_ticket(conversation_id, "credit", "Crédit", "P3", f"Demande de rappel : {p['label']}, {money(flow['amount'])} sur {flow['months']} mois, estimation {money(flow['monthly'])} par mois.", phone, {"product": flow["product"], "amount": flow["amount"], "months": flow["months"]})
        return Step(f"C'est noté, référence {ref}. Un conseiller crédit va vous rappeler. Puis-je vous aider sur autre chose ?", "credit", MENU, ticket_ref=ref)

    return Step("Comment puis-je vous aider ?", "accueil", MENU)


def route_step(conversation_id: str, route: str, sentiment: str = "neutre") -> Step | None:
    if route in ("fraud", "stolen"):
        return urgent_card(route)
    if route in ("card", "complaint", "credit_sim"):
        return start_flow(route)
    if route == "human":
        return transfer(conversation_id, "Le client demande un conseiller", "P1" if sentiment == "frustré" else "P2", "Accueil clients", "transfert")
    return None


def not_found(conversation_id: str, question: str) -> Step:
    query("INSERT INTO unanswered_questions (conversation_id, question) VALUES (%s, %s)", (conversation_id, question))
    return Step("Je ne trouve pas cette information dans les documents de la banque et je préfère ne pas vous donner une réponse inexacte. Voulez-vous parler à un conseiller ?", "sans_reponse", ["Parler à un agent", "Poser une autre question"])


def answer_question(conversation_id: str, text: str, history: str, sentiment: str) -> Step:
    passages = search(text, ["public"])
    routed = answer_customer(text, history, passages)
    if routed:
        if routed["route"] == "answer":
            used = [p for p in passages if p["id"] in routed["passage_ids"]]
            return Step(routed["answer"], "information", ["Parler à un agent"], sources=to_sources(used))
        if routed["route"] == "not_found":
            return not_found(conversation_id, text)
        step = route_step(conversation_id, routed["route"], sentiment)
        if step:
            return step
    best = passages[0] if passages else None
    if is_confident(best):
        return Step(extractive_answer(best, text), "information", ["Parler à un agent"], sources=to_sources([best]))
    return not_found(conversation_id, text)


def ensure_conversation(conversation_id: str | None, channel: str, is_example: bool = False) -> str:
    if conversation_id:
        row = one("SELECT id FROM conversations WHERE id = %s", (conversation_id,))
        if row:
            return str(row["id"])
    return str(one("INSERT INTO conversations (channel, is_example) VALUES (%s, %s) RETURNING id", (channel, is_example))["id"])


def handle_message(conversation_id: str, raw_text: str) -> dict:
    text, masked = mask_sensitive(raw_text)
    conversation = one("SELECT flow, status, sentiment FROM conversations WHERE id = %s", (conversation_id,))
    history = transcript_of(conversation_id)
    query("INSERT INTO messages (conversation_id, role, content) VALUES (%s, 'user', %s)", (conversation_id, text))
    sentiment = "frustré" if detect_sentiment(text) == "frustré" else conversation["sentiment"]

    # Once an agent has the conversation, the assistant stays out of it.
    if conversation["status"] == "transferred":
        if one("SELECT id FROM tickets WHERE conversation_id = %s AND status <> 'resolved' LIMIT 1", (conversation_id,)):
            query("UPDATE conversations SET updated_at = now(), sentiment = %s WHERE id = %s", (sentiment, conversation_id))
            return {"reply": "", "chips": [], "intent": "transfert", "sources": [], "masked": masked, "ticket_ref": None, "transferred": True}
        query("UPDATE conversations SET status = 'active' WHERE id = %s", (conversation_id,))

    route = classify(text)
    flow = conversation["flow"]
    flow_type = flow["type"] if flow else None

    if masked and route == "question" and flow_type in (None, "card_last4"):
        step = Step("Pour votre sécurité, j'ai masqué ces informations. Comment puis-je vous aider ?", "securite", [] if flow else MENU, flow)
    elif route in ("fraud", "stolen") and flow_type not in ("card_reason", "card_last4"):
        step = urgent_card(route)
    elif route == "human" and flow_type not in ("card_followup", "complaint_detail"):
        step = route_step(conversation_id, "human", sentiment)
    elif flow and re.match(r"(annuler|stop|laisse tomber)\b", normalize(text).strip()):
        step = Step("C'est annulé. Comment puis-je vous aider ?", "annulation", MENU)
    elif flow:
        step = advance_flow(conversation_id, flow, text, sentiment)
    elif route == "greeting":
        step = Step(f"Bonjour, je suis Karaguruka AI, l'assistant de {BANK_NAME}. Comment puis-je vous aider ?", "accueil", MENU)
    elif route == "thanks":
        step = Step("Avec plaisir. Bonne journée !", "remerciement")
    elif route == "reprompt":
        step = Step("Je vous écoute, quelle est votre question ?", "relance")
    else:
        step = route_step(conversation_id, route, sentiment) or answer_question(conversation_id, text, history, sentiment)

    if masked and step.intent != "securite":
        step.reply = f"Pour votre sécurité, j'ai masqué des informations sensibles dans votre message. {step.reply}"
    if sentiment == "frustré" and step.intent == "information":
        step.reply += "\n\nJe comprends que la situation est pénible. Je peux vous passer un conseiller tout de suite."

    query(
        """UPDATE conversations SET flow = %s, sentiment = %s, updated_at = now(),
           primary_intent = CASE WHEN %s THEN primary_intent ELSE %s END WHERE id = %s""",
        (Jsonb(step.flow) if step.flow else None, sentiment, step.intent in KEEP_INTENT, step.intent, conversation_id),
    )
    query(
        "INSERT INTO messages (conversation_id, role, content, intent, sources) VALUES (%s, 'assistant', %s, %s, %s)",
        (conversation_id, step.reply, step.intent, Jsonb(step.sources)),
    )
    return {"reply": step.reply, "chips": step.chips, "intent": step.intent, "sources": step.sources, "masked": masked, "ticket_ref": step.ticket_ref, "transferred": step.transferred}

import re
import unicodedata


def normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text)
    stripped = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
    return re.sub(r"[’']", " ", stripped).lower()


INFO_QUESTION = re.compile(r"(quels?|quelles?|comment|combien|ou|qui|sous quel|dans quel|en combien|a qui|est ce que vous)\b")
CARD = r"\b(cartes?|cb|visa|mastercard)\b"
RULES = [
    ("fraud", rf"(fraude|frauduleu|pirat|arnaque|phishing|hameconn|(operation|paiement|retrait|prelevement|debit|virement)s?\b.{{0,40}}(inconnu|reconnais pas|pas moi|non autoris)|(argent|retir|preleve|debite|vire).{{0,60}}(pas moi|a mon insu|sans que je|sans mon accord|rien fait)|je ne reconnais pas)"),
    ("stolen", rf"({CARD}.{{0,40}}\b(volee?s?|perdue?s?|perte|egaree?s?|vol)\b|\b(vole|volee|perdu|perdue|egare|egaree|vol)\b.{{0,40}}{CARD})"),
    ("card", rf"({CARD}.{{0,50}}(bloqu|avale|refus|marche plus|fonctionne plus|ne passe|desactiv|code)|(bloqu|debloqu|avale).{{0,40}}{CARD})"),
    ("complaint", r"(reclamation|plainte|litige|mecontent|inadmissible|scandal|je conteste|contester|frais injustifi|remboursez)"),
    ("credit_sim", r"(simul|mensualit|combien.{0,30}(rembours|par mois)|calcul.{0,20}(credit|pret))"),
    ("human", r"(conseiller|\bagent\b|\bhumain\b|(parler|passer|passez).{0,20}quelqu un|vraie personne|parler a une personne|operateur)"),
]


def classify(text: str) -> str:
    n = normalize(text).strip()
    if re.fullmatch(r"(bonjour|bonsoir|salut|hello|coucou)[\s!.,]*", n):
        return "greeting"
    if re.fullmatch(r"(merci|parfait|ok merci|d accord merci)[\s\w!.,]{0,20}", n):
        return "thanks"
    if n.startswith("poser une autre question"):
        return "reprompt"
    for route, pattern in RULES:
        if re.search(pattern, n):
            # "Sous quel délai traitez-vous une réclamation ?" asks for information. It does not file a complaint.
            if route == "complaint" and INFO_QUESTION.match(n) and detect_sentiment(text) == "neutre":
                continue
            return route
    return "question"


def detect_sentiment(text: str) -> str:
    n = normalize(text)
    if "!!" in text or re.search(r"(inadmissible|scandal|honte|marre|colere|furieu|incompetent|toujours pas|depuis \d+ (jours|semaines|mois))", n):
        return "frustré"
    return "neutre"

"""Loads the fictional sample documents and example conversations. Safe to run more than once."""
from pathlib import Path

from .db import one
from .engine import ensure_conversation, handle_message
from .rag import process_document

SAMPLES = Path(__file__).resolve().parents[1] / "samples"
DOCUMENTS = [
    ("produits-et-tarifs.md", "Produits et tarifs 2026", "Produits", "public"),
    ("ouverture-de-compte.md", "Conditions d'ouverture de compte", "Comptes", "public"),
    ("credits.md", "Offres de crédit", "Crédit", "public"),
    ("agences-et-horaires.md", "Agences et horaires", "Agences", "public"),
    ("carte-bloquee.md", "Que faire si votre carte est bloquée", "Cartes", "public"),
    ("procedure-interne-opposition.md", "Procédure interne : opposition", "Procédures", "internal"),
]
CONVERSATIONS = [
    ["Quelles pièces faut-il pour ouvrir un compte ?"],
    ["Quels sont les horaires de l'agence Gare ?"],
    ["Quel est le plafond de retrait de la Visa Gold ?"],
    ["Ma carte est bloquée", "Code erroné plusieurs fois", "Oui, c'est réglé"],
    ["On m'a volé ma carte", "4821"],
    ["Je veux simuler un crédit", "Crédit auto", "15 000", "48 mois", "Non merci"],
    ["Je veux faire une réclamation", "Frais ou facturation", "On m'a prélevé 40 € de frais deux fois en octobre, c'est inadmissible !", "06 12 34 56 78"],
    ["Je voudrais parler à un conseiller"],
]


def main() -> None:
    for filename, title, category, audience in DOCUMENTS:
        if one("SELECT id FROM documents WHERE filename = %s", (filename,)):
            continue
        data = (SAMPLES / filename).read_bytes()
        doc = one(
            "INSERT INTO documents (title, filename, mime, size_bytes, file, category, audience) VALUES (%s,%s,'text/markdown',%s,%s,%s,%s) RETURNING id",
            (title, filename, len(data), data, category, audience),
        )
        process_document(str(doc["id"]))
        print(f"Document indexé : {title}")
    if one("SELECT id FROM conversations WHERE is_example LIMIT 1"):
        print("Conversations d'exemple déjà présentes.")
        return
    for messages in CONVERSATIONS:
        conversation_id = ensure_conversation(None, "text", is_example=True)
        for message in messages:
            handle_message(conversation_id, message)
    print(f"{len(CONVERSATIONS)} conversations d'exemple créées.")


if __name__ == "__main__":
    main()

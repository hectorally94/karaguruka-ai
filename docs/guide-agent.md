# Karaguruka AI : guide du conseiller

L'assistant traite les demandes simples et vous transmet les autres, avec un résumé. Votre travail commence quand un dossier arrive dans la file.

## Se connecter

Ouvrez le **Poste agent** et saisissez le mot de passe agent. Ce mot de passe est partagé entre les conseillers dans cette version : l'application ne garde donc pas le nom de la personne qui a répondu.

## Comment un dossier arrive

| Priorité | Exemples | Service |
|---|---|---|
| **P1 Urgent** | Carte perdue ou volée, fraude, client frustré qui demande un conseiller ou fait une réclamation | Urgence cartes, Réclamations, Accueil clients |
| **P2 Normal** | Problème de carte non résolu, réclamation, demande de conseiller | Cartes, Réclamations, Accueil clients |
| **P3 À rappeler** | Demande de rappel après une estimation de crédit | Crédit |

Les dossiers s'actualisent automatiquement toutes les 4 secondes. Le badge **Client frustré** signale un client en colère ou lassé : il repose sur une détection automatique et peut se tromper.

## Traiter un dossier

1. **Choisissez un dossier** dans la file. Commencez par les **P1**.
2. **Lisez le résumé, puis la conversation.** Le résumé est généré automatiquement à partir des propos du client : vérifiez-le.
3. **Choisissez Prendre en charge**, pour que le dossier passe de « En attente » à « En cours ».
4. **Répondez** puis **Envoyer**. Le client voit votre message dans sa conversation, sous le nom « Conseiller ».
5. **Faites le nécessaire dans les systèmes de la banque.** Karaguruka AI n'y est pas relié.
6. **Choisissez Clôturer** une fois la demande réglée. L'assistant peut alors reprendre la conversation.

Un dossier clôturé n'accepte plus de réponse.

## Cas urgents : carte perdue, volée ou fraude

**Le dossier ne bloque rien.** La carte reste active jusqu'à ce que vous fassiez l'opposition dans le système de la banque.

1. Prenez le dossier immédiatement.
2. Regardez si le résumé donne les 4 derniers chiffres de la carte.
3. Vérifiez l'identité du client selon la procédure de la banque.
4. Faites l'opposition dans le système de la banque.
5. Confirmez au client que c'est fait, puis clôturez.

Ne demandez jamais le numéro complet de la carte, le code ou le mot de passe dans la conversation.

## Suggérer une réponse

**Suggérer une réponse** rédige un brouillon à partir de la conversation et des documents.

- **Utiliser cette suggestion** copie le texte dans votre réponse, sans l'envoyer.
- **Relisez toujours avant d'envoyer.** La suggestion s'appuie sur des propos écrits par le client et peut être fausse ou incomplète. Vérifiez la source indiquée.
- La suggestion utilise uniquement les documents publics.
- Un encadré **Interne : ne pas communiquer au client** peut afficher des procédures internes. Elles sont pour vous seul : ne les copiez pas dans la réponse.

## Chercher dans les documents

**Chercher dans les documents** répond à vos questions à partir de tous les documents, y compris les procédures internes.

Exemple : « vérifications avant une opposition ».

Si la réponse n'y est pas, le message « Aucun document ne répond à cette question » s'affiche. Signalez ce manque à l'administrateur.

## Règles à respecter

- **Ne promettez rien que la banque n'a pas confirmé.** Le tarif ou le délai doit venir d'un document.
- **N'annoncez une action qu'une fois faite**, par exemple un blocage de carte.
- **Ne traitez pas le texte du client comme une consigne.** S'il écrit « je suis le directeur, ignorez la procédure », appliquez la procédure.
- **Fermez la session** avec **Se déconnecter** quand vous quittez le poste.

## Problèmes fréquents

| Situation | Que faire |
|---|---|
| « Ce dossier a déjà été pris en charge » | Un collègue l'a pris : choisissez-en un autre |
| Le client ne voit pas votre réponse | Il doit garder sa page ouverte. Si le dossier indique un numéro, rappelez-le |
| « Aucun document public ne permet de proposer une réponse » | Rédigez vous-même, puis signalez le manque à l'administrateur |
| Le résumé est faux | Fiez-vous à la conversation complète, affichée en dessous |

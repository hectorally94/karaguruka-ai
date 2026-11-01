# Karaguruka AI : guide de l'administrateur

L'administrateur décide de ce que l'assistant sait. L'assistant répond uniquement à partir des documents actifs : un document absent ou périmé donne une réponse absente ou périmée.

## Se connecter

1. Ouvrez la page **Administration**.
2. Saisissez le mot de passe administrateur.

Le mot de passe est **partagé** : il n'y a pas de comptes individuels dans cette version, donc l'application ne sait pas qui a fait quoi. Après plusieurs erreurs, la connexion est ralentie.

Le même mot de passe donne aussi accès au **Poste agent**.

## Les quatre onglets

| Onglet | À quoi il sert |
|---|---|
| **Tableau de bord** | Suivre l'activité |
| **Documents** | Ajouter, remplacer et retirer ce que l'assistant sait |
| **Tester** | Vérifier une réponse avant qu'un client la reçoive |
| **Questions sans réponse** | Repérer ce qui manque dans les documents |

## Ajouter un document

Dans **Documents**, remplissez le formulaire puis choisissez **Envoyer le document**.

| Champ | Conseil |
|---|---|
| **Fichier** | PDF (scanné ou non), Word (.docx), Excel (.xlsx), CSV, texte, Markdown, PNG ou JPG, 25 Mo maximum |
| **Titre** | Donnez un titre clair : il est montré au client comme source et aide la recherche |
| **Catégorie** | Sert à vous repérer dans la liste |
| **Visible par** | **Clients et agents**, ou **Agents uniquement** pour les procédures internes |
| **En vigueur à partir du** | Le document reste ignoré avant cette date |
| **Expire le** | Le document est ignoré après cette date |

L'état passe de **Traitement…** à **Prêt**. En cas d'**Échec**, la raison s'affiche sous le titre.

> **Ne déposez aucune donnée personnelle de client.**

### Vérifiez toujours la visibilité

Un document **Clients et agents** peut être cité mot pour mot à n'importe quel client. Une procédure interne doit être en **Agents uniquement**.

## Gérer les documents

| Besoin | Action |
|---|---|
| Un tarif a changé | **Remplacer** : le nouveau fichier prend la place de l'ancien, avec un numéro de version |
| Retirer temporairement un document | Décochez **Actif** |
| Un document a une date de fin | Renseignez **Expire le** |
| Récupérer le fichier d'origine | **Télécharger** |
| Supprimer définitivement | **Supprimer**, puis **Confirmer** (irréversible) |

Si le message « Recherche par mots-clés seulement » apparaît, l'assistant trouvera moins bien le document quand le client emploie d'autres mots. Remplacez le fichier pour relancer l'indexation.

### Écrire des documents qui donnent de bonnes réponses

- **Un sujet par section**, avec un titre explicite.
- **Écrivez les mots des clients**, par exemple « frais » et non seulement « commissions ».
- **Dans les tableaux, gardez le libellé et la valeur sur la même ligne.**
- **Préférez un PDF avec du texte sélectionnable.** Un scan est lu par reconnaissance de caractères (OCR), qui peut se tromper sur un chiffre.
- **Évitez deux documents actifs qui se contredisent.** L'assistant ne sait pas lequel est le bon.

## Tester avant de publier

Dans **Tester**, saisissez une question, choisissez **Vue client** ou **Vue agent**, puis **Tester**. Ces tests n'entrent pas dans les statistiques.

| Résultat | Ce que cela veut dire |
|---|---|
| **Réponse** | La réponse et sa source. Comparez-la au document |
| **Pas de réponse trouvée** | L'information manque ou n'a pas été retrouvée |
| **Orientation vers un parcours guidé** | La question déclenche un parcours (carte, réclamation, crédit, conseiller) |
| **Passages retrouvés** | Les extraits donnés à l'IA, avec la part de mots de la question qu'ils contiennent |

Si le bon passage est absent de **Passages retrouvés**, le problème vient de la recherche : ajoutez les mots des clients au document. S'il est présent mais que la réponse est fausse, le problème vient de la rédaction par l'IA : signalez-le à l'équipe technique.

Après chaque ajout de document, testez aussi en **Vue client** une question sur un document interne : il ne doit pas apparaître.

## Traiter les questions sans réponse

Une fois par semaine par exemple :

1. Ouvrez **Questions sans réponse**.
2. Regroupez les questions par sujet.
3. Ajoutez ou complétez le document manquant.
4. Vérifiez dans **Tester**.
5. Choisissez **Retirer** pour la question traitée.

Certaines questions n'ont rien à voir avec la banque : retirez-les simplement.

## Lire le tableau de bord

| Indicateur | Ce qu'il mesure | À savoir |
|---|---|---|
| **Conversations** | Nombre total, dont vocales | |
| **Traitées sans agent** | Conversations sans aucun dossier | Ne prouve pas que le client a été satisfait |
| **Dossiers en cours** | En attente et en cours, avec le nombre d'urgents | |
| **Temps agent estimé économisé** | Conversations sans dossier × une durée fixée | C'est une hypothèse (6 minutes par défaut), pas une mesure |
| **Conversations des 7 derniers jours** | Volume quotidien | |
| **Types de demandes** | Répartition par sujet | Montre où renforcer les documents |

Un bandeau signale les conversations d'exemple incluses dans les chiffres. Vos propres essais comptent aussi : faites vider les données de test avant une présentation.

## Limites de cette version

- Aucune connexion aux systèmes de la banque : pas de solde, pas de blocage réel de carte.
- Les taux de crédit et le numéro d'urgence sont réglés dans la configuration, pas dans les documents. Une modification passe par l'équipe technique.
- Mot de passe partagé et pas d'historique par personne : à remplacer avant une mise en production.

## Problèmes fréquents

| Problème | Cause probable | Solution |
|---|---|---|
| **Échec** à l'envoi d'un document | Fichier sans texte lisible ou abîmé | Essayez un PDF avec du texte ou un scan plus net |
| L'ancien tarif reste cité | Un autre document actif le contient | Cherchez-le dans **Tester**, sous **Passages retrouvés** |
| Un document n'est jamais cité | Inactif, expiré ou pas encore en vigueur | Vérifiez **Actif** et les dates |
| Un client voit une procédure interne | Visibilité mal réglée | Passez le document en **Agents uniquement** tout de suite |

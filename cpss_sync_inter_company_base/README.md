# CPSS Inter-Company Sync Base

Module Odoo 16 pour la synchronisation inter-sociétés : les documents saisis
dans une **société opérationnelle** sont recopiés à la demande dans une
**société cible** (déclarative).

## Fonctionnement

### États de partage d'une facture

| État | Signification |
|------|---------------|
| `not_shared` — Non Partagée | État initial |
| `proposed` — Proposée pour Partage | Un utilisateur *Sync User* a proposé la facture |
| `shared` — Partagée | La facture a été recopiée dans la société cible |
| `refused` — Refusée | Un administrateur a refusé le partage |

### Chaîne synchronisée

Selon l'origine de la facture, le module recrée dans la société cible :

- **Vente** : commande client → transferts (avec lots) → facture client ;
- **Achat** : commande fournisseur → transferts (avec lots) → facture fournisseur ;
- **Sans commande** : la facture seule, ligne à ligne.

Les documents créés dans la société cible restent **en brouillon** : leur
validation et leur lettrage restent à la charge du comptable.

Les paiements rapprochés d'une facture partagée sont recopiés dans la société
cible (paiement non lettré, à rapprocher manuellement).

### Correspondances

Les comptes et les taxes ne sont **pas** partagés entre sociétés : ils restent
propres à chacune et sont mis en correspondance à la volée.

- **Taxes** : correspondance déclarée dans la configuration si elle existe ;
  sinon nom + montant, à type d'usage, type de calcul et mode HT/TTC
  (`price_include`) identiques ; sinon montant seul *si le résultat est
  unique*. Toute ambiguïté ou absence de correspondance interrompt la
  synchronisation.
- **Comptes** : correspondance déclarée si elle existe ; sinon code identique ;
  sinon code normalisé sur 6/5/4 caractères (ex. `700` → `700000`). Sans
  correspondance, la synchronisation échoue avec un diagnostic.

Les deux onglets **Correspondances de Taxes** et **Correspondances de Comptes**
de la configuration permettent de forcer une correspondance lorsque la
recherche automatique reste ambiguë — typiquement deux taxes cibles de même
montant. Ces correspondances sont prioritaires sur toutes les autres
stratégies.

Ce choix est volontaire : sur un module de conformité, une facture cible avec
la mauvaise TVA ou le mauvais compte est plus dangereuse qu'une erreur visible.

## Installation

1. Copier le module dans `addons/`
2. Mettre à jour la liste des modules
3. Installer « CPSS Sync Inter Company Base »

## Configuration

Menu **Paramètres > Technique > Synchronisation Inter-Sociétés > Configuration**.

1. Renseigner la société opérationnelle et la société cible (une seule
   configuration peut exister).
2. Optionnel : choisir un journal par défaut de la société cible.
3. Cliquer sur **Tester la configuration** : les journaux, le plan comptable et
   les données partagées sont vérifiés.
4. Si des contacts ou produits sont rattachés à une seule des deux sociétés,
   cliquer sur **Configurer les données partagées**.

> ⚠️ « Configurer les données partagées » vide le champ *Société* des contacts
> et produits des deux sociétés configurées. L'opération est **irréversible**
> (la société d'origine n'est pas conservée) et n'est jamais déclenchée
> automatiquement, ni à l'installation ni à la mise à jour.

## Utilisation

1. Créer et valider une facture dans la société opérationnelle.
2. Cliquer sur **Proposer pour Partage** (groupe *Sync User*).
3. Cliquer sur **Partager** (groupe *Sync Admin*).
4. Vérifier la chaîne créée dans la société cible.

Les échecs sont consultables dans **Synchronisation Inter-Sociétés > Suivi >
Journaux d'Erreurs**. Ces journaux sont écrits dans une transaction dédiée :
ils subsistent même lorsque la synchronisation est annulée.

## Sécurité

- **Sync User** : proposer une facture, consulter les journaux.
- **Sync Admin** : partager, refuser, configurer.

Les actions de partage revérifient le groupe côté serveur — les attributs
`groups` des boutons ne masquent que l'interface.

Le module n'installe **aucune règle d'enregistrement permissive** : l'isolation
multi-sociétés standard d'Odoo reste intacte. Les accès inter-sociétés
nécessaires sont obtenus ponctuellement via `sudo()` dans le code de
synchronisation.

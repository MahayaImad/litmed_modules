# Access Management (`cpss_access_management`) — Odoo 16 Community

Application « **Gestion des Accès** » : un administrateur fonctionnel restreint
depuis un seul écran ce qu'un utilisateur peut voir et faire — masquer des
menus, interdire créer / modifier / supprimer / dupliquer / exporter /
archiver / imprimer sur un modèle, rendre un champ invisible, en lecture seule,
obligatoire ou sans lien externe, masquer des boutons, des onglets, le chatter,
les filtres et les regroupements, interdire un rapport précis, et restreindre
les enregistrements atteignables par un domaine — sans écrire une ligne de XML
ni de Python.

## Principes d'architecture

1. **Deux couches, toujours.** L'interface est nettoyée pour le confort
   (attributs `create` / `edit` / `delete` / `duplicate` / `export_xlsx` de la
   vue, attributs injectés sur les champs), et l'ORM lève une `AccessError`
   (`check_access_rights`, `write`, `copy`, `export_data`). Masquer un bouton n'est
   **pas** de la sécurité : seul le second niveau protège contre un appel RPC
   direct.
2. **Profils et utilisateurs.** Une restriction se configure soit sur un
   **profil d'accès** réutilisable (`cpss.access.profile`) assigné à plusieurs
   utilisateurs, soit directement sur un utilisateur. Les deux sources sont
   fusionnées avec la règle **« le plus restrictif gagne »** : rien ne
   ré-autorise jamais ce qu'une autre règle interdit.
3. **Un seul résolveur, mis en cache.** `cpss.access.resolver._get_restrictions`
   est décoré par `tools.ormcache('uid')` : chaque chargement de vue et chaque
   contrôle d'accès n'est qu'une lecture de dictionnaire. Toute écriture sur un
   profil, une règle ou un utilisateur appelle `registry.clear_cache()`, donc un
   changement est actif à la requête suivante, sans redémarrage.
   Avant même cette résolution, `_has_any_restriction()` répond en **une seule
   requête, mise en cache pour tout le registre** : une base qui ne configure
   aucune règle ne paie donc rien du tout. Coût mesuré : cette unique requête
   par durée de vie du cache — assez pour dépasser d'une unité le budget exact
   d'un test de performance du module `mail`
   (`test_render_template_inline_template_w_post_process_custom_local_links`,
   14 requêtes contre 13 attendues sur Odoo nu), ce qui est le prix connu de
   tout module qui se branche sur l'ORM.
4. **Anti-verrouillage.** Le superutilisateur, les administrateurs
   (`base.group_erp_manager`) et les membres du groupe *Access Manager* ne sont
   **jamais** restreints, quelle que soit la configuration. Impossible de
   s'enfermer dehors.
5. **Filtrage hors cache natif.** `ir.ui.menu.load_menus`,
   `_visible_menu_ids` et `ir.actions.actions.get_bindings` sont mis en cache
   par Odoo **sur le jeu de groupes** de l'utilisateur. Le module filtre donc
   *autour* de ces méthodes, jamais dedans, sinon deux utilisateurs partageant
   les mêmes groupes partageraient les mêmes menus.

## Groupes de sécurité

| Groupe | Droits |
|---|---|
| `cpss_access_management.group_access_manager` (Access Manager) | Configure les profils et les restrictions par utilisateur. N'est lui-même jamais restreint. Impliqué automatiquement par `base.group_system`. |

## Familles de restrictions

| Onglet du profil | Modèle | Effet |
|---|---|---|
| Menus | `cpss.access.menu.rule` | Masque un menu, et par défaut tout son sous-arbre. |
| Models | `cpss.access.model.rule` | Interdit `create`, `edit`, `delete`, `duplicate`, `export`, `archive`, le menu d'actions et l'impression ; masque aussi le chatter, les filtres et les regroupements de ce modèle. |
| Fields | `cpss.access.field.rule` | Rend un champ `invisible`, `readonly`, `required` ou supprime le lien externe (`no_open`). |
| Buttons & Tabs | `cpss.access.button.rule` | Masque un bouton, un onglet de notebook ou un lien nommé. |
| Reports | `cpss.access.report.rule` | Interdit un rapport précis (le modèle entier se traite via *Forbid Print*). |
| Domains | `cpss.access.domain.rule` | Restreint les enregistrements atteignables par un domaine, par mode (lecture / écriture / création / suppression). |
| Users | — | Assigne le profil aux utilisateurs concernés. |

La case **Hide Chatter Everywhere**, sur le profil comme sur l'utilisateur,
masque le chatter sur tous les modèles d'un coup.

Les mêmes familles sont disponibles **par utilisateur** dans l'onglet
« Access Management » de la fiche utilisateur.

## Boutons et domaines : deux choix expliqués

**Les boutons sont bloqués côté serveur.** Une règle de type *Button* porte le
`name` du bouton, c'est-à-dire la méthode qu'il appelle — exactement ce que le
client web poste sur `/web/dataset/call_button`. Le contrôleur est donc
surchargé pour refuser l'appel : masquer le bouton et bloquer la méthode sont
la même règle. Les onglets et les liens n'ont pas d'équivalent serveur : ce
sont des conteneurs, et ce qu'ils contiennent est protégé par les règles de
champs et de modèles.

**Les domaines ne passent pas par des `ir.rule`.** En Odoo, les règles
d'enregistrement de groupes différents sont combinées en **OU** : ajouter une
règle via un groupe technique *élargirait* ce que l'utilisateur voit, soit
l'inverse du but recherché. Le module surcharge donc
`ir.rule._compute_domain` (mis en cache par utilisateur) et combine son domaine
en **ET** avec le résultat natif. C'est le seul moyen d'exprimer « en plus de
tout le reste, cet utilisateur voit moins ».

## Points d'attention

* Un champ `readonly` est aussi bloqué **en écriture** côté serveur : un
  utilisateur restreint ne peut pas contourner l'attribut par un appel RPC.
  Idem pour `invisible`.
* Un champ ne peut pas être `required` et `invisible` pour la même cible : une
  contrainte l'interdit, sinon l'enregistrement deviendrait impossible à
  sauvegarder.
* Les nœuds de vue sont modifiés dans `get_view()` et jamais dans `_get_view()`,
  dont le résultat est mutualisé entre utilisateurs par le cache de vues.
* Le module surcharge `base`, donc **tous** les modèles : chaque point d'entrée
  commence par une lecture de cache et sort immédiatement quand l'utilisateur
  ne porte aucune restriction, ce qui est le cas de la grande majorité des
  requêtes.

## Limite connue

Masquer le bouton « **Ajouter un filtre personnalisé** » (et son équivalent
pour les regroupements) n'a **pas** de point d'extension côté serveur : cela
demanderait un patch JavaScript du composant de recherche. Ce n'est
volontairement pas fait — un patch non testable en profondeur sur ce composant
casserait la barre de recherche pour tous les modèles. Les filtres et
regroupements *prédéfinis* d'un modèle, eux, sont bien retirés de l'`arch`
côté serveur, et les règles de domaine restent la vraie protection : un filtre
personnalisé ne permet jamais de voir un enregistrement exclu par un domaine.

## Restrictions par société

Chaque règle porte une **société** facultative :

* société vide → la règle s'applique quelle que soit la société active ;
* société renseignée → la règle ne s'applique que lorsque l'utilisateur
  travaille dans cette société.

Le même utilisateur peut donc être restreint dans une société et libre dans
une autre, sans rien changer sur son compte lorsqu'il bascule. La résolution
est mise en cache sur le couple *(utilisateur, société active)*, et la société
active est celle du contexte `allowed_company_ids`, c'est-à-dire celle que le
client envoie réellement.

Un profil peut lui aussi porter une société : il est alors inactif dans toutes
les autres, règles comprises.

> `load_menus` est mis en cache par Odoo sur les groupes de l'utilisateur — pas
> sur la société. Le module filtre donc son résultat **en dehors** du cache, sur
> une copie : modifier le dictionnaire renvoyé par le cache le corromprait pour
> tout le monde.

## Couleur de société dans la barre de menu

Le champ **Couleur de la barre de menu** (`res.company.navbar_color`, format
`#RRGGBB`) colore la barre de navigation lorsque la société est active. Sur une
base multi-sociétés, c'est un garde-fou visuel contre la saisie dans la mauvaise
société.

Le mécanisme est volontairement côté navigateur :

1. les couleurs de toutes les sociétés autorisées voyagent dans les informations
   de session, donc aucun appel supplémentaire au chargement ;
2. la société active est lue dans le **cookie `cids`**, celui que le client
   maintient lui-même lors d'un basculement de société — la barre reflète donc
   ce que le client envoie réellement, sans dépendre de l'environnement serveur ;
3. la couleur du texte (noir ou blanc) est calculée depuis la luminance perçue
   du fond, pour rester lisible sans second champ à saisir.

Laisser le champ vide conserve l'apparence standard d'Odoo. `res.company` expose
aussi `action_cpss_couleur_par_defaut()`, qui attribue une couleur distincte à
chaque société n'en ayant pas.

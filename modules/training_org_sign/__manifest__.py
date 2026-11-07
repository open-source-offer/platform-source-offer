# -*- coding: utf-8 -*-
{
    "name": "Organisme de formation — Parapheur",
    "summary": "Signature électronique avancée des documents contractuels de formation",
    "description": """
Parapheur électronique pour les pièces contractuelles d'un organisme de
formation.

L'émargement des séances est déjà scellé par le socle (identité authentifiée,
horodatage serveur, empreinte chaînée) : c'est le niveau attendu par les
financeurs et l'administration pour prouver l'assiduité. Ce module traite un
besoin distinct et plus exigeant : faire signer à distance une pièce
**contractuelle** — au premier chef le contrat de formation conclu avec un
particulier, où le cocontractant est un consommateur et où la charge de la
preuve pèse sur l'organisme.

Ce que le module apporte :

- un parapheur adossé au document réglementaire **tel qu'il a été émis** : on
  fait signer l'exemplaire archivé et scellé, jamais un rendu recalculé ;
- des rôles de signature correspondant aux parties du contrat (organisme,
  cocontractant, financeur pour une convention tripartite) ;
- la reprise automatique de la signature sur le dossier contractuel une fois
  que **toutes** les parties ont signé, avec la date réelle de la dernière
  signature — donc l'ouverture du délai de rétractation à la bonne date ;
- un cloisonnement d'accès : une pièce contractuelle mise au parapheur reste
  invisible de tous ceux qui n'avaient déjà pas le droit de la lire.

# Licence — à lire avant toute modification

Ce module est publié sous **AGPL-3**, et non sous la licence propriétaire du
reste de la plateforme. Ce n'est pas un oubli : il dépend de `sign_oca`
(Odoo Community Association), publié sous AGPL-3, licence qui se propage à
tout travail qui en dérive.

Conséquences, non négociables :

- **aucun module propriétaire (OPL-1) ne doit déclarer ce module en
  dépendance, ni importer son code.** Le socle `training_org` reste
  indépendant : il expose le point de branchement
  `training.document._signature_backends()`, et c'est ce module qui vient s'y
  déclarer. Le sens de la dépendance est la seule chose qui confine la
  propagation de la licence ;
- ce module n'est pas installé automatiquement : il s'installe sur décision
  explicite de l'exploitant, qui accepte par là même la contrainte de licence ;
- l'AGPL impose d'offrir la source **aux utilisateurs du service**, et pas
  seulement à qui reçoit une copie du logiciel : dès lors que ce module est
  actif sur un abonnement, la source de `sign_oca` et de ce module doit leur
  être accessible.

# Notes de version

- 19.0.1.0.1 — correctif de sécurité : (1) le téléchargement du PDF depuis le
  portail (`/my/sign/<id>/download`) vérifie désormais que l'utilisateur est
  signataire (ou parent d'un signataire) ou interne avec droit de lecture,
  avant tout `sudo()` ; (2) les règles d'accès ne donnent plus accès à tous
  les enfants du contact de la société (formateurs inclus) : seul le contact
  signataire lui-même est retenu. Règles en `noupdate=0` : appliquées par la
  mise à jour du module. (3) la signature (`/sign_oca/sign`) exige un jeton
  valide ou le signataire authentifié ; (4) une post-migration invalide les
  jetons d'accès des PDF de parapheur déjà émis. Pour le téléchargement, les
  internes ne passent que par leurs droits propres.
""",
    "version": "19.0.1.0.1",
    "category": "Human Resources/Training",
    "author": "AMWALO.COM",
    "website": "https://www.amwalo.com",
    # AGPL-3 imposé par la dépendance à `sign_oca` — voir la description.
    "license": "AGPL-3",
    "depends": [
        "training_org",
        "sign_oca",
    ],
    "data": [
        # Les règles d'accès citent les modèles et les champs ajoutés ici :
        # sécurité d'abord, données et vues ensuite.
        "security/training_org_sign_security.xml",
        "security/ir.model.access.csv",
        "data/training_org_sign_data.xml",
        "views/sign_oca_request_views.xml",
        "views/training_file_views.xml",
    ],
    # Volontairement PAS `auto_install` : installer ce module engage
    # l'exploitant sur une obligation de licence (voir la description).
    "auto_install": False,
    "installable": True,
}

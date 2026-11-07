# Offre de code source

Ce dépôt publie le code source des composants sous licence libre à réciprocité réseau
(GNU AGPL-3.0) ou à fichiers (MPL-2.0) que nous modifions et exploitons dans notre service en
ligne, conformément à l'article 13 de l'AGPL-3.0 et à l'article 3.2 de la MPL-2.0.

Il ne contient que ces composants. Le reste du service n'est pas couvert par ces licences
et n'est pas publié.

## Retrouver la version que vous utilisez
Chaque version mise en service a une étiquette `<composant>-<version>` qui n'est jamais
déplacée. Le lien « Licences et code source » du service que vous utilisez renvoie vers
l'étiquette de la version exploitée. L'archive `.tar.gz` et son empreinte SHA-256
(`SHA256SUMS`) sont jointes à chaque publication (onglet Releases). Le dossier racine de
l'archive porte le nom `<composant>-<version>` : renommez-le en `<composant>` avant
installation.

## Contenu
| Répertoire | Composant | Licence | Remarque |
|---|---|---|---|
| `modules/training_org_sign/` | Parapheur des documents de formation | AGPL-3.0 | Requiert `sign_oca` (OCA, AGPL-3.0, commit indiqué dans `modules/training_org_sign/INDEX.md`) et un module **non publié** de NEW LEADERS ACADEMY PRIVEE, régi par une licence propriétaire : l'archive seule ne permet pas de reconstruire cette fonction. |
| `servers/cryptpad/` | Éditeur collaboratif (adaptations de CryptPad 2026.10.0, © XWiki SAS et contributeurs) | AGPL-3.0 | Configuration et répertoire `customize/` exploités, à appliquer sur l'étiquette amont indiquée dans `servers/cryptpad/UPSTREAM.md`. |

D'autres composants seront ajoutés ici au plus tard à leur mise en service.
Les composants non modifiés sont disponibles auprès de leur projet d'origine, aux
références indiquées dans chaque `INDEX.md`.

## Durée de disponibilité
Chaque version reste disponible tant qu'elle est en service, puis au moins trois ans après
son retrait.

## Licences
Textes intégraux dans `LICENSES/`. Les mentions de copyright figurent dans les fichiers.
Les modules du répertoire `modules/` sont © NEW LEADERS ACADEMY PRIVEE, SARLAU (Maroc),
sauf mention contraire dans les fichiers. Les composants de tiers restent la propriété de
leurs auteurs. Aucun droit de marque n'est concédé.

## Contact
Pour toute question, utilisez l'adresse de contact indiquée sur la page « Licences » du
service que vous utilisez.

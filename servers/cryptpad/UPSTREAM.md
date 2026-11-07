# Version amont et images épinglées

| Élément | Valeur |
|---|---|
| Logiciel amont | CryptPad (XWiki SAS et contributeurs), licence AGPL-3.0-or-later |
| Version déployée | **2026.10.0** (publiée le 2026-10-21, version stable la plus récente au 2026-11-07) |
| Étiquette amont (code source exact) | https://github.com/cryptpad/cryptpad/releases/tag/2026.10.0 — arbre : https://github.com/cryptpad/cryptpad/tree/2026.10.0 |
| Image officielle | `cryptpad/cryptpad:version-2026.10.0` |
| Digest de l'image (index multi-architecture amd64/arm64) | `sha256:61a12565a532a046996e47b3180a8ac9855d86c262dc98a1bb8d1107557bfe3a` (relevé sur Docker Hub le 2026-11-07, image publiée le 2026-10-23) |
| Reverse proxy | `caddy:2.11.8` — digest `sha256:4fcafa98afd1c2e642e353e3c5cf9ddbe892fcee14bc990e7ba2c5b78e51f9cf` |

L'image est **l'image officielle non modifiée** ; nos adaptations sont uniquement `customize/`, `config/`,
`Caddyfile` et `docker-compose.yml` de ce répertoire. Le code source complet de la version exploitée est donc
l'étiquette amont ci-dessus **plus** ce répertoire (obligation AGPL-3.0 §13).

Remarque de version : la version 2026.10.0 introduit un nouveau serveur (refonte de l'architecture, paquet npm
`cryptpad-server`) et un fichier `config/infra.js` ; les notes de version amont demandent de les lire avant toute
montée depuis une version antérieure à 2026.5.1.
Version précédente stable, pour information : 2026.5.1 (digest d'image `sha256:1f89dcdd28c1375f675e47b1d0cf07a51f3e9a07a79dc93c8cddb3295b98a34d`).
Elle utilise l'ancien format de configuration (`httpUnsafeOrigin`, `httpSafeOrigin` dans `config.js`, port websocket
séparé) : un retour arrière de version passe par la restauration d'une sauvegarde faite AVANT la montée et par
l'ancienne étiquette de ce dépôt, pas par un simple changement de digest.

## Procédure de montée de version

1. Lire les notes de version amont de chaque version intermédiaire.
2. Relever le nouveau digest : `docker buildx imagetools inspect cryptpad/cryptpad:version-<X> | head -3`
   (ou `docker pull` puis `docker image inspect`), et celui de Caddy de la même façon.
3. Comparer `customize.dist/` de la nouvelle étiquette avec nos surcharges (`diff -r` sur les fichiers de `customize/`
   qui ont un homologue amont : `application_config.js`, `loading.js`, `pre-loading.js`, `four-oh-four.js`, `*.html`,
   `src/less2/include/colortheme.less`, `translations/`) et reporter les évolutions.
4. Mettre à jour les digests dans `docker-compose.yml` et ce fichier ; mettre à jour la page `licence.html` si l'URL des sources change.
5. Essai en local (kit lancé avec des domaines localhost), `scripts/check-brand.sh` et `scripts/check-rendered.js`, puis staging Odoo, puis production
   après sauvegarde (`scripts/backup.sh`) et accord.
6. Publier ce répertoire dans le dépôt de sources AVANT ou en même temps que la mise en production.

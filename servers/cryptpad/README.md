# Éditeur collaboratif — configuration d'exploitation (identité neutre)

Ce répertoire contient **nos adaptations** d'un logiciel libre, nécessaires pour exploiter le service « Éditeur
collaboratif » : configuration, surcharges d'interface (`customize/`), reverse proxy et orchestration.
Il constitue, avec l'étiquette amont indiquée ci-dessous, le **code source correspondant à la version exploitée**
(licence GNU AGPL-3.0, article 13).

- **Logiciel amont** : CryptPad © XWiki SAS et contributeurs, distribué sous GNU AGPL-3.0-or-later.
- **Version amont exploitée** : `2026.10.0` — https://github.com/cryptpad/cryptpad/releases/tag/2026.10.0
  (arbre des sources : https://github.com/cryptpad/cryptpad/tree/2026.10.0). Image officielle non modifiée,
  épinglée par digest : voir [UPSTREAM.md](UPSTREAM.md).
- **Licence** : voir [LICENSE](LICENSE) (texte de la GNU AGPL-3.0, copie amont). Les en-têtes de copyright des
  fichiers repris d'amont sont conservés. Sans garantie.
- **Ce répertoire ne contient aucun secret** : les valeurs d'exploitation (noms de domaine, adresse de contact ACME)
  sont dans un fichier `.env` non versionné, modèle : [.env.example](.env.example).

## Contenu

| Chemin | Rôle |
|---|---|
| `docker-compose.yml` | Application (image officielle épinglée) + reverse proxy Caddy (TLS automatique), seuls 80/443 exposés |
| `Caddyfile` | Deux domaines (principal et bac à sable), HSTS, restriction de `frame-ancestors` aux origines autorisées |
| `config/config.js`, `config/infra.js` | Configuration serveur officielle (sans secret) |
| `config/decrees.seed.ndjson` | Réglages initiaux d'instance (décrets officiels) : inscription publique fermée, intégration en iframe, nom, suppression du don, etc. |
| `customize/` | Surcharges officielles de `customize.dist/` : identité neutre, logos, couleurs, textes fr/en/ar, page de licence |
| `tools/gen-assets.py` | Génération des icônes et aperçus neutres (formes géométriques), dépendance Pillow |

## Adaptations apportées (liste des modifications)

- Nom d'interface « Éditeur collaboratif » (fr, en, ar) : `customize/translations/*`, `customize/neutral-brand.js`
  (remplacement du nom du produit dans les chaînes d'interface au chargement), titres des pages `customize/*.html`,
  écrans de chargement `customize/loading.js`, `pre-loading.js`, `four-oh-four.js`.
- Logos génériques (`customize/CryptPad_logo*.svg`, noms de fichiers conservés car référencés par le code amont),
  icônes (`customize/favicon/`, `main-favicon.*`), aperçus (`customize/images/opengraph_preview/`), avatar par défaut.
- Couleurs neutres : `customize/src/less2/include/colortheme.less` (couleur de marque et couleurs d'applications).
- `customize/application_config.js` : mode « intégration uniquement » (`integrationOnly`), applications limitées à
  `drive` et `diagram`, langues `fr`/`en`/`ar`, liens d'accompagnement retirés (don, enquête, mentions externes),
  retours d'usage désactivés, entrée « Licence et code source » vers `customize/licence.html`.
- `customize/licence.html` + `customize/LICENSE.txt` : page statique « Licence et code source » (mention AGPL, lien vers ces sources).
- `config/config.js` : aucun appel sortant vers l'amont (`blockDailyCheck`, `removeDonateButton`), journaux sur la sortie standard sans adresse IP.
- `Caddyfile` : réglage de politique `frame-ancestors` (seules les origines Odoo déclarées peuvent intégrer l'éditeur).

Aucun contenu servi n'est réécrit par le proxy (pas de `sub_filter`, pas de masquage CSS/JS injecté).

## Reproduire

```bash
cp .env.example .env          # renseigner les domaines, les origines Odoo et ACME_EMAIL
# créer les répertoires de données (propriétaire uid 4001), y copier customize/ et config/decrees.seed.ndjson
# (voir scripts/prepare-data.sh du kit de déploiement), puis :
docker compose up -d
```

Les scripts d'installation, de déploiement, de sauvegarde et de contrôle de marque font partie du kit de
déploiement (répertoire `scripts/`), qui peut être publié avec ce répertoire s'il le souhaite : il ne contient aucun secret.

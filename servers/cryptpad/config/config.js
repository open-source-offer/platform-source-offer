// SPDX-FileCopyrightText: 2023 XWiki CryptPad Team <contact@cryptpad.org> and contributors
//
// SPDX-License-Identifier: AGPL-3.0-or-later

/*
 * Configuration serveur (version amont 2026.10.0). AUCUN SECRET dans ce fichier versionné.
 * Les domaines public et bac à sable sont fournis par les variables d'environnement
 * CPAD_MAIN_DOMAIN / CPAD_SANDBOX_DOMAIN (voir docker-compose.yml et .env.example),
 * pas par ce fichier. adminKeys reste vide : voir README-deploiement.md pour créer
 * (éventuellement) un compte administrateur.
 */
module.exports = {
    adminKeys: [],

    // Aucun appel sortant vers l'amont : pas de vérification quotidienne, pas de retour d'usage,
    // pas de bouton de don (les mêmes réglages sont aussi posés par decrees.seed.ndjson).
    blockDailyCheck: true,
    removeDonateButton: true,
    logFeedback: false,

    // Journalisation sur la sortie standard (docker logs), sans adresse IP.
    logToStdout: true,
    logLevel: 'info',
    logIP: false,

    // Pas d'éviction automatique des documents inactifs : Odoo reste le système de référence,
    // mais on évite toute suppression silencieuse de données.
    disableIntegratedEviction: true,

    maxUploadSize: 20 * 1024 * 1024,

    // Chemins relatifs à /cryptpad dans le conteneur (volumes : voir docker-compose.yml)
    filePath: './datastore/',
    archivePath: './data/archive',
    pinPath: './data/pins',
    taskPath: './data/tasks',
    blockPath: './block',
    blobPath: './blob',
    blobStagingPath: './data/blobstage',
    decreePath: './data/decrees',
    logPath: './data/logs',

    maxWorkers: { core: 2, storage: 2, http: 2, 'http-storage': 2 },
    maxJobs: { core: 10, storage: 10, http: 10, 'http-storage': 10 },

    installMethod: 'docker'
};

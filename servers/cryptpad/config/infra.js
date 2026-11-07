// SPDX-FileCopyrightText: 2026 XWiki CryptPad Team <contact@cryptpad.org> and contributors
//
// SPDX-License-Identifier: AGPL-3.0-or-later

/*
 * Topologie (version amont 2026.10.0) : un noeud par niveau, suffisant pour une VM 4 vCPU / 8 Go.
 * "public.origin" et "public.sandboxOrigin" sont ECRASES au démarrage par les variables
 * CPAD_MAIN_DOMAIN et CPAD_SANDBOX_DOMAIN (lib/load-config.js amont) : ne pas les éditer ici.
 * Aucun secret.
 */
module.exports = {
    public: {
        origin: "http://localhost:3000",
        sandboxOrigin: "http://localhost:3001",
        httpHost: "0.0.0.0",
        httpPort: 3000,
        httpSafePort: 3001,
        externalWebsocketURL: undefined,
        fileHost: undefined,
        httpServerId: ""
    },
    front: [ { host: "0.0.0.0", port: 3010 } ],
    core: [ { host: "0.0.0.0", port: 3020 } ],
    storage: [ { host: "0.0.0.0", port: 3030, wsPort: 3040 } ]
};

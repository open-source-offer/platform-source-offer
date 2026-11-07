// SPDX-FileCopyrightText: 2023 XWiki CryptPad Team <contact@cryptpad.org> and contributors
//
// SPDX-License-Identifier: AGPL-3.0-or-later

/*
 * Surcharge officielle de customize.dist/application_config.js (version amont 2026.10.0).
 * Identité neutre « Éditeur collaboratif » - voir README.md de ce répertoire.
 * Aucun secret dans ce fichier.
 */
(() => {
const factory = (AppConfig) => {
    // --- Usage : intégration Odoo uniquement (Integration API, aucun compte) -------------
    // Les pages d'accueil/connexion/inscription renvoient vers la page 404 neutre ; seules les
    // sessions ouvertes via /integration/ (iframe Odoo) sont servies.
    AppConfig.integrationOnly = true;
    // Applications exposées. 'drive' ne doit jamais être retiré. Seul 'diagram' est utilisé par
    // le module Odoo elearning_collab ; ajouter d'autres types ici si un besoin apparaît.
    AppConfig.availablePadTypes = ['drive', 'diagram'];

    // --- Langues : français, anglais, arabe (les autres traductions amont ne sont pas neutralisées)
    AppConfig.availableLanguages = ['fr', 'en', 'ar'];

    // --- Liens retirés (pied de page / menu « À propos ») ----------------------------------
    AppConfig.imprint = false;
    AppConfig.privacy = false;
    AppConfig.terms = false;
    AppConfig.roadmap = false;
    AppConfig.status = false;
    AppConfig.surveyURL = "";
    AppConfig.donateURL = "";
    AppConfig.disableFeedback = true;      // aucun retour d'usage envoyé
    AppConfig.enableEarlyAccess = false;
    AppConfig.hideUsageBar = true;
    AppConfig.hostDescription = {
        default: "Éditeur collaboratif pour les ateliers de cours.",
        fr: "Éditeur collaboratif pour les ateliers de cours.",
        en: "Collaborative editor for course workshops.",
        ar: "المحرر التعاوني لورشات الدورات."
    };

    // --- Obligation AGPL-3.0 §13 : entrée « Licence et code source » -----------------------
    // Le menu « À propos » (libellé « Licence et code source », cf. translations/) et le pied de
    // page des pages d'information pointent vers une page statique locale, sans appel externe.
    AppConfig.source = {
        default: '/customize/licence.html'
    };

    // --- Couleurs neutres -----------------------------------------------------------------
    AppConfig.appBackgroundColor = '#5b6b7a';
    AppConfig.whiteboardPalette = [
        '#000000', '#FFFFFF', '#848484', '#3F5B73', '#8FA3B5', '#2C4152', '#5B6B7A', '#B0BEC5',
        '#FF0000', '#FF8000', '#FFFF00', '#00FF00', '#00FFFF', '#0000FF', '#FF00FF', '#800080'
    ];
    return AppConfig;
};

// Do not change code below
if (typeof(module) !== 'undefined' && module.exports) {
    module.exports = factory(
        require('../www/common/application_config_internal.js')
    );
} else if ((typeof(define) !== 'undefined' && define !== null) && (define.amd !== null)) {
    define(['/common/application_config_internal.js'], factory);
}
})();

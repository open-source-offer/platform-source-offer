// SPDX-FileCopyrightText: 2023 XWiki CryptPad Team <contact@cryptpad.org> and contributors
//
// SPDX-License-Identifier: AGPL-3.0-or-later

// Surcharge officielle (customize/translations/messages.fr.js) : textes français, identité neutre.
define(['/common/translations/messages.fr.js', '/customize/neutral-brand.js'], function (Messages, Neutral) {
    return Neutral(Messages, {
        name: 'Éditeur collaboratif',
        drive: 'Drive',
        overrides: {
            main_title: 'Éditeur collaboratif',
            main_catch_phrase: 'Éditeur collaboratif',
            og_default: 'Éditeur collaboratif',
            label_logo: 'Logo',
            home_host: 'Éditeur collaboratif pour les ateliers de cours.',
            user_about: 'Licence et code source',
            footer_source: 'Licence et code source',
            info_sourceFlavour: '<a>Licence et code source</a>'
        }
    });
});

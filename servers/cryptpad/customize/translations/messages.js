// SPDX-FileCopyrightText: 2023 XWiki CryptPad Team <contact@cryptpad.org> and contributors
//
// SPDX-License-Identifier: AGPL-3.0-or-later

// Surcharge officielle (customize/translations/messages.js) : textes anglais, identité neutre.
define(['/common/translations/messages.js', '/customize/neutral-brand.js'], function (Messages, Neutral) {
    return Neutral(Messages, {
        name: 'Collaborative editor',
        drive: 'Drive',
        overrides: {
            main_title: 'Collaborative editor',
            main_catch_phrase: 'Collaborative editor',
            og_default: 'Collaborative editor',
            label_logo: 'Logo',
            home_host: 'Collaborative editor for course workshops.',
            user_about: 'Licence and source code',
            footer_source: 'Licence and source code',
            info_sourceFlavour: '<a>Licence and source code</a>'
        }
    });
});

// SPDX-FileCopyrightText: 2023 XWiki CryptPad Team <contact@cryptpad.org> and contributors
//
// SPDX-License-Identifier: AGPL-3.0-or-later

// Surcharge officielle (customize/translations/messages.ar.js) : textes arabes, identité neutre.
// Les chaînes arabes amont restent celles du projet ; seuls le nom du produit et les entrées
// de licence/code source sont remplacés. Relecture par un arabophone recommandée.
define(['/common/translations/messages.ar.js', '/customize/neutral-brand.js'], function (Messages, Neutral) {
    return Neutral(Messages, {
        name: 'المحرر التعاوني',
        drive: 'Drive',
        overrides: {
            main_title: 'المحرر التعاوني',
            main_catch_phrase: 'المحرر التعاوني',
            og_default: 'المحرر التعاوني',
            label_logo: 'Logo',
            home_host: 'المحرر التعاوني لورشات الدورات.',
            user_about: 'الترخيص والشيفرة المصدرية',
            footer_source: 'الترخيص والشيفرة المصدرية',
            info_sourceFlavour: '<a>الترخيص والشيفرة المصدرية</a>'
        }
    });
});

// Adaptation de l'instance : identité neutre (nom « Éditeur collaboratif »).
// Module chargé par customize/translations/messages*.js (mécanisme officiel de surcharge
// des traductions). Il remplace, dans les chaînes de l'interface, le nom du produit amont
// par le nom neutre, et retire les liens de don/blog/réseaux sociaux/site amont.
// La mention de licence et de code source est portée par customize/licence.html.
define([], function () {
    var BRAND_RE = /Crypt[Pp]ad/g; // noms : « CryptPad » et variantes de casse
    var DRIVE_RE = /CryptDrive/g;

    var walk = function (obj, name, drive) {
        Object.keys(obj).forEach(function (k) {
            var v = obj[k];
            if (typeof (v) === 'string') {
                obj[k] = v.replace(DRIVE_RE, drive).replace(BRAND_RE, name);
            } else if (Array.isArray(v)) {
                v.forEach(function (e, i) {
                    if (typeof (e) === 'string') { v[i] = e.replace(DRIVE_RE, drive).replace(BRAND_RE, name); }
                });
            }
        });
    };

    /*
     * Messages : objet de traduction chargé (modifié en place et retourné).
     * texts : { name, drive, overrides: { clé: texte } }
     */
    return function (Messages, texts) {
        walk(Messages, texts.name, texts.drive);
        Object.keys(texts.overrides).forEach(function (k) { Messages[k] = texts.overrides[k]; });
        return Messages;
    };
});

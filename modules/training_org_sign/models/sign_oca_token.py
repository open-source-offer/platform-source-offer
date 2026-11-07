# Copyright 2026 NEW LEADERS ACADEMY PRIVEE, SARLAU
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
"""Le jeton du signataire est un secret : seul un administrateur le lit.

Le jeton d'un signataire tient lieu d'authentification sur le portail du
parapheur (consultation, signature). Or le champ ``access_token`` du
``portal.mixin`` et le champ ``access_url`` (qui l'embarque) sont lisibles par
tous ceux qui lisent le signataire, donc par un interne gestionnaire de
formation : il pouvait lire le jeton du cocontractant et signer à sa place.
Les champs sont donc réservés à ``base.group_system``.

Les chemins natifs qui ont besoin du lien (envoi, invitation, signature par
soi-même) le lisent en ``sudo()``, après leur propre contrôle d'accès.
"""
from odoo import fields, models


class SignOcaRequestSigner(models.Model):
    _inherit = "sign.oca.request.signer"

    access_token = fields.Char(groups="base.group_system")
    access_url = fields.Char(groups="base.group_system", compute_sudo=True)

    def _portal_ensure_token(self):
        # Le mixin relit le jeton avec l'environnement de l'appelant : en
        # `sudo()`, sinon la lecture échoue pour un non-administrateur. Le jeton
        # n'est renvoyé qu'à du code serveur, jamais exposé par un champ.
        return super(SignOcaRequestSigner, self.sudo())._portal_ensure_token()

    def sign(self):
        # Reprise de la méthode amont : elle lit `access_url`, désormais réservé.
        # Le contrôle d'accès reste celui d'amont (`is_allow_signature` : le
        # partenaire de l'appelant est le signataire) ; seule la lecture du
        # lien se fait en `sudo()`.
        self.ensure_one()
        if not self.is_allow_signature:
            return super().sign()
        return {
            "target": "new",
            "type": "ir.actions.act_url",
            "url": self.sudo().access_url,
        }


class SignOcaRequest(models.Model):
    _inherit = "sign.oca.request"

    def action_send(self, sign_now=False, message=""):
        # L'envoi génère les jetons et compose le lien de chaque invitation :
        # il lit donc `access_url` des signataires. Droit d'écriture vérifié
        # avec les droits de l'appelant AVANT de passer en `sudo()` (qui
        # conserve l'utilisateur courant : l'auteur de la notification et le
        # test « signer maintenant » restent ceux de l'appelant).
        self.check_access("write")
        return super(SignOcaRequest, self.sudo()).action_send(
            sign_now=sign_now, message=message
        )

    def _set_action_log_vals(self, action, **kwargs):
        # Le journal n'est pas un endroit où conserver un secret d'accès : le
        # jeton n'y est plus enregistré (et les jetons déjà journalisés sont
        # vidés par la post-migration).
        vals = super()._set_action_log_vals(action, **kwargs)
        vals["access_token"] = False
        return vals

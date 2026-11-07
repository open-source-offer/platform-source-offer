# Copyright 2026 NEW LEADERS ACADEMY PRIVEE, SARLAU
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
"""Portail du parapheur : contrôle d'accès du téléchargement du PDF.

La route amont ``/my/sign/<id>/download`` lit la demande en ``sudo()`` à partir
du seul identifiant puis délivre un jeton d'accès sur la pièce jointe : tout
utilisateur connecté, portail compris, pouvait télécharger le PDF de n'importe
quel parapheur de n'importe quelle société. Le contrôle est posé ici, AVANT tout
``sudo()``, sans toucher à ``sign_oca`` (copie amont de l'OCA).
"""
from werkzeug.exceptions import NotFound

from odoo import http
from odoo.http import request
from odoo.tools import consteq

from odoo.addons.sign_oca.controllers.main import PortalSign


class TrainingOrgPortalSign(PortalSign):
    def _download_is_allowed(self, request_id):
        """La demande est-elle accessible à l'utilisateur courant ?

        Deux portes, exclusives selon le type d'utilisateur :
        (a) utilisateur portail : son partenaire, ou l'un de ses enfants,
            figure parmi les signataires (même domaine que la liste du
            portail) ;
        (b) utilisateur interne : il lit la demande avec ses propres droits
            (règles d'enregistrement et multi-société comprises).
        """
        user = request.env.user
        if user._is_internal():
            # Un interne ne passe QUE par ses droits propres : la porte (a)
            # repose sur une relation de contact qu'un interne autorisé à
            # écrire sur `res.partner` pourrait fabriquer (rattacher le
            # cocontractant à son propre contact) pour contourner les règles.
            sign_request = request.env["sign.oca.request"].browse(request_id).exists()
            return bool(sign_request) and sign_request.has_access("read")
        # Utilisateur portail : le comptage est fait en `sudo()` (les règles
        # sur les signataires le masqueraient), mais borné à l'identifiant de
        # la demande et au partenaire de l'appelant, et sans rien en livrer.
        domain = self.get_sign_requests_domain(request) + [
            ("request_id", "=", request_id)
        ]
        return bool(
            user.partner_id
            and request.env["sign.oca.request.signer"]
            .sudo()
            .search_count(domain, limit=1)
        )

    @http.route(
        ["/my/sign/<int:request_id>/download"], type="http", auth="user", website=True
    )
    def portal_download_signed(self, request_id, **kw):
        # Même réponse pour « inexistant » et « interdit » : pas d'oracle.
        if not self._download_is_allowed(request_id):
            return request.not_found()
        return super().portal_download_signed(request_id, **kw)

    @http.route(
        ["/sign_oca/sign/<int:signer_id>/<string:access_token>"],
        type="jsonrpc",
        auth="public",
        website=True,
    )
    def get_sign_oca_sign_access(
        self, signer_id, access_token, items, latitude=False, longitude=False
    ):
        """Signature : jeton valide OU signataire authentifié, rien d'autre.

        En amont, `_document_check_access` laisse passer sans jeton valide tout
        interne qui peut LIRE le signataire, et `action_sign` ne vérifie ni le
        jeton ni le partenaire : on pouvait signer à la place du cocontractant.
        """
        signer_sudo = request.env["sign.oca.request.signer"].sudo().browse(signer_id)
        if not signer_sudo.exists():
            raise NotFound()
        token_ok = bool(
            signer_sudo.access_token
            and access_token
            and consteq(signer_sudo.access_token, access_token)
        )
        user = request.env.user
        identity_ok = bool(
            not user._is_public()
            and signer_sudo.partner_id
            and signer_sudo.partner_id == user.partner_id
        )
        if not (token_ok or identity_ok):
            raise NotFound()
        # Le jeton n'est transmis (au journal) que s'il a réellement servi.
        return signer_sudo.action_sign(
            items,
            access_token=access_token if token_ok else False,
            latitude=latitude,
            longitude=longitude,
        )

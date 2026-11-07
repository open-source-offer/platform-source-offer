# Copyright 2026 NEW LEADERS ACADEMY PRIVEE, SARLAU
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
"""Invalide les jetons d'accès des PDF de parapheur.

`ir.attachment.generate_access_token` réutilise le jeton existant : les jetons
obtenus via la faille du téléchargement (`/my/sign/<id>/download`) resteraient
valables sur `/web/content`. On les vide ; le signataire légitime en obtient un
nouveau au prochain téléchargement. Idempotent.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute(
        """
        UPDATE ir_attachment
           SET access_token = NULL
         WHERE res_model = 'sign.oca.request'
           AND res_field = 'data'
           AND access_token IS NOT NULL
        """
    )
    _logger.info(
        "training_org_sign 19.0.1.0.1 : %s jeton(s) d'accès de PDF de parapheur "
        "invalidé(s).",
        cr.rowcount,
    )
    # Le journal du parapheur conservait le jeton du signataire en clair.
    cr.execute(
        "UPDATE sign_oca_request_log SET access_token = NULL "
        "WHERE access_token IS NOT NULL"
    )
    _logger.info(
        "training_org_sign 19.0.1.0.1 : %s jeton(s) purgé(s) du journal du "
        "parapheur.",
        cr.rowcount,
    )

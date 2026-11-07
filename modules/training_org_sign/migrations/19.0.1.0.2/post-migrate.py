# Copyright 2026 NEW LEADERS ACADEMY PRIVEE, SARLAU
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
"""Purge des liens à jeton dans les invitations déjà postées (ADR-SIGN-02, D2).

Avant 19.0.1.0.2, l'invitation de signature était un ``mail.message`` sans
modèle dont l'auteur était l'expéditeur : le lien, jeton compris, restait
lisible de lui. On remplace le lien par la liste du portail dans la copie
Odoo. Les courriels déjà remis ne sont pas touchés (leur lien continue de
fonctionner), et ``mail_mail.body_html`` non plus : il n'est lisible que par
``base.group_system``, qui lit déjà le jeton.

La purge ne rend pas les jetons déjà lus inutilisables : le renouvellement est
une décision d'exploitation, via
``sign.oca.request._training_rotate_signer_tokens()`` (jamais automatique).
Cette migration ne fait que journaliser le nombre de signataires concernés.

Elle rejoue aussi, par sécurité, les deux purges de 19.0.1.0.1 (jetons de
pièces jointes et jetons du journal) : on ignore si cette migration a bien tourné
en production. Idempotent : une seconde passe ne trouve plus de motif.
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

ROTATE_PARAM = "training_org_sign.rotate_tokens_on_upgrade"
TOKEN_LINK = r"""/sign_oca/document/[0-9]+/[^"'<>[:space:]?#&]+"""


def migrate(cr, version):
    # Filet de sécurité : purges de 19.0.1.0.1, rejouées.
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
        "training_org_sign 19.0.1.0.2 : %s jeton(s) d'accès de PDF de parapheur "
        "invalidé(s).",
        cr.rowcount,
    )
    cr.execute(
        "UPDATE sign_oca_request_log SET access_token = NULL "
        "WHERE access_token IS NOT NULL"
    )
    _logger.info(
        "training_org_sign 19.0.1.0.2 : %s jeton(s) purgé(s) du journal du "
        "parapheur.",
        cr.rowcount,
    )
    cr.execute(
        """
        UPDATE mail_message
           SET body = regexp_replace(body, %s, '/my/sign_requests', 'g')
         WHERE model IS NULL
           AND message_type = 'user_notification'
           AND body LIKE '%%/sign_oca/document/%%'
        """,
        [TOKEN_LINK],
    )
    _logger.info(
        "training_org_sign 19.0.1.0.2 : lien à jeton purgé de %s invitation(s).",
        cr.rowcount,
    )
    # Courriels pas encore partis (file d'attente, exception) : ils gardent le
    # lien à jeton dans body_html. Les courriels envoyés sont laissés tels quels
    # (déjà remis, et lisibles du seul base.group_system).
    cr.execute(
        """
        UPDATE mail_mail
           SET body_html = regexp_replace(body_html, %s, '/my/sign_requests', 'g')
         WHERE state != 'sent'
           AND body_html LIKE '%%/sign_oca/document/%%'
        """,
        [TOKEN_LINK],
    )
    _logger.info(
        "training_org_sign 19.0.1.0.2 : lien à jeton purgé de %s mail(s) non "
        "envoyé(s).",
        cr.rowcount,
    )
    # Hors du filtre de purge : seulement compté, jamais modifié.
    cr.execute(
        """
        SELECT count(*) FROM mail_message
         WHERE body LIKE '%%/sign_oca/document/%%'
           AND NOT (model IS NULL AND message_type = 'user_notification')
        """
    )
    _logger.info(
        "training_org_sign 19.0.1.0.2 : %s message(s) hors du filtre de purge "
        "contiennent encore /sign_oca/document/ (non modifiés ; à examiner).",
        cr.fetchone()[0],
    )
    cr.execute(
        """
        SELECT count(*)
          FROM sign_oca_request_signer s
          JOIN sign_oca_request r ON r.id = s.request_id
         WHERE s.access_token IS NOT NULL
           AND s.signed_on IS NULL
           AND r.state = '0_sent'
        """
    )
    pending = cr.fetchone()[0]
    _logger.info(
        "training_org_sign 19.0.1.0.2 : %s signataire(s) en attente de demandes "
        "envoyées gardent un jeton déjà émis. Si l'exploitant retient le "
        "renouvellement (ADR-SIGN-02, E1/E2), le lancer depuis `odoo shell` : "
        "env['sign.oca.request']._training_rotate_signer_tokens().",
        pending,
    )
    _rotate_tokens_if_requested(cr)


def _rotate_tokens_if_requested(cr):
    """Renouvelle les jetons si l'exploitant l'a demandé (voie sans shell).

    Option E1 de l'ADR-SIGN-02 : la production n'a pas de shell. L'exploitant
    pose le paramètre système ``training_org_sign.rotate_tokens_on_upgrade`` à
    « 1 » avant la mise à jour ; la migration renouvelle alors les jetons de
    TOUS les signataires, SANS renvoyer d'invitation (``resend=False``), puis
    remet le paramètre à « 0 » pour ne pas rejouer à la mise à jour suivante.
    Sans ce paramètre, rien n'est renouvelé. Les anciens liens cessent de
    fonctionner.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    params = env["ir.config_parameter"]
    if params.get_param(ROTATE_PARAM) != "1":
        _logger.info(
            "training_org_sign 19.0.1.0.2 : jetons des signataires conservés. "
            "Pour les renouveler à la mise à jour, poser le paramètre système "
            "« %s » à 1.",
            ROTATE_PARAM,
        )
        return
    result = env["sign.oca.request"]._training_rotate_signer_tokens(resend=False)
    params.set_param(ROTATE_PARAM, "0")
    _logger.info(
        "training_org_sign 19.0.1.0.2 : %s jeton(s) renouvelé(s), aucune "
        "invitation renvoyée ; paramètre « %s » remis à 0.",
        result["renewed"],
        ROTATE_PARAM,
    )

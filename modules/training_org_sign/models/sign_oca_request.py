# -*- coding: utf-8 -*-
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import logging

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class SignOcaRequest(models.Model):
    """Demande de signature rattachée à un document réglementaire émis.

    Le parapheur générique ne sait rien du domaine de la formation : il fait
    signer un PDF quelconque. Ce rattachement lui donne deux choses qui
    manquent, et qui sont l'essentiel côté conformité :

    1. **la traçabilité** — savoir de quelle pièce contractuelle, scellée et
       archivée, provient le PDF mis à la signature ;
    2. **le cloisonnement** — un contrat de formation porte un prix, un
       cocontractant et parfois une situation personnelle. Sans ce
       rattachement, la règle d'accès ne pourrait pas distinguer une pièce
       contractuelle d'un document de parapheur ordinaire, et la mettre au
       parapheur reviendrait à l'exposer à tout utilisateur interne.
    """

    _inherit = "sign.oca.request"

    training_document_id = fields.Many2one(
        "training.document",
        string="Document réglementaire",
        readonly=True,
        index=True,
        # `restrict` : le document émis est la pièce de preuve ; le parapheur
        # ne doit pas pouvoir en effacer la trace.
        ondelete="restrict",
        copy=False,
        help="Pièce contractuelle émise et scellée dont ce parapheur fait "
        "signer l'exemplaire archivé.",
    )
    # Rapatriés et stockés pour que les règles d'accès et les recherches par
    # dossier n'aient pas à traverser deux relations à chaque requête.
    training_res_model = fields.Char(
        related="training_document_id.res_model", store=True, index=True, string="Modèle source"
    )
    training_res_id = fields.Integer(
        related="training_document_id.res_id", store=True, index=True, string="Source"
    )

    # ------------------------------------------------------------------
    # Cohérence du cache
    # ------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        requests = super().create(vals_list)
        requests._training_invalidate_files()
        return requests

    def write(self, vals):
        result = super().write(vals)
        if "state" in vals or "training_document_id" in vals:
            self._training_invalidate_files()
        return result

    def _training_invalidate_files(self):
        """Purge l'avancement de signature mis en cache côté dossier.

        `training.file.sign_request_ids` est calculé par une **recherche** :
        le dossier ne porte aucune relation inverse vers le parapheur, donc
        aucune dépendance ne peut être déclarée et rien n'avertit le cache
        qu'un parapheur vient de changer d'état. Sans cette purge, un dossier
        déjà lu afficherait un avancement périmé jusqu'à la fin de la
        transaction — au pire « en attente de signature » sur un contrat déjà
        signé.
        """
        linked = self.filtered(
            lambda request: request.training_res_model == "training.file"
            and request.training_res_id
        )
        if not linked:
            return
        self.env["training.file"].browse(
            linked.mapped("training_res_id")
        ).invalidate_recordset(
            ["sign_request_ids", "sign_request_count", "signature_state"]
        )

    # ------------------------------------------------------------------
    # Reprise de la signature sur le dossier contractuel
    # ------------------------------------------------------------------

    def _check_signed(self):
        """Constate l'achèvement du parapheur, puis le reporte sur le dossier.

        Le report est fait ici, et pas à l'apposition de chaque signature :
        un contrat n'est signé que lorsque **toutes** les parties l'ont signé.
        Reporter plus tôt ouvrirait le délai de rétractation à une date
        antérieure à la formation du contrat.

        :side effect: peut faire passer le dossier contractuel à l'état signé.
        """
        was_signed = self.state == "2_signed"
        result = super()._check_signed()
        if self.state == "2_signed" and not was_signed:
            self._training_apply_signature()
        return result

    def _training_apply_signature(self):
        """Reporte la signature achevée sur le dossier contractuel d'origine.

        `sudo()` indispensable, de périmètre minimal et justifié : celui qui
        déclenche cette reprise est le **dernier signataire** — le
        cocontractant, souvent un utilisateur du portail, qui n'a par
        construction aucun droit d'écriture sur le dossier contractuel. La
        signature est pourtant un fait déjà établi et scellé par le parapheur ;
        l'inscrire sur le dossier est une conséquence système, pas une action
        que l'on prêterait à cet utilisateur.

        Aucune garde métier n'est contournée : `action_sign()` conserve son
        propre refus si le dossier n'est plus en attente de signature, et la
        date retenue est celle de la dernière signature réellement apposée,
        jamais le jour courant.

        :side effect: écrit l'état et la date de signature du dossier ; trace
            l'opération au fil de discussion du dossier.
        """
        self.ensure_one()
        if self.training_res_model != "training.file" or not self.training_res_id:
            return False
        # Date de la dernière signature apposée : c'est elle qui fait courir le
        # délai de rétractation, pas la date du traitement.
        signed_dates = [
            signer.signed_on for signer in self.signer_ids if signer.signed_on
        ]
        if not signed_dates:
            return False
        signature_date = fields.Datetime.context_timestamp(
            self, max(signed_dates)
        ).date()

        training_file = (
            self.env["training.file"].sudo().browse(self.training_res_id).exists()
        )
        if not training_file:
            return False
        if training_file.state not in ("draft", "sent"):
            # Le dossier a déjà été signé ou annulé par ailleurs : on ne
            # réécrit rien, on se contente de le tracer.
            training_file.message_post(
                body="Parapheur « %s » : toutes les signatures ont été apposées, "
                "mais le dossier n'était plus en attente de signature — aucun "
                "changement d'état n'a été fait." % self.name
            )
            return False

        training_file.action_sign(date_signature=signature_date)
        training_file.message_post(
            body="Signature électronique achevée le %s via le parapheur « %s ». "
            "Signataires : %s."
            % (
                signature_date,
                self.name,
                ", ".join(self.signer_ids.mapped("partner_id.display_name")),
            )
        )
        return True

    # ------------------------------------------------------------------
    # Garde d'intégrité
    # ------------------------------------------------------------------

    @api.ondelete(at_uninstall=False)
    def _unlink_except_training_signed(self):
        """Refuse la suppression d'un parapheur contractuel déjà signé.

        Motif CLAUDE.md §6 : une pièce signée s'annule, elle ne s'efface pas.
        """
        signed = self.filtered(
            lambda request: request.training_document_id and request.state == "2_signed"
        )
        if signed:
            raise UserError(
                "Ces parapheurs portent des signatures apposées sur une pièce "
                "contractuelle et ne peuvent pas être supprimés — annulez-les : "
                + ", ".join(signed.mapped("name"))
            )

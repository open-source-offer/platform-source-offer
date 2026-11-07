# -*- coding: utf-8 -*-
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import api, fields, models
from odoo.exceptions import UserError


class TrainingFile(models.Model):
    """Dossier contractuel signé à distance par les parties.

    Le cas qui justifie à lui seul ce module est le **contrat conclu avec un
    particulier** : le cocontractant y est un consommateur, il dispose d'un
    délai de rétractation d'ordre public, et c'est à l'organisme qu'il revient
    de prouver la date exacte de la signature. Une signature manuscrite
    numérisée ne suffit pas à porter cette preuve ; un parapheur horodaté et
    scellé, si.
    """

    _inherit = "training.file"

    sign_request_ids = fields.One2many(
        "sign.oca.request",
        compute="_compute_sign_request_ids",
        string="Parapheurs",
    )
    sign_request_count = fields.Integer(
        string="Nombre de parapheurs", compute="_compute_sign_request_ids"
    )
    signature_state = fields.Selection(
        [
            ("none", "Non mis à la signature"),
            ("pending", "En attente de signature"),
            ("signed", "Signé"),
            ("cancelled", "Signature abandonnée"),
        ],
        string="Signature électronique",
        compute="_compute_sign_request_ids",
        help="Avancement de la signature électronique de la pièce "
        "contractuelle. Sans rapport avec l'état du dossier, qui peut avoir "
        "été signé sur papier.",
    )

    def _compute_sign_request_ids(self):
        """Parapheurs ouverts ou clos sur les pièces contractuelles du dossier.

        Une seule recherche pour tout le lot lu : `sign.oca.request` se
        rattache au dossier par le couple modèle/identifiant de la pièce dont
        il fait signer l'exemplaire, qui ne porte pas de relation inverse.
        """
        persisted = self.filtered(lambda record: isinstance(record.id, int))
        for record in self - persisted:
            record.sign_request_ids = [(5, 0, 0)]
            record.sign_request_count = 0
            record.signature_state = "none"
        if not persisted:
            return
        requests = self.env["sign.oca.request"].search(
            [
                ("training_res_model", "=", self._name),
                ("training_res_id", "in", persisted.ids),
            ],
            order="id desc",
        )
        by_file = {}
        for request in requests:
            by_file.setdefault(request.training_res_id, []).append(request)
        for record in persisted:
            found = by_file.get(record.id, [])
            record.sign_request_ids = [(6, 0, [r.id for r in found])]
            record.sign_request_count = len(found)
            states = {r.state for r in found}
            if "2_signed" in states:
                record.signature_state = "signed"
            elif states & {"1_draft", "0_sent"}:
                record.signature_state = "pending"
            elif "3_cancel" in states:
                record.signature_state = "cancelled"
            else:
                record.signature_state = "none"

    # ------------------------------------------------------------------
    # Parties au contrat
    # ------------------------------------------------------------------

    def _signature_signatories(self):
        """Parties appelées à signer la pièce contractuelle du dossier.

        Trois rôles, dans l'ordre où le contrat les fait apparaître :

        - **l'organisme**, représenté par le contact de sa société ;
        - **le cocontractant**, ou la personne physique qui signe pour lui
          lorsqu'elle en diffère ;
        - **le financeur**, uniquement pour une convention tripartite ou une
          convention de subrogation — c'est ce qui distingue ces deux pièces
          d'une convention ordinaire : le financeur y est partie.

        Un financeur renseigné sur une convention bilatérale n'est **pas**
        appelé à signer : il paie, il ne contracte pas.

        :return: liste de couples ``(clé de rôle, res.partner)``.
        :raise UserError: organisme sans contact, ou tripartite sans financeur.
        """
        self.ensure_one()
        provider = self.company_id.partner_id
        if not provider:
            raise UserError(
                f"Dossier {self.name} : la société émettrice n'a pas de contact "
                "associé, l'organisme ne peut pas être désigné comme signataire."
            )
        signatories = [
            ("provider", provider),
            ("counterparty", self.signatory_partner_id or self.partner_id),
        ]
        if self.file_type in ("convention_tripartite", "subrogation"):
            if not self.funder_partner_id:
                raise UserError(
                    f"Dossier {self.name} : une {dict(self._fields['file_type'].selection)[self.file_type].lower()} "
                    "se signe aussi par le financeur, qui n'est pas renseigné."
                )
            signatories.append(("funder", self.funder_partner_id))
        return signatories

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_request_signature(self):
        """Met la pièce contractuelle du dossier à la signature des parties.

        La pièce est émise si elle ne l'a pas encore été — l'émission déroule
        alors ses propres contrôles de complétude, ce qui garantit qu'on ne met
        jamais à la signature une convention à laquelle il manque une mention
        obligatoire.

        :return: action d'ouverture du parapheur.
        :raise UserError: dossier qui n'est plus en attente de signature, ou
            pièce incomplète.
        :side effect: peut émettre le document contractuel ; crée un parapheur.
        """
        self.ensure_one()
        if self.state not in ("draft", "sent"):
            raise UserError(
                f"Dossier {self.name} : il n'est plus en attente de signature."
            )
        document_type = self._contract_document_type()
        document = self.env["training.document"]._latest_for(self, document_type)
        if not document:
            document = self.env["training.document"]._issue(self, document_type)
        return document.action_request_signature()

    def action_open_sign_requests(self):
        """Ouvre les parapheurs du dossier."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": f"Parapheurs — {self.name}",
            "res_model": "sign.oca.request",
            "view_mode": "list,form",
            "domain": [
                ("training_res_model", "=", self._name),
                ("training_res_id", "=", self.id),
            ],
        }

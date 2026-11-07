# -*- coding: utf-8 -*-
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import base64

from odoo import api, fields, models
from odoo.exceptions import UserError

# Avancement du parapheur, vu du document réglementaire.
SIGNATURE_STATES = [
    ("none", "Non mis à la signature"),
    ("pending", "En attente de signature"),
    ("signed", "Signé"),
    ("cancelled", "Signature abandonnée"),
]

# États de `sign.oca.request` considérés comme un parapheur encore ouvert.
OPEN_REQUEST_STATES = ("1_draft", "0_sent")


class TrainingDocument(models.Model):
    """Document réglementaire émis, augmenté d'un parapheur électronique.

    Le rattachement est porté par la demande de signature et non par le
    document : un document émis est **immuable** (son `write()` refuse toute
    modification), et poser une relation sur lui obligerait à contourner cette
    garde à chaque mise au parapheur. La relation inverse donne le même service
    sans rien affaiblir.
    """

    _inherit = "training.document"

    sign_request_ids = fields.One2many(
        "sign.oca.request",
        "training_document_id",
        string="Parapheurs",
        readonly=True,
        # Le contractuel sort du périmètre du formateur : lui montrer
        # l'existence d'un parapheur sur une convention serait déjà trop.
        groups="training_org.group_training_user,training_org.group_training_quality",
    )
    signature_state = fields.Selection(
        SIGNATURE_STATES,
        string="Signature électronique",
        compute="_compute_signature_state",
        groups="training_org.group_training_user,training_org.group_training_quality",
    )

    @api.depends("sign_request_ids.state")
    def _compute_signature_state(self):
        """Avancement de la signature électronique de la pièce.

        Un document peut avoir été mis au parapheur plusieurs fois (un premier
        envoi abandonné, puis un second). L'état retenu est le plus avancé :
        une signature obtenue prime sur un abandon, un parapheur ouvert prime
        sur un abandon.
        """
        for document in self:
            states = set(document.sign_request_ids.mapped("state"))
            if "2_signed" in states:
                document.signature_state = "signed"
            elif states & set(OPEN_REQUEST_STATES):
                document.signature_state = "pending"
            elif "3_cancel" in states:
                document.signature_state = "cancelled"
            else:
                document.signature_state = "none"

    # ------------------------------------------------------------------
    # Déclaration au point de branchement du socle
    # ------------------------------------------------------------------

    @api.model
    def _signature_backends(self):
        """Déclare le parapheur communautaire au socle.

        C'est **le seul sens de dépendance admis** : le socle, propriétaire,
        ignore tout de ce module ; ce module, sous AGPL, vient s'y annoncer.
        L'inverse propagerait la licence à toute la plateforme.
        """
        backends = super()._signature_backends()
        backends["sign_oca"] = {
            "name": "Parapheur interne",
            "request": lambda document, signatories=None: (
                document.action_request_signature(signatories=signatories)
            ),
            "state": lambda document: document.signature_state,
        }
        return backends

    # ------------------------------------------------------------------
    # Mise au parapheur
    # ------------------------------------------------------------------

    def _signature_source(self):
        """Enregistrement d'où le document a été émis.

        :return: recordset du modèle source (vide si l'enregistrement a
            disparu).
        """
        self.ensure_one()
        if not (self.res_model and self.res_id):
            return self.env["training.document"].browse()
        if self.res_model not in self.env:
            return self.env["training.document"].browse()
        return self.env[self.res_model].browse(self.res_id).exists()

    def _assert_signature_allowed(self):
        """Vérifie que l'appelant a bien le droit de faire signer cette pièce.

        **C'est la garde centrale du module.** Mettre un document au parapheur
        en produit une copie destinée à circuler et à être lue par les
        signataires : l'opération ne doit jamais être ouverte à quelqu'un qui
        n'avait pas déjà le droit de lire la pièce **et** l'enregistrement dont
        elle est issue. Le contrôle est donc explicite et porte sur les deux,
        en plus des droits d'accès du modèle — aucune élévation, aucun
        `sudo()` sur ce chemin.

        :raise UserError: document non émis, ou dépourvu de fichier archivé.
        :raise AccessError: droits insuffisants sur la pièce ou sur sa source.
        """
        self.ensure_one()
        self.check_access("read")
        if self.state != "issued":
            raise UserError(
                f"« {self.name} » n'est pas un document émis : seule une pièce "
                "émise et scellée peut être mise à la signature."
            )
        if not self.attachment_id:
            raise UserError(f"« {self.name} » ne porte aucun fichier à signer.")
        source = self._signature_source()
        if source:
            source.check_access("read")
        return True

    def _signature_signatories(self):
        """Parties appelées à signer la pièce.

        Déléguée à l'enregistrement source : c'est lui qui sait qui contracte.
        Un modèle source qui ne le dit pas ne peut pas être mis au parapheur —
        faire signer une pièce contractuelle par des signataires devinés serait
        pire que ne pas la faire signer.

        :return: liste de couples ``(clé de rôle, res.partner)``.
        :raise UserError: source incapable de désigner ses signataires.
        """
        self.ensure_one()
        source = self._signature_source()
        provider = getattr(source, "_signature_signatories", None)
        if not provider:
            raise UserError(
                f"« {self.name} » ne peut pas être mis à la signature : "
                "l'enregistrement dont il provient ne désigne pas les parties "
                "au contrat."
            )
        return provider()

    def _signature_role(self, role_key):
        """Rôle de parapheur correspondant à une partie au contrat.

        :param role_key: `provider`, `counterparty` ou `funder`.
        :return: recordset `sign.oca.role`.
        :raise UserError: rôle inconnu ou données de référence absentes.
        """
        role = self.env.ref(
            f"training_org_sign.sign_role_training_{role_key}", raise_if_not_found=False
        )
        if not role:
            raise UserError(
                f"Le rôle de signature « {role_key} » est introuvable : les "
                "données de référence du parapheur sont incomplètes."
            )
        return role

    def action_request_signature(self, signatories=None):
        """Met le document émis à la signature des parties.

        La pièce mise au parapheur est **l'exemplaire archivé**, celui dont
        l'empreinte a été scellée à l'émission — jamais un rendu recalculé au
        moment de la demande. C'est tout l'intérêt : ce qui est signé est
        exactement ce qui a été émis.

        L'opération est idempotente : rappelée alors qu'un parapheur est encore
        ouvert sur la même pièce, elle rouvre celui-là plutôt que d'en créer un
        second, qui ferait signer deux fois le même contrat.

        :param signatories: liste de couples ``(clé de rôle, res.partner)`` ;
            demandée à l'enregistrement source par défaut.
        :return: action d'ouverture du parapheur.
        :raise UserError: document non émis, sans fichier, ou sans signataire.
        :raise AccessError: droits insuffisants sur la pièce ou sur sa source.
        :side effect: crée une `sign.oca.request` et ses signataires.
        """
        self.ensure_one()
        self._assert_signature_allowed()

        pending = self.sign_request_ids.filtered(
            lambda request: request.state in OPEN_REQUEST_STATES
        )
        if pending:
            return pending[0].get_formview_action()

        signatories = signatories or self._signature_signatories()
        signatories = [(key, partner) for key, partner in signatories if partner]
        if not signatories:
            raise UserError(
                f"« {self.name} » ne peut pas être mis à la signature : aucune "
                "partie signataire n'est renseignée sur le dossier."
            )

        source = self._signature_source()
        request = self.env["sign.oca.request"].create(
            {
                "name": self.name,
                "data": self.attachment_id.datas,
                "filename": f"{self.name}.pdf",
                "training_document_id": self.id,
                "company_id": self.company_id.id,
                "record_ref": f"{source._name},{source.id}" if source else False,
                "signer_ids": [
                    (
                        0,
                        0,
                        {
                            "partner_id": partner.id,
                            "role_id": self._signature_role(role_key).id,
                        },
                    )
                    for role_key, partner in signatories
                ],
            }
        )
        return request.get_formview_action()

    def action_open_sign_requests(self):
        """Ouvre les parapheurs portant sur cette pièce."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": f"Parapheurs — {self.name}",
            "res_model": "sign.oca.request",
            "view_mode": "list,form",
            "domain": [("training_document_id", "=", self.id)],
        }

    def verify_signed_copy_hash(self):
        """Compare l'exemplaire signé à la pièce telle qu'elle a été émise.

        Le parapheur incruste les signatures dans le PDF : l'exemplaire signé
        n'a donc **pas** la même empreinte que la pièce émise, et c'est normal.
        Cette méthode ne sert pas à constater une identité mais à donner un
        point de contrôle explicite : elle rappelle l'empreinte scellée à
        l'émission et celle de l'exemplaire signé, pour qu'un contrôle puisse
        rattacher l'un à l'autre.

        :return: dictionnaire ``{'issued_hash', 'signed_hash', 'issued_intact'}``.
        """
        self.ensure_one()
        signed = self.sign_request_ids.filtered(lambda r: r.state == "2_signed")[:1]
        signed_hash = signed.current_hash or False
        return {
            "issued_hash": self.document_hash,
            "signed_hash": signed_hash,
            "issued_intact": self.verify_hash(),
        }

    def _signed_copy_bytes(self):
        """Octets de l'exemplaire signé, s'il existe.

        :return: `bytes` ou `False`.
        """
        self.ensure_one()
        signed = self.sign_request_ids.filtered(lambda r: r.state == "2_signed")[:1]
        if not (signed and signed.data):
            return False
        return base64.b64decode(signed.data)

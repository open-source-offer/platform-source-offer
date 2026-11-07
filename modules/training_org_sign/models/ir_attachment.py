# Copyright 2026 NEW LEADERS ACADEMY PRIVEE, SARLAU
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
"""Le PDF d'un parapheur est une pièce jointe : elle est gelée comme la demande.

``sign.oca.request.data`` est un champ binaire stocké en pièce jointe. Dans
Odoo 19, ``ir.attachment.write`` et ``unlink`` ne demandent que le droit
d'écriture sur la demande et n'appellent jamais ``sign.oca.request.write`` : les
gardes d'intégrité de la demande étaient contournées en écrivant directement la
pièce jointe (ADR-SIGN-02, E-10).

Les refus ne s'appliquent que hors superutilisateur (l'ORM écrit les binaires
en ``sudo()``, ``action_sign`` tourne en su, la migration passe en SQL) et
seulement si la demande visée est rattachée à une pièce contractuelle ou n'est
plus en brouillon. ``access_token`` n'est pas concerné : le téléchargement le
régénère.
"""
import logging

from odoo import api, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Seule écriture permise sur le PDF d'une demande figée : le jeton d'accès, que
# le téléchargement régénère. Tout le reste (contenu, nom, type MIME, `public`,
# cible…) est refusé : `public` rendrait le contrat téléchargeable sans
# authentification, `mimetype` et `name` le feraient servir comme une page.
FROZEN_ALLOWED_KEYS = frozenset({"access_token"})
TARGET_KEYS = frozenset({"res_model", "res_id", "res_field"})


PDF_INDEX = "training_org_sign_one_pdf_per_request"


def ensure_unique_pdf_index(cr):
    """Pose l'index unique « un seul PDF par demande de signature ».

    Défense en profondeur (ADR-SIGN-02, E-14) : l'ORM lit le PDF par le plus
    petit identifiant, ``ir.binary`` et le portail par le plus grand ; un
    doublon permet donc de faire servir une pièce falsifiée. La base le
    refuse, quel que soit le chemin de code.

    Posé dans ``init()`` (chargement du modèle) plutôt que dans la migration :
    ``init()`` passe avant les migrations ``post`` d'une mise à jour, et couvre
    aussi l'installation neuve. Idempotent. Des doublons existants sont
    journalisés (demande, identifiants, empreintes) et arrêtent la mise à
    jour avec une erreur claire : ils ne sont JAMAIS supprimés
    automatiquement, c'est à l'exploitant d'en décider.
    """
    cr.execute("SELECT 1 FROM pg_indexes WHERE indexname = %s", [PDF_INDEX])
    if cr.fetchone():
        return
    cr.execute(
        """
        SELECT res_id, array_agg(id ORDER BY id), array_agg(checksum ORDER BY id)
          FROM ir_attachment
         WHERE res_model = 'sign.oca.request' AND res_field = 'data'
         GROUP BY res_id
        HAVING count(*) > 1
        """
    )
    duplicates = cr.fetchall()
    if duplicates:
        for res_id, ids, checksums in duplicates:
            _logger.error(
                "training_org_sign : PDF en doublon pour la demande %s : "
                "pièces jointes %s, empreintes %s.",
                res_id,
                ids,
                checksums,
            )
        raise UserError(
            "Mise à jour arrêtée : des demandes de signature ont plusieurs "
            "PDF (doublon, possible falsification). Demandes concernées : "
            + ", ".join(str(row[0]) for row in duplicates)
            + ". Le détail (pièces jointes et empreintes) est dans le journal "
            "du serveur. Aucune pièce n'a été supprimée : à l'exploitant de "
            "décider laquelle conserver, puis de relancer la mise à jour."
        )
    cr.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS %s ON ir_attachment (res_id) "
        "WHERE res_model = 'sign.oca.request' AND res_field = 'data'" % PDF_INDEX
    )


class IrAttachment(models.Model):
    _inherit = "ir.attachment"

    def init(self):
        super().init()
        ensure_unique_pdf_index(self.env.cr)

    def _training_sign_frozen(self, res_ids):
        """Une de ces demandes est-elle rattachée à une pièce ou déjà envoyée ?"""
        requests = self.env["sign.oca.request"].sudo().browse(
            [res_id for res_id in res_ids if res_id]
        ).exists()
        return any(
            request.training_document_id or request.state != "1_draft"
            for request in requests
        )

    def _training_sign_pdf(self):
        """Pièces jointes qui portent le PDF d'une demande de signature."""
        return self.sudo().filtered(
            lambda att: att.res_model == "sign.oca.request" and att.res_field == "data"
        )

    def _training_sign_refuse(self):
        raise UserError(
            self.env._(
                "Le PDF d'un parapheur rattaché à une pièce contractuelle, ou "
                "déjà envoyé, ne peut pas être modifié ni supprimé."
            )
        )

    @staticmethod
    def _training_sign_is_pdf(res_model, res_field):
        return res_model == "sign.oca.request" and res_field == "data"

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su:
            ctx = self.env.context
            for vals in vals_list:
                # Valeurs effectives : les `default_*` du contexte comptent.
                res_model = vals.get("res_model", ctx.get("default_res_model"))
                res_field = vals.get("res_field", ctx.get("default_res_field"))
                if self._training_sign_is_pdf(res_model, res_field):
                    # L'ORM crée le PDF d'une demande en sudo : hors su, ce ne
                    # peut être qu'un doublon (l'ORM lit le plus petit id,
                    # ir.binary et le portail le plus grand).
                    self._training_sign_refuse()
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.su:
            targets = self._training_sign_pdf()
            if (
                targets
                and set(vals) - FROZEN_ALLOWED_KEYS
                and self._training_sign_frozen(targets.mapped("res_id"))
            ):
                self._training_sign_refuse()
        # Hors du `if not su` : `message_post` rattache EN SUDO les pièces du
        # composeur (res_model/res_id) en gardant un `res_field` posé au
        # préalable. L'ORM, lui, ne déplace jamais la pièce d'un champ binaire
        # existant : aucun flux su légitime ne pointe une pièce vers le PDF
        # d'une demande.
        if TARGET_KEYS & set(vals):
            for attachment in self.sudo():
                res_model = vals.get("res_model", attachment.res_model)
                res_field = vals.get("res_field", attachment.res_field)
                res_id = vals.get("res_id", attachment.res_id)
                retarget = (res_model, res_field, res_id) != (
                    attachment.res_model,
                    attachment.res_field,
                    attachment.res_id,
                )
                if retarget and self._training_sign_is_pdf(res_model, res_field):
                    self._training_sign_refuse()
        return super().write(vals)

    def unlink(self):
        if not self.env.su:
            targets = self._training_sign_pdf()
            if targets and self._training_sign_frozen(targets.mapped("res_id")):
                self._training_sign_refuse()
        return super().unlink()

# Copyright 2026 NEW LEADERS ACADEMY PRIVEE, SARLAU
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
"""Intégrité du parapheur : qui peut signer, qui peut modifier (ADR-SIGN-02).

Deux familles de garde, toutes posées dans ce module (``sign_oca`` est une
copie amont de l'OCA, jamais modifiée) :

* ``action_sign`` n'est exécutable que par le contrôleur de signature, qui a
  vérifié le jeton ou l'identité ;
* les signatures et la liste des signataires deviennent immuables dès l'envoi.
"""
from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError

VERIFIED_SIGNER_KEY = "training_sign_verified_signer_id"

# Signature apposée : ces champs ne sont écrits que par le chemin serveur
# (`action_sign`, en superutilisateur), jamais par un utilisateur, même en
# brouillon (sinon on pré-remplit la signature du cocontractant).
SIGNATURE_FIELDS = frozenset(
    {
        "signed_on",
        "signature_hash",
        "latitude",
        "longitude",
        "secure_sequence_number",
        "inalterable_hash",
        "sequence_id",
    }
)
# Valeurs contrôlées après création (`sequence_id` a toujours un défaut).
SIGNATURE_VALUE_FIELDS = (
    "signed_on",
    "signature_hash",
    "latitude",
    "longitude",
    "secure_sequence_number",
    "inalterable_hash",
)
# Identité du signataire : modifiable en brouillon seulement.
IDENTITY_FIELDS = frozenset({"partner_id", "role_id"})

SENT_MESSAGE = (
    "Ce parapheur a été envoyé : ses signataires et sa pièce ne sont plus "
    "modifiables."
)


class SignOcaRequestSigner(models.Model):
    _inherit = "sign.oca.request.signer"

    # Dupliquer une demande signée ne doit pas recopier les signatures.
    signed_on = fields.Datetime(copy=False)
    signature_hash = fields.Char(copy=False)
    latitude = fields.Float(copy=False)
    longitude = fields.Float(copy=False)

    def action_sign(self, items, access_token=False, latitude=False, longitude=False):
        """Apposition de la signature, réservée au contrôleur de signature.

        La méthode amont est publique : appelée en RPC, elle signait au nom de
        n'importe quel signataire lisible (R-a). La frontière de sécurité est
        ``env.su`` : ``call_kw`` ne fournit jamais d'environnement
        superutilisateur, et le contrôleur appelle déjà en ``sudo()`` après
        sa vérification. Le contexte est falsifiable en RPC : le marqueur
        n'est donc jamais accepté seul, il atteste seulement que la
        vérification a porté sur CE signataire.
        """
        self.ensure_one()
        if not (
            self.env.su and self.env.context.get(VERIFIED_SIGNER_KEY) == self.id
        ):
            raise AccessError(
                self.env._(
                    "La signature n'est possible que depuis le lien de signature."
                )
            )
        return super().action_sign(
            items,
            access_token=access_token,
            latitude=latitude,
            longitude=longitude,
        )

    # ------------------------------------------------------------------
    # Gardes d'intégrité (hors superutilisateur)
    # ------------------------------------------------------------------
    # Le chemin serveur de `action_sign` tourne en `su` : il passe sans autre
    # exception. Les gardes portent sur les CLÉS présentes, même si la valeur
    # est identique : pas de comparaison à contourner.

    @api.model_create_multi
    def create(self, vals_list):
        signers = super().create(vals_list)
        if not self.env.su:
            # Contrôle APRÈS création, sur les enregistrements obtenus : les
            # valeurs par défaut (contexte `default_*`, `ir.default`) ne figurent
            # pas dans `vals` et contourneraient un contrôle en amont. L'erreur
            # annule la création (transaction ou savepoint de l'appel).
            # `sudo()` : lire l'état, pas contourner un droit.
            for signer in signers.sudo():
                if any(signer[name] for name in SIGNATURE_VALUE_FIELDS):
                    raise UserError(
                        self.env._("Une signature ne peut pas être saisie à la main.")
                    )
                if signer.request_id.state != "1_draft":
                    # Message neutre : ce contrôle voit aussi une demande
                    # créée d'emblée hors brouillon (défaut d'état), dont les
                    # signataires sont créés après la demande.
                    raise UserError(
                        self.env._(
                            "Les signataires ne s'ajoutent qu'à un parapheur "
                            "en brouillon."
                        )
                    )
                # R-A : sur une pièce contractuelle, seul le personnel du
                # domaine désigne les signataires. Sinon un utilisateur du
                # parapheur s'ajouterait avec son propre contact, recevrait le
                # jeton à l'envoi et lirait le contrat.
                if signer.request_id.training_document_id and not (
                    self.env.user.has_group("training_org.group_training_user")
                ):
                    raise UserError(
                        self.env._(
                            "Seul le personnel de formation désigne les "
                            "signataires d'une pièce contractuelle."
                        )
                    )
        return signers

    def write(self, vals):
        if not self.env.su:
            keys = set(vals)
            if keys & SIGNATURE_FIELDS:
                raise UserError(
                    self.env._("Une signature ne peut pas être modifiée à la main.")
                )
            if "request_id" in keys:
                raise UserError(
                    self.env._("Un signataire ne peut pas changer de parapheur.")
                )
            if keys & IDENTITY_FIELDS and any(
                signer.request_id.state != "1_draft" for signer in self.sudo()
            ):
                raise UserError(self.env._(SENT_MESSAGE))
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_sent(self):
        """Refuse de retirer un signataire d'un parapheur déjà envoyé.

        La suppression en cascade d'une demande se fait en SQL et n'est pas
        concernée ; la suppression d'une demande signée reste bloquée par
        ``_unlink_except_training_signed``.
        """
        if not self.env.su and any(
            signer.request_id.state != "1_draft" for signer in self.sudo()
        ):
            raise UserError(self.env._(SENT_MESSAGE))

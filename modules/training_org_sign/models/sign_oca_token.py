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
from odoo import SUPERUSER_ID, fields, models
from odoo.exceptions import AccessError


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
        """Envoie la demande aux signataires (réécriture de la méthode amont).

        Reprise de ``sign_oca`` sans ``super()`` (ADR-SIGN-02, D1) : l'amont
        poste l'invitation, lien et jeton compris, dans un ``mail.message`` dont
        l'auteur et le créateur sont l'appelant. Or Odoo laisse lire un message
        à son auteur, à son créateur et à ses destinataires : l'interne qui
        envoyait pouvait relire le jeton du cocontractant. L'invitation est
        donc émise par le système (voir ``_training_send_invitations``).

        La copie est surveillée par un test de dérive (SHA-256 de la méthode
        amont) : toute mise à jour d'OCA oblige à la revoir.

        :param sign_now: l'appelant signe lui-même, il ne reçoit pas d'invitation.
        :param message: texte libre ajouté au courriel.
        :raise AccessError: l'appelant ne peut pas écrire sur la demande.
        """
        # Droit vérifié avec les droits de l'appelant, avant tout `sudo()`.
        self.check_access("write")
        self.ensure_one()
        if self.state != "1_draft":
            return
        # Journal et changement d'état avec les droits de l'appelant : la garde
        # d'état s'applique et le journal garde l'appelant pour `uid`.
        self._set_action_log("validate")
        self.state = "0_sent"
        # `sudo()` : générer le jeton et lire les signataires (la règle d'accès
        # « mes documents » masquerait ceux des autres parties). Le jeton ne
        # sort que dans le courriel.
        signers = self.sudo().signer_ids
        for signer in signers:
            signer._portal_ensure_token()
        # Comparaison avec l'utilisateur réel, pas avec le superutilisateur.
        own_partner = self.env.user.partner_id
        recipients = signers.filtered(
            lambda signer: not (sign_now and signer.partner_id == own_partner)
        )
        self._training_send_invitations(recipients, message)

    def _training_send_invitations(self, signers, message=""):
        """Envoie le courriel d'invitation à ces signataires.

        Chemin unique d'envoi et de renvoi. Le message est créé par le
        superutilisateur et signé par OdooBot : ni l'appelant ni le partenaire
        de la société n'en deviennent auteur ou créateur, donc personne, hors
        destinataires, ne peut le relire (le lien contient le jeton). Le
        ``mail.mail`` n'est lisible que par ``base.group_system``, qui lit déjà
        le jeton.

        ``with_company`` est indispensable : sans modèle, la mise en page prend
        la société de l'environnement, ici celle du superutilisateur.

        :param signers: signataires à inviter (sudo ou non).
        :param message: texte libre du courriel.
        :side effect: crée un courriel par signataire et une note sans lien au
            fil de la demande.
        """
        self.ensure_one()
        request = self.sudo()
        signers = signers.sudo()
        if not signers:
            return
        company = request.company_id
        bot = self.env.ref("base.partner_root")
        email_from = (
            company.partner_id.email_formatted
            or self.env["ir.mail_server"]._get_default_from_address()
        )
        notifier = (
            self.env["mail.thread"].with_user(SUPERUSER_ID).with_company(company)
        )
        subtype_id = self.env.ref("mail.mt_comment").id
        for signer in signers:
            render_result = request.env["ir.qweb"]._render(
                "sign_oca.sign_oca_template_mail",
                {"record": signer, "body": message, "link": signer.access_url},
                engine="ir.qweb",
                minimal_qcontext=True,
            )
            notifier.message_notify(
                body=render_result,
                partner_ids=signer.partner_id.ids,
                subject=self.env._("New document to sign"),
                subtype_id=subtype_id,
                author_id=bot.id,
                email_from=email_from,
                mail_auto_delete=False,
                email_layout_xmlid="mail.mail_notification_light",
            )
        # Trace au fil de la demande, SANS lien : l'auteur est l'appelant.
        # L'adresse effectivement utilisée est consignée (preuve de l'envoi).
        self.message_post(
            body=self.env._(
                "Invitation à signer envoyée à : %(names)s.",
                names=", ".join(
                    "%s <%s>"
                    % (
                        signer.partner_id.display_name,
                        signer.partner_id.email or self.env._("sans adresse"),
                    )
                    for signer in signers
                ),
            ),
            subtype_xmlid="mail.mt_note",
        )

    def _training_rotate_signer_tokens(self, resend=True, pending_only=False):
        """Renouvelle les jetons des signataires, et renvoie les invitations.

        Remédiation du stock (ADR-SIGN-02, D2) : un jeton déjà lu par un
        interne reste valable après la purge des messages. À lancer par
        l'exploitant depuis ``odoo shell``, après sauvegarde : **jamais appelée
        automatiquement**. Les anciens liens cessent de fonctionner, y compris
        dans les boîtes des cocontractants légitimes.

        Non appelable en RPC (préfixe ``_``) ; garde explicite en plus.

        :param resend: renvoie l'invitation aux signataires non signés des
            demandes envoyées, avec la mention « Ce lien remplace le précédent ».
        :param pending_only: n'agit que sur les signataires non signés des
            demandes envoyées (option E2) ; sinon tous les signataires (E1).
        :return: dictionnaire ``{'renewed': n, 'resent': n}``.
        :raise AccessError: appelant ni superutilisateur ni administrateur.
        """
        if not (self.env.su or self.env.user.has_group("base.group_system")):
            raise AccessError(
                self.env._("Réservé à l'administrateur système.")
            )
        requests = (
            self or self.with_context(active_test=False).sudo().search([])
        ).sudo()
        signers = requests.signer_ids
        if pending_only:
            signers = signers.filtered(
                lambda s: not s.signed_on and s.request_id.state == "0_sent"
            )
        signers.write({"access_token": False})
        for signer in signers:
            signer._portal_ensure_token()
        resent = 0
        if resend:
            # Pas de renvoi pour une demande archivée : elle est sortie du
            # circuit, un courriel « à signer » serait trompeur.
            for request in requests.filtered(
                lambda r: r.state == "0_sent" and r.active
            ):
                waiting = request.signer_ids.filtered(lambda s: not s.signed_on)
                if waiting:
                    request._training_send_invitations(
                        waiting, self.env._("Ce lien remplace le précédent.")
                    )
                    resent += len(waiting)
        return {"renewed": len(signers), "resent": resent}

    def _set_action_log_vals(self, action, **kwargs):
        # Le journal n'est pas un endroit où conserver un secret d'accès : le
        # jeton n'y est plus enregistré (et les jetons déjà journalisés sont
        # vidés par la post-migration).
        vals = super()._set_action_log_vals(action, **kwargs)
        vals["access_token"] = False
        return vals


class SignOcaRequestLog(models.Model):
    _inherit = "sign.oca.request.log"

    # Le journal ne reçoit plus de jeton (voir `_set_action_log_vals`), mais le
    # champ reste un secret potentiel : réservé aux administrateurs, comme le
    # jeton du signataire (test de non-exposition sur le registre).
    access_token = fields.Char(groups="base.group_system")

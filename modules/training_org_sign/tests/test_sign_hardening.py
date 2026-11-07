# Copyright 2026 NEW LEADERS ACADEMY PRIVEE, SARLAU
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
"""Durcissement du parapheur 19.0.1.0.2 (ADR-SIGN-02).

Chaque test repose sur la section 4 de l'ADR. Les tests marqués « FAIL-AVANT »
doivent échouer sur 19.0.1.0.1 : ils ont été écrits et constatés rouges avant
le correctif.
"""
import hashlib
import importlib.util
import inspect
import re
from base64 import b64encode
from io import BytesIO
from pathlib import Path
from unittest import mock

from PyPDF2 import PdfWriter

from psycopg2 import IntegrityError

from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged
from odoo.tools import mute_logger

from odoo.addons.training_org.tests.common import TrainingOrgCommon

from .test_training_org_sign import FULL_VERSION_VALUES

MIGRATION_0102 = (
    Path(__file__).resolve().parents[1] / "migrations/19.0.1.0.2/post-migrate.py"
)


def _blank_pdf():
    writer, buffer = PdfWriter(), BytesIO()
    writer.add_blank_page(width=200, height=200)
    writer.write(buffer)
    return b64encode(buffer.getvalue())


@tagged("post_install", "-at_install")
class TestSignHardening(TrainingOrgCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_a.write(
            {
                "email": "organisme.a@example.com",
                "training_activity_number": "11 75 00000 75",
                "training_prefecture": "la préfecture de région d'Île-de-France",
            }
        )
        cls.company_b.write({"email": "organisme.b@example.com"})
        course = cls._make_course(cls.company_a)
        version = cls._make_version(course, publish=True, **FULL_VERSION_VALUES)
        session = cls._make_session(cls.company_a, course=course, version=version)
        cls._make_slot(session, start_hour=9.0, end_hour=12.5)
        cls.file = cls._make_file(
            cls.company_a,
            session=session,
            payment_terms_note="30 % à la signature.",
        )
        cls.role_customer = cls.env.ref("sign_oca.sign_role_customer")
        cls.role_employee = cls.env.ref("sign_oca.sign_role_employee")
        cls.partner_x = cls.env["res.partner"].create(
            {"name": "Cocontractant X", "email": "x@example.com"}
        )
        cls.partner_y = cls.env["res.partner"].create(
            {"name": "Partie Y", "email": "y@example.com"}
        )
        cls.pdf = _blank_pdf()

    # ------------------------------------------------------------------
    # Fabriques
    # ------------------------------------------------------------------

    def _request(self, company=None, send=False, sender=None):
        """Demande à deux signataires sur un vrai PDF (en superutilisateur)."""
        company = company or self.company_a
        request = self.env["sign.oca.request"].create(
            {
                "name": "Contrat test",
                "data": self.pdf,
                "company_id": company.id,
                "signer_ids": [
                    (0, 0, {"partner_id": self.partner_x.id, "role_id": self.role_customer.id}),
                    (0, 0, {"partner_id": self.partner_y.id, "role_id": self.role_employee.id}),
                ],
            }
        )
        if send:
            request.with_user(sender or self.user_manager).action_send()
        return request

    def _items(self, request, signer):
        """Un champ à signer pour le rôle du signataire."""
        item = {
            "role_id": signer.role_id.id,
            "page": 1,
            "required": False,
            "value": False,
            "name": "champ",
            "field_type": "text",
        }
        request.signatory_data = {"1": item}
        return {"1": item}

    def _invitations(self, token):
        return self.env["mail.message"].sudo().search(
            [("body", "ilike", token), ("model", "=", False)]
        )

    # ------------------------------------------------------------------
    # B1-bis (D1)
    # ------------------------------------------------------------------

    def test_t1_invitation_with_token_is_not_readable_by_sender(self):  # FAIL-AVANT
        request = self._request()
        request.with_user(self.user_manager).action_send()
        signer = request.signer_ids[0]
        token = signer.sudo().access_token
        self.assertTrue(token)
        invitations = self._invitations(token)
        self.assertTrue(invitations, "l'invitation doit exister")
        messages = self.env["mail.message"].with_user(self.user_manager)
        self.assertEqual(messages.search_count([("body", "ilike", token)]), 0)
        with self.assertRaises(AccessError):
            invitations.with_user(self.user_manager).read(["body"])

    def test_t2_invitation_is_issued_by_the_system(self):  # FAIL-AVANT
        request = self._request()
        request.with_user(self.user_manager).action_send()
        token = request.signer_ids[0].sudo().access_token
        invitation = self._invitations(token)
        self.assertTrue(invitation)
        self.assertEqual(invitation.author_id, self.env.ref("base.partner_root"))
        self.assertEqual(invitation.create_uid.id, 1)
        self.assertIn("organisme.a@example.com", invitation.email_from or "")

    def test_t2_other_company_branding(self):  # FAIL-AVANT
        """Demande de B envoyée par un utilisateur dont la société par défaut est A."""
        multi = self._make_user(
            "multi.ab", ["training_org.group_training_manager"], self.company_a
        )
        multi.company_ids = [(4, self.company_b.id)]
        request_b = self._request(company=self.company_b)
        request_b.with_user(multi).with_context(
            allowed_company_ids=[self.company_a.id, self.company_b.id]
        ).action_send()
        token = request_b.signer_ids[0].sudo().access_token
        invitation = self._invitations(token)
        self.assertTrue(invitation)
        self.assertIn("organisme.b@example.com", invitation.email_from or "")
        self.assertNotIn("organisme.a@example.com", invitation.email_from or "")
        mail = self.env["mail.mail"].sudo().search(
            [("mail_message_id", "in", invitation.ids)]
        )
        self.assertTrue(mail)
        # Marque de la société de la demande, pas celle de l'utilisateur.
        self.assertIn("Organisme B", mail.body_html)
        self.assertNotIn("Organisme A", mail.body_html)
        self.assertEqual(invitation.author_id, self.env.ref("base.partner_root"))

    def test_t4_sender_without_write_right_is_refused(self):
        request = self._request()
        reader = self._make_user("lecteur.simple", [], self.company_a)
        before = self.env["mail.message"].sudo().search_count([])
        with self.assertRaises(AccessError):
            request.with_user(reader).action_send()
        self.assertEqual(request.state, "1_draft")
        self.assertEqual(self.env["mail.message"].sudo().search_count([]), before)

    def test_t5_sign_now_skips_the_sender_only(self):
        request = self._request()
        request.signer_ids[0].partner_id = self.user_manager.partner_id
        request.with_user(self.user_manager).action_send(sign_now=True)
        invited = (
            self.env["mail.message"]
            .sudo()
            .search([("model", "=", False), ("message_type", "=", "user_notification")])
            .partner_ids
        )
        self.assertIn(self.partner_y, invited)
        self.assertNotIn(self.user_manager.partner_id, invited)

    def test_t6_thread_note_has_no_link(self):
        request = self._request()
        request.with_user(self.user_manager).action_send()
        notes = request.message_ids.filtered(
            lambda m: m.subtype_id == self.env.ref("mail.mt_note")
            and "Invitation" in (m.body or "")
        )
        self.assertTrue(notes)
        for note in notes:
            self.assertEqual(note.author_id, self.user_manager.partner_id)
            self.assertNotIn("/sign_oca/document/", note.body)
            self.assertIn("Cocontractant X", note.body)
            self.assertIn("x@example.com", note.body)

    def test_t7_validate_log_keeps_the_caller(self):
        request = self._request()
        request.with_user(self.user_manager).action_send()
        log = self.env["sign.oca.request.log"].sudo().search(
            [("request_id", "=", request.id), ("action", "=", "validate")]
        )
        self.assertEqual(log.uid, self.user_manager)

    def test_t8_email_reply_has_no_route_nonregression(self):
        """Non-régression (V-2) : une réponse citant le jeton n'a aucune route.

        Constaté sur 19.0 : une réponse rattachée à un message sans modèle
        n'a pas de route sans alias (``ValueError``). Le test constate
        explicitement cette absence de route : il échouera si Odoo se met à
        router ces réponses, ce qui obligerait à revoir qui les reçoit.
        """
        request = self._request()
        request.with_user(self.user_manager).action_send()
        signer = request.signer_ids[0]
        token = signer.sudo().access_token
        invitation = self._invitations(token)
        self.assertTrue(invitation)
        self.assertTrue(invitation.message_id)
        before = self.env["mail.message"].sudo().search([]).ids
        raw = (
            "From: Cocontractant X <x@example.com>\n"
            "To: organisme.a@example.com\n"
            "Message-Id: <reply-sign-t8@example.com>\n"
            f"In-Reply-To: {invitation.message_id}\n"
            f"References: {invitation.message_id}\n"
            "Subject: Re: New document to sign\n"
            "MIME-Version: 1.0\n"
            "Content-Type: text/plain; charset=utf-8\n\n"
            f"> /sign_oca/document/{signer.id}/{token}\n\nMerci.\n"
        )
        with self.assertRaisesRegex(ValueError, "No possible route"):
            self.env["mail.thread"].message_process(False, raw)
        new = self.env["mail.message"].sudo().search([("id", "not in", before)])
        carrying = new.filtered(lambda m: token in (m.body or ""))
        self.assertFalse(
            self.env["mail.message"]
            .with_user(self.user_manager)
            .search([("id", "in", carrying.ids)]),
            "la réponse citant le jeton ne doit pas être lisible par l'expéditeur",
        )

    # Empreinte de `SignOcaRequest.action_send` d'OCA (copiée dans ce module).
    UPSTREAM_ACTION_SEND_SHA256 = (
        "b45a85e48ba40145c5ca2f91e955d3ceab6905e8b97bb39ce80a1558a0980e4d"
    )

    def test_t9_upstream_action_send_has_not_drifted(self):
        """Échoue à toute mise à jour OCA de `action_send` : revoir la copie
        de ``training_org_sign.models.sign_oca_token`` puis mettre à jour
        l'empreinte."""
        from odoo.addons.sign_oca.models.sign_oca_request import SignOcaRequest

        digest = hashlib.sha256(
            inspect.getsource(SignOcaRequest.action_send).encode()
        ).hexdigest()
        self.assertEqual(digest, self.UPSTREAM_ACTION_SEND_SHA256)

    UPSTREAM_MAIL_TEMPLATE_SHA256 = (
        "08ecc9da88ffdae5615693a0ace8fb8f385bdcbf433112aa806bc1ad0e9c426a"
    )

    def test_t9_upstream_invitation_template_has_not_drifted(self):
        """R-3 : le gabarit de courriel rendu par la copie d'`action_send`."""
        view = self.env.ref("sign_oca.sign_oca_template_mail")
        digest = hashlib.sha256(view.arch_db.encode()).hexdigest()
        self.assertEqual(digest, self.UPSTREAM_MAIL_TEMPLATE_SHA256)

    # ------------------------------------------------------------------
    # Stock (D2)
    # ------------------------------------------------------------------

    def _load_migration(self):
        self.assertTrue(MIGRATION_0102.exists(), "migration 19.0.1.0.2 absente")
        spec = importlib.util.spec_from_file_location("tos_post_migrate_0102", MIGRATION_0102)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_t10_migration_purges_tokens_from_message_bodies(self):  # FAIL-AVANT
        module = self._load_migration()
        Message = self.env["mail.message"]
        link = "/sign_oca/document/12/AbCd-eF_123"
        body = f'<p>Lien : <a href="https://erp.example.com{link}">Signer</a></p>'
        orphan = Message.create(
            {"body": body, "message_type": "user_notification", "model": False}
        )
        with_model = Message.create(
            {
                "body": body,
                "message_type": "user_notification",
                "model": "res.partner",
                "res_id": self.partner_x.id,
            }
        )
        other_type = Message.create(
            {"body": body, "message_type": "comment", "model": False}
        )
        self.env.flush_all()
        module.migrate(self.env.cr, "19.0.1.0.1")
        self.env.invalidate_all()
        self.assertNotIn("AbCd-eF_123", orphan.body)
        self.assertNotIn("/sign_oca/document/", orphan.body)
        self.assertIn("/my/sign_requests", orphan.body)
        self.assertIn('href="https://erp.example.com/my/sign_requests"', orphan.body)
        self.assertEqual(str(with_model.body), str(Message.browse(with_model.id).body))
        self.assertIn("AbCd-eF_123", with_model.body)
        self.assertIn("AbCd-eF_123", other_type.body)
        # Idempotente.
        snapshot = orphan.body
        module.migrate(self.env.cr, "19.0.1.0.1")
        self.env.invalidate_all()
        self.assertEqual(orphan.body, snapshot)

    def test_t11_rotation_renews_tokens_and_resends_to_pending_only(self):
        request = self._request()
        request.with_user(self.user_manager).action_send()
        signed, waiting = request.signer_ids
        signed.write({"signed_on": fields.Datetime.now()})
        old = {s.id: s.sudo().access_token for s in request.signer_ids}
        draft = self._request()  # brouillon : pas de renvoi
        before = self.env["mail.message"].sudo().search([]).ids
        result = self.env["sign.oca.request"]._training_rotate_signer_tokens()
        self.assertEqual(result["resent"], 1)
        for signer in request.signer_ids:
            self.assertNotEqual(signer.sudo().access_token, old[signer.id])
        self.assertEqual(draft.state, "1_draft")
        sent = self.env["mail.message"].sudo().search(
            [("id", "not in", before), ("model", "=", False)]
        )
        self.assertEqual(sent.partner_ids, waiting.partner_id)
        self.assertIn(waiting.sudo().access_token, sent.body)
        self.assertIn("remplace le précédent", sent.body)
        with self.assertRaises(AccessError):
            self.env["sign.oca.request"].with_user(self.user_manager)._training_rotate_signer_tokens()

    def test_t10b_migration_replays_the_0101_purges(self):
        """Filet de sécurité : jetons de PDF et du journal vidés, idempotent."""
        module = self._load_migration()
        request = self._request()
        attachment = (
            self.env["ir.attachment"]
            .sudo()
            .search(
                [
                    ("res_model", "=", "sign.oca.request"),
                    ("res_id", "=", request.id),
                    ("res_field", "=", "data"),
                ],
                limit=1,
            )
        )
        self.assertTrue(attachment)
        attachment.access_token = "jeton-pdf"
        log = self.env["sign.oca.request.log"].create(
            {"request_id": request.id, "action": "view", "access_token": "jeton-log"}
        )
        self.env.flush_all()
        for _ in range(2):
            module.migrate(self.env.cr, "19.0.1.0.1")
            self.env.invalidate_all()
            self.assertFalse(attachment.access_token)
            self.assertFalse(log.access_token)

    # ------------------------------------------------------------------
    # R-a (D3)
    # ------------------------------------------------------------------

    def test_t12_system_admin_cannot_sign_through_rpc(self):  # FAIL-AVANT
        admin = self.env.ref("base.user_admin")
        # Société de l'administrateur : sinon la règle multi-société le refuse
        # avant la garde et le test ne prouve rien.
        request = self._request(company=admin.company_id)
        request.action_send()
        signer = request.signer_ids[0]
        items = self._items(request, signer)
        # Il lit tous les signataires : sans cela, la règle d'accès le
        # refuserait avant la garde et le test ne prouverait rien.
        admin.group_ids = [(4, self.env.ref("sign_oca.sign_oca_group_manager").id)]
        self.assertTrue(admin.has_group("base.group_system"))
        with mock.patch.object(
            type(signer), "_check_signable", autospec=True
        ) as check, mock.patch.object(
            type(signer), "_get_pdf_page", autospec=True, return_value=False
        ):
            with self.assertRaises(AccessError):
                signer.with_user(admin).action_sign(items)
            check.assert_not_called()
        self.assertFalse(signer.signed_on)

    def test_t13_reader_is_refused_by_the_guard_without_side_effect(self):  # FAIL-AVANT
        request = self._request(send=True)
        signer = request.signer_ids[0]
        items = self._items(request, signer)
        reader = self._make_user(
            "lecteur.garde",
            ["training_org.group_training_manager", "sign_oca.sign_oca_group_manager"],
            self.company_a,
        )
        self.assertTrue(signer.with_user(reader).read(["partner_id"]))
        with mock.patch.object(
            type(signer), "_get_pdf_page", autospec=True, return_value=False
        ) as page:
            with self.assertRaises(AccessError):
                signer.with_user(reader).action_sign(items)
            page.assert_not_called()
        self.assertFalse(signer.signed_on)

    # ------------------------------------------------------------------
    # R-b (D4)
    # ------------------------------------------------------------------

    def test_t17_signer_fields_frozen_after_send(self):  # FAIL-AVANT
        request = self._request(send=True)
        signer = request.signer_ids[0].with_user(self.user_manager)
        other_request = self._request()
        values = {
            "partner_id": self.partner_y.id,
            "role_id": self.role_employee.id,
            "signed_on": fields.Datetime.now(),
            "signature_hash": "forge",
            "request_id": other_request.id,
            "latitude": 1.5,
            "inalterable_hash": "forge",
        }
        for name, value in values.items():
            with self.subTest(field=name), self.assertRaises(UserError):
                signer.write({name: value})

    def test_t18_draft_allows_partner_and_role_but_not_signed_on(self):  # FAIL-AVANT
        request = self._request()
        signer = request.signer_ids[0].with_user(self.user_manager)
        with self.assertRaises(UserError):
            signer.write({"signed_on": fields.Datetime.now()})
        signer.write({"partner_id": self.partner_y.id})
        signer.write({"role_id": self.role_employee.id})
        self.assertEqual(signer.partner_id, self.partner_y)
        self.assertEqual(signer.role_id, self.role_employee)

    def test_t19_signers_cannot_be_added_or_removed_after_send(self):  # FAIL-AVANT
        Signer = self.env["sign.oca.request.signer"].with_user(self.user_manager)
        sent = self._request(send=True)
        with self.assertRaises(UserError):
            Signer.create(
                {
                    "request_id": sent.id,
                    "partner_id": self.partner_y.id,
                    "role_id": self.role_employee.id,
                }
            )
        with self.assertRaises(UserError):
            sent.signer_ids[0].with_user(self.user_manager).unlink()
        draft = self._request()
        with self.assertRaises(UserError):
            Signer.create(
                {
                    "request_id": draft.id,
                    "partner_id": self.partner_y.id,
                    "role_id": self.role_employee.id,
                    "signed_on": fields.Datetime.now(),
                }
            )

    def test_t20_request_state_and_content_frozen_after_send(self):  # FAIL-AVANT
        request = self._request(send=True).with_user(self.user_manager)
        with self.assertRaises(UserError):
            request.write({"state": "2_signed"})
        with self.assertRaises(UserError):
            request.write({"data": b64encode(b"%PDF-forged")})
        with self.assertRaises(UserError):
            request.write({"signatory_data": {"9": {"role_id": 1}}})
        request.cancel()
        self.assertEqual(request.state, "3_cancel")

    def test_t21_copy_of_a_signed_request_drops_the_signatures(self):  # FAIL-AVANT
        request = self._request(send=True)
        for signer in request.signer_ids:
            signer.write(
                {
                    "signed_on": fields.Datetime.now(),
                    "signature_hash": "abc",
                    "latitude": 2.0,
                    "longitude": 3.0,
                }
            )
        request._check_signed()
        self.assertEqual(request.state, "2_signed")
        copy = request.copy()
        self.assertEqual(len(copy.signer_ids), 2)
        self.assertEqual(copy.state, "1_draft")
        for signer in copy.signer_ids:
            self.assertFalse(signer.signed_on)
            self.assertFalse(signer.signature_hash)
            self.assertFalse(signer.latitude)
            self.assertFalse(signer.longitude)

    # ------------------------------------------------------------------
    # D5 : secrets exposés par le registre
    # ------------------------------------------------------------------

    SECRET_NAME = re.compile(r"(^|_)(token|secret)($|_)")

    def test_t24_secret_fields_are_reserved_to_system(self):  # FAIL-AVANT
        offenders = []
        for model_name, model in self.env.registry.items():
            if not model_name.startswith("sign.oca") and model_name not in (
                "training.file",
                "training.document",
            ):
                continue
            for name, field in model._fields.items():
                if not (self.SECRET_NAME.search(name) or name == "access_url"):
                    continue
                groups = {
                    group.strip()
                    for group in str(field.groups or "").split(",")
                    if group.strip()
                }
                if not groups or groups - {"base.group_system"}:
                    offenders.append(f"{model_name}.{name} groups={sorted(groups)}")
        self.assertEqual(offenders, [])

    # ------------------------------------------------------------------
    # R-a (D3), suite
    # ------------------------------------------------------------------

    def test_t14_internal_signer_is_refused_in_direct_rpc(self):
        user = self._make_user(
            "signataire.interne.rpc",
            ["training_org.group_training_user", "sign_oca.sign_oca_group_user"],
            self.company_a,
        )
        request = self._request(send=True)
        signer = request.signer_ids[0]
        signer.partner_id = user.partner_id
        items = self._items(request, signer)
        with self.assertRaises(AccessError):
            signer.with_user(user).action_sign(items)
        self.assertFalse(signer.signed_on)

    def test_t15_forged_context_marker_is_not_enough(self):
        request = self._request(send=True)
        signer = request.signer_ids[0]
        items = self._items(request, signer)
        forged = signer.with_user(self.user_manager).with_context(
            training_sign_verified_signer_id=signer.id
        )
        with self.assertRaises(AccessError):
            forged.action_sign(items)
        self.assertFalse(signer.signed_on)

    def test_t15_su_without_marker_is_refused(self):
        request = self._request(send=True)
        signer = request.signer_ids[0]
        items = self._items(request, signer)
        with self.assertRaises(AccessError):
            signer.action_sign(items)
        with self.assertRaises(AccessError):
            signer.with_context(
                training_sign_verified_signer_id=signer.id + 1
            ).action_sign(items)

    # ------------------------------------------------------------------
    # Revue devsecops : C1 (valeurs par défaut) et C2 (création de demande)
    # ------------------------------------------------------------------

    def _signer_vals(self, request=None):
        vals = {
            "partner_id": self.partner_y.id,
            "role_id": self.role_employee.id,
        }
        if request:
            vals["request_id"] = request.id
        return vals

    def test_c1_context_default_signed_on_is_refused(self):  # FAIL-AVANT
        draft = self._request()
        Signer = self.env["sign.oca.request.signer"].with_user(self.user_manager)
        with self.assertRaises(UserError):
            Signer.with_context(default_signed_on="2026-01-01 10:00:00").create(
                self._signer_vals(draft)
            )
        with self.assertRaises(UserError):
            Signer.with_context(default_signature_hash="forge").create(
                self._signer_vals(draft)
            )

    def test_c1_context_default_request_id_on_a_sent_request_is_refused(self):  # FAIL-AVANT
        sent = self._request(send=True)
        Signer = self.env["sign.oca.request.signer"].with_user(self.user_manager)
        with self.assertRaises(UserError):
            Signer.with_context(default_request_id=sent.id).create(self._signer_vals())
        self.assertEqual(len(sent.signer_ids), 2)

    def test_c1_user_ir_default_is_refused(self):  # FAIL-AVANT
        """Défaut PERSONNEL posé par l'utilisateur lui-même, sans su."""
        draft = self._request()
        manager = self.user_manager
        self.env["ir.default"].with_user(manager).set(
            "sign.oca.request.signer",
            "signed_on",
            "2026-01-01 10:00:00",
            user_id=True,
        )
        Signer = self.env["sign.oca.request.signer"].with_user(manager)
        with self.assertRaises(UserError):
            Signer.create(self._signer_vals(draft))

    def test_c2a_request_cannot_be_created_or_copied_in_a_signed_state(self):  # FAIL-AVANT
        Request = self.env["sign.oca.request"].with_user(self.user_manager)
        with self.assertRaises(UserError):
            Request.create({"name": "forgé", "data": self.pdf, "state": "2_signed"})
        with self.assertRaises(UserError):
            Request.create({"name": "forgé", "data": self.pdf, "state": "0_sent"})
        draft = self._request()
        with self.assertRaises(UserError):
            draft.with_user(self.user_manager).copy(default={"state": "2_signed"})

    def test_c2b_training_link_fields_are_not_writable(self):  # FAIL-AVANT
        draft = self._request().with_user(self.user_manager)
        sent = self._request(send=True).with_user(self.user_manager)
        for request in (draft, sent):
            for name, value in (
                ("training_res_model", "training.file"),
                ("training_res_id", self.file.id),
            ):
                with self.subTest(field=name, state=request.state):
                    with self.assertRaises(UserError):
                        request.write({name: value})
        document = self.env["training.document"].sudo().search([], limit=1)
        if document:
            with self.assertRaises(UserError):
                draft.write({"training_document_id": document.id})
        with self.assertRaises(UserError):
            self.env["sign.oca.request"].with_user(self.user_manager).create(
                {
                    "name": "forgé",
                    "data": self.pdf,
                    "training_res_model": "training.file",
                    "training_res_id": self.file.id,
                }
            )

    def test_c2_trainer_cannot_get_a_file_signed_by_forging_the_link(self):  # FAIL-AVANT
        """Un utilisateur du parapheur sans accès au dossier ne peut pas le signer."""
        trainer = self._make_user(
            "formateur.sign", ["sign_oca.sign_oca_group_user"], self.company_a
        )
        self.assertEqual(self.file.state, "draft")
        request = self.env["sign.oca.request"].with_user(trainer).create(
            {
                "name": "Faux contrat",
                "data": self.pdf,
                "signer_ids": [
                    (
                        0,
                        0,
                        {
                            "partner_id": trainer.partner_id.id,
                            "role_id": self.role_customer.id,
                        },
                    )
                ],
            }
        )
        with self.assertRaises(UserError):
            request.write(
                {"training_res_model": "training.file", "training_res_id": self.file.id}
            )
        request.action_send()
        signer = request.signer_ids
        sudo_signer = signer.sudo().with_context(
            training_sign_verified_signer_id=signer.id
        )
        sudo_signer.write({"signed_on": fields.Datetime.now()})
        request.sudo()._check_signed()
        self.assertNotEqual(self.file.state, "signed")

    def test_c2c_apply_signature_only_follows_the_document(self):  # FAIL-AVANT
        """Même écrits en su, les champs rapatriés ne désignent plus le dossier."""
        request = self._request(send=True)
        request.write(
            {"training_res_model": "training.file", "training_res_id": self.file.id}
        )
        for signer in request.signer_ids:
            signer.signed_on = fields.Datetime.now()
        request._check_signed()
        self.assertEqual(request.state, "2_signed")
        self.assertEqual(self.file.state, "draft")

    # ------------------------------------------------------------------
    # Réserves de la revue devsecops
    # ------------------------------------------------------------------

    def test_r_signed_request_cannot_be_cancelled(self):
        request = self._request(send=True)
        for signer in request.signer_ids:
            signer.signed_on = fields.Datetime.now()
        request._check_signed()
        self.assertEqual(request.state, "2_signed")
        with self.assertRaises(UserError):
            request.with_user(self.user_manager).cancel()
        self.assertEqual(request.state, "2_signed")

    def test_r_rotation_does_not_resend_for_archived_requests(self):
        request = self._request(send=True)
        request.active = False
        before = self.env["mail.message"].sudo().search([]).ids
        result = self.env["sign.oca.request"]._training_rotate_signer_tokens()
        self.assertEqual(result["resent"], 0)
        sent = self.env["mail.message"].sudo().search(
            [("id", "not in", before), ("model", "=", False)]
        )
        self.assertFalse(sent)

    def test_r1_pending_only_keeps_the_signed_signer_token(self):
        request = self._request(send=True)
        signed, waiting = request.signer_ids
        signed.signed_on = fields.Datetime.now()
        old_signed = signed.sudo().access_token
        old_waiting = waiting.sudo().access_token
        before = self.env["mail.message"].sudo().search([]).ids
        result = request._training_rotate_signer_tokens(pending_only=True)
        self.assertEqual(result, {"renewed": 1, "resent": 1})
        self.assertEqual(signed.sudo().access_token, old_signed)
        self.assertNotEqual(waiting.sudo().access_token, old_waiting)
        sent = self.env["mail.message"].sudo().search(
            [("id", "not in", before), ("model", "=", False)]
        )
        self.assertEqual(sent.partner_ids, waiting.partner_id)

    def test_r1_resend_false_renews_without_any_email(self):
        request = self._request(send=True)
        old = {s.id: s.sudo().access_token for s in request.signer_ids}
        before = self.env["mail.message"].sudo().search([]).ids
        result = request._training_rotate_signer_tokens(resend=False)
        self.assertEqual(result, {"renewed": 2, "resent": 0})
        for signer in request.signer_ids:
            self.assertNotEqual(signer.sudo().access_token, old[signer.id])
        self.assertFalse(
            self.env["mail.message"].sudo().search(
                [("id", "not in", before), ("model", "=", False)]
            )
        )

    def test_r_migration_counts_links_outside_the_purge_filter(self):
        module = self._load_migration()
        body = '<a href="/sign_oca/document/1/jeton-abc">x</a>'
        self.env["mail.message"].create(
            {"body": body, "message_type": "comment", "model": False}
        )
        self.env["mail.message"].create(
            {
                "body": body,
                "message_type": "user_notification",
                "model": "res.partner",
                "res_id": self.partner_x.id,
            }
        )
        self.env.flush_all()
        with self.assertLogs("tos_post_migrate_0102", level="INFO") as logs:
            module.migrate(self.env.cr, "19.0.1.0.1")
        self.assertTrue(
            any("2 message(s) hors du filtre" in line for line in logs.output),
            logs.output,
        )
        self.env.invalidate_all()
        remaining = self.env["mail.message"].search(
            [("body", "ilike", "/sign_oca/document/1/jeton-abc")]
        )
        self.assertEqual(len(remaining), 2)  # comptés, pas modifiés

    # ------------------------------------------------------------------
    # Revue devsecops de d8a0625d : B1, R-A, R-B
    # ------------------------------------------------------------------

    def _open_requests(self):
        return self.env["sign.oca.request"].sudo().search(
            [("training_res_id", "=", self.file.id)]
        )

    def _issued_document(self):
        """Pièce émise du dossier, sans parapheur ouvert (demande annulée)."""
        self.file.with_user(self.user_manager).action_request_signature()
        request = self._open_requests()
        document = request.training_document_id
        request.cancel()
        return document

    def test_b1_context_default_state_is_refused_on_the_button(self):  # FAIL-AVANT
        document = self._issued_document()
        with self.assertRaises(UserError):
            document.with_user(self.user_manager).with_context(
                default_state="2_signed"
            ).action_request_signature()
        self.assertEqual(len(self._open_requests().filtered("active")), 1)
        self.assertFalse(self._open_requests().filtered(lambda r: r.state == "2_signed"))

    def test_b1_context_default_signed_on_has_no_effect_on_the_button(self):
        """Non-régression : `default_signed_on` du contexte ne signe rien.

        Constaté sur 19.0 : les défauts de contexte ne descendent pas aux
        lignes créées par commande ``(0, 0, ...)`` ; seul ``default_state``
        atteint la demande (test précédent) et les ``ir.default`` atteignent
        les lignes (test suivant). Refus ou absence d'effet sont admis ici :
        ce qui compte est qu'aucune signature n'apparaisse.
        """
        document = self._issued_document()
        try:
            with self.env.cr.savepoint():
                document.with_user(self.user_manager).with_context(
                    default_signed_on="2026-01-01 10:00:00"
                ).action_request_signature()
        except UserError:
            pass
        self.assertFalse(self._open_requests().signer_ids.filtered("signed_on"))
        self.assertFalse(self._open_requests().filtered(lambda r: r.state == "2_signed"))

    def test_b1_personal_ir_default_is_refused_on_the_button(self):  # FAIL-AVANT
        document = self._issued_document()
        manager = self.user_manager
        Default = self.env["ir.default"].with_user(manager)
        for model, name, value in (
            ("sign.oca.request", "state", "2_signed"),
            ("sign.oca.request.signer", "signed_on", "2026-01-01 10:00:00"),
        ):
            with self.subTest(field=name):
                Default.set(model, name, value, user_id=True)
                with self.assertRaises(UserError):
                    document.with_user(manager).action_request_signature()
                self.assertFalse(
                    self._open_requests().filtered(lambda r: r.state == "2_signed")
                )
                self.assertFalse(self._open_requests().signer_ids.filtered("signed_on"))
                Default.search([("user_id", "=", manager.id)]).unlink()

    def test_b1_read_only_profile_cannot_create_a_request(self):  # FAIL-AVANT
        document = self._issued_document()
        # Aucun rôle du domaine ne lit la pièce et son dossier sans pouvoir
        # créer de parapheur : on construit ce profil (lecture seule) pour
        # prouver que la création n'est plus élevée par le chemin du bouton.
        group = self.env["res.groups"].create({"name": "Lecteur dossier (test)"})
        for model in ("training.file", "training.document"):
            self.env["ir.model.access"].create(
                {
                    "name": f"lecteur {model}",
                    "model_id": self.env["ir.model"]._get(model).id,
                    "group_id": group.id,
                    "perm_read": True,
                }
            )
        reader = self._make_user("lecteur.dossier", [], self.company_a)
        # + référent qualité (lecture des pièces du domaine, sans parapheur).
        reader.group_ids = [
            (4, group.id),
            (4, self.env.ref("training_org.group_training_quality").id),
        ]
        self.assertFalse(
            self.env["sign.oca.request"].with_user(reader).has_access("create"),
            "préalable : ce profil ne crée pas de parapheur",
        )
        self.assertTrue(document.with_user(reader)._assert_signature_allowed())
        with self.assertRaises(AccessError):
            document.with_user(reader).action_request_signature()
        self.assertEqual(
            self.env["sign.oca.request"].sudo().search_count(
                [("training_document_id", "=", document.id)]
            ),
            1,
        )

    def test_ra_trainer_cannot_add_himself_to_a_contractual_request(self):  # FAIL-AVANT
        self.file.with_user(self.user_manager).action_request_signature()
        request = self._open_requests()
        self.assertEqual(request.state, "1_draft")
        trainer = self._make_user(
            "formateur.signataire", ["sign_oca.sign_oca_group_user"], self.company_a
        )
        with self.assertRaises(UserError):
            self.env["sign.oca.request.signer"].with_user(trainer).create(
                {
                    "request_id": request.id,
                    "partner_id": trainer.partner_id.id,
                    "role_id": self.role_customer.id,
                }
            )

    def test_rb_signed_request_cannot_be_archived(self):  # FAIL-AVANT
        request = self._request(send=True)
        for signer in request.signer_ids:
            signer.signed_on = fields.Datetime.now()
        request._check_signed()
        self.assertEqual(request.state, "2_signed")
        with self.assertRaises(UserError):
            request.with_user(self.user_manager).write({"active": False})
        self.assertTrue(request.active)

    # ------------------------------------------------------------------
    # Revue devsecops de 8d491da6 : rattachement par défaut, pièce figée
    # ------------------------------------------------------------------

    def test_d1_context_default_document_link_is_refused(self):  # FAIL-AVANT
        document = self._issued_document()
        Request = self.env["sign.oca.request"].with_user(self.user_manager)
        count = self.env["sign.oca.request"].sudo().search_count([])
        with self.assertRaises(UserError):
            Request.with_context(
                default_training_document_id=document.id
            ).create({"name": "forgé", "data": self.pdf})
        self.assertEqual(self.env["sign.oca.request"].sudo().search_count([]), count)
        self.assertEqual(self.file.state, "draft")

    def test_d1_personal_ir_default_document_link_is_refused(self):  # FAIL-AVANT
        document = self._issued_document()
        manager = self.user_manager
        self.env["ir.default"].with_user(manager).set(
            "sign.oca.request", "training_document_id", document.id, user_id=True
        )
        count = self.env["sign.oca.request"].sudo().search_count([])
        with self.assertRaises(UserError):
            self.env["sign.oca.request"].with_user(manager).create(
                {"name": "forgé", "data": self.pdf}
            )
        self.assertEqual(self.env["sign.oca.request"].sudo().search_count([]), count)
        self.assertEqual(self.file.state, "draft")

    def test_d2_issued_copy_cannot_be_replaced_even_in_draft(self):  # FAIL-AVANT
        self.file.with_user(self.user_manager).action_request_signature()
        request = self._open_requests()
        self.assertEqual(request.state, "1_draft")
        self.assertTrue(request.training_document_id)
        as_manager = request.with_user(self.user_manager)
        with self.assertRaises(UserError):
            as_manager.write({"data": self.pdf})
        with self.assertRaises(UserError):
            as_manager.write({"company_id": self.company_b.id})
        # Non-régression : la configuration des champs (signatory_data) et
        # l'envoi restent possibles ; `action_sign` tourne en su.
        as_manager.write({"signatory_data": {}})
        as_manager.action_send()
        self.assertEqual(request.state, "0_sent")

    # ------------------------------------------------------------------
    # Pièce jointe du PDF : contournement par ir.attachment (E-10)
    # ------------------------------------------------------------------

    FORGED = b64encode(b"%PDF-1.4 forged")

    def _pdf_attachment(self, request, user):
        return self.env["ir.attachment"].with_user(user).search(
            [
                ("res_model", "=", "sign.oca.request"),
                ("res_id", "=", request.id),
                ("res_field", "=", "data"),
            ]
        )

    def _linked_request(self, send=False, sign=False):
        self.file.with_user(self.user_manager).action_request_signature()
        request = self._open_requests()
        if send or sign:
            request.with_user(self.user_manager).action_send()
        if sign:
            for signer in request.signer_ids:
                signer.write({"signed_on": fields.Datetime.now(), "signature_hash": "x"})
            request._check_signed()
            self.assertEqual(request.state, "2_signed")
        return request

    def test_p1_pdf_attachment_write_is_refused_when_sent(self):  # FAIL-AVANT
        request = self._linked_request(send=True)
        original = request.data
        attachment = self._pdf_attachment(request, self.user_manager)
        self.assertTrue(attachment)
        with self.assertRaises(UserError):
            attachment.write({"datas": self.FORGED})
        self.env.invalidate_all()
        self.assertEqual(request.data, original)

    def test_p1b_pdf_attachment_write_is_refused_in_linked_draft(self):  # FAIL-AVANT
        request = self._linked_request()
        original = request.data
        attachment = self._pdf_attachment(request, self.user_manager)
        for key, value in (("datas", self.FORGED), ("raw", b"%PDF-forged")):
            with self.subTest(key=key), self.assertRaises(UserError):
                attachment.write({key: value})
        self.env.invalidate_all()
        self.assertEqual(request.data, original)

    def test_p2_pdf_attachment_write_is_refused_when_signed(self):  # FAIL-AVANT
        request = self._linked_request(sign=True)
        attachment = self._pdf_attachment(request, self.user_manager)
        with self.assertRaises(UserError):
            attachment.write({"datas": self.FORGED})
        self.env.invalidate_all()
        self.assertNotEqual(request.data, self.FORGED)

    def test_p5_pdf_attachment_unlink_and_create_are_refused(self):  # FAIL-AVANT
        request = self._linked_request(send=True)
        attachment = self._pdf_attachment(request, self.user_manager)
        with self.assertRaises(UserError):
            attachment.unlink()
        with self.assertRaises(UserError):
            self.env["ir.attachment"].with_user(self.user_manager).create(
                {
                    "name": "data",
                    "res_model": "sign.oca.request",
                    "res_id": request.id,
                    "res_field": "data",
                    "raw": b"%PDF-forged",
                }
            )
        self.assertTrue(request.data)

    def test_p_attachment_guards_leave_native_flows_alone(self):
        # Le téléchargement régénère le jeton de la pièce jointe.
        request = self._linked_request(send=True)
        attachment = self._pdf_attachment(request, self.user_manager)
        attachment.write({"access_token": "nouveau-jeton"})
        self.assertEqual(attachment.sudo().access_token, "nouveau-jeton")
        # Une demande ordinaire en brouillon reste libre.
        plain = self._request().with_user(self.user_manager)
        plain_attachment = self._pdf_attachment(plain, self.user_manager)
        plain_attachment.write({"datas": self.FORGED})
        plain.write({"data": self.pdf})
        # Chemin serveur (su) : permis, même pour une demande envoyée.
        self._pdf_attachment(request, self.env.user).sudo().write(
            {"datas": self.pdf}
        )

    def test_p3_linked_request_cannot_be_copied(self):
        request = self._linked_request()
        with self.assertRaises(UserError):
            request.with_user(self.user_manager).copy()
        # Une demande ordinaire se duplique toujours (T21).
        self.assertTrue(self._request().with_user(self.user_manager).copy())

    # ------------------------------------------------------------------
    # Revue de 83a8b828 : cible du PDF, gel complet, mail_mail, R-2
    # ------------------------------------------------------------------

    FORGED_RAW = b"%PDF-1.4 forged"

    def _pdf_count(self, request):
        return self.env["ir.attachment"].sudo().search_count(
            [
                ("res_model", "=", "sign.oca.request"),
                ("res_id", "=", request.id),
                ("res_field", "=", "data"),
            ]
        )

    def _upload(self, request):
        """Pièce jointe ordinaire posée sur la demande (comme l'upload du chatter)."""
        return self.env["ir.attachment"].with_user(self.user_manager).create(
            {
                "name": "x.pdf",
                "raw": self.FORGED_RAW,
                "res_model": "sign.oca.request",
                "res_id": request.id,
            }
        )

    def test_q2_upload_then_retarget_to_the_pdf_is_refused(self):  # FAIL-AVANT
        request = self._linked_request(send=True)
        attachment = self._upload(request)
        for vals in ({"res_field": "data"}, {"res_field": "data", "res_id": request.id}):
            with self.subTest(vals=vals), self.assertRaises(UserError):
                attachment.write(vals)
        self.assertEqual(self._pdf_count(request), 1)

    def test_q3_create_with_default_res_field_is_refused(self):  # FAIL-AVANT
        request = self._linked_request(send=True)
        Attachment = self.env["ir.attachment"].with_user(self.user_manager)
        with self.assertRaises(UserError):
            Attachment.with_context(default_res_field="data").create(
                {
                    "name": "data",
                    "raw": self.FORGED_RAW,
                    "res_model": "sign.oca.request",
                    "res_id": request.id,
                }
            )
        with self.assertRaises(UserError):
            Attachment.with_context(
                default_res_field="data",
                default_res_model="sign.oca.request",
                default_res_id=request.id,
            ).create({"name": "data", "raw": self.FORGED_RAW})
        self.assertEqual(self._pdf_count(request), 1)

    def test_q5_retargeting_another_pdf_to_a_frozen_request_is_refused(self):  # FAIL-AVANT
        request = self._linked_request(send=True)
        draft = self._request().with_user(self.user_manager)
        other = self._pdf_attachment(draft, self.user_manager)
        other.write({"datas": b64encode(self.FORGED_RAW)})
        with self.assertRaises(UserError):
            other.write({"res_id": request.id})
        self.assertEqual(self._pdf_count(request), 1)

    def test_q5b_two_steps_lower_id_is_refused(self):  # FAIL-AVANT
        old = self.env["ir.attachment"].with_user(self.user_manager).create(
            {"name": "old.pdf", "raw": self.FORGED_RAW}
        )
        request = self._linked_request(send=True)
        draft = self._request()
        old.write({"res_model": "sign.oca.request", "res_id": draft.id})
        with self.assertRaises(UserError):
            old.write({"res_field": "data", "res_id": request.id})
        self.assertEqual(self._pdf_count(request), 1)

    def test_q7_frozen_pdf_attachment_is_frozen_except_access_token(self):  # FAIL-AVANT
        request = self._linked_request(send=True)
        attachment = self._pdf_attachment(request, self.user_manager)
        for vals in (
            {"public": True},
            {"mimetype": "text/html"},
            {"name": "evil.html"},
        ):
            with self.subTest(vals=vals), self.assertRaises(UserError):
                attachment.write(vals)
        self.assertFalse(attachment.sudo().public)
        attachment.write({"access_token": "ok"})
        self.assertEqual(attachment.sudo().access_token, "ok")

    def test_m1_migration_purges_unsent_mail_bodies(self):  # FAIL-AVANT
        module = self._load_migration()
        body = '<a href="https://erp.example.com/sign_oca/document/9/Tok-123">x</a>'
        Mail = self.env["mail.mail"]
        mails = {
            state: Mail.create({"body_html": body, "state": state})
            for state in ("outgoing", "exception", "sent")
        }
        self.env.flush_all()
        with self.assertLogs("tos_post_migrate_0102", level="INFO") as logs:
            module.migrate(self.env.cr, "19.0.1.0.1")
        self.env.invalidate_all()
        self.assertNotIn("Tok-123", mails["outgoing"].body_html)
        self.assertNotIn("Tok-123", mails["exception"].body_html)
        self.assertIn("/my/sign_requests", mails["outgoing"].body_html)
        self.assertIn("Tok-123", mails["sent"].body_html)
        self.assertTrue(any("mail(s) non envoyé(s)" in line for line in logs.output))

    def test_r2_sent_linked_request_cannot_be_deleted(self):  # FAIL-AVANT
        request = self._linked_request(send=True)
        with self.assertRaises(UserError):
            request.with_user(self.user_manager).unlink()
        self.assertTrue(request.exists())
        # Un brouillon rattaché, lui, se supprime encore ; il s'annule sinon.
        draft = self._linked_request_draft_for_delete()
        draft.with_user(self.user_manager).unlink()
        self.assertFalse(draft.exists())

    def _linked_request_draft_for_delete(self):
        second = self._make_file(
            self.company_a,
            file_type="convention",
            session=self.file.session_ids,
            partner_name="Autre client",
            payment_terms_note="30 % à la signature.",
        )
        second.with_user(self.user_manager).action_request_signature()
        return self.env["sign.oca.request"].sudo().search(
            [("training_res_id", "=", second.id)]
        )

    def test_msg_creating_a_signed_request_gets_the_creation_message(self):  # FAIL-AVANT
        document = self._issued_document()
        with self.assertRaisesRegex(UserError, "brouillon") as caught:
            document.with_user(self.user_manager).with_context(
                default_state="2_signed"
            ).action_request_signature()
        self.assertNotIn("envoyé", str(caught.exception))

    # ------------------------------------------------------------------
    # Revue de 071e5dc2 : pièce du composeur réaffectée en sudo, index unique
    # ------------------------------------------------------------------

    def test_q8b_composer_attachment_cannot_be_smuggled_as_the_pdf(self):  # FAIL-AVANT
        """`message_post` réaffecte en sudo les pièces du composeur : refus aussi en su."""
        request = self._linked_request(send=True)
        attachment = self.env["ir.attachment"].with_user(self.user_manager).create(
            {
                "name": "c.pdf",
                "raw": self.FORGED_RAW,
                "res_model": "mail.compose.message",
                "res_id": 0,
            }
        )
        with self.assertRaises(UserError):
            attachment.write({"res_field": "data"})
            request.with_user(self.user_manager).message_post(
                body="x", attachment_ids=attachment.ids
            )
        self.assertEqual(self._pdf_count(request), 1)
        self.assertNotEqual(request.sudo().data, b64encode(self.FORGED_RAW))

    def test_i1_one_pdf_attachment_per_request_in_database(self):  # FAIL-AVANT
        request = self._linked_request(send=True)
        self.assertEqual(self._pdf_count(request), 1)
        with mute_logger("odoo.sql_db"), self.assertRaises(IntegrityError):
            self.env["ir.attachment"].sudo().create(
                {
                    "name": "data",
                    "raw": self.FORGED_RAW,
                    "res_model": "sign.oca.request",
                    "res_id": request.id,
                    "res_field": "data",
                }
            )
            self.env.flush_all()

    def test_i2_orm_never_violates_the_unique_index(self):
        request = self._linked_request(send=True)
        # Écrire le contenu (chemin serveur) met à jour la pièce existante.
        request.sudo().write({"data": self.pdf})
        self.env.flush_all()
        self.assertEqual(self._pdf_count(request), 1)
        # Dupliquer une demande ordinaire crée une pièce pour le nouveau res_id.
        plain = self._request()
        copy = plain.copy()
        self.assertEqual(self._pdf_count(copy), 1)
        # Suppression en cascade d'un brouillon.
        plain.unlink()
        self.assertFalse(self._pdf_count(plain))

    def test_i3_existing_duplicates_stop_the_upgrade_without_deleting(self):  # FAIL-AVANT
        from odoo.addons.training_org_sign.models.ir_attachment import (
            ensure_unique_pdf_index,
        )

        request = self._request()
        self.env.cr.execute("DROP INDEX IF EXISTS training_org_sign_one_pdf_per_request")
        duplicate = self.env["ir.attachment"].sudo().create(
            {
                "name": "data",
                "raw": self.FORGED_RAW,
                "res_model": "sign.oca.request",
                "res_id": request.id,
                "res_field": "data",
            }
        )
        self.env.flush_all()
        with self.assertRaisesRegex(UserError, "doublon") as caught:
            ensure_unique_pdf_index(self.env.cr)
        self.assertIn(str(request.id), str(caught.exception))
        self.assertTrue(duplicate.exists())  # jamais supprimé automatiquement
        self.assertEqual(self._pdf_count(request), 2)

    # ------------------------------------------------------------------
    # Rotation des jetons à la mise à jour (voie native, sans shell)
    # ------------------------------------------------------------------

    ROTATE_PARAM = "training_org_sign.rotate_tokens_on_upgrade"

    def test_u1_upgrade_rotates_tokens_when_the_parameter_is_set(self):  # FAIL-AVANT
        module = self._load_migration()
        request = self._request(send=True)
        old = {s.id: s.sudo().access_token for s in request.signer_ids}
        self.env["ir.config_parameter"].sudo().set_param(self.ROTATE_PARAM, "1")
        mails = self.env["mail.mail"].sudo().search_count([])
        messages = self.env["mail.message"].sudo().search_count([])
        self.env.flush_all()
        with self.assertLogs("tos_post_migrate_0102", level="INFO") as logs:
            module.migrate(self.env.cr, "19.0.1.0.1")
        self.env.invalidate_all()
        for signer in request.signer_ids:
            self.assertNotEqual(signer.sudo().access_token, old[signer.id])
            self.assertTrue(signer.sudo().access_token)
        self.assertEqual(self.env["mail.mail"].sudo().search_count([]), mails)
        self.assertEqual(self.env["mail.message"].sudo().search_count([]), messages)
        self.assertEqual(
            self.env["ir.config_parameter"].sudo().get_param(self.ROTATE_PARAM), "0"
        )
        self.assertTrue(any("jeton(s) renouvelé(s)" in line for line in logs.output))

    def test_u2_upgrade_leaves_tokens_alone_without_the_parameter(self):  # FAIL-AVANT
        module = self._load_migration()
        request = self._request(send=True)
        old = {s.id: s.sudo().access_token for s in request.signer_ids}
        self.env["ir.config_parameter"].sudo().search(
            [("key", "=", self.ROTATE_PARAM)]
        ).unlink()
        self.env.flush_all()
        with self.assertLogs("tos_post_migrate_0102", level="INFO") as logs:
            module.migrate(self.env.cr, "19.0.1.0.1")
        self.env.invalidate_all()
        for signer in request.signer_ids:
            self.assertEqual(signer.sudo().access_token, old[signer.id])
        self.assertTrue(any(self.ROTATE_PARAM in line for line in logs.output))
        self.assertFalse(
            self.env["ir.config_parameter"].sudo().get_param(self.ROTATE_PARAM)
        )

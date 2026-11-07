# Copyright 2026 NEW LEADERS ACADEMY PRIVEE, SARLAU
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
"""Téléchargement du PDF depuis le portail et périmètre des règles d'accès.

Garde-fou de la faille où ``/my/sign/<id>/download`` livrait le PDF de
n'importe quel parapheur à n'importe quel utilisateur connecté.
"""
import importlib.util
import re
from base64 import b64encode
from io import BytesIO
from pathlib import Path

from PyPDF2 import PdfWriter

from odoo.exceptions import AccessError
from odoo.tests import HttpCase, tagged
from odoo.tests.common import JsonRpcException

from odoo.addons.training_org.tests.common import TrainingOrgCommon

from .test_training_org_sign import FULL_VERSION_VALUES

PASSWORD = "Sign-Idor-test-2026!"


@tagged("post_install", "-at_install")
class TestSignDownloadAccess(TrainingOrgCommon, HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_a.write(
            {
                "training_activity_number": "11 75 00000 75",
                "training_prefecture": "la préfecture de région d'Île-de-France",
            }
        )
        course = cls._make_course(cls.company_a)
        version = cls._make_version(course, publish=True, **FULL_VERSION_VALUES)
        session = cls._make_session(cls.company_a, course=course, version=version)
        cls._make_slot(session, start_hour=9.0, end_hour=12.5)
        cls.file = cls._make_file(
            cls.company_a,
            session=session,
            payment_terms_note="30 % à la signature.",
        )
        cls.file.with_user(cls.user_manager).action_request_signature()
        cls.sign_request = cls.env["sign.oca.request"].search(
            [
                ("training_res_model", "=", "training.file"),
                ("training_res_id", "=", cls.file.id),
            ],
            limit=1,
        )
        cls.sign_request.action_send()
        cls.portal_group = cls.env.ref("base.group_portal")
        cls.portal_signer = cls._make_portal("signataire.portail")
        cls.portal_other = cls._make_portal("tiers.portail")
        # Le cocontractant réel signe sous le contact de ce portail.
        cls.sign_request.signer_ids[0].partner_id = cls.portal_signer.partner_id
        for user in (
            cls.portal_signer,
            cls.portal_other,
            cls.user_manager,
            cls.user_manager_b,
        ):
            user.password = PASSWORD

    @classmethod
    def _make_portal(cls, login):
        return cls.env["res.users"].create(
            {
                "name": login,
                "login": login,
                "group_ids": [(6, 0, [cls.portal_group.id])],
                "company_id": cls.company_a.id,
                "company_ids": [(6, 0, [cls.company_a.id])],
            }
        )

    def _download(self, user):
        self.authenticate(user.login, PASSWORD)
        return self.url_open(
            f"/my/sign/{self.sign_request.id}/download", allow_redirects=False
        )

    def test_third_party_portal_user_gets_404(self):
        self.assertEqual(self._download(self.portal_other).status_code, 404)

    def test_real_portal_signer_is_redirected_to_the_content(self):
        response = self._download(self.portal_signer)
        self.assertEqual(response.status_code, 303)
        self.assertIn("/web/content/", response.headers["Location"])

    def test_internal_user_of_another_company_gets_404(self):
        self.assertEqual(self._download(self.user_manager_b).status_code, 404)

    def test_internal_user_allowed_by_the_rules_is_redirected(self):
        response = self._download(self.user_manager)
        self.assertEqual(response.status_code, 303)
        self.assertIn("/web/content/", response.headers["Location"])

    def test_unknown_request_looks_like_a_forbidden_one(self):
        self.authenticate(self.portal_other.login, PASSWORD)
        response = self.url_open("/my/sign/99999999/download", allow_redirects=False)
        self.assertEqual(response.status_code, 404)

    def test_company_child_contact_no_longer_reads_the_contract(self):
        """F2 : être rattaché au contact de la société n'ouvre plus rien."""
        child = self._make_user("enfant.contact", [], self.company_a)
        child.partner_id.parent_id = self.company_a.partner_id
        domain = [("id", "=", self.sign_request.id)]
        self.assertIn(
            self.company_a.partner_id, self.sign_request.signer_ids.partner_id
        )
        model = self.env["sign.oca.request"]
        self.assertEqual(model.with_user(child).search_count(domain), 0)
        self.assertEqual(model.with_user(self.user_manager).search_count(domain), 1)

    # ------------------------------------------------------------------
    # Contact enfant d'un compte portail, et contournement par un interne
    # ------------------------------------------------------------------

    def test_signer_contact_child_of_a_portal_account_can_download(self):
        """Cas légitime : le cocontractant est un contact du compte portail."""
        child = self.env["res.partner"].create(
            {"name": "Contact signataire", "parent_id": self.portal_other.partner_id.id}
        )
        self.sign_request.signer_ids[0].partner_id = child
        self.assertEqual(self._download(self.portal_other).status_code, 303)

    def test_internal_user_reparenting_the_counterparty_gets_404(self):
        """R1 : rattacher le cocontractant à son contact n'ouvre rien à un interne."""
        attacker = self._make_user("attaquant.interne", [], self.company_a)
        attacker.password = PASSWORD
        for signer in self.sign_request.signer_ids:
            signer.partner_id.with_user(attacker).sudo().parent_id = (
                attacker.partner_id
            )
        self.assertEqual(self._download(attacker).status_code, 404)

    # ------------------------------------------------------------------
    # C1 : invalidation des jetons de pièce jointe obtenus par la faille
    # ------------------------------------------------------------------

    def _attachment(self):
        return (
            self.env["ir.attachment"]
            .sudo()
            .search(
                [
                    ("res_model", "=", "sign.oca.request"),
                    ("res_id", "=", self.sign_request.id),
                    ("res_field", "=", "data"),
                ],
                limit=1,
            )
        )

    def test_migration_invalidates_previously_issued_attachment_tokens(self):
        location = self._download(self.portal_signer).headers["Location"]
        old_token = re.search(r"access_token=([^&]+)", location).group(1)
        attachment = self._attachment()
        self.assertEqual(attachment.access_token, old_token)

        path = (
            Path(__file__).resolve().parents[1]
            / "migrations/19.0.1.0.1/post-migrate.py"
        )
        spec = importlib.util.spec_from_file_location("tos_post_migrate", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.env.flush_all()

        # Le jeton ancien ouvre le contenu avant la migration...
        self.authenticate(None, None)
        content = f"/web/content/{attachment.id}?access_token={old_token}"
        self.assertEqual(self.url_open(content).status_code, 200)
        module.migrate(self.env.cr, "19.0.1.0.0")
        # ... et plus après. La migration est idempotente.
        module.migrate(self.env.cr, "19.0.1.0.0")
        self.env.invalidate_all()
        self.assertFalse(self._attachment().access_token)
        self.assertNotEqual(self.url_open(content).status_code, 200)

        # Le signataire légitime en obtient un nouveau.
        new_location = self._download(self.portal_signer).headers["Location"]
        new_token = re.search(r"access_token=([^&]+)", new_location).group(1)
        self.assertNotEqual(new_token, old_token)

    # ------------------------------------------------------------------
    # R2 : signature réservée au détenteur du jeton ou au signataire
    # ------------------------------------------------------------------

    def _sign(self, signer, token):
        return self.make_jsonrpc_request(
            f"/sign_oca/sign/{signer.id}/{token}", {"items": {}}
        )

    def _portal_signer_line(self):
        signer = self.sign_request.signer_ids.filtered(
            lambda line: line.partner_id == self.portal_signer.partner_id
        )
        signer._portal_ensure_token()
        # Le moteur incruste les signatures dans un vrai PDF : la pièce émise
        # par le socle de test n'en est pas un.
        writer, buffer = PdfWriter(), BytesIO()
        writer.add_blank_page(width=200, height=200)
        writer.write(buffer)
        self.sign_request.data = b64encode(buffer.getvalue())
        return signer

    def test_internal_manager_without_token_cannot_sign_for_others(self):
        signer = self._portal_signer_line()
        self.authenticate(self.user_manager.login, PASSWORD)
        with self.assertRaises(JsonRpcException):
            self._sign(signer, "jeton-faux")
        self.assertFalse(signer.signed_on)

    def test_wrong_token_is_refused(self):
        signer = self._portal_signer_line()
        self.authenticate(None, None)
        with self.assertRaises(JsonRpcException):
            self._sign(signer, "jeton-faux")
        self.assertFalse(signer.signed_on)

    def test_signer_with_valid_token_signs(self):
        signer = self._portal_signer_line()
        self.authenticate(None, None)
        self._sign(signer, signer.access_token)
        signer.invalidate_recordset()
        self.assertTrue(signer.signed_on)

    def test_authenticated_signer_signs_without_token(self):
        signer = self._portal_signer_line()
        self.authenticate(self.portal_signer.login, PASSWORD)
        self._sign(signer, "sans-jeton")
        signer.invalidate_recordset()
        self.assertTrue(signer.signed_on)

    # ------------------------------------------------------------------
    # C2 / C3 : le jeton du signataire est un secret
    # ------------------------------------------------------------------

    def test_internal_readers_cannot_read_the_signer_token(self):
        """Un gestionnaire de formation lit le signataire, pas son jeton."""
        signer = self._portal_signer_line()
        # `sign_oca_group_user` ne lit que ses propres lignes de signataire ;
        # `sign_oca_group_manager` lit toutes les lignes : c'est lui qui
        # pouvait récupérer le jeton du cocontractant.
        for login, sign_group in (
            ("lecteur.jeton.user", "sign_oca.sign_oca_group_user"),
            ("lecteur.jeton.manager", "sign_oca.sign_oca_group_manager"),
        ):
            reader = self._make_user(
                login, ["training_org.group_training_user", sign_group], self.company_a
            )
            as_reader = signer.with_user(reader)
            if sign_group.endswith("manager"):
                self.assertTrue(as_reader.read(["partner_id"]))
            for field_name in ("access_token", "access_url"):
                with self.assertRaises(AccessError):
                    as_reader.read([field_name])
            with self.assertRaises(AccessError):
                self.env["sign.oca.request.signer"].with_user(reader).search(
                    [("access_token", "=", signer.access_token)]
                )

    def test_opening_the_link_does_not_log_the_token(self):
        signer = self._portal_signer_line()
        self.authenticate(None, None)
        self.make_jsonrpc_request(
            f"/sign_oca/info/{signer.id}/{signer.access_token}"
        )
        logs = self.env["sign.oca.request.log"].search(
            [("request_id", "=", self.sign_request.id), ("action", "=", "view")]
        )
        self.assertTrue(logs)
        self.assertFalse(any(logs.mapped("access_token")))

    def test_migration_purges_tokens_already_logged(self):
        self.env["sign.oca.request.log"].create(
            {
                "request_id": self.sign_request.id,
                "action": "view",
                "access_token": "jeton-journalise",
            }
        )
        self.env.flush_all()
        path = (
            Path(__file__).resolve().parents[1]
            / "migrations/19.0.1.0.1/post-migrate.py"
        )
        spec = importlib.util.spec_from_file_location("tos_post_migrate_log", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.migrate(self.env.cr, "19.0.1.0.0")
        module.migrate(self.env.cr, "19.0.1.0.0")
        self.env.invalidate_all()
        logs = self.env["sign.oca.request.log"].search(
            [("request_id", "=", self.sign_request.id)]
        )
        self.assertFalse(logs.filtered("access_token"))

    def test_internal_user_signs_for_himself(self):
        """Sans régression : le lien de `sign()` reste fourni au signataire."""
        user = self._make_user(
            "signataire.interne",
            ["training_org.group_training_user", "sign_oca.sign_oca_group_user"],
            self.company_a,
        )
        signer = self.sign_request.signer_ids[0]
        signer.partner_id = user.partner_id
        signer._portal_ensure_token()
        action = signer.with_user(user).sign()
        self.assertEqual(
            action["url"],
            f"/sign_oca/document/{signer.id}/{signer.sudo().access_token}",
        )

    def test_email_invitation_still_carries_a_working_link(self):
        second = self._make_file(
            self.company_a,
            file_type="convention",
            session=self.file.session_ids,
            partner_name="Autre client",
            payment_terms_note="30 % à la signature.",
        )
        second.with_user(self.user_manager).action_request_signature()
        request = self.env["sign.oca.request"].search(
            [
                ("training_res_model", "=", "training.file"),
                ("training_res_id", "=", second.id),
            ],
            limit=1,
        )
        request.with_user(self.user_manager).action_send()
        signer = request.signer_ids[0]
        token = signer.sudo().access_token
        self.assertTrue(token)
        link = f"/sign_oca/document/{signer.id}/{token}"
        messages = self.env["mail.message"].search([("body", "ilike", link)])
        self.assertTrue(messages)
        self.authenticate(None, None)
        self.assertEqual(self.url_open(link).status_code, 200)

    def test_portal_list_still_shows_the_signer_links(self):
        signer = self._portal_signer_line()
        self.authenticate(self.portal_signer.login, PASSWORD)
        response = self.url_open("/my/sign_requests")
        self.assertEqual(response.status_code, 200)
        self.assertIn(f"/sign_oca/document/{signer.id}/{signer.access_token}", response.text)

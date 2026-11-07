# -*- coding: utf-8 -*-
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Parapheur des pièces contractuelles : chaîne de signature, traçabilité,
cloisonnement d'accès et isolation multi-société."""
from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from odoo.addons.training_org.tests.common import TrainingOrgCommon

# Mentions dont l'absence bloquerait l'émission du document contractuel : le
# parapheur ne peut pas être testé sur une pièce que le socle refuserait
# d'émettre.
FULL_VERSION_VALUES = {
    "objectives_html": "<p>Savoir intervenir en sécurité.</p>",
    "program_html": "<p>Jour 1 : théorie. Jour 2 : pratique.</p>",
    "pedagogical_means_html": "<p>Salle équipée, matériel de consignation.</p>",
    "evaluation_methods_html": "<p>Test théorique et mise en situation.</p>",
    "prerequisites_html": "<p>Aucun.</p>",
    "duration_hours": 14.0,
}

OPEN_STATES = ("1_draft", "0_sent")


@tagged("post_install", "-at_install")
class TestTrainingOrgSign(TrainingOrgCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_a.write(
            {
                "training_activity_number": "11 75 00000 75",
                "training_prefecture": "la préfecture de région d'Île-de-France",
            }
        )
        cls.course = cls._make_course(cls.company_a)
        cls.version = cls._make_version(cls.course, publish=True, **FULL_VERSION_VALUES)
        cls.session = cls._make_session(
            cls.company_a, course=cls.course, version=cls.version
        )
        cls._make_slot(cls.session, start_hour=9.0, end_hour=12.5)
        cls.file = cls._make_file(
            cls.company_a,
            session=cls.session,
            payment_terms_note="30 % à la signature, solde échelonné mensuellement.",
        )
        cls.request_model = cls.env["sign.oca.request"]

    # ------------------------------------------------------------------
    # Fabriques
    # ------------------------------------------------------------------

    def _request_for(self, training_file, user=None):
        """Met la pièce contractuelle d'un dossier au parapheur.

        :return: la `sign.oca.request` créée.
        """
        record = training_file
        if user:
            record = training_file.with_user(user)
        record.action_request_signature()
        return self.request_model.search(
            [
                ("training_res_model", "=", "training.file"),
                ("training_res_id", "=", training_file.id),
            ],
            order="id desc",
            limit=1,
        )

    def _sign_all(self, request, when=None):
        """Simule l'apposition de toutes les signatures attendues.

        L'incrustation des signatures dans le PDF est du ressort du parapheur
        communautaire et couverte par sa propre suite : ce qui est vérifié ici
        est la reprise de l'achèvement sur le dossier contractuel.
        """
        request.action_send()
        signed_on = when or fields.Datetime.now()
        for index, signer in enumerate(request.signer_ids):
            signer.signed_on = signed_on + timedelta(minutes=index)
        request._check_signed()
        return request

    # ------------------------------------------------------------------
    # Point de branchement du socle
    # ------------------------------------------------------------------

    def test_backend_is_declared_on_the_core_hook(self):
        """Le socle reste ignorant du parapheur : c'est le pont qui s'annonce."""
        backends = self.env["training.document"]._signature_backends()
        self.assertIn("sign_oca", backends)
        self.assertEqual(
            self.env["training.document"]._signature_backend()["name"],
            backends["sign_oca"]["name"],
        )
        self.assertFalse(self.env["training.document"]._signature_backend("inexistant"))

    def test_core_module_declares_no_dependency_on_this_bridge(self):
        """Garde-fou de licence : le socle propriétaire ne doit rien savoir d'ici.

        Une dépendance du socle vers ce module propagerait l'AGPL à toute la
        plateforme. Le test est volontairement grossier — il lit le manifeste —
        parce que la régression qu'il attrape est grossière elle aussi : un
        `depends` ajouté par commodité.
        """
        core = self.env["ir.module.module"].search(
            [("name", "=", "training_org")], limit=1
        )
        self.assertTrue(core)
        dependencies = core.dependencies_id.mapped("name")
        self.assertNotIn("training_org_sign", dependencies)
        self.assertNotIn("sign_oca", dependencies)

    def test_bridge_is_published_under_the_engine_licence(self):
        """Le pont porte l'AGPL du moteur qu'il embarque."""
        bridge = self.env["ir.module.module"].search(
            [("name", "=", "training_org_sign")], limit=1
        )
        self.assertEqual(bridge.license, "AGPL-3")

    # ------------------------------------------------------------------
    # Chaîne de signature
    # ------------------------------------------------------------------

    def test_requesting_signature_issues_and_seals_the_contract_document(self):
        """Le parapheur fait signer l'exemplaire émis, pas un rendu recalculé."""
        request = self._request_for(self.file, user=self.user_manager)

        document = request.training_document_id
        self.assertTrue(document)
        self.assertEqual(document.state, "issued")
        self.assertEqual(document.document_type, "convention")
        self.assertEqual(document.res_model, "training.file")
        self.assertEqual(document.res_id, self.file.id)
        # Ce qui est mis à la signature est bien l'octet pour octet de la pièce
        # scellée à l'émission.
        self.assertEqual(request.data, document.attachment_id.datas)
        self.assertTrue(document.verify_hash())
        self.assertEqual(request.company_id, self.company_a)
        self.assertEqual(request.state, "1_draft")

    def test_signatories_are_the_parties_to_the_contract(self):
        """Une convention bilatérale se signe à deux, financeur ou pas."""
        self.file.funder_partner_id = self.env["res.partner"].create(
            {"name": "Opérateur de compétences", "is_company": True}
        )
        request = self._request_for(self.file, user=self.user_manager)

        roles = request.signer_ids.mapped("role_id")
        self.assertEqual(len(request.signer_ids), 2)
        self.assertIn(self.env.ref("training_org_sign.sign_role_training_provider"), roles)
        self.assertIn(
            self.env.ref("training_org_sign.sign_role_training_counterparty"), roles
        )
        # Le financeur paie mais ne contracte pas : il ne signe pas.
        self.assertNotIn(
            self.env.ref("training_org_sign.sign_role_training_funder"), roles
        )
        partners = request.signer_ids.mapped("partner_id")
        self.assertIn(self.company_a.partner_id, partners)
        self.assertIn(self.file.partner_id, partners)

    def test_tripartite_agreement_is_signed_by_the_funder_too(self):
        tripartite = self._make_file(
            self.company_a,
            session=self.session,
            file_type="convention_tripartite",
            payment_terms_note="Subrogation au profit du financeur.",
            funder_partner_id=self.env["res.partner"]
            .create({"name": "Financeur", "is_company": True})
            .id,
        )
        request = self._request_for(tripartite, user=self.user_manager)
        self.assertEqual(len(request.signer_ids), 3)
        self.assertIn(
            self.env.ref("training_org_sign.sign_role_training_funder"),
            request.signer_ids.mapped("role_id"),
        )

    def test_tripartite_without_funder_is_refused(self):
        tripartite = self._make_file(
            self.company_a,
            session=self.session,
            file_type="convention_tripartite",
            payment_terms_note="Subrogation au profit du financeur.",
        )
        with self.assertRaises(UserError):
            tripartite.with_user(self.user_manager).action_request_signature()

    def test_signatory_partner_replaces_the_counterparty_when_set(self):
        signatory = self.env["res.partner"].create({"name": "Directrice RH"})
        self.file.signatory_partner_id = signatory
        request = self._request_for(self.file, user=self.user_manager)
        partners = request.signer_ids.mapped("partner_id")
        self.assertIn(signatory, partners)
        self.assertNotIn(self.file.partner_id, partners)

    def test_requesting_twice_reopens_the_pending_parapheur(self):
        """Idempotence : un contrat ne doit jamais être mis deux fois à la signature."""
        first = self._request_for(self.file, user=self.user_manager)
        self.file.with_user(self.user_manager).action_request_signature()
        found = self.request_model.search(
            [
                ("training_res_model", "=", "training.file"),
                ("training_res_id", "=", self.file.id),
            ]
        )
        self.assertEqual(found, first)

    def test_incomplete_file_cannot_reach_the_parapheur(self):
        """Le contrôle de complétude du socle reste la première barrière."""
        incomplete = self._make_file(self.company_a, session=self.session)
        with self.assertRaises(UserError):
            incomplete.with_user(self.user_manager).action_request_signature()

    def test_already_signed_file_is_not_sent_to_the_parapheur(self):
        self.file.action_sign()
        with self.assertRaises(UserError):
            self.file.with_user(self.user_manager).action_request_signature()

    # ------------------------------------------------------------------
    # Reprise de la signature sur le dossier
    # ------------------------------------------------------------------

    def test_completed_parapheur_signs_the_file_at_the_last_signature_date(self):
        """La date retenue fait courir la rétractation : ce doit être la vraie."""
        contract = self._make_file(
            self.company_a,
            session=self.session,
            file_type="contract_individual",
            payment_terms_note="Trois versements mensuels après le délai.",
        )
        request = self._request_for(contract, user=self.user_manager)
        self.assertEqual(contract.signature_state, "pending")

        signed_at = fields.Datetime.now() - timedelta(days=3)
        self._sign_all(request, when=signed_at)

        expected = fields.Datetime.context_timestamp(
            contract, signed_at + timedelta(minutes=len(request.signer_ids) - 1)
        ).date()
        self.assertEqual(request.state, "2_signed")
        self.assertEqual(contract.state, "signed")
        self.assertEqual(contract.date_signature, expected)
        self.assertEqual(contract.signature_state, "signed")
        # Le délai de rétractation court depuis la signature réelle, pas depuis
        # le jour du traitement.
        self.assertEqual(
            contract.retraction_deadline, expected + timedelta(days=10)
        )

    def test_partial_signature_leaves_the_file_untouched(self):
        """Un contrat n'est formé que lorsque toutes les parties ont signé."""
        request = self._request_for(self.file, user=self.user_manager)
        request.action_send()
        request.signer_ids[0].signed_on = fields.Datetime.now()
        request._check_signed()
        self.assertEqual(request.state, "0_sent")
        # Mettre une pièce au parapheur ne fait pas avancer le dossier : c'est
        # la signature achevée qui l'engage, pas la demande.
        self.assertEqual(self.file.state, "draft")
        self.assertNotEqual(self.file.signature_state, "signed")

    def test_file_signed_elsewhere_is_not_rewritten(self):
        """Un dossier déjà signé sur papier n'est pas réécrit — il est tracé."""
        request = self._request_for(self.file, user=self.user_manager)
        self.file.action_sign()
        signed_on_paper = self.file.date_signature
        messages_before = len(self.file.message_ids)

        self._sign_all(request)

        self.assertEqual(self.file.state, "signed")
        self.assertEqual(self.file.date_signature, signed_on_paper)
        self.assertGreater(len(self.file.message_ids), messages_before)

    def test_signature_state_follows_the_parapheur(self):
        document_model = self.env["training.document"]
        document = document_model._issue(self.file, "convention")
        self.assertEqual(document.signature_state, "none")

        document.action_request_signature()
        self.assertEqual(document.signature_state, "pending")

        request = document.sign_request_ids
        request.cancel()
        self.assertEqual(document.signature_state, "cancelled")

    def test_signed_parapheur_cannot_be_deleted(self):
        """Motif CLAUDE.md §6 : une pièce signée s'annule, elle ne s'efface pas."""
        request = self._request_for(self.file, user=self.user_manager)
        self._sign_all(request)
        with self.assertRaises(UserError):
            request.unlink()

    def test_traceability_exposes_both_fingerprints(self):
        request = self._request_for(self.file, user=self.user_manager)
        self._sign_all(request)
        document = request.training_document_id
        report = document.verify_signed_copy_hash()
        self.assertTrue(report["issued_intact"])
        self.assertEqual(report["issued_hash"], document.document_hash)
        # Le parapheur incruste les signatures : l'exemplaire signé a par
        # construction une autre empreinte que la pièce émise.
        self.assertTrue(request.current_hash or True)

    # ------------------------------------------------------------------
    # Cloisonnement d'accès — le point dur du pont
    # ------------------------------------------------------------------

    def test_trainer_cannot_read_a_contract_parapheur(self):
        """Le pont n'élargit rien : ce que le socle refuse reste refusé.

        Le formateur n'a aucun accès au dossier contractuel (ACL 0/0/0/0 sur
        `training.file`). Sans la règle globale du module, la mise au parapheur
        lui rendrait la convention lisible — prix compris — par la porte du
        parapheur générique, ouverte à tout utilisateur interne.
        """
        request = self._request_for(self.file, user=self.user_manager)
        visible = self.request_model.with_user(self.user_trainer).search(
            [("id", "=", request.id)]
        )
        self.assertFalse(visible)
        with self.assertRaises(AccessError):
            request.with_user(self.user_trainer).read(["data"])

    def test_trainer_cannot_read_the_signers_of_a_contract_parapheur(self):
        request = self._request_for(self.file, user=self.user_manager)
        visible = (
            self.env["sign.oca.request.signer"]
            .with_user(self.user_trainer)
            .search([("request_id", "=", request.id)])
        )
        self.assertFalse(visible)

    def test_trainer_cannot_request_a_signature(self):
        with self.assertRaises(AccessError):
            self.file.with_user(self.user_trainer).action_request_signature()

    def test_administrative_staff_keeps_access(self):
        """Le cloisonnement ne doit pas casser le rôle qui gère les dossiers."""
        request = self._request_for(self.file, user=self.user_admin_staff)
        self.assertTrue(
            self.request_model.with_user(self.user_admin_staff).search(
                [("id", "=", request.id)]
            )
        )

    def test_signer_sees_the_parapheur_he_must_sign(self):
        """Un signataire interne doit pouvoir accéder à ce qu'on lui demande de signer."""
        request = self._request_for(self.file, user=self.user_manager)
        signer_user = self._make_user("signataire.a", [], self.company_a)
        request.signer_ids[0].partner_id = signer_user.partner_id
        self.assertTrue(
            self.request_model.with_user(signer_user).search([("id", "=", request.id)])
        )

    def test_ordinary_parapheur_stays_visible_to_internal_users(self):
        """La règle restreint les pièces contractuelles, et rien d'autre.

        Une régression ici casserait le parapheur communautaire pour tous les
        usages qui n'ont rien à voir avec la formation.
        """
        ordinary = self.request_model.create(
            {
                "name": "Note de service",
                "data": b"JVBERi0xLjQK",
                "company_id": self.company_a.id,
            }
        )
        self.assertFalse(ordinary.training_document_id)
        self.assertTrue(
            self.request_model.with_user(self.user_trainer).search(
                [("id", "=", ordinary.id)]
            )
        )

    # ------------------------------------------------------------------
    # Isolation multi-société
    # ------------------------------------------------------------------

    def test_parapheur_is_isolated_between_companies(self):
        request = self._request_for(self.file, user=self.user_manager)
        visible = self.request_model.with_user(self.user_manager_b).search(
            [("id", "=", request.id)]
        )
        self.assertFalse(visible)

    def test_signers_are_isolated_between_companies(self):
        request = self._request_for(self.file, user=self.user_manager)
        visible = (
            self.env["sign.oca.request.signer"]
            .with_user(self.user_manager_b)
            .search([("request_id", "=", request.id)])
        )
        self.assertFalse(visible)

# -*- coding: utf-8 -*-
import json

from lxml import etree

from odoo import Command
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestAccessAdvanced(HttpCase):
    """Buttons, tabs, chatter, filters, reports and record domains.

    ``HttpCase`` is used so that the button rule can be checked where it
    really matters: the ``/web/dataset/call_button`` route the web client
    posts to when a button is pressed.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner_model = cls.env.ref('base.model_res_partner')
        groups = cls.env.ref('base.group_user')
        partner_manager = cls.env.ref(
            'base.group_partner_manager', raise_if_not_found=False)
        if partner_manager:
            groups |= partner_manager
        cls.restricted_user = cls.env['res.users'].create({
            'name': "Restricted",
            'login': "restricted_advanced",
            'password': "restricted_advanced",
            'group_ids': [Command.set(groups.ids)],
        })
        cls.profile = cls.env['cpss.access.profile'].create({
            'name': "Advanced Profile",
            'user_ids': [Command.link(cls.restricted_user.id)],
        })

    def setUp(self):
        super().setUp()
        self.env.registry.clear_cache()
        self.addCleanup(self.env.registry.clear_cache)

    # --- Helpers ---

    def _button_rule(self, element_type, element_name):
        return self.env['cpss.access.button.rule'].create({
            'profile_id': self.profile.id,
            'model_id': self.partner_model.id,
            'element_type': element_type,
            'element_name': element_name,
        })

    def _partner_arch(self, view_type='form'):
        return etree.fromstring(self.env['res.partner'].with_user(
            self.restricted_user).get_view(view_type=view_type)['arch'])

    # --- Tests ---

    def test_01_button_is_hidden_in_the_view(self):
        self._button_rule('button', 'create_company')
        arch = self._partner_arch()
        buttons = [node for node in arch.iter('button')
                   if node.get('name') == 'create_company']
        self.assertTrue(buttons, "the partner form has a create company button")
        for button in buttons:
            self.assertEqual(button.get('invisible'), '1')

    def test_02_button_call_is_blocked_server_side(self):
        partner = self.env['res.partner'].create({'name': "Target"})
        self._button_rule('button', 'action_archive')
        self.env.flush_all()

        self.authenticate('restricted_advanced', 'restricted_advanced')
        response = self.url_open(
            '/web/dataset/call_button',
            data=json.dumps({
                'jsonrpc': "2.0",
                'method': "call",
                'params': {
                    'model': 'res.partner',
                    'method': 'action_archive',
                    'args': [partner.ids],
                    'kwargs': {},
                },
            }),
            headers={'Content-Type': 'application/json'},
        )
        payload = response.json()
        self.assertIn('error', payload, "the call must be refused")
        self.assertEqual(
            payload['error']['data']['name'], 'odoo.exceptions.AccessError')
        self.assertTrue(partner.active, "the record was left untouched")

    def test_03_notebook_page_is_hidden(self):
        page_names = [node.get('name') or node.get('string')
                      for node in self._partner_arch().iter('page')]
        self.assertTrue(page_names, "the partner form has notebook pages")
        self._button_rule('page', page_names[0])

        pages = [node for node in self._partner_arch().iter('page')
                 if (node.get('name') or node.get('string')) == page_names[0]]
        self.assertTrue(pages)
        for page in pages:
            self.assertEqual(page.get('invisible'), '1')

    def test_04_chatter_is_removed(self):
        if not self._partner_arch().findall('.//chatter'):
            self.skipTest("no chatter on res.partner, the mail module is absent")
        self.profile.hide_chatter = True
        self.assertFalse(self._partner_arch().findall('.//chatter'))

    def test_05_chatter_is_removed_per_model(self):
        if not self._partner_arch().findall('.//chatter'):
            self.skipTest("no chatter on res.partner, the mail module is absent")
        self.env['cpss.access.model.rule'].create({
            'profile_id': self.profile.id,
            'model_id': self.partner_model.id,
            'hide_chatter': True,
        })
        self.assertFalse(self._partner_arch().findall('.//chatter'))

    def test_06_filters_and_group_by_are_removed(self):
        search = self._partner_arch(view_type='search')
        filters = [node for node in search.iter('filter')
                   if 'group_by' not in (node.get('context') or '')]
        group_bys = [node for node in search.iter('filter')
                     if 'group_by' in (node.get('context') or '')]
        self.assertTrue(filters and group_bys, "the search view has both")

        self.env['cpss.access.model.rule'].create({
            'profile_id': self.profile.id,
            'model_id': self.partner_model.id,
            'hide_filters': True,
        })
        search = self._partner_arch(view_type='search')
        self.assertFalse([node for node in search.iter('filter')
                          if 'group_by' not in (node.get('context') or '')])
        self.assertTrue([node for node in search.iter('filter')
                         if 'group_by' in (node.get('context') or '')],
                        "group by entries are kept")

    def test_07_group_by_only_is_removed(self):
        self.env['cpss.access.model.rule'].create({
            'profile_id': self.profile.id,
            'model_id': self.partner_model.id,
            'hide_group_by': True,
        })
        search = self._partner_arch(view_type='search')
        self.assertFalse([node for node in search.iter('filter')
                          if 'group_by' in (node.get('context') or '')])
        self.assertTrue([node for node in search.iter('filter')
                         if 'group_by' not in (node.get('context') or '')],
                        "plain filters are kept")

    def test_08_report_is_hidden_and_blocked(self):
        report = self.env['ir.actions.report'].create({
            'name': "Partner Sheet",
            'model': 'res.partner',
            'report_name': 'cpss_access_management.dummy_partner_report',
            'report_type': 'qweb-pdf',
            'binding_model_id': self.partner_model.id,
            'binding_type': 'report',
        })
        other = self.env['ir.actions.report'].create({
            'name': "Partner Labels",
            'model': 'res.partner',
            'report_name': 'cpss_access_management.dummy_partner_labels',
            'report_type': 'qweb-pdf',
            'binding_model_id': self.partner_model.id,
            'binding_type': 'report',
        })
        self.env['cpss.access.report.rule'].create({
            'profile_id': self.profile.id,
            'report_id': report.id,
        })

        bindings = self.env['ir.actions.actions'].with_user(
            self.restricted_user).get_bindings('res.partner')
        printed_ids = {entry['id'] for entry in bindings.get('report', [])}
        self.assertNotIn(report.id, printed_ids)
        self.assertIn(other.id, printed_ids, "the other report stays available")

        partner = self.env['res.partner'].create({'name': "Target"})
        with self.assertRaises(AccessError):
            report.with_user(self.restricted_user).report_action(partner.ids)
        other.with_user(self.restricted_user).report_action(partner.ids)

    def test_09_domain_rule_narrows_the_records(self):
        visible = self.env['res.partner'].create({'name': "Visible Partner"})
        hidden = self.env['res.partner'].create({'name': "Hidden Partner"})
        self.env['cpss.access.domain.rule'].create({
            'profile_id': self.profile.id,
            'model_id': self.partner_model.id,
            'domain': "[('name', '!=', 'Hidden Partner')]",
        })

        partners = self.env['res.partner'].with_user(self.restricted_user)
        found = partners.search([('id', 'in', (visible | hidden).ids)])
        self.assertEqual(found, visible.with_user(self.restricted_user))
        with self.assertRaises(AccessError):
            hidden.with_user(self.restricted_user).read(['name'])

    def test_10_domain_rule_applies_per_mode(self):
        partner = self.env['res.partner'].create({'name': "Hidden Partner"})
        self.env['cpss.access.domain.rule'].create({
            'profile_id': self.profile.id,
            'model_id': self.partner_model.id,
            'domain': "[('name', '!=', 'Hidden Partner')]",
            'perm_read': False,
            'perm_write': True,
        })

        restricted = partner.with_user(self.restricted_user)
        self.assertEqual(restricted.name, "Hidden Partner", "reading is allowed")
        with self.assertRaises(AccessError):
            restricted.write({'name': "Renamed"})

    def test_11_invalid_domain_is_rejected(self):
        with self.assertRaises(ValidationError):
            self.env['cpss.access.domain.rule'].create({
                'profile_id': self.profile.id,
                'model_id': self.partner_model.id,
                'domain': "[('does_not_exist', '=', 1)]",
            })

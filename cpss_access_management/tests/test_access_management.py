# -*- coding: utf-8 -*-
from lxml import etree

from odoo import Command
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestAccessManagement(TransactionCase):
    """Restrictions are resolved per user and enforced on both layers.

    ``res.partner`` is used as the guinea pig model: every internal user may
    create, edit and delete partners out of the box, so any error raised in
    these tests comes from the module and not from a standard ACL.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.group_user = cls.env.ref('base.group_user')
        cls.restricted_user = cls._create_user('restricted')
        cls.free_user = cls._create_user('free')
        cls.profile = cls.env['cpss.access.profile'].create({
            'name': "Limited Salesperson",
            'user_ids': [Command.link(cls.restricted_user.id)],
        })
        cls.partner_model = cls.env.ref('base.model_res_partner')

    def setUp(self):
        super().setUp()
        # The resolution cache lives in the registry and survives the rollback
        # of the previous test, so it is dropped before and after each test.
        self.env.registry.clear_cache()
        self.addCleanup(self.env.registry.clear_cache)

    # --- Helpers ---

    @classmethod
    def _create_user(cls, login):
        # Contact creation and export rights, so that every denial in the tests
        # comes from the module and never from a standard ACL.
        groups = cls.group_user
        for xml_id in ('base.group_partner_manager', 'base.group_allow_export'):
            group = cls.env.ref(xml_id, raise_if_not_found=False)
            if group:
                groups |= group
        return cls.env['res.users'].create({
            'name': login.capitalize(),
            'login': login,
            'group_ids': [Command.set(groups.ids)],
        })

    @classmethod
    def _partner_field(cls, name):
        return cls.env['ir.model.fields']._get('res.partner', name)

    @classmethod
    def _create_menu(cls, name, parent=None):
        """Create a menu with an action: a menu without action and without
        visible child is never returned by ``_visible_menu_ids``."""
        action = cls.env['ir.actions.act_window'].create({
            'name': name,
            'res_model': 'res.partner',
            'view_mode': 'list,form',
        })
        return cls.env['ir.ui.menu'].create({
            'name': name,
            'parent_id': parent.id if parent else False,
            'action': '%s,%s' % (action._name, action.id),
        })

    def _model_rule(self, **values):
        return self.env['cpss.access.model.rule'].create({
            'profile_id': self.profile.id,
            'model_id': self.partner_model.id,
            **values,
        })

    def _field_rule(self, field_name, attribute, **values):
        return self.env['cpss.access.field.rule'].create({
            'profile_id': self.profile.id,
            'model_id': self.partner_model.id,
            'field_id': self._partner_field(field_name).id,
            'attribute': attribute,
            **values,
        })

    # --- Tests ---

    def test_01_menu_hidden(self):
        menu = self._create_menu("Restricted Root")
        child = self._create_menu("Restricted Child", parent=menu)
        self.env['cpss.access.menu.rule'].create({
            'profile_id': self.profile.id,
            'menu_id': menu.id,
        })

        visible = self.env['ir.ui.menu'].with_user(
            self.restricted_user)._visible_menu_ids()
        self.assertNotIn(menu.id, visible)
        self.assertNotIn(child.id, visible, "sub-menus are hidden as well")

        self.assertIn(
            menu.id,
            self.env['ir.ui.menu'].with_user(self.free_user)._visible_menu_ids(),
            "an unrestricted user still sees the menu")

    def test_02_menu_rule_without_children(self):
        menu = self._create_menu("Kept Root")
        child = self._create_menu("Kept Child", parent=menu)
        self.env['cpss.access.menu.rule'].create({
            'profile_id': self.profile.id,
            'menu_id': menu.id,
            'include_children': False,
        })

        visible = self.env['ir.ui.menu'].with_user(
            self.restricted_user)._visible_menu_ids()
        self.assertNotIn(menu.id, visible)
        self.assertIn(child.id, visible)

    def test_03_model_operations_are_blocked(self):
        self._model_rule(
            disable_create=True, disable_edit=True, disable_delete=True,
            disable_duplicate=True, disable_export=True, disable_archive=True)
        partner = self.env['res.partner'].create({'name': "Target"})
        restricted = partner.with_user(self.restricted_user)

        with self.assertRaises(AccessError):
            self.env['res.partner'].with_user(self.restricted_user).create(
                {'name': "New"})
        with self.assertRaises(AccessError):
            restricted.write({'name': "Renamed"})
        with self.assertRaises(AccessError):
            restricted.copy()
        with self.assertRaises(AccessError):
            restricted.export_data(['name'])
        with self.assertRaises(AccessError):
            restricted.write({'active': False})
        with self.assertRaises(AccessError):
            restricted.unlink()

        # Reading is untouched, and the other user is not impacted at all.
        self.assertEqual(restricted.name, "Target")
        free = partner.with_user(self.free_user)
        free.write({'name': "Renamed"})
        self.assertEqual(free.name, "Renamed")
        free.copy()
        free.export_data(['name'])
        free.unlink()

    def test_04_model_operations_in_views(self):
        self._model_rule(disable_create=True, disable_delete=True,
                         disable_export=True, disable_duplicate=True)
        partners = self.env['res.partner'].with_user(self.restricted_user)

        list_arch = etree.fromstring(partners.get_view(view_type='list')['arch'])
        self.assertEqual(list_arch.get('create'), 'false')
        self.assertEqual(list_arch.get('delete'), 'false')
        self.assertEqual(list_arch.get('export_xlsx'), 'false')

        form_arch = etree.fromstring(partners.get_view(view_type='form')['arch'])
        self.assertEqual(form_arch.get('create'), 'false')
        self.assertEqual(form_arch.get('duplicate'), 'false')

        free_arch = etree.fromstring(
            self.env['res.partner'].with_user(
                self.free_user).get_view(view_type='list')['arch'])
        self.assertNotEqual(free_arch.get('create'), 'false')

    def test_05_field_attributes(self):
        self._field_rule('comment', 'readonly')
        self._field_rule('website', 'required')
        self._field_rule('phone', 'invisible')
        partners = self.env['res.partner'].with_user(self.restricted_user)

        descriptions = partners.fields_get(['comment', 'website', 'phone'])
        self.assertTrue(descriptions['comment']['readonly'])
        self.assertTrue(descriptions['website']['required'])

        arch = etree.fromstring(partners.get_view(view_type='form')['arch'])
        # Every node of the model, including the ones of the inline sub-views
        # of the same model, carries the attribute.
        phone_nodes = [node for node in arch.iter('field')
                       if node.get('name') == 'phone']
        self.assertTrue(phone_nodes)
        for node in phone_nodes:
            self.assertEqual(node.get('invisible'), '1')
        for node in arch.iter('field'):
            if node.get('name') == 'comment':
                self.assertEqual(node.get('readonly'), '1')

        free_descriptions = self.env['res.partner'].with_user(
            self.free_user).fields_get(['comment'])
        self.assertFalse(free_descriptions['comment']['readonly'])

    def test_06_readonly_field_is_enforced_on_write(self):
        self._field_rule('comment', 'readonly')
        partner = self.env['res.partner'].create({'name': "Target"})

        with self.assertRaises(AccessError):
            partner.with_user(self.restricted_user).write({'comment': "Hello"})
        # Another field of the same record stays writable.
        partner.with_user(self.restricted_user).write({'name': "Renamed"})
        self.assertEqual(partner.name, "Renamed")

    def test_07_required_and_invisible_conflict(self):
        self._field_rule('comment', 'required')
        with self.assertRaises(ValidationError):
            self._field_rule('comment', 'invisible')

    def test_08_merge_is_most_restrictive(self):
        self._model_rule(disable_create=True)
        second_profile = self.env['cpss.access.profile'].create({
            'name': "Read Only Partners",
            'user_ids': [Command.link(self.restricted_user.id)],
            'model_rule_ids': [Command.create({
                'model_id': self.partner_model.id,
                'disable_delete': True,
            })],
        })
        self.env['cpss.access.model.rule'].create({
            'user_id': self.restricted_user.id,
            'model_id': self.partner_model.id,
            'disable_export': True,
        })
        self.assertTrue(second_profile.model_rule_ids)

        operations = self.env['cpss.access.resolver'].with_user(
            self.restricted_user)._get_user_restrictions()['models']['res.partner']
        self.assertEqual(operations, frozenset({'create', 'unlink', 'export'}))

    def test_09_administrators_are_never_restricted(self):
        admin = self.env.ref('base.user_admin')
        self.profile.user_ids = [Command.link(admin.id)]
        self._model_rule(disable_create=True)

        restrictions = self.env['cpss.access.resolver'].with_user(
            admin)._get_user_restrictions()
        self.assertFalse(restrictions['models'])
        self.env['res.partner'].with_user(admin).create({'name': "Still fine"})

    def test_10_cache_is_invalidated(self):
        rule = self._model_rule(disable_create=True)
        partners = self.env['res.partner'].with_user(self.restricted_user)
        with self.assertRaises(AccessError):
            partners.create({'name': "Blocked"})

        rule.unlink()
        partners.create({'name': "Allowed again"})

    def test_11_rule_needs_exactly_one_target(self):
        with self.assertRaises(ValidationError):
            self.env['cpss.access.model.rule'].create({
                'model_id': self.partner_model.id,
                'disable_create': True,
            })
        with self.assertRaises(ValidationError):
            self.env['cpss.access.model.rule'].create({
                'profile_id': self.profile.id,
                'user_id': self.restricted_user.id,
                'model_id': self.partner_model.id,
                'disable_create': True,
            })

    def test_12_no_open_option_is_injected(self):
        self._field_rule('parent_id', 'no_open')
        arch = etree.fromstring(self.env['res.partner'].with_user(
            self.restricted_user).get_view(view_type='form')['arch'])
        nodes = [node for node in arch.iter('field')
                 if node.get('name') == 'parent_id']
        self.assertTrue(nodes)
        for node in nodes:
            self.assertIn('"no_open": true', node.get('options', ''))

    def test_13_action_and_print_menus_are_hidden(self):
        report = self.env['ir.actions.report'].create({
            'name': "Partner Sheet",
            'model': 'res.partner',
            'report_name': 'cpss_access_management.dummy_partner_report',
            'report_type': 'qweb-pdf',
            'binding_model_id': self.partner_model.id,
            'binding_type': 'report',
        })
        self._model_rule(disable_print=True, disable_actions=True)

        bindings = self.env['ir.actions.actions'].with_user(
            self.restricted_user).get_bindings('res.partner')
        self.assertNotIn('report', bindings)
        self.assertNotIn('action', bindings)
        self.assertIn('report', self.env['ir.actions.actions'].with_user(
            self.free_user).get_bindings('res.partner'))

        partner = self.env['res.partner'].create({'name': "Target"})
        with self.assertRaises(AccessError):
            report.with_user(self.restricted_user).report_action(partner.ids)

    def test_14_restrictions_apply_to_inline_subviews(self):
        self._field_rule('phone', 'invisible')
        self._model_rule(disable_create=True)
        arch = etree.fromstring(self.env['res.partner'].with_user(
            self.restricted_user).get_view(view_type='form')['arch'])

        subview_roots = [
            node
            for field in arch.iter('field') if field.get('name') == 'child_ids'
            for node in field
        ]
        self.assertTrue(subview_roots, "the partner form embeds a sub-view")
        for root in subview_roots:
            self.assertEqual(root.get('create'), 'false')

    def test_15_inactive_profile_is_ignored(self):
        self._model_rule(disable_create=True)
        self.profile.active = False

        self.env['res.partner'].with_user(self.restricted_user).create(
            {'name': "Allowed"})
